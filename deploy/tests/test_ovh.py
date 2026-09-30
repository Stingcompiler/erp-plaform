"""Validate the SSH protocol and privileged archive boundary without credentials."""

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
from types import SimpleNamespace
import tarfile
import tempfile
import unittest
from unittest.mock import patch


def load(name, filename):
    path = Path(__file__).resolve().parents[1] / "ovh" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gateway = load("gateway", "gateway.py")
controller = load("controller", "deploy_release.py")
SHA = "a" * 40
DIGEST = "b" * 64


class ProtocolTests(unittest.TestCase):
    def test_only_fixed_commands_are_accepted(self):
        self.assertEqual(gateway.parse_command("ready"), ("ready",))
        self.assertEqual(gateway.parse_command(f"deploy {SHA} {DIGEST}"), ("deploy", SHA, DIGEST))
        self.assertEqual(gateway.parse_command(f"upload {SHA} {DIGEST}"), ("upload", SHA, DIGEST))
        for command in ("sh", "sudo bash", "sftp", "scp -t /etc", f"deploy {SHA};id {DIGEST}", f"deploy {SHA} {DIGEST} extra", "upload ../x ../y"):
            with self.subTest(command=command), self.assertRaises(ValueError):
                gateway.parse_command(command)

    def test_controller_requires_full_identifiers(self):
        controller.validate_arguments(SHA, DIGEST)
        for sha, digest in (("short", DIGEST), (SHA, "short"), ("a" * 40 + "\n", DIGEST), ("../x", DIGEST)):
            with self.assertRaises(ValueError):
                controller.validate_arguments(sha, digest)

    def test_upload_is_atomic_and_checked(self):
        with tempfile.TemporaryDirectory() as name:
            payload = b"tested archive"
            checksum = hashlib.sha256(payload).hexdigest()
            size = gateway.receive_archive(io.BytesIO(payload), name, SHA, checksum)
            self.assertEqual(size, len(payload))
            self.assertEqual((Path(name) / f"{SHA}.tar.gz").read_bytes(), payload)
            self.assertEqual(list(Path(name).glob(".upload-*")), [])

    def test_bad_or_oversized_upload_does_not_replace_previous_file(self):
        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / f"{SHA}.tar.gz"
            destination.write_bytes(b"previous valid archive")
            for limit in (2, 100):
                with self.assertRaises(ValueError):
                    gateway.receive_archive(io.BytesIO(b"bad archive"), name, SHA, DIGEST, max_bytes=limit)
                self.assertEqual(destination.read_bytes(), b"previous valid archive")
                self.assertEqual(list(Path(name).glob(".upload-*")), [])

    def test_stale_commit_is_rejected(self):
        response = io.BytesIO(json.dumps({"sha": "c" * 40}).encode())
        with patch.object(controller, "urlopen", return_value=response), self.assertRaises(ValueError):
            controller.require_latest_main({"repository": "owner/repo"}, SHA)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.archive = self.root / "input.tar.gz"
        self.destination = self.root / "tree"
        self.destination.mkdir()

    def write_archive(self, entries):
        with tarfile.open(self.archive, "w:gz") as archive:
            for name, kind, content in entries:
                info = tarfile.TarInfo(name)
                info.type = kind
                info.size = len(content) if kind == tarfile.REGTYPE else 0
                if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                    info.linkname = "/etc/passwd"
                archive.addfile(info, io.BytesIO(content) if kind == tarfile.REGTYPE else None)

    def test_regular_files_extract(self):
        self.write_archive([(".", tarfile.DIRTYPE, b""), ("./backend", tarfile.DIRTYPE, b""), ("./backend/manage.py", tarfile.REGTYPE, b"source")])
        controller.safe_extract(self.archive, self.destination)
        self.assertEqual((self.destination / "backend/manage.py").read_bytes(), b"source")

    def test_backup_script_remains_executable_without_privileged_mode_bits(self):
        source = Path(__file__).resolve().parents[1] / "standalone/backup.sh"
        content = source.read_bytes()
        with tarfile.open(self.archive, "w:gz") as archive:
            info = tarfile.TarInfo("deploy/standalone/backup.sh")
            info.size = len(content)
            info.mode = 0o6777
            archive.addfile(info, io.BytesIO(content))
        controller.safe_extract(self.archive, self.destination)
        script = self.destination / "deploy/standalone/backup.sh"
        self.assertEqual(script.stat().st_mode & 0o7777, 0o755)
        result = subprocess.run([str(script), "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_traversal_absolute_paths_links_and_devices_rejected_before_writes(self):
        for name, kind in (("../escape", tarfile.REGTYPE), ("/absolute", tarfile.REGTYPE), ("backend/link", tarfile.SYMTYPE), ("hardlink", tarfile.LNKTYPE), ("device", tarfile.CHRTYPE)):
            with self.subTest(name=name):
                self.write_archive([("first", tarfile.REGTYPE, b"ok"), (name, kind, b"bad")])
                with self.assertRaises(ValueError):
                    controller.safe_extract(self.archive, self.destination)
                self.assertEqual(list(self.destination.iterdir()), [])

    def test_duplicate_normalized_paths_rejected(self):
        self.write_archive([("file", tarfile.REGTYPE, b"one"), ("./file", tarfile.REGTYPE, b"two")])
        with self.assertRaises(ValueError):
            controller.safe_extract(self.archive, self.destination)

    def test_expanded_size_limit(self):
        self.write_archive([("large", tarfile.REGTYPE, b"12345")])
        with patch.object(controller, "MAX_EXPANDED_BYTES", 4), self.assertRaises(ValueError):
            controller.safe_extract(self.archive, self.destination)
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_file_count_limit(self):
        self.write_archive([("one", tarfile.REGTYPE, b"1"), ("two", tarfile.REGTYPE, b"2")])
        with patch.object(controller, "MAX_MEMBERS", 1), self.assertRaises(ValueError):
            controller.safe_extract(self.archive, self.destination)

    def test_upload_copy_verifies_digest(self):
        incoming = self.root / "incoming"
        incoming.mkdir()
        payload = b"valid archive bytes"
        (incoming / f"{SHA}.tar.gz").write_bytes(payload)
        target = self.root / "copied"
        controller.copy_upload(incoming, SHA, target, hashlib.sha256(payload).hexdigest())
        self.assertEqual(target.read_bytes(), payload)

    def test_uploaded_symlink_cannot_make_root_read_another_file(self):
        incoming = self.root / "incoming"
        incoming.mkdir()
        sensitive = self.root / "private"
        sensitive.write_bytes(b"secret-sentinel")
        (incoming / f"{SHA}.tar.gz").symlink_to(sensitive)
        target = self.root / "copied"
        with self.assertRaises(OSError):
            controller.copy_upload(incoming, SHA, target, DIGEST)
        self.assertFalse(target.exists())

    def test_privileged_errors_do_not_disclose_exception_contents(self):
        with patch.object(controller.os, "geteuid", return_value=0), patch.object(sys, "argv", ["controller", SHA, DIGEST]), patch.object(controller.Path, "read_text", side_effect=ValueError("secret-sentinel")), patch("sys.stderr", new_callable=io.StringIO) as output:
            self.assertEqual(controller.main(), 1)
            self.assertNotIn("secret-sentinel", output.getvalue())


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.config = {
            "repository": "owner/repo", "python": "/usr/bin/python3.12",
            "app_user": pwd.getpwuid(os.getuid()).pw_name,
            "env_file": "/protected/settings.env", "health_host": "pro.vezano.app",
        }
        for key in ("incoming", "private_stage", "releases", "logs", "state", "backups"):
            path = self.root / key
            path.mkdir()
            self.config[key] = str(path)
        self.config["lock"] = str(self.root / "lock")
        self.old = self.root / "old"
        self.old.mkdir()
        self.current = self.root / "current"
        self.current.symlink_to(self.old)
        self.config["link"] = str(self.current)
        self.config_path = self.root / "config.json"
        self.config_path.write_text(json.dumps(self.config))
        archive_path = Path(self.config["incoming"]) / f"{SHA}.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            for name, content in {
                "VERSION": b"1.0.0", "backend/manage.py": b"source",
                "backend/requirements.lock": b"pins", "release-manifest.json": b"{}",
                "frontend/out/index.html": b"tested export",
                "deploy/standalone/upgrade.sh": b"NEVER EXECUTE THIS AS ROOT",
            }.items():
                info = tarfile.TarInfo(name)
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
        self.digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        self.commands = []
        self.mode = "saas"
        self.upgrade_result = 0

    def fake_run(self, arguments, **kwargs):
        self.commands.append((arguments, kwargs))
        if "--verbosity" in arguments:
            return SimpleNamespace(returncode=0, stdout=self.mode + "\n")
        if arguments[0] == "bash":
            if not self.upgrade_result:
                release = Path(arguments[arguments.index("--release") + 1])
                self.current.unlink()
                self.current.symlink_to(release)
            return SimpleNamespace(returncode=self.upgrade_result)
        return SimpleNamespace(returncode=0)

    def run_controller(self):
        with patch.object(controller, "CONFIG", self.config_path), patch.object(controller.os, "geteuid", return_value=0), patch.object(controller.os, "chown"), patch.object(controller, "require_latest_main"), patch.object(controller.subprocess, "run", side_effect=self.fake_run), patch.object(sys, "argv", ["controller", SHA, self.digest]), patch("sys.stdout", new_callable=io.StringIO), patch("sys.stderr", new_callable=io.StringIO):
            return controller.main()

    def test_fixed_reviewed_root_script_and_no_migration_policy(self):
        self.assertEqual(self.run_controller(), 0)
        upgrades = [(args, kwargs) for args, kwargs in self.commands if args[0] == "bash"]
        self.assertEqual(len(upgrades), 1)
        args, kwargs = upgrades[0]
        self.assertEqual(args[1], controller.UPGRADE)
        self.assertIn("--require-no-migrations", args)
        self.assertEqual(args[args.index("--worker-service") + 1], "none")
        self.assertNotIn("--skip-backup", args)
        self.assertEqual(kwargs["env"], {"PATH": "/usr/local/bin:/usr/bin:/bin"})
        saved = json.loads((Path(self.config["state"]) / "last-success.json").read_text())
        self.assertEqual(saved["commit"], SHA)
        self.assertEqual(self.current.resolve().name, f"1.0.0-{SHA[:12]}-auto")

    def test_standalone_rejected_without_invoking_root_upgrade(self):
        self.mode = "standalone"
        self.assertEqual(self.run_controller(), 1)
        self.assertFalse(any(args[0] == "bash" for args, _ in self.commands))
        self.assertEqual(self.current.resolve(), self.old)

    def test_failed_upgrade_does_not_record_success(self):
        self.upgrade_result = 1
        self.assertEqual(self.run_controller(), 1)
        self.assertFalse((Path(self.config["state"]) / "last-success.json").exists())
        self.assertEqual(self.current.resolve(), self.old)


if __name__ == "__main__":
    unittest.main()
