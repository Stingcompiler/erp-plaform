"""Server-side, first-party visit recording for the public faces of the
platform: the marketing pages the export serves and the /s/<slug>/ pages.

Why not a client script: ad-blockers hide a third of visitors from any
injected tag, a tag means a consent banner, and every page here is already
served by this process — so the server records the view itself. No cookies
are set and no PII is stored: the visitor hash is sha256 over (day, secret
key, client IP, user agent), which collapses one visitor's views within a
day and is unlinkable across days once the day changes.

Recording is deliberately allowed to fail: a page must never be slowed or
broken by its own measurement, so `record` swallows everything.
"""

import hashlib
import logging
from urllib.parse import urlsplit

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# Top-level path segments of the export that are marketing surface. The rest
# of the export is the signed-in workspace shell (or auth flows), which is
# nobody's business to count.
MARKETING_PREFIXES = frozenset(
    {"", "pricing", "product", "register", "solutions", "guides", "compare"}
)

# Substrings that mark a crawler UA. Kept deliberately broad: bot traffic is
# stored (so the SEO page can show crawl activity) but never counted as human.
BOT_MARKERS = (
    "bot", "crawl", "spider", "slurp", "preview", "fetch", "monitor",
    "curl", "wget", "python", "headless", "lighthouse", "scan",
)

# Hosts whose referrals are internal navigation, not an acquisition source.
_OWN_HOSTS = {"vezano.app", "www.vezano.app", "enterprise.vezano.app", "localhost", "127.0.0.1"}


def marketing_kind_for(clean_path):
    """('marketing', language) for a marketing export path, else None.

    `clean_path` is the export path with no leading/trailing slash, e.g.
    "" (landing), "en/pricing", "guides/collect-customer-debts".
    """
    segments = clean_path.split("/")
    language = "ar"
    if segments[0] == "en":
        language = "en"
        segments = segments[1:] or [""]
    if segments[0] in MARKETING_PREFIXES:
        return "marketing", language
    return None


def _visitor_hash(request, day):
    from core.activity import get_client_ip

    user_agent = request.META.get("HTTP_USER_AGENT", "")
    raw = f"{day}{settings.SECRET_KEY}{get_client_ip(request)}{user_agent}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _referrer_host(request):
    host = urlsplit(request.META.get("HTTP_REFERER", "")).netloc.lower()
    host = host.split(":")[0].removeprefix("www.")
    if not host or host in _OWN_HOSTS or f"www.{host}" in _OWN_HOSTS:
        return ""
    return host[:100]


def _is_bot(user_agent):
    lowered = user_agent.lower()
    return not lowered or any(marker in lowered for marker in BOT_MARKERS)


def record(request, path, *, page_kind, company_id=None, language=""):
    """Record one public page view; never raises, never slows the page much.

    Signed-in people (the auth cookie is present) are staff or customers
    using the product, not visitors, and are not recorded.
    """
    try:
        if request.method != "GET":
            return
        if settings.SIMPLE_JWT["AUTH_COOKIE"] in request.COOKIES:
            return
        from website.models import PageVisit

        user_agent = request.META.get("HTTP_USER_AGENT", "")
        PageVisit.objects.create(
            path=("/" + path.strip("/"))[:200] if path.strip("/") else "/",
            page_kind=page_kind,
            company_id=company_id,
            referrer_host=_referrer_host(request),
            device="phone" if "Mobi" in user_agent else "desktop",
            language=language[:8],
            visitor_hash=_visitor_hash(request, timezone.localdate()),
            is_bot=_is_bot(user_agent),
        )
    except Exception:  # noqa: BLE001 - measurement must never break the page
        logger.exception("Could not record page visit for %r", path)


def rollup(today=None):
    """Fold every finished day still in PageVisit into DailyPageStat, then
    prune hot rows older than seven days. Idempotent: a re-run recomputes
    the same days from the same rows and overwrites the same stat rows.
    """
    from django.db.models import Count

    from website.models import DailyPageStat, PageVisit

    today = today or timezone.localdate()
    days = list(
        PageVisit.objects.filter(created_at__date__lt=today)
        .dates("created_at", "day")
    )
    written = 0
    for day in days:
        day_rows = PageVisit.objects.filter(created_at__date=day)
        by_page = {}
        for row in day_rows.values("path", "page_kind", "company_id").annotate(n=Count("id")):
            by_page[row["path"]] = {
                "page_kind": row["page_kind"],
                "company_id": row["company_id"],
            }
        for path, meta in by_page.items():
            humans = day_rows.filter(path=path, is_bot=False)
            counts = {"referrers": {}, "devices": {}, "languages": {}}
            for field, key in (
                ("referrer_host", "referrers"), ("device", "devices"), ("language", "languages"),
            ):
                for row in humans.values(field).annotate(n=Count("id")):
                    counts[key][row[field] or ""] = row["n"]
            DailyPageStat.objects.update_or_create(
                date=day,
                path=path,
                defaults={
                    "page_kind": meta["page_kind"],
                    "company_id": meta["company_id"],
                    "visits": humans.count(),
                    "visitors": humans.values("visitor_hash").distinct().count(),
                    "bot_visits": day_rows.filter(path=path, is_bot=True).count(),
                    **counts,
                },
            )
            written += 1
    cutoff = timezone.now() - timezone.timedelta(days=7)
    pruned = PageVisit.objects.filter(created_at__lt=cutoff).delete()[0]
    return {"days": [str(day) for day in days], "stats_written": written, "pruned": pruned}
