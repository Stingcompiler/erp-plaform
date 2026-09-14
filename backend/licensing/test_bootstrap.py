from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from licensing.models import Installation


@override_settings(VEZANO_DEPLOYMENT_MODE="standalone", SUBSCRIPTION_POLICY="enforce")
class BootstrapStandaloneTests(TestCase):
    def bootstrap(self, *args):
        out = StringIO()
        call_command("bootstrap_standalone", *args, stdout=out)
        return out.getvalue()

    def test_first_run_creates_the_identity_and_records_the_version(self):
        out = self.bootstrap("--organisation", "Acme", "--app-version", "1.0.0")
        installation = Installation.objects.get()
        self.assertIn(str(installation.installation_id), out)
        self.assertEqual(installation.application_version, "1.0.0")
        self.assertEqual(installation.previous_version, "")
        self.assertIsNone(installation.upgraded_at)

    def test_a_version_change_keeps_the_previous_one_and_the_time(self):
        self.bootstrap("--organisation", "Acme", "--app-version", "1.0.0")
        out = self.bootstrap("--app-version", "1.1.0")
        installation = Installation.objects.get()
        self.assertEqual(installation.application_version, "1.1.0")
        self.assertEqual(installation.previous_version, "1.0.0")
        self.assertIsNotNone(installation.upgraded_at)
        self.assertEqual(installation.organisation_name, "Acme")
        self.assertIn("1.1.0 (previously 1.0.0)", out)

    def test_repeating_the_same_version_is_not_an_upgrade(self):
        self.bootstrap("--organisation", "Acme", "--app-version", "1.0.0")
        self.bootstrap("--app-version", "1.0.0")
        installation = Installation.objects.get()
        self.assertEqual(installation.previous_version, "")
        self.assertIsNone(installation.upgraded_at)

    def test_identity_is_stable_across_runs(self):
        first = Installation.current().installation_id
        self.bootstrap("--organisation", "Acme")
        self.bootstrap("--organisation", "Acme Renamed")
        self.assertEqual(Installation.objects.get().installation_id, first)
        self.assertEqual(Installation.objects.get().organisation_name, "Acme Renamed")

    @override_settings(VEZANO_DEPLOYMENT_MODE="saas")
    def test_refused_on_the_hosted_platform(self):
        with self.assertRaises(CommandError):
            self.bootstrap("--organisation", "Acme")
