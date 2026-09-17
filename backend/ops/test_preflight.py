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
            "licence_keys",
            "licence",
            "scheduled_jobs",
            "backup_freshness",
            "dependency_lock",
        ):
            self.assertIn(expected, codes)


class LicenceKeyTests(TestCase):
    def test_not_applicable_on_saas(self):
        with override_settings(VEZANO_DEPLOYMENT_MODE="saas", VEZANO_LICENSE_PUBLIC_KEYS={}):
            self.assertEqual(preflight.check_licence_keys().level, preflight.OK)

    def test_standalone_without_a_key_is_blocking(self):
        with override_settings(
            VEZANO_DEPLOYMENT_MODE="standalone", VEZANO_LICENSE_PUBLIC_KEYS={}
        ):
            self.assertEqual(preflight.check_licence_keys().level, preflight.FAIL)

    def test_standalone_with_a_mangled_key_is_blocking(self):
        # What a shell makes of the JSON form when it strips the quotes.
        with override_settings(
            VEZANO_DEPLOYMENT_MODE="standalone",
            VEZANO_LICENSE_PUBLIC_KEYS={"k": "-----BEGIN PUBLIC KEY-----\n"[:5]},
        ):
            finding = preflight.check_licence_keys()
            self.assertEqual(finding.level, preflight.FAIL)
            self.assertIn("k", finding.detail)

    def test_standalone_with_a_pem_key_passes(self):
        with override_settings(
            VEZANO_DEPLOYMENT_MODE="standalone",
            VEZANO_LICENSE_PUBLIC_KEYS={
                "k": "-----BEGIN PUBLIC KEY-----\nx\n-----END PUBLIC KEY-----\n"
            },
        ):
            self.assertEqual(preflight.check_licence_keys().level, preflight.OK)


class StandaloneReadinessTests(TestCase):
    def test_https_is_a_hard_requirement_for_standalone(self):
        with override_settings(
            VEZANO_DEPLOYMENT_MODE="standalone", FORCE_HTTPS=False, DEBUG=False,
            ALLOWED_HOSTS=["erp.local"],
        ):
            self.assertEqual(preflight.check_https_consistency().level, preflight.FAIL)
        with override_settings(
            VEZANO_DEPLOYMENT_MODE="standalone", FORCE_HTTPS=True, DEBUG=False,
            ALLOWED_HOSTS=["erp.local"],
        ):
            self.assertEqual(preflight.check_https_consistency().level, preflight.OK)

    def test_scheduled_jobs_not_applicable_on_saas(self):
        with override_settings(VEZANO_DEPLOYMENT_MODE="saas"):
            self.assertEqual(preflight.check_scheduled_jobs().level, preflight.OK)

    def test_missing_timers_block_a_standalone_install(self):
        from unittest import mock

        with override_settings(VEZANO_DEPLOYMENT_MODE="standalone"):
            with mock.patch("shutil.which", return_value="/bin/systemctl"):
                fake = mock.Mock(stdout="inactive\n")
                with mock.patch("subprocess.run", return_value=fake):
                    finding = preflight.check_scheduled_jobs()
        self.assertEqual(finding.level, preflight.FAIL)
        self.assertIn("vezano-backup.timer", finding.detail)

    def test_lock_file_is_present(self):
        self.assertEqual(preflight.check_dependency_lock().level, preflight.OK)

    def test_mode_flip_over_a_live_installation_is_refused(self):
        from django.core.exceptions import ImproperlyConfigured

        from config.deployment import assert_mode_matches_installation
        from licensing.models import Installation

        with override_settings(VEZANO_DEPLOYMENT_MODE="standalone"):
            Installation.current()
            self.assertEqual(assert_mode_matches_installation(), "standalone")
        with override_settings(VEZANO_DEPLOYMENT_MODE="saas"):
            with self.assertRaises(ImproperlyConfigured):
                assert_mode_matches_installation()
            self.assertEqual(preflight.check_deployment_profile().level, preflight.FAIL)
