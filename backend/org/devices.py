"""Devices: the plan's ``devices`` limit and what happens at sign-in.

A device is a browser profile (org.models.Device). The client sends its id
with every sign-in; the server registers it, refuses it when it is revoked
or would exceed the plan, and stamps it into the session's tokens so that
revoking a device also ends its sessions.

A company user must present a device id (review F06: a client that simply
omitted it used to sign in uncounted, so the plan's device limit was
optional). Platform accounts — the Vezano team's console logins, which
belong to no company and are never counted against a plan — are the one
documented exception; there is no exception for scripts or curl.

Revocation is read from the database with the cache only as an
accelerator (review F05: a cache-only flag came back "not revoked" after an
eviction or a cache-table rebuild, and a removed device kept working until
its refresh token expired).
"""

from django.core.cache import cache
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from core.activity import log_activity
from org.models import Device

DEVICE_ID_MAX = 64
# The cache only shortens the DB lookup; a miss is answered by the database,
# so the TTL is about request cost, not correctness.
REVOKED_CACHE_TTL = 60 * 5
_MISS = object()


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


def requires_device(user):
    """Business logins need a device identity; platform accounts do not."""
    return user.company_id is not None and not getattr(user, "is_platform_admin", False)


def is_revoked(company_id, device_id):
    if company_id is None or not device_id:
        return False
    key = _revoked_key(company_id, device_id)
    cached = cache.get(key, _MISS)
    if cached is not _MISS:
        return bool(cached)
    revoked = Device.objects.filter(
        company_id=company_id, device_id=device_id, is_active=False,
    ).exists()
    cache.set(key, revoked, REVOKED_CACHE_TTL)
    return revoked


def register_device(company, device_id, user, request):
    """Touch or create the device for this sign-in; raise DeviceRefused when
    it may not be used. Returns the Device, or None when no id was sent."""
    from subscriptions.services import assert_capacity

    device_id = clean_device_id(device_id)
    if company is None:
        return None
    if not device_id:
        if requires_device(user):
            raise DeviceRefused("device_required")
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
    cache.set(_revoked_key(device.company_id, device.device_id), False, REVOKED_CACHE_TTL)
    log_activity(
        action="device_reactivated", request=request, user=actor, company=device.company,
        entity_type="Device", entity_id=device.pk, metadata={"device_id": device.device_id},
    )
    return device
