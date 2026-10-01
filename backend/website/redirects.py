"""Redirects the platform team manages from /platform-seo (phase C).

A redirect sends one old public address to a new one: an exact path of the
marketing export (either language edition, e.g. /en/old/) or of a company
page (/s/<slug>/…). It never touches the API, the admin, assets or the
signed-in app — those are refused when a redirect is saved *and* skipped
when a request is served, so a bad row cannot lock anyone out.

- `normalize_source` / `request_key`: the one form a path is stored and
  looked up in (leading slash, no trailing slash, lowercase, no host, no
  query).
- `check_redirect`: every rule, as {field: message}; the API, the CSV import
  and the "test a URL" box share it.
- `redirect_response`: what core.frontend and website.public_pages ask
  before serving; the active redirects come from the shared SEO state
  (website.seo, cached for a minute, cleared on save/delete).
"""
import logging
from urllib.parse import unquote, urlsplit, urlunsplit

from django.conf import settings
from django.db import DatabaseError, connection, transaction
from django.db.models import F
from django.http import HttpResponsePermanentRedirect, HttpResponseRedirect
from django.utils import timezone
from django.utils.translation import gettext as _

log = logging.getLogger(__name__)

STATUS_CODES = (301, 302)
# A permanent redirect may be kept by browsers and proxies a little while; a
# temporary one never, so switching it off is seen at once.
PERMANENT_MAX_AGE = 300
SOURCE_MAX_LENGTH = 255
TARGET_MAX_LENGTH = 500
ENGLISH_PREFIX = "/en"

# Never redirected, whatever is saved: the API, the admin, static and
# hashed assets, the files crawlers and the PWA fetch by name, the directory
# of company pages itself, and the two home pages. The signed-in app's
# routes are added from the export's robots.txt (its Disallow lines, which
# the frontend writes from lib/site.js PRIVATE_PATH_PREFIXES) on top of the
# copy below, so a route is protected even before the export is rebuilt.
PROTECTED_PREFIXES = (
    "/api", "/admin", "/_next", "/static", "/media", "/icons", "/email",
    # Every platform console page: /platform/, /platform-seo/, …
    "/platform",
    "/login", "/activate-owner", "/forgot-password", "/reset-password",
    "/dashboard", "/sales", "/inventory", "/purchasing", "/returns", "/reports",
    "/finance", "/debts", "/crm", "/hr", "/labels", "/logs", "/org", "/users",
    "/settings", "/subscription", "/website", "/customer-records", "/web-orders",
    "/supplier-records",
)
PROTECTED_EXACT = frozenset({
    "/", ENGLISH_PREFIX, "/s", "/404",
    "/sw.js", "/manifest.webmanifest", "/robots.txt", "/sitemap.xml", "/sitemap-sites.xml",
    "/favicon.ico", "/index.txt",
})
# "/platform" protects "/platform-seo" too (a dash continues the name); every
# other prefix protects itself and what is under it.
_DASH_PREFIXES = ("/platform",)
_UNSAFE = set(" <>\"'`\\") | {chr(code) for code in range(32)} | {"\x7f"}


class RedirectPathError(ValueError):
    """A path that cannot be a redirect source; the message says why."""


def public_hosts():
    return {host.lower() for host in settings.VEZANO_PUBLIC_HOSTS}


def _collapse(path):
    """Leading slash, single slashes, no trailing slash except the root,
    lowercase. The form every source is stored and looked up in."""
    parts = [part for part in path.split("/") if part]
    return ("/" + "/".join(parts)).lower()


def request_key(path):
    """The lookup key of a request path (already decoded by Django)."""
    return _collapse(path or "/")


def normalize_source(value):
    """The stored form of a source as the team types it. Accepts a full URL
    on one of the site's own hosts (pasted from the address bar) and keeps
    only its path; refuses another host, a query or a fragment.

    Raises RedirectPathError."""
    raw = (value or "").strip()
    if not raw:
        raise RedirectPathError(_("Enter the old path, such as /old-page or /en/old-page."))
    if "://" in raw or raw.startswith("//"):
        parts = urlsplit(raw if "://" in raw else "https:" + raw)
        if (parts.hostname or "").lower() not in public_hosts():
            raise RedirectPathError(
                _("The old address must be on this site; enter only its path.")
            )
        if parts.query or parts.fragment:
            raise RedirectPathError(_("The old path cannot carry a query (?) or a fragment (#)."))
        raw = parts.path or "/"
    if "?" in raw or "#" in raw:
        raise RedirectPathError(_("The old path cannot carry a query (?) or a fragment (#)."))
    raw = unquote(raw)
    if any(ch in _UNSAFE for ch in raw):
        raise RedirectPathError(_("The path contains characters a URL cannot carry."))
    path = _collapse(raw)
    if len(path) > SOURCE_MAX_LENGTH:
        raise RedirectPathError(_("The path is too long."))
    return path


def _strip_language(key):
    if key == ENGLISH_PREFIX or key.startswith(ENGLISH_PREFIX + "/"):
        return key[len(ENGLISH_PREFIX):] or "/"
    return key


def _covered(key, prefix):
    prefix = prefix.rstrip("/") or "/"
    if key == prefix or key.startswith(prefix + "/"):
        return True
    return prefix in _DASH_PREFIXES and key.startswith(prefix + "-")


def protected_prefixes():
    """The built-in prefixes plus the export's robots.txt Disallow lines."""
    from core.frontend import FRONTEND_DIST
    from website.seo_health import robots_disallows

    found = list(PROTECTED_PREFIXES)
    try:
        text = (FRONTEND_DIST / "robots.txt").read_text(encoding="utf-8")
    except OSError:
        text = ""
    for prefix in robots_disallows(text):
        prefix = _collapse(prefix.split("*", 1)[0].split("$", 1)[0])
        if prefix != "/" and prefix not in found:
            found.append(prefix)
    return tuple(found)


def is_protected(key, prefixes=None):
    """Whether the lookup key `key` may never be redirected (in either
    language edition)."""
    prefixes = PROTECTED_PREFIXES if prefixes is None else prefixes
    for candidate in {key, _strip_language(key)}:
        if candidate in PROTECTED_EXACT:
            return True
        if any(_covered(candidate, prefix) for prefix in prefixes):
            return True
    return False


def target_key(target, *, allow_external=False):
    """(lookup key of the page a target lands on, or None for another
    site; error message or "")."""
    target = (target or "").strip()
    if not target:
        return None, _("Enter where the old path should go.")
    if len(target) > TARGET_MAX_LENGTH:
        return None, _("The new address is too long.")
    if any(ch in _UNSAFE for ch in target):
        return None, _("The new address contains characters a URL cannot carry.")
    if target.startswith("/"):
        if target.startswith("//"):
            return None, _("Start an address on this site with a single /.")
        return request_key(unquote(urlsplit(target).path)), ""
    parts = urlsplit(target)
    if parts.scheme.lower() != "https" or not parts.hostname:
        return None, _("Use a path starting with / or a full https:// address.")
    if parts.username or parts.password:
        return None, _("The new address cannot carry a user name or password.")
    if parts.hostname.lower() in public_hosts():
        return request_key(unquote(parts.path)), ""
    if not allow_external:
        return None, _(
            "This address is on another site. Tick “allow another site” if that is intended."
        )
    return None, ""


def active_pairs(exclude_pk=None):
    """(source, target key) of every active redirect but `exclude_pk`."""
    from website.models import SeoRedirect

    rows = SeoRedirect.objects.filter(is_active=True)
    if exclude_pk is not None:
        rows = rows.exclude(pk=exclude_pk)
    return [
        (row.source_path, target_key(row.target, allow_external=True)[0])
        for row in rows.only("source_path", "target")
    ]


def check_redirect(source, target, *, allow_external=False, status_code=301, is_active=True,
                   others=(), prefixes=None, app_page=None):
    """Every rule a redirect must pass, as {field: message} (empty when it
    is fine). `source` is already normalised; `others` are the (source,
    target key) pairs of the other active redirects; `app_page(key)` says
    whether the export serves that path as a signed-in app page."""
    errors = {}
    if is_protected(source, prefixes):
        errors["source_path"] = _(
            "This path belongs to the app, the API or the site's files and cannot be redirected."
        )
    elif app_page is not None and app_page(source):
        errors["source_path"] = _(
            "This path is a page of the signed-in app and cannot be redirected."
        )
    if status_code not in STATUS_CODES:
        errors["status_code"] = _("Use 301 (permanent) or 302 (temporary).")
    landing, problem = target_key(target, allow_external=allow_external)
    if problem:
        errors["target"] = problem
    elif landing == source:
        errors["target"] = _("The new address is the old path itself.")
    elif is_active:
        sources = {pair[0] for pair in others}
        targets = {pair[1] for pair in others if pair[1]}
        if landing is not None and landing in sources:
            errors["target"] = _(
                "The new address is itself redirected; point straight to its final page."
            )
        if "source_path" not in errors and source in targets:
            errors["source_path"] = _(
                "Another redirect lands on this path; redirecting it too would make a chain."
            )
    return errors


def with_query(target, query):
    """`target` with the request's query string kept (after any query the
    target already has, before its fragment)."""
    if not query:
        return target
    parts = urlsplit(target)
    joined = f"{parts.query}&{query}" if parts.query else query
    return urlunsplit((parts.scheme, parts.netloc, parts.path, joined, parts.fragment))


def build_response(target, status_code, query=""):
    location = with_query(target, query)
    if status_code == 301:
        response = HttpResponsePermanentRedirect(location)
        response["Cache-Control"] = f"public, max-age={PERMANENT_MAX_AGE}"
    else:
        response = HttpResponseRedirect(location)
        response["Cache-Control"] = "no-store"
    return response


def record_hit(pk):
    """One more hit, in a single UPDATE; never fails the response."""
    from website.models import SeoRedirect

    try:
        update = SeoRedirect.objects.filter(pk=pk)
        values = {"hits": F("hits") + 1, "last_hit_at": timezone.now()}
        if connection.in_atomic_block:
            with transaction.atomic():
                update.update(**values)
        else:
            update.update(**values)
    except DatabaseError:
        log.warning("Could not count a hit on redirect %s", pk, exc_info=True)


def lookup(key):
    """The active redirect for a lookup key, from the cached state, or None.
    A protected key never has one, whatever is stored."""
    from website.seo import seo_state

    if is_protected(key):  # assets and the API never even read the cache
        return None
    state = seo_state()
    if is_protected(key, state.get("redirect_guard") or PROTECTED_PREFIXES):
        return None
    return (state.get("redirects") or {}).get(key)


def redirect_response(request):
    """The redirect answering this request, or None to serve it as usual.
    Only GET and HEAD are redirected; a form post keeps its page."""
    if request.method not in ("GET", "HEAD"):
        return None
    found = lookup(request_key(request.path))
    if found is None:
        return None
    response = build_response(
        found["target"], found["status_code"], request.META.get("QUERY_STRING", "")
    )
    record_hit(found["id"])
    return response


def follow_redirects(view):
    """Decorator for the /s/ views: answer from the redirect map first. It
    wraps the cache_control decorators, so a 302 keeps its no-store."""
    from functools import wraps

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        response = redirect_response(request)
        if response is not None:
            return response
        return view(request, *args, **kwargs)

    return wrapper


def describe(path_or_url):
    """What a request for `path_or_url` would get right now — the "test a
    URL" box. Reads the database, not the cache, so a just-saved redirect
    shows at once."""
    from website.models import SeoRedirect

    raw = (path_or_url or "").strip()
    query = ""
    if "?" in raw:
        raw, _sep, query = raw.partition("?")
        query = query.split("#", 1)[0]
    raw = raw.split("#", 1)[0]
    try:
        key = normalize_source(raw)
    except RedirectPathError as error:
        return {"input": path_or_url, "outcome": "invalid", "message": str(error)}
    result = {
        "input": path_or_url, "path": key, "query": query, "outcome": "none",
        "redirect": None, "location": None, "status_code": None,
    }
    if is_protected(key, protected_prefixes()):
        result["outcome"] = "protected"
        return result
    row = SeoRedirect.objects.filter(source_path=key).first()
    if row is None:
        return result
    result["redirect"] = {
        "id": row.pk, "source_path": row.source_path, "target": row.target,
        "status_code": row.status_code, "is_active": row.is_active,
    }
    if not row.is_active:
        result["outcome"] = "inactive"
        return result
    result.update(
        outcome="redirect", status_code=row.status_code,
        location=with_query(row.target, query),
    )
    return result


def load_map():
    """{source: {id, target, status_code}} of the active redirects, for the
    shared SEO state. A missing table (code deployed before its migration)
    is an empty map, inside a savepoint so the request's transaction lives."""
    from website.models import SeoRedirect

    try:
        with transaction.atomic():
            return {
                row.source_path: {
                    "id": row.pk, "target": row.target, "status_code": row.status_code,
                }
                for row in SeoRedirect.objects.filter(is_active=True).only(
                    "source_path", "target", "status_code"
                )
            }
    except DatabaseError:
        log.warning("Redirects unavailable; serving pages without them", exc_info=True)
        return {}
