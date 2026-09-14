from django.test import TestCase, override_settings

from ops import preflight


class FindingTests(TestCase):
    def test_only_fail_is_blocking(self):
        self.assertTrue(preflight.Finding("x", preflight.FAIL, "d").is_blocking)
        self.assertFalse(preflight.Finding("x", preflight.WARN, "d").is_blocking)
        self.assertFalse(preflight.Finding("x", preflight.OK, "d").is_blocking)

    def test_as_dict_round_trips(self):
        finding = preflight.Finding("media", preflight.WARN, "detail")
        self.assertEqual(
            finding.as_dict(), {"code": "media", "level": "warn", "detail": "detail"}
        )


class CheckTests(TestCase):
    def test_secret_key_check_rejects_the_insecure_default(self):
        with override_settings(SECRET_KEY=preflight.INSECURE_SECRET):
            self.assertEqual(preflight.check_secret_key().level, preflight.FAIL)

    def test_secret_key_check_rejects_a_short_key(self):
        with override_settings(SECRET_KEY="short"):
            self.assertEqual(preflight.check_secret_key().level, preflight.FAIL)

    def test_secret_key_check_passes_a_long_custom_key(self):
        with override_settings(SECRET_KEY="a" * 48):
            self.assertEqual(preflight.check_secret_key().level, preflight.OK)

    def test_deployment_profile_rejects_debug_in_standalone(self):
        with override_settings(
            VEZANO_DEPLOYMENT_MODE="standalone",
            SUBSCRIPTION_POLICY="enforce",
            DEBUG=True,
        ):
            finding = preflight.check_deployment_profile()
            self.assertEqual(finding.level, preflight.FAIL)
            self.assertIn("DEBUG", finding.detail)

    def test_deployment_profile_is_ok_for_saas_enforce(self):
        with override_settings(
            VEZANO_DEPLOYMENT_MODE="saas", SUBSCRIPTION_POLICY="enforce"
        ):
            self.assertEqual(preflight.check_deployment_profile().level, preflight.OK)

    def test_deployment_profile_reports_invalid_settings(self):
        with override_settings(VEZANO_DEPLOYMENT_MODE="nonsense"):
            self.assertEqual(preflight.check_deployment_profile().level, preflight.FAIL)

    def test_database_check_warns_on_sqlite(self):
        from django.db import connection

        expected = preflight.WARN if connection.vendor == "sqlite" else preflight.OK
        self.assertEqual(preflight.check_database().level, expected)

    def test_frontend_build_is_present_in_this_tree(self):
        self.assertEqual(preflight.check_frontend_build().level, preflight.OK)

    def test_media_writable_writes_and_removes_its_probe(self):
        finding = preflight.check_media_writable()
        self.assertEqual(finding.level, preflight.OK)

    def test_licence_check_is_not_applicable_in_saas(self):
        with override_settings(VEZANO_DEPLOYMENT_MODE="saas"):
            self.assertEqual(preflight.check_licence().level, preflight.OK)

    def test_migrations_plan_is_reported(self):
        # The test database is fully migrated, so nothing should be pending.
        self.assertEqual(preflight.check_pending_migrations().level, preflight.OK)
        self.assertEqual(preflight.pending_migrations(), [])


class RunPreflightTests(TestCase):
    def test_run_preflight_covers_every_code_once(self):
        findings = preflight.run_preflight()
        codes = [finding.code for finding in findings]
        self.assertEqual(len(codes), len(set(codes)))
        for expected in (
            "deployment_profile",
            "secret_key",
            "database",
            "migrations",
            "media",
            "frontend_build",
            "licence",
        ):
            self.assertIn(expected, codes)
