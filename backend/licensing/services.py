import base64
import json
import uuid
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from core.entitlements import EntitlementDecision
from licensing.models import Installation, LicenseActivation


REQUIRED_FIELDS = {
    "license_id",
    "installation_id",
    "organisation_name",
    "kind",
    "key_id",
    "modules",
    "limits",
}


def canonical_payload(payload):
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _aware_datetime(value, field):
    if not value:
        return None
    result = parse_datetime(value)
    if result is None:
        raise ValidationError({field: "Use an ISO-8601 date and time."})
    if timezone.is_naive(result):
        result = timezone.make_aware(result)
    return result


def verify_envelope(envelope, installation=None):
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
        raise ValidationError("Licence file must contain payload and signature.")
    payload = envelope["payload"]
    missing = sorted(REQUIRED_FIELDS - set(payload))
    if missing:
        raise ValidationError({"payload": f"Missing fields: {', '.join(missing)}"})
    installation = installation or Installation.current()
    try:
        if uuid.UUID(str(payload["installation_id"])) != installation.installation_id:
            raise ValidationError(
                {"installation_id": "This licence belongs to another installation."}
            )
        license_id = uuid.UUID(str(payload["license_id"]))
    except (TypeError, ValueError, AttributeError):
        raise ValidationError("Licence identifiers are invalid.")
    if payload["kind"] not in {LicenseActivation.PERPETUAL, LicenseActivation.TERM}:
        raise ValidationError({"kind": "Licence kind must be perpetual or term."})
    key_pem = settings.VEZANO_LICENSE_PUBLIC_KEYS.get(str(payload["key_id"]))
    if not key_pem:
        raise ValidationError(
            {"key_id": "The signing key is not trusted by this installation."}
        )
    try:
        public_key = serialization.load_pem_public_key(key_pem.encode("utf-8"))
        signature = base64.b64decode(envelope.get("signature", ""), validate=True)
        public_key.verify(signature, canonical_payload(payload))
    except (ValueError, TypeError, InvalidSignature) as exc:
        raise ValidationError(
            {"signature": "The licence signature is invalid."}
        ) from exc
    usable_until = _aware_datetime(payload.get("usable_until"), "usable_until")
    grace_until = _aware_datetime(payload.get("grace_until"), "grace_until")
    if payload["kind"] == LicenseActivation.TERM and usable_until is None:
        raise ValidationError(
            {"usable_until": "A fixed-term licence needs an end date."}
        )
    maintenance_until = (
        parse_date(payload.get("maintenance_until"))
        if payload.get("maintenance_until")
        else None
    )
    return {
        **payload,
        "license_id": license_id,
        "usable_until": usable_until,
        "grace_until": grace_until,
        "maintenance_until": maintenance_until,
    }


@transaction.atomic
def activate_license(envelope, actor=None):
    installation = Installation.current()
    payload = verify_envelope(envelope, installation)
    now = timezone.now()
    installation.activations.filter(superseded_at__isnull=True).update(
        superseded_at=now
    )
    activation, created = LicenseActivation.objects.update_or_create(
        license_id=payload["license_id"],
        defaults={
            "installation": installation,
            "organisation_name": payload["organisation_name"],
            "kind": payload["kind"],
            "key_id": payload["key_id"],
            "modules": payload["modules"],
            "limits": payload["limits"],
            "usable_until": payload["usable_until"],
            "grace_until": payload["grace_until"],
            "maintenance_until": payload["maintenance_until"],
            "max_application_version": payload.get("max_application_version", ""),
            "payload": envelope["payload"],
            "signature": envelope["signature"],
            "activated_by": actor,
            "superseded_at": None,
        },
    )
    return activation, created


def active_license():
    try:
        installation = Installation.objects.order_by("pk").first()
        return (
            installation
            and installation.activations.filter(superseded_at__isnull=True).first()
        )
    except Exception:
        return None


def resolve_license_entitlements(now=None):
    now = now or timezone.now()
    activation = active_license()
    if not activation:
        return EntitlementDecision(
            "standalone",
            "unlicensed",
            frozenset(),
            {},
            False,
            reason="No valid standalone licence is installed.",
        )
    state, allow_writes = "active", True
    valid_until = activation.usable_until
    if (
        activation.kind == LicenseActivation.TERM
        and activation.usable_until
        and now > activation.usable_until
    ):
        if activation.grace_until and now <= activation.grace_until:
            state, valid_until = "grace", activation.grace_until
        else:
            state, allow_writes = "read_only", False
    return EntitlementDecision(
        "standalone",
        state,
        frozenset(activation.modules or {"*"}),
        dict(activation.limits or {}),
        allow_writes,
        valid_until,
    )
