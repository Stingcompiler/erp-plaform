"""Content-Security-Policy for the HTML this server sends: the Next.js
static export (the app and the marketing site), the company pages under
/s/, and the few Django-rendered pages.

Two headers:

- ``Content-Security-Policy`` (enforced) is a baseline nothing in the
  product needs to break: scripts, styles, fonts, frames and connections
  only from this origin (plus Google Fonts for the /s/ pages), no plugins,
  no <base> hijack, forms post only here, and framing only as
  X-Frame-Options already allows. Inline scripts stay allowed in it because
  the static export inlines its bootstrap (``self.__next_f.push``), which
  changes with every build.
- ``Content-Security-Policy-Report-Only`` is the strict version: inline
  scripts only by the SHA-256 of the exact ones in this response. The
  browser console lists anything it would block, so the strict policy can
  be switched to enforced once a release shows no reports.

JSON-LD (``<script type="application/ld+json">``) is data, not script, and
needs no allowance. Styles keep 'unsafe-inline' (React style attributes and
the pages' own <style> blocks).
"""

import base64
import hashlib
import re

from django.conf import settings

_SCRIPT = re.compile(rb"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script\s*>", re.I | re.S)
_TYPE = re.compile(rb"""\btype\s*=\s*["']?([^"'\s>]+)""", re.I)
_SRC = re.compile(rb"\bsrc\s*=", re.I)
_JS_TYPES = {b"", b"text/javascript", b"application/javascript", b"module"}


def _inline_script_hashes(body):
    hashes = []
    for match in _SCRIPT.finditer(body):
        attrs = match.group("attrs")
        if _SRC.search(attrs):
            continue
        kind = _TYPE.search(attrs)
        if kind and kind.group(1).lower() not in _JS_TYPES:
            continue  # JSON-LD and other data blocks never run
        digest = hashlib.sha256(match.group("body")).digest()
        token = f"'sha256-{base64.b64encode(digest).decode()}'"
        if token not in hashes:
            hashes.append(token)
    return hashes


def _policy(scripts, frame_ancestors):
    directives = [
        "default-src 'self'",
        f"script-src {scripts}",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com data:",
        # Product photos and logos may live on the public media bucket.
        "img-src 'self' data: blob: https:",
        "connect-src 'self'",
        "media-src 'self' blob:",
        "worker-src 'self'",
        "manifest-src 'self'",
        # The website editor previews the company page in a same-origin frame.
        "frame-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        f"frame-ancestors {frame_ancestors}",
    ]
    return "; ".join(directives)


class ContentSecurityPolicyMiddleware:
    """Adds both headers to HTML responses. Placed right after
    SecurityMiddleware, so it sees X-Frame-Options as the clickjacking
    middleware (or a view, like the website preview) left it."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not getattr(settings, "CSP_ENABLED", True):
            return response
        content_type = response.get("Content-Type", "")
        if not content_type.startswith("text/html"):
            return response
        frame = response.get("X-Frame-Options", "").upper()
        ancestors = "'self'" if frame == "SAMEORIGIN" else "'none'"
        response["Content-Security-Policy"] = _policy("'self' 'unsafe-inline'", ancestors)
        if not getattr(response, "streaming", False):
            hashes = _inline_script_hashes(response.content)
            response["Content-Security-Policy-Report-Only"] = _policy(
                " ".join(["'self'", *hashes]), ancestors
            )
        return response
