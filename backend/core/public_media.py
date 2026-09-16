"""Serve the `public/` subtree of MEDIA_ROOT to anonymous visitors.

Uploads are never served through MEDIA_URL: medical reports and payment
proofs go through company-scoped viewset actions. The images a merchant
puts on their public page are the one exception — they are meant for every
visitor and for search engines — so they are stored under
MEDIA_ROOT/public/ and only that prefix is reachable here. Anything else
under MEDIA_ROOT stays exactly as protected as before.

Files are named by a random hex (website.images), so a URL cannot be
guessed and a replaced image gets a new URL; long caching is safe.
"""
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from django.utils._os import safe_join
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

PUBLIC_PREFIX = "public"
CONTENT_TYPES = {
    ".webp": "image/webp",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


def public_media_url(name):
    """Site-relative URL of a stored file name such as 'public/sites/3/abc.webp'.
    Relative so the app and the page work on every host (and in development);
    the public page makes it absolute where a crawler needs that."""
    if not name:
        return ""
    return f"/media/{name}"


@require_GET
@cache_control(public=True, max_age=60 * 60 * 24 * 365, immutable=True)
def serve_public_media(request, path):
    root = Path(settings.MEDIA_ROOT) / PUBLIC_PREFIX
    try:
        full = Path(safe_join(str(root), path))
    except ValueError:
        raise Http404
    content_type = CONTENT_TYPES.get(full.suffix.lower())
    if content_type is None or not full.is_file():
        raise Http404
    return FileResponse(open(full, "rb"), content_type=content_type)
