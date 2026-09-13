from django.test import TestCase

from ops import restore_check


class ModelCountTests(TestCase):
    def setUp(self):
        from org.models import Branch, Company

        self.company = Company.objects.create(name="Restore Count Co")
        self.other = Company.objects.create(name="Other Restore Co")
        Branch.objects.create(company=self.company, name="One")
        Branch.objects.create(company=self.company, name="Two")
        Branch.objects.create(company=self.other, name="Other")

    def test_counts_include_every_concrete_model(self):
        counts = restore_check.model_counts()
        self.assertIn("org.Branch", counts)
        self.assertEqual(counts["org.Branch"], 3)

    def test_counts_can_be_scoped_to_one_company(self):
        counts = restore_check.model_counts(company_id=self.company.pk)
        self.assertEqual(counts["org.Branch"], 2)

    def test_company_scoping_skips_models_without_a_company_field(self):
        counts = restore_check.model_counts(company_id=self.company.pk)
        for key in counts:
            self.assertNotIn("auth.", key)
            self.assertNotIn("sessions.", key)

    def test_volatile_apps_are_excluded_from_the_default_set(self):
        labels = restore_check.counted_apps()
        self.assertNotIn("sessions", labels)
        self.assertNotIn("token_blacklist", labels)
        self.assertIn("org", labels)


class MediaInventoryTests(TestCase):
    def test_missing_directory_is_reported_as_absent(self):
        inventory = restore_check.media_inventory(root="/nonexistent-media-root")
        self.assertFalse(inventory["present"])
        self.assertEqual(inventory["files"], 0)

    def test_counts_files_and_bytes(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("12345", encoding="utf-8")
            (root / "sub").mkdir()
            (root / "sub" / "b.txt").write_text("67", encoding="utf-8")
            inventory = restore_check.media_inventory(root=root)
            self.assertTrue(inventory["present"])
            self.assertEqual(inventory["files"], 2)
            self.assertEqual(inventory["bytes"], 7)
            self.assertEqual(len(inventory["sha256"]), 64)


class FingerprintComparisonTests(TestCase):
    def test_identical_fingerprints_have_no_differences(self):
        fingerprint = {"counts": {"org.Branch": 2}, "media": {"files": 1, "bytes": 10}}
        self.assertEqual(restore_check.compare_fingerprints(fingerprint, fingerprint), [])

    def test_a_count_difference_is_reported(self):
        expected = {"counts": {"org.Branch": 2}}
        actual = {"counts": {"org.Branch": 1}}
        problems = restore_check.compare_fingerprints(expected, actual)
        self.assertEqual(len(problems), 1)
        self.assertIn("Row count differs for org.Branch", problems[0])

    def test_a_missing_table_is_reported(self):
        problems = restore_check.compare_fingerprints(
            {"counts": {"org.Branch": 2}}, {"counts": {}}
        )
        self.assertTrue(any("Table missing after restore" in p for p in problems))

    def test_an_extra_table_is_reported(self):
        problems = restore_check.compare_fingerprints(
            {"counts": {}}, {"counts": {"org.Branch": 2}}
        )
        self.assertTrue(any("Unexpected table after restore" in p for p in problems))

    def test_media_differences_are_reported(self):
        expected = {"counts": {}, "media": {"files": 0, "bytes": 0}}
        actual = {"counts": {}, "media": {"files": 1, "bytes": 26}}
        problems = restore_check.compare_fingerprints(expected, actual)
        self.assertTrue(any("Media files differs" in p for p in problems))
        self.assertTrue(any("Media bytes differs" in p for p in problems))

    def test_media_hash_mismatch_is_reported(self):
        expected = {"counts": {}, "media": {"files": 1, "bytes": 1, "sha256": "a" * 64}}
        actual = {"counts": {}, "media": {"files": 1, "bytes": 1, "sha256": "b" * 64}}
        problems = restore_check.compare_fingerprints(expected, actual)
        self.assertTrue(any("media tree hash" in p for p in problems))


class DataFingerprintTests(TestCase):
    def test_fingerprint_carries_version_counts_and_media(self):
        fingerprint = restore_check.data_fingerprint()
        self.assertIn("application_version", fingerprint)
        self.assertIn("counts", fingerprint)
        self.assertIn("media", fingerprint)

    def test_media_can_be_omitted(self):
        fingerprint = restore_check.data_fingerprint(include_media=False)
        self.assertNotIn("media", fingerprint)

    def test_media_hash_is_optional(self):
        with_hash = restore_check.data_fingerprint(with_media_hash=True)
        without_hash = restore_check.data_fingerprint(with_media_hash=False)
        self.assertEqual(without_hash["media"]["sha256"], "")
        self.assertIsInstance(with_hash["media"]["sha256"], str)
