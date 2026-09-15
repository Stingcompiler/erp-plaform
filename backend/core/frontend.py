"""Serves the Next.js static export (frontend/out) from Django in production.

Local dev keeps using `next dev` on :3000 against this API on :8000 via CORS
(see config/settings.py CORS_ALLOWED_ORIGINS) — this view is only wired into
urls.py when DEBUG is False, so the two workflows don't collide.
"""
import mimetypes

from django.conf import settings
from django.http import FileResponse, Http404

FRONTEND_DIST = settings.BASE_DIR.parent / "frontend" / "out"

# Not in every distribution's mime.types; without it the manifest would go
# out as application/octet-stream and the browser would refuse to install.
mimetypes.add_type("application/manifest+json", ".webmanifest")

# Next's static export hashes filenames under _next/static/, so those are
# safe to cache indefinitely; every other exported file is plain HTML/JSON
# that can change on each deploy.
IMMUTABLE_PREFIX = "_next/static/"


def _candidates(clean_path):
    if clean_path == "":
        return [FRONTEND_DIST / "index.html"]
    base = FRONTEND_DIST / clean_path
    return [base, base / "index.html", FRONTEND_DIST / f"{clean_path}.html"]


def _serve_file(candidate, clean, status=200):
    content_type, _ = mimetypes.guess_type(str(candidate))
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
            return _serve_file(candidate, clean)

    not_found = FRONTEND_DIST / "404.html"
    if not_found.is_file():
        return _serve_file(not_found, "404.html", status=404)
    raise Http404
