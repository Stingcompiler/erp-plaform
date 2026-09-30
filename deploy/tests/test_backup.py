"""Run the real backup shell with privileged-account and data-reader doubles."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "standalone/backup.sh"
DOUBLE = r'''
import json, os, pathlib, subprocess, sys
p = pathlib.Path(os.environ["BACKUP_TEST_STATE"])
s = json.loads(p.read_text())
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
if name == "id":
    print(0 if len(args) == 1 or args[-1] == "root" else 1001)
    sys.exit(0)
if name == "runuser":
    s["readers"].append({"account": args[1], "command": args[args.index("--") + 1:]})
    p.write_text(json.dumps(s))
    args = args[args.index("--") + 1:]
    args[2:2] = ["BACKUP_TEST_STATE=" + str(p), "BACKUP_TEST_AS_APP=1"]
    sys.exit(subprocess.call(args))
if os.environ.get("BACKUP_TEST_AS_APP") != "1":
    raise RuntimeError("Application code/data reader ran with root privileges")
if name == "app-python":
    if args[0] == "-":
        # An empty override would mask the protected file's persistent MEDIA_ROOT.
        assert "MEDIA_ROOT" not in os.environ
        print(s["database_url"] if args[1] == "DATABASE_URL" else s["media"])
    else:
        assert args[0] == "-c"
        assert os.environ["MEDIA_ROOT"] == s["media"]
        if s.get("bad_fingerprint"):
            print("Unexpected startup output")
        else:
            print(json.dumps({"counts": {"example": 1}, "media": {"hash": "example"}}))
elif name == "pg_dump":
    if s.get("dump_failure"): sys.exit(1)
    sys.stdout.buffer.write(b"database-dump")
elif name == "tar":
    sys.exit(subprocess.call([s["tar"]] + args))
else:
    raise RuntimeError(name)
'''


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.tools = self.root / "tools"
        self.tools.mkdir()
        for name in ("id", "runuser", "app-python", "pg_dump", "tar"):
            path = self.tools / name
            path.write_text(f"#!{sys.executable}\n" + DOUBLE)
            path.chmod(0o755)
        self.home = self.root / "release"
        (self.home / "backend").mkdir(parents=True)
        self.media = self.root / "media"
        self.media.mkdir()
        (self.media / "example.txt").write_text("uploaded media")
        self.env_file = self.root / "protected.env"
        self.env_file.write_text("secret-sentinel\n")
        self.state = {"readers": [], "media": str(self.media),
                      "database_url": "postgresql://user:secret-sentinel@example/db",
                      "tar": shutil.which("tar")}
        self.state_path = self.root / "state.json"
        self.backups = self.root / "backups"

    def run_backup(self, account="vezano"):
        self.state_path.write_text(json.dumps(self.state))
        env = dict(os.environ, PATH=f"{self.tools}:{os.environ['PATH']}",
                   BACKUP_TEST_STATE=str(self.state_path), VEZANO_HOME=str(self.home),
                   VEZANO_ENV_FILE=str(self.env_file), VEZANO_BACKUP_DIR=str(self.backups),
                   VEZANO_PYTHON=str(self.tools / "app-python"), VEZANO_BACKUP_APP_USER=account)
        result = subprocess.run(["bash", str(SCRIPT), "--label", "test"],
                                env=env, capture_output=True, text=True, timeout=20)
        self.state = json.loads(self.state_path.read_text())
        self.assertNotIn("secret-sentinel", result.stdout + result.stderr)
        return result

    def test_app_readers_and_protected_complete_backup(self):
        result = self.run_backup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        readers = self.state["readers"]
        self.assertEqual(len(readers), 5)  # two settings, fingerprint, pg_dump, tar
        self.assertTrue(all(reader["account"] == "vezano" for reader in readers))
        backup, = self.backups.iterdir()
        self.assertEqual(backup.stat().st_mode & 0o777, 0o700)
        manifest = json.loads((backup / "backup-manifest.json").read_text())
        self.assertEqual(set(manifest["artefacts"]),
                         {"database.dump", "media.tar.gz", "fingerprint.json", "environment.env"})
        for name, details in manifest["artefacts"].items():
            path = backup / name
            self.assertEqual(details["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads((backup / "fingerprint.json").read_text())["counts"], {"example": 1})

    def test_failed_dump_removes_partial_backup(self):
        self.state["dump_failure"] = True
        self.assertNotEqual(self.run_backup().returncode, 0)
        self.assertEqual(list(self.backups.iterdir()), [])

    def test_root_application_account_refused(self):
        self.assertNotEqual(self.run_backup("root").returncode, 0)
        self.assertEqual(self.state["readers"], [])
        self.assertFalse(self.backups.exists())

    def test_malformed_fingerprint_refuses_completed_backup(self):
        self.state["bad_fingerprint"] = True
        self.assertNotEqual(self.run_backup().returncode, 0)
        self.assertEqual(list(self.backups.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
