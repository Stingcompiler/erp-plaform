import json
import uuid
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from licensing.issuing import build_payload, generate_keypair, load_private_key, sign_payload
from licensing.models import Installation
from licensing.services import activate_license, resolve_license_entitlements


class IssuingRoundTripTests(TestCase):
    """Vendor issues with the private key; the customer installation verifies
    with only the public key. The two halves must agree byte for byte."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.keys = Path(self.tmp.name) / "keys"
        out = StringIO()
        call_command("license_keygen", key_id="vezano-test", out_dir=str(self.keys), stdout=out)
        self.private_path = self.keys / "vezano-test.private.pem"
        public_pem = (self.keys / "vezano-test.public.pem").read_text()
        self.override = override_settings(
            VEZANO_DEPLOYMENT_MODE="standalone",
            SUBSCRIPTION_POLICY="observe",  # ignored in standalone: enforce always
            VEZANO_LICENSE_PUBLIC_KEYS={"vezano-test": public_pem},
        )
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.installation = Installation.objects.create(organisation_name="Customer Co")

    def _issue(self, **flags):
        out_file = Path(self.tmp.name) / f"{uuid.uuid4()}.json"
        base = dict(
            private_key=str(self.private_path),
            key_id="vezano-test",
            installation_id=str(self.installation.installation_id),
            organisation="Customer Co",
            out=str(out_file),
        )
        base.update(flags)
        call_command("issue_license", stdout=StringIO(), **base)
        return json.loads(out_file.read_text())

    def test_keygen_refuses_to_write_inside_the_repository(self):
        repo_dir = Path(__file__).resolve().parents[1] / "tmp-keys"
        with self.assertRaises(CommandError):
            call_command("license_keygen", key_id="x", out_dir=str(repo_dir), stdout=StringIO())
        self.assertFalse(repo_dir.exists())

    def test_keygen_never_overwrites_a_signing_key(self):
        with self.assertRaises(CommandError):
            call_command(
                "license_keygen", key_id="vezano-test", out_dir=str(self.keys), stdout=StringIO()
            )

    def test_perpetual_licence_round_trip(self):
        envelope = self._issue(
            kind="perpetual",
            maintenance_until="2027-12-31",
            limit=["users=25"],
            modules="sales,inventory",
        )
        activation, created = activate_license(envelope)
        self.assertTrue(created)
        self.assertEqual(activation.kind, "perpetual")
        self.assertEqual(activation.limits, {"users": 25})
        self.assertEqual(activation.modules, ["inventory", "sales"])
        decision = resolve_license_entitlements()
        self.assertEqual(decision.state, "active")
        self.assertTrue(decision.allow_writes)
        self.assertNotIn("hr", decision.modules)

    def test_term_licence_active_then_grace_then_read_only(self):
        last_day = date.today() + timedelta(days=30)
        envelope = self._issue(
            kind="term", usable_until=last_day.isoformat(), grace_days=7, modules="*"
        )
        activate_license(envelope)
        now = timezone.now()
        self.assertEqual(resolve_license_entitlements(now).state, "active")
        after_end = now + timedelta(days=33)
        grace = resolve_license_entitlements(after_end)
        self.assertEqual(grace.state, "grace")
        self.assertTrue(grace.allow_writes)
        self.assertIn("renew", grace.reason.lower())
        after_grace = now + timedelta(days=40)
        closed = resolve_license_entitlements(after_grace)
        self.assertEqual(closed.state, "read_only")
        self.assertFalse(closed.allow_writes)

    def test_licence_for_another_installation_is_rejected(self):
        envelope = self._issue(installation_id=str(uuid.uuid4()))
        with self.assertRaises(ValidationError):
            activate_license(envelope)

    def test_licence_signed_with_an_untrusted_key_is_rejected(self):
        other_private, _ = generate_keypair()
        other_path = Path(self.tmp.name) / "rogue.pem"
        other_path.write_text(other_private)
        envelope = self._issue(private_key=str(other_path), key_id="vezano-test")
        with self.assertRaises(ValidationError):
            activate_license(envelope)

    def test_newer_licence_supersedes_the_previous_one(self):
        first = self._issue(limit=["users=5"])
        second = self._issue(limit=["users=50"])
        activate_license(first)
        activate_license(second)
        self.assertEqual(resolve_license_entitlements().limits, {"users": 50})
        self.assertEqual(
            self.installation.activations.filter(superseded_at__isnull=True).count(), 1
        )

    def test_release_above_licence_ceiling_blocks_writes_but_not_reads(self):
        envelope = self._issue(max_version="0.9.0")  # VERSION file says 1.0.0
        activate_license(envelope)
        decision = resolve_license_entitlements()
        self.assertEqual(decision.state, "version_not_covered")
        self.assertFalse(decision.allow_writes)
        self.assertIn("1.0.0", decision.reason)
        covered = self._issue(max_version="1.0.99")
        activate_license(covered)
        self.assertTrue(resolve_license_entitlements().allow_writes)

    def test_standalone_always_enforces_regardless_of_policy_setting(self):
        from config.deployment import get_deployment_config

        self.assertEqual(get_deployment_config().entitlement_policy, "enforce")

    def test_build_payload_validation(self):
        with self.assertRaises(ValueError):
            build_payload(
                installation_id=uuid.uuid4(),
                organisation_name="X",
                kind="term",
                key_id="k",
                modules=["*"],
                limits={},
            )
        with self.assertRaises(ValueError):
            build_payload(
                installation_id=uuid.uuid4(),
                organisation_name="X",
                kind="perpetual",
                key_id="k",
                modules=["*"],
                limits={"users": -1},
            )
        payload = build_payload(
            installation_id=uuid.uuid4(),
            organisation_name="X",
            kind="term",
            key_id="k",
            modules=["*"],
            limits={},
            usable_until=date(2027, 1, 31),
            grace_days=14,
        )
        self.assertTrue(payload["usable_until"].startswith("2027-01-31T23:59:59"))
        self.assertTrue(payload["grace_until"].startswith("2027-02-14T23:59:59"))
        signed = sign_payload(payload, load_private_key(self.private_path))
        self.assertIn("signature", signed)


class LicenseImportEndpointTests(TestCase):
    """The owner-facing endpoint must answer a rejected licence with a 400
    and the reason — it used to raise straight through as a 500."""

    def test_wrong_installation_is_a_400_with_reason(self):
        from rest_framework.test import APIClient
        from accounts.models import Role, User
        from org.models import Company

        private_pem, public_pem = generate_keypair()
        with override_settings(
            VEZANO_DEPLOYMENT_MODE="standalone",
            VEZANO_LICENSE_PUBLIC_KEYS={"k": public_pem},
        ):
            Installation.objects.create(organisation_name="Mine")
            company = Company.objects.create(name="Mine")
            owner = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
            user = User.objects.create_user("o@m.test", "passw0rd123", company=company, role=owner)
            tmp = TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            key_path = Path(tmp.name) / "k.pem"
            key_path.write_text(private_pem)
            payload = build_payload(
                installation_id=uuid.uuid4(),
                organisation_name="Other",
                kind="perpetual",
                key_id="k",
                modules=["*"],
                limits={},
            )
            envelope = sign_payload(payload, load_private_key(key_path))
            client = APIClient()
            client.force_authenticate(user)
            response = client.post("/api/license/", envelope, format="json")
            self.assertEqual(response.status_code, 400, response.content)
            self.assertIn("installation_id", response.data)
