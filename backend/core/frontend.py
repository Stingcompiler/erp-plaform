"""Serves the Next.js static export (frontend/out) from Django in production.

Local dev keeps using `next dev` on :3000 against this API on :8000 via CORS
(see config/settings.py CORS_ALLOWED_ORIGINS) — this view is only wired into
urls.py when DEBUG is False, so the two workflows don't collide.
"""
import mimetypes
from pathlib import Path

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, Http404, HttpResponse
from django.utils._os import safe_join

from core.seo_inject import append_robots_extra, inject_seo

FRONTEND_DIST = settings.BASE_DIR.parent / "frontend" / "out"

# Not in every distribution's mime.types; without it the manifest would go
# out as application/octet-stream and the browser would refuse to install.
mimetypes.add_type("application/manifest+json", ".webmanifest")

# Next's static export hashes filenames under _next/static/, so those are
# safe to cache indefinitely; every other exported file is plain HTML/JSON
# that can change on each deploy.
IMMUTABLE_PREFIX = "_next/static/"


def _candidates(clean_path):
    """Files under the export that may answer `clean_path`, or an empty list
    when the path escapes the export directory.

    The catch-all URL hands us whatever the client sent, so ``../`` segments
    (raw or percent-encoded, decoded by the URL resolver) would otherwise walk
    out of ``frontend/out`` into the backend tree: the protected environment
    file, the SQLite database, MEDIA_ROOT. ``safe_join`` resolves the path and
    refuses anything not contained in the export; a refused path is a plain
    404, the same answer an unknown page gets."""
    if clean_path == "":
        return [FRONTEND_DIST / "index.html"]
    try:
        base = Path(safe_join(str(FRONTEND_DIST), clean_path))
    except (SuspiciousFileOperation, ValueError):
        return []
    return [base, base / "index.html", base.with_name(f"{base.name}.html")]


def _rewritten(candidate, clean):
    """The exported text with the platform team's SEO settings applied, or
    None when the file is not one they can touch (assets, JSON, images) or
    there is nothing to apply. HTML gets its <head> rewritten; robots.txt
    gets the extra lines. See website.seo / core.seo_inject."""
    if clean.startswith(IMMUTABLE_PREFIX):
        return None
    from website.seo import page_seo_for_url, site_seo

    if candidate.suffix == ".html":
        site, page = site_seo(), page_seo_for_url(clean)
        if site.empty and page.empty:
            return None
        return inject_seo(candidate.read_text(encoding="utf-8"), site, page)
    if clean == "robots.txt" and site_seo().robots_extra.strip():
        return append_robots_extra(candidate.read_text(encoding="utf-8"), site_seo().robots_extra)
    return None


def _serve_file(candidate, clean, status=200):
    content_type, _ = mimetypes.guess_type(str(candidate))
    rewritten = _rewritten(candidate, clean)
    if rewritten is not None:
        response = HttpResponse(
            rewritten.encode("utf-8"), content_type=content_type, status=status
        )
    else:
        response = FileResponse(
            open(candidate, "rb"), content_type=content_type, status=status
        )
    if clean.startswith(IMMUTABLE_PREFIX):
        # Content-hashed assets never change under a given name.
        response["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        # HTML (and other non-hashed exports) must revalidate every load, or a
        # browser will keep a stale page referencing chunk names from a previous
        # build after a redeploy. Without this, redeploys silently break clients.
        response["Cache-Control"] = "no-cache, must-revalidate"
    return response


def serve_frontend(request, path=""):
    clean = path.strip("/")
    for candidate in _candidates(clean):
        if candidate.is_file():
            # Count marketing page views (server-side, first-party; see
            # website/analytics.py). Only real HTML pages — assets and the
            # signed-in workspace shell are excluded there and here.
            if candidate.suffix == ".html" or candidate.name == "index.html":
                from website.analytics import marketing_kind_for, record

                classified = marketing_kind_for(clean)
                if classified:
                    record(request, clean, page_kind=classified[0], language=classified[1])
            return _serve_file(candidate, clean)

    not_found = FRONTEND_DIST / "404.html"
    if not_found.is_file():
        return _serve_file(not_found, "404.html", status=404)
    raise Http404
