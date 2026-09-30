"""Exercise the actual upgrade shell script with isolated service/DB doubles.

No production environment, network, root permissions, Django or PostgreSQL is
used. Run: python3 -m unittest discover -s deploy/tests -v
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "standalone" / "upgrade.sh"

DOUBLE = r'''
import json, os, pathlib, subprocess, sys
state_path = pathlib.Path(os.environ["TEST_STATE"])
state = json.loads(state_path.read_text())
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
def save():
    state_path.write_text(json.dumps(state))
def record(event):
    state["events"].append(event)
    save()
def quit_if(key):
    if state.get(key): sys.exit(1)
if name == "runuser":
    # Pass just the test harness through env -i; production receives no such
    # override. The supplied application command still uses its own cwd.
    args = args[args.index("--") + 1:]
    args.insert(2, "TEST_STATE=" + str(state_path))
    sys.exit(subprocess.call(args))
elif name == "systemctl":
    action = args[0]
    if action == "show":
        unit = args[1]
        prop = next(a.split("=", 1)[1] for a in args if a.startswith("--property="))
        defaults = {"LoadState": "not-found", "ActiveState": "inactive"}
        print(state["units"].get(unit, defaults).get(prop, ""))
    elif action == "is-active":
        sys.exit(0 if state["units"][args[-1]]["ActiveState"] == "active" else 3)
    else:
        unit = args[1]
        record(["systemctl", action, unit])
        if action == "stop" and unit == "vezano-web.service": quit_if("stop_failure")
        if action == "restart" and pathlib.Path(state["link"]).resolve() == pathlib.Path(state["new"]):
            quit_if("restart_failure")
        if action == "start" and unit == "vezano-worker.service": quit_if("worker_start_failure")
        state["units"][unit]["ActiveState"] = "inactive" if action == "stop" else "active"
        save()
elif name == "python":
    if args[0] == "-c":
        # Health JSON parsing is real, rather than a success-only double.
        sys.exit(subprocess.call([sys.executable] + args))
    command = args[1]
    record(["manage", command] + args[2:])
    if command == "verify_release": quit_if("verify_failure")
    elif command == "shell": print(state.get("mode", "saas"))
    elif command == "check": quit_if("check_failure")
    elif command == "collectstatic": quit_if("static_failure")
    elif command == "preflight":
        quit_if("preflight_failure")
        if pathlib.Path(state["link"]).resolve() == pathlib.Path(state["new"]):
            quit_if("postflight_failure")
    elif command == "bootstrap_standalone": quit_if("bootstrap_failure")
    elif command == "migrate":
        if "--plan" in args: quit_if("plan_failure")
        elif "--check" in args:
            paused = state["units"]["vezano-web.service"]["ActiveState"] == "inactive"
            pending = state.get("pending") or (paused and state.get("pending_after_pause"))
            sys.exit(1 if pending else 0)
        else:
            quit_if("migration_failure")
            state["pending"] = False
            save()
elif name == "curl":
    new = pathlib.Path(state["link"]).resolve() == pathlib.Path(state["new"])
    if new and state.get("health_failure"): sys.exit(22)
    if new and state.get("bad_health"):
        print('{"status":"ok","database":"failed","deployment_mode":"saas"}')
    else:
        print(json.dumps({"status":"ok","database":"ok","deployment_mode":state.get("mode", "saas")}))
elif name == "flock": quit_if("lock_busy")
elif name == "mv":
    # GNU mv -T is absent on macOS; exercise the same atomic rename operation.
    record(["promote", args[-2], args[-1]])
    os.replace(args[-2], args[-1])
elif name == "sleep": pass
else: raise RuntimeError(name)
'''


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.tools = self.root / "tools"
        self.tools.mkdir()
        for name in ("systemctl", "runuser", "curl", "flock", "mv", "sleep"):
            self.executable(self.tools / name, DOUBLE)
        self.old, self.new = self.root / "old", self.root / "new"
        for release in (self.old, self.new):
            (release / "backend").mkdir(parents=True)
            (release / "backend" / "manage.py").touch()
            (release / "venv" / "bin").mkdir(parents=True)
            self.executable(release / "venv" / "bin" / "python", DOUBLE)
            (release / "release-manifest.json").write_text("{}")
            (release / "VERSION").write_text("1.0.0\n")
        self.link = self.root / "current"
        self.link.symlink_to(self.old)
        self.env = self.root / "protected.env"
        self.env.write_text("DO_NOT_DISPLAY=secret-sentinel\n")
        self.script_dir = self.root / "scripts"
        self.script_dir.mkdir()
        self.script = self.script_dir / "upgrade.sh"
        shutil.copyfile(SCRIPT, self.script)
        # The integration assertion is backup ordering, not pg_dump itself.
        (self.script_dir / "backup.sh").write_text(
            f"{sys.executable} - <<'PY'\n"
            "import json,os,pathlib,sys\n"
            "p=pathlib.Path(os.environ['TEST_STATE'])\n"
            "s=json.loads(p.read_text())\n"
            "s['events'].append(['backup'])\n"
            "p.write_text(json.dumps(s))\n"
            "sys.exit(1 if s.get('backup_failure') else 0)\nPY\n"
        )
        self.state_path = self.root / "state.json"
        self.state = {
            "events": [], "link": str(self.link), "old": str(self.old), "new": str(self.new),
            "units": {"vezano-web.service": self.unit("gunicorn")},
        }

    def executable(self, path, code):
        path.write_text(f"#!{sys.executable}\n" + code)
        path.chmod(0o755)

    def unit(self, executable, active=True):
        return {
            "LoadState": "loaded", "ActiveState": "active" if active else "inactive",
            "WorkingDirectory": str(self.link / "backend"),
            "ExecStart": f"{{ path={self.link}/venv/bin/{executable} ; argv[]=redacted ; }}",
            "Environment": f"VEZANO_ENV_FILE={self.env}",
            "User": "vezano", "Group": "vezano",
        }

    def run_upgrade(self, *extra):
        self.state_path.write_text(json.dumps(self.state))
        env = dict(os.environ, PATH=f"{self.tools}:{os.environ['PATH']}", TEST_STATE=str(self.state_path))
        result = subprocess.run(
            ["/bin/bash", str(self.script), "--release", str(self.new),
             "--link", str(self.link), "--env-file", str(self.env),
             "--backup-dir", str(self.root / "backups"), "--health-host", "pro.vezano.app",
             "--yes", *extra], env=env, capture_output=True, text=True, timeout=20,
        )
        self.state = json.loads(self.state_path.read_text())
        self.assertNotIn("secret-sentinel", result.stdout + result.stderr)
        return result

    def assert_failed_untouched(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.link.resolve(), self.old)
        self.assertFalse(any(e[0] == "systemctl" for e in self.state["events"]))

    def test_saas_missing_worker_and_no_migrations_promotes(self):
        result = self.run_upgrade("--require-no-migrations", "--worker-service", "none")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.link.resolve(), self.new)
        events = self.state["events"]
        self.assertFalse(any("vezano-worker.service" in e for e in events))
        self.assertFalse(any("bootstrap_standalone" in e for e in events))
        self.assertFalse(any(e[:2] == ["manage", "migrate"] and "--noinput" in e for e in events))
        self.assertLess(events.index(["systemctl", "stop", "vezano-web.service"]), events.index(["backup"]))

    def test_auto_missing_worker_promotes(self):
        result = self.run_upgrade()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_prepare_only_checks_without_service_changes(self):
        result = self.run_upgrade("--prepare-only", "--require-no-migrations")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.link.resolve(), self.old)
        self.assertFalse(any(e[0] in {"systemctl", "backup", "promote"} for e in self.state["events"]))
        self.assertIn(["manage", "collectstatic", "--noinput"], self.state["events"])

    def test_inactive_worker_stays_inactive(self):
        self.state["units"]["vezano-worker.service"] = self.unit("celery", active=False)
        result = self.run_upgrade()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(any(e[0] == "systemctl" and "vezano-worker.service" in e for e in self.state["events"]))

    def test_active_worker_and_timers_resume(self):
        self.state["units"]["vezano-worker.service"] = self.unit("celery")
        for name in ("vezano-daily-scans.timer", "vezano-backup.timer"):
            self.state["units"][name] = {"LoadState": "loaded", "ActiveState": "active"}
        result = self.run_upgrade()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        events = self.state["events"]
        self.assertLess(events.index(["systemctl", "stop", "vezano-worker.service"]), events.index(["backup"]))
        self.assertIn(["systemctl", "start", "vezano-worker.service"], events)
        self.assertIn(["systemctl", "start", "vezano-backup.timer"], events)

    def test_standalone_bootstraps(self):
        self.state["mode"] = "standalone"
        result = self.run_upgrade()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(["manage", "bootstrap_standalone", "--app-version", "1.0.0"], self.state["events"])

    def test_preparation_failures_never_stop_production(self):
        for failure in ("verify_failure", "check_failure", "static_failure", "preflight_failure", "plan_failure"):
            with self.subTest(failure=failure):
                self.state["events"] = []
                self.state[failure] = True
                self.assert_failed_untouched(self.run_upgrade())
                del self.state[failure]

    def test_missing_manifest_fails_before_commands(self):
        (self.new / "release-manifest.json").unlink()
        self.assert_failed_untouched(self.run_upgrade())

    def test_pending_migrations_rejected_for_code_only_promotion(self):
        self.state["pending"] = True
        self.assert_failed_untouched(self.run_upgrade("--require-no-migrations"))

    def test_hardcoded_service_release_rejected(self):
        self.state["units"]["vezano-web.service"]["WorkingDirectory"] = str(self.old / "backend")
        self.assert_failed_untouched(self.run_upgrade())

    def test_hardcoded_executable_rejected(self):
        self.state["units"]["vezano-web.service"]["ExecStart"] = f"{{ path={self.old}/venv/bin/gunicorn ; }}"
        self.assert_failed_untouched(self.run_upgrade())

    def test_missing_web_rejected(self):
        del self.state["units"]["vezano-web.service"]
        self.assert_failed_untouched(self.run_upgrade())

    def test_failed_worker_rejected(self):
        self.state["units"]["vezano-worker.service"] = self.unit("celery")
        self.state["units"]["vezano-worker.service"]["ActiveState"] = "failed"
        self.assert_failed_untouched(self.run_upgrade())

    def test_different_service_environment_rejected(self):
        self.state["units"]["vezano-web.service"]["Environment"] += " DATABASE_URL=secret-sentinel"
        self.assert_failed_untouched(self.run_upgrade())

    def test_worker_missing_explicitly_requested_is_error(self):
        self.assert_failed_untouched(self.run_upgrade("--worker-service", "required.service"))

    def test_cannot_ignore_an_active_worker(self):
        self.state["units"]["vezano-worker.service"] = self.unit("celery")
        self.assert_failed_untouched(self.run_upgrade("--worker-service", "none"))

    def test_lock_contention_rejected(self):
        self.state["lock_busy"] = True
        self.assert_failed_untouched(self.run_upgrade())

    def test_missing_option_value_is_clear_error(self):
        self.assert_failed_untouched(self.run_upgrade("--worker-service"))

    def test_backup_failure_recovers_old_web(self):
        self.state["backup_failure"] = True
        result = self.run_upgrade()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.link.resolve(), self.old)
        self.assertEqual(self.state["units"]["vezano-web.service"]["ActiveState"], "active")

    def test_changed_migration_plan_after_pause_recovers_old_web(self):
        self.state["pending_after_pause"] = True
        result = self.run_upgrade("--require-no-migrations")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.link.resolve(), self.old)
        self.assertEqual(self.state["units"]["vezano-web.service"]["ActiveState"], "active")
        self.assertFalse(any("--noinput" in e and "migrate" in e for e in self.state["events"]))

    def test_worker_start_failure_recovers_link_and_reports_incomplete_recovery(self):
        self.state["units"]["vezano-worker.service"] = self.unit("celery")
        self.state["worker_start_failure"] = True
        result = self.run_upgrade()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.link.resolve(), self.old)
        self.assertIn("recovery needs operator attention", result.stdout)

    def test_no_migration_start_and_health_failures_recover_old_web(self):
        for failure in ("restart_failure", "health_failure", "bad_health", "postflight_failure"):
            with self.subTest(failure=failure):
                self.state["events"] = []
                self.state[failure] = True
                result = self.run_upgrade("--require-no-migrations")
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(self.link.resolve(), self.old)
                self.assertEqual(self.state["units"]["vezano-web.service"]["ActiveState"], "active")
                del self.state[failure]

    def test_migration_failure_leaves_writers_stopped(self):
        self.state.update(pending=True, migration_failure=True)
        result = self.run_upgrade()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.link.resolve(), self.old)
        self.assertEqual(self.state["units"]["vezano-web.service"]["ActiveState"], "inactive")
        self.assertNotIn(["systemctl", "restart", "vezano-web.service"], self.state["events"])

    def test_failure_after_migration_does_not_rollback_code(self):
        self.state.update(pending=True, health_failure=True)
        result = self.run_upgrade()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.link.resolve(), self.new)
        self.assertEqual(self.state["units"]["vezano-web.service"]["ActiveState"], "inactive")

    def test_standalone_bootstrap_failure_stops_writers(self):
        self.state.update(mode="standalone", bootstrap_failure=True)
        result = self.run_upgrade()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state["units"]["vezano-web.service"]["ActiveState"], "inactive")

    def test_stop_failure_does_not_migrate(self):
        self.state.update(pending=True, stop_failure=True)
        result = self.run_upgrade()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any("--noinput" in e and "migrate" in e for e in self.state["events"]))
        self.assertEqual(self.link.resolve(), self.old)


if __name__ == "__main__":
    unittest.main()
