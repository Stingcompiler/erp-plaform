"""Print a fresh VAPID key pair for Web Push, ready to paste into Render.

Run once. The private key must stay secret; both go into the environment
as VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY (public key is what browsers get).
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


def _b64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class Command(BaseCommand):
    help = "Generate a VAPID key pair (P-256) for Web Push."

    def handle(self, *args, **options):
        key = ec.generate_private_key(ec.SECP256R1())
        private = _b64url(key.private_numbers().private_value.to_bytes(32, "big"))
        public = _b64url(
            key.public_key().public_bytes(
                serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
            )
        )
        self.stdout.write(f"VAPID_PRIVATE_KEY={private}")
        self.stdout.write(f"VAPID_PUBLIC_KEY={public}")
