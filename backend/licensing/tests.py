import base64
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from licensing.models import Installation
from licensing.services import (
    activate_license,
    canonical_payload,
    resolve_license_entitlements,
)


class SignedLicenceTests(TestCase):
    def setUp(self):
        self.private = Ed25519PrivateKey.generate()
        public_pem = (
            self.private.public_key()
            .public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("utf-8")
        )
        self.settings = override_settings(
            VEZANO_DEPLOYMENT_MODE="standalone",
            SUBSCRIPTION_POLICY="enforce",
            VEZANO_LICENSE_PUBLIC_KEYS={"test-key": public_pem},
        )
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        self.installation = Installation.objects.create(organisation_name="Local Co")

    def envelope(self):
        payload = {
            "license_id": str(uuid.uuid4()),
            "installation_id": str(self.installation.installation_id),
            "organisation_name": "Local Co",
            "kind": "perpetual",
            "key_id": "test-key",
            "modules": ["sales", "inventory"],
            "limits": {"users": 25},
            "maintenance_until": timezone.now().date().isoformat(),
        }
        signature = self.private.sign(canonical_payload(payload))
        return {
            "payload": payload,
            "signature": base64.b64encode(signature).decode("ascii"),
        }

    def test_signed_perpetual_licence_works_offline(self):
        activation, created = activate_license(self.envelope())
        self.assertTrue(created)
        decision = resolve_license_entitlements()
        self.assertTrue(decision.allow_writes)
        self.assertIn("sales", decision.modules)
        self.assertEqual(activation.installation, self.installation)

    def test_modified_payload_is_rejected(self):
        envelope = self.envelope()
        envelope["payload"]["limits"]["users"] = 999
        with self.assertRaises(ValidationError):
            activate_license(envelope)
