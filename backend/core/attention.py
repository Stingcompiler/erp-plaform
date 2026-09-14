"""Attention badges: what appeared for this user since they last looked.

A *source* is one thing that can need a person's attention (an invoice that
became overdue, a return waiting for disposition, a registration to review).
Each app registers its sources here; the registry never stores a count — it
asks the source how many items appeared after the user's last visit to that
part of the app. The only stored state is that last visit (`AttentionSeen`),
so the numbers can never drift from the real records.

A source is scoped exactly like the views that show its records: by company,
by the branch a branch-level role is confined to, and by the RBAC module the
role can read. The server decides what a person may be nudged about; the UI
only draws the number.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone
from django.utils.module_loading import autodiscover_modules

logger = logging.getLogger(__name__)

TONE_INFO = "info"        # something new waits for an ordinary action
TONE_WARN = "warn"        # money waits for an approval
TONE_DANGER = "danger"    # a risk that should not wait

# Before any visit is recorded, "since" reaches back this far so a fresh
# account is not greeted by every historical item at once.
FIRST_LOOK_WINDOW = timedelta(days=7)
CACHE_SECONDS = 30


@dataclass(frozen=True)
class Source:
    key: str
    module: str | None   # RBAC module the user must be able to read; None = platform team
    tone: str
    count_since: object  # callable(user, since) -> int


_REGISTRY: dict[str, Source] = {}
_discovered = False


def register(key, module, tone=TONE_INFO):
    """Decorator: `@register("returns", "sales_returns")` over a `(user, since) -> int`."""

    def wrap(fn):
        _REGISTRY[key] = Source(key=key, module=module, tone=tone, count_since=fn)
        return fn

    return wrap


def sources():
    global _discovered
    if not _discovered:
        # Each app keeps its sources in <app>/attention.py; importing them
        # registers them. Done lazily so app loading order never matters.
        autodiscover_modules("attention")
        _discovered = True
    return _REGISTRY


def visible_sources(user):
    from core.rbac import role_can

    platform = bool(getattr(user, "is_platform_admin", False))
    for source in sources().values():
        if source.module is None:
            if platform:
                yield source
        elif not platform and role_can(user, source.module, write=False):
            yield source


def branch_scope(user):
    """The branch a branch-level role is confined to, else None (no narrowing)."""
    role = getattr(user, "role", None)
    if not (role and getattr(role, "scope_level", None) == "branch"):
        return None
    return getattr(user, "branch_id", None)


def scope_branch(qs, user, field="branch"):
    branch_id = branch_scope(user)
    if branch_id is None:
        return qs
    return qs.filter(**{f"{field}_id": branch_id})


def _cache_key(user):
    return f"attention:{user.pk}"


def invalidate(user):
    cache.delete(_cache_key(user))


def seen_map(user):
    from core.models import AttentionSeen

    return dict(AttentionSeen.objects.filter(user=user).values_list("key", "seen_at"))


def counts_for(user, use_cache=True):
    """{key: count} for every source this user may see, plus tones and total."""
    key = _cache_key(user)
    if use_cache:
        cached = cache.get(key)
        if cached is not None:
            return cached
    now = timezone.now()
    seen = seen_map(user)
    counts, tones = {}, {}
    for source in visible_sources(user):
        since = seen.get(source.key) or (now - FIRST_LOOK_WINDOW)
        try:
            count = int(source.count_since(user, since) or 0)
        except Exception:  # noqa: BLE001 - one broken source must not blank the rest
            logger.exception("attention source %s failed for user %s", source.key, user.pk)
            count = 0
        if count:
            counts[source.key] = count
            tones[source.key] = source.tone
    payload = {
        "counts": counts,
        "tones": tones,
        "total": sum(counts.values()),
        "as_of": now.isoformat(),
    }
    if use_cache:
        cache.set(key, payload, CACHE_SECONDS)
    return payload


def mark_seen(user, key):
    """Record that the user looked at `key` now. Unknown keys are ignored
    silently (an older client may name a source that no longer exists)."""
    from core.models import AttentionSeen

    if key not in sources():
        return False
    AttentionSeen.objects.update_or_create(
        user=user, key=key, defaults={"seen_at": timezone.now()}
    )
    invalidate(user)
    return True
