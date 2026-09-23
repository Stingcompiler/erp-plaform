"""Vendor-side licence issuing: the half of the scheme that holds the private key.

Everything a customer's server does with a licence is in `services.py` and
needs only the public key. This module runs on the vendor's machine (never
on a customer host, never on Render) to create the signed envelope that
`services.verify_envelope` checks.

Key handling rules, enforced here rather than left to memory:
  - the private key is read from a file path (or an env var naming one),
    never from settings and never from the repository;
  - a licence names the `key_id` it was signed with, so keys can be rotated
    by shipping a new public key to installations and issuing with the new
    one, while old licences keep verifying against the old public key.
"""

import base64
import json
import uuid
from datetime import datetime, time, timezone as dt_timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from licensing.services import canonical_payload

KINDS = ("perpetual", "term")


def generate_keypair():
    """New Ed25519 pair as (private_pem, public_pem) strings."""
    private = Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        private.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return private_pem, public_pem


def load_private_key(path):
    data = Path(path).read_bytes()
    key = serialization.load_pem_private_key(data, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("The licence signing key must be an Ed25519 private key.")
    return key


def _end_of_day_utc(day):
    """A date on a licence means 'through the end of that day', in UTC, so an
    installation in any timezone stops no earlier than the printed date."""
    return datetime.combine(day, time(23, 59, 59), tzinfo=dt_timezone.utc)


def build_payload(
    *,
    installation_id,
    organisation_name,
    kind,
    key_id,
    modules,
    limits,
    usable_until=None,
    grace_days=0,
    maintenance_until=None,
    max_application_version="",
    license_id=None,
    issued_at=None,
):
    """The unsigned payload, validated the way the customer side will see it.

    `modules` is a list of module names or ["*"]; `limits` maps resource ->
    integer. Dates are `datetime.date`; `usable_until` is mandatory for a
    term licence and forbidden for a perpetual one.
    """
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}.")
    installation_uuid = uuid.UUID(str(installation_id))
    if not organisation_name or not organisation_name.strip():
        raise ValueError("organisation_name is required.")
    if kind == "term" and usable_until is None:
        raise ValueError("A term licence needs usable_until.")
    if kind == "perpetual" and usable_until is not None:
        raise ValueError("A perpetual licence has no usable_until; use maintenance_until.")
    for name, value in (limits or {}).items():
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"limit {name!r} must be a non-negative integer.")
    if not modules:
        raise ValueError("modules must list at least one module or ['*'].")
    payload = {
        "license_id": str(license_id or uuid.uuid4()),
        "installation_id": str(installation_uuid),
        "organisation_name": organisation_name.strip(),
        "kind": kind,
        "key_id": key_id,
        "modules": sorted(set(modules)),
        "limits": dict(sorted((limits or {}).items())),
        "issued_at": (issued_at or datetime.now(dt_timezone.utc)).isoformat(),
    }
    if usable_until is not None:
        end = _end_of_day_utc(usable_until)
        payload["usable_until"] = end.isoformat()
        if grace_days:
            from datetime import timedelta

            payload["grace_until"] = (end + timedelta(days=grace_days)).isoformat()
    if maintenance_until is not None:
        payload["maintenance_until"] = maintenance_until.isoformat()
    if max_application_version:
        payload["max_application_version"] = max_application_version
    return payload


def sign_payload(payload, private_key):
    signature = private_key.sign(canonical_payload(payload))
    return {"payload": payload, "signature": base64.b64encode(signature).decode("ascii")}


def envelope_json(envelope):
    return json.dumps(envelope, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
