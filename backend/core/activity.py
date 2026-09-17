from core.models import ActivityLog


def get_client_ip(request):
    """Client IP behind exactly one trusted proxy (Render, or the standalone
    reverse proxy). The proxy APPENDS the peer address to X-Forwarded-For, so
    the last entry is the one it saw; earlier entries are whatever the client
    chose to send and must not be trusted for audit or throttling."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if hops:
            return hops[-1]
    return request.META.get("REMOTE_ADDR")


def log_activity(
    *,
    action,
    user=None,
    company=None,
    entity_type="",
    entity_id="",
    request=None,
    metadata=None,
):
    """
    Write one audit row. Central so every milestone logs identically.

    company/user are resolved from the authenticated user when not passed
    explicitly, so callers usually only need `action`, `request`, and the
    entity being touched.
    """
    if user is None and request is not None:
        candidate = getattr(request, "user", None)
        if candidate is not None and candidate.is_authenticated:
            user = candidate

    if company is None and user is not None:
        company = getattr(user, "company", None)

    ip = get_client_ip(request) if request is not None else None

    return ActivityLog.objects.create(
        action=action,
        user=user,
        company=company,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id != "" else "",
        ip_address=ip,
        metadata=metadata or {},
    )
