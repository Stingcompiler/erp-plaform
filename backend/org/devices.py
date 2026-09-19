"""Devices: the plan's ``devices`` limit and what happens at sign-in.

A device is a browser profile (org.models.Device). The client sends its id
with every sign-in; the server registers it, refuses it when it is revoked
or would exceed the plan, and stamps it into the session's tokens so that
revoking a device also ends its sessions. Sign-ins that carry no device id
(scripts, tests) register nothing and are not counted.
"""

from django.core.cache import cache
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from core.activity import log_activity
from org.models import Device

DEVICE_ID_MAX = 64
REVOKED_CACHE_TTL = 60 * 60 * 24 * 14  # outlives the longest refresh token


class DeviceRefused(Exception):
    """Sign-in must stop: ``code`` is what the client shows, ``limit`` the
    plan's device count when that is the reason."""

    def __init__(self, code, limit=None):
        super().__init__(code)
        self.code = code
        self.limit = limit


def clean_device_id(raw):
    value = str(raw or "").strip()
    return value[:DEVICE_ID_MAX] if value else ""


def _revoked_key(company_id, device_id):
    return f"device-revoked:{company_id}:{device_id}"


def is_revoked(company_id, device_id):
    return bool(cache.get(_revoked_key(company_id, device_id)))


def register_device(company, device_id, user, request):
    """Touch or create the device for this sign-in; raise DeviceRefused when
    it may not be used. Returns the Device, or None when no id was sent."""
    from subscriptions.services import assert_capacity

    device_id = clean_device_id(device_id)
    if not device_id or company is None:
        return None
    agent = str(request.META.get("HTTP_USER_AGENT", ""))[:255]
    now = timezone.now()
    device = Device.objects.filter(company=company, device_id=device_id).first()
    if device is not None:
        if not device.is_active:
            raise DeviceRefused("device_revoked")
        device.last_seen_at = now
        device.last_user = user
        device.user_agent = agent or device.user_agent
        if user.branch_id and device.branch_id != user.branch_id:
            device.branch_id = user.branch_id
        device.save(update_fields=["last_seen_at", "last_user", "user_agent", "branch"])
        return device
    try:
        assert_capacity(company, "devices")
    except ValidationError as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        limit = detail.get("limit")
        raise DeviceRefused(
            "device_limit_reached", limit=int(str(limit)) if limit is not None else None
        )
    device = Device.objects.create(
        company=company, device_id=device_id, user_agent=agent,
        branch_id=user.branch_id, last_user=user, last_seen_at=now,
    )
    log_activity(
        action="device_registered", request=request, user=user, company=company,
        entity_type="Device", entity_id=device.pk, metadata={"device_id": device_id},
    )
    return device


def revoke_device(device, actor, request=None):
    if not device.is_active:
        return device
    device.is_active = False
    device.revoked_at = timezone.now()
    device.revoked_by = actor
    device.save(update_fields=["is_active", "revoked_at", "revoked_by"])
    # Sessions opened from this device carry its id in their tokens; the
    # authenticator checks this flag on every request (accounts.authentication).
    cache.set(_revoked_key(device.company_id, device.device_id), True, REVOKED_CACHE_TTL)
    log_activity(
        action="device_revoked", request=request, user=actor, company=device.company,
        entity_type="Device", entity_id=device.pk,
        metadata={"device_id": device.device_id, "label": device.label},
    )
    return device


def reactivate_device(device, actor, request=None):
    """Undo a revocation — the device must still fit the plan."""
    from subscriptions.services import assert_capacity

    if device.is_active:
        return device
    assert_capacity(device.company, "devices")
    device.is_active = True
    device.revoked_at = None
    device.revoked_by = None
    device.save(update_fields=["is_active", "revoked_at", "revoked_by"])
    cache.delete(_revoked_key(device.company_id, device.device_id))
    log_activity(
        action="device_reactivated", request=request, user=actor, company=device.company,
        entity_type="Device", entity_id=device.pk, metadata={"device_id": device.device_id},
    )
    return device
