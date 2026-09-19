import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase

from ops import release


class VersionAndHashingTests(TestCase):
    def test_application_version_reads_the_version_file(self):
        self.assertRegex(release.application_version(), r"^\d+\.\d+\.\d+")

    def test_application_version_falls_back_when_the_file_is_absent(self):
        self.assertEqual(
            release.application_version(root=Path("/nonexistent")), "0.0.0-unknown"
        )

    def test_deployed_commit_prefers_render_then_generic_then_none(self):
        self.assertEqual(
            release.deployed_commit({"RENDER_GIT_COMMIT": "9c0313ef1234567890"}), "9c0313ef"
        )
        self.assertEqual(
            release.deployed_commit({"RENDER_GIT_COMMIT": " ", "GIT_COMMIT": "abcdef01ff"}),
            "abcdef01",
        )
        self.assertIsNone(release.deployed_commit({}))

    def test_sha256_file_matches_a_known_digest(self):
        payload = b"vezano"
        target = Path(tempfile.gettempdir()) / "vezano-hash-probe.bin"
        target.write_bytes(payload)
        self.addCleanup(target.unlink)
        self.assertEqual(release.sha256_file(target), hashlib.sha256(payload).hexdigest())

    def test_sha256_tree_changes_when_a_file_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("one", encoding="utf-8")
            first = release.sha256_tree(root)
            (root / "a.txt").write_text("two", encoding="utf-8")
            self.assertNotEqual(first, release.sha256_tree(root))

    def test_sha256_tree_changes_when_a_file_is_renamed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("same", encoding="utf-8")
            first = release.sha256_tree(root)
            (root / "a.txt").rename(root / "b.txt")
            self.assertNotEqual(first, release.sha256_tree(root))


class InventoryTests(TestCase):
    def test_migration_inventory_covers_the_commercial_apps(self):
        rows = release.migration_inventory()
        apps = {row["app"] for row in rows}
        self.assertIn("subscriptions", apps)
        self.assertIn("licensing", apps)
        for row in rows:
            self.assertEqual(len(row["sha256"]), 64)

    def test_dependency_inventory_lists_pinned_packages(self):
        inventory = release.dependency_inventory()
        self.assertTrue(inventory["present"])
        self.assertTrue(inventory["packages"])
        self.assertEqual(len(inventory["sha256"]), 64)

    def test_frontend_inventory_reports_the_built_export(self):
        inventory = release.frontend_inventory()
        self.assertTrue(inventory["present"])
        self.assertGreater(inventory["files"], 0)
        self.assertEqual(len(inventory["sha256"]), 64)


class ManifestTests(TestCase):
    def test_build_manifest_carries_version_migrations_and_frontend(self):
        manifest = release.build_manifest()
        self.assertEqual(manifest["application_version"], release.application_version())
        self.assertTrue(manifest["migrations"])
        self.assertIn("frontend", manifest)
        self.assertEqual(manifest["manifest_checksum"], release.manifest_checksum(manifest))

    def test_a_fresh_manifest_verifies_against_its_own_tree(self):
        self.assertEqual(release.verify_manifest(release.build_manifest()), [])

    def test_editing_the_manifest_is_detected(self):
        manifest = release.build_manifest()
        manifest["application_version"] = "9.9.9"
        problems = release.verify_manifest(manifest)
        self.assertTrue(any("checksum" in problem for problem in problems))

    def test_a_modified_migration_is_reported(self):
        manifest = release.build_manifest()
        original = release.migration_inventory

        def altered():
            rows = original()
            if rows:
                rows[0] = {**rows[0], "sha256": "0" * 64}
            return rows

        with patch.object(release, "migration_inventory", altered):
            problems = release.verify_manifest(manifest)
        self.assertTrue(any("Modified migration" in problem for problem in problems))

    def test_a_missing_migration_is_reported(self):
        manifest = release.build_manifest()
        original = release.migration_inventory

        with patch.object(release, "migration_inventory", lambda: original()[1:]):
            problems = release.verify_manifest(manifest)
        self.assertTrue(any("Missing migration" in problem for problem in problems))

    def test_non_dict_manifest_is_rejected(self):
        self.assertEqual(
            release.verify_manifest(["not", "a", "manifest"]),
            ["The manifest is not a JSON object."],
        )

    def test_write_manifest_and_checksums_round_trip(self):
        manifest = release.build_manifest()
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = release.write_manifest(
                manifest, Path(directory) / release.MANIFEST_NAME
            )
            checksums_path = release.write_checksums(
                manifest, Path(directory) / release.CHECKSUM_NAME
            )
            reloaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(reloaded["manifest_checksum"], manifest["manifest_checksum"])
            checksums = checksums_path.read_text(encoding="utf-8")
            self.assertIn(release.MANIFEST_NAME, checksums)
            self.assertIn("VERSION", checksums)
