"""Proof-of-payment uploads: trust the bytes, never the client's label.

A visitor or a company owner uploads a screenshot of a bank transfer. The
browser's ``content_type`` is whatever the client says it is; an SVG (or an
HTML file) labelled ``image/png`` used to pass and was then served inline
from the app's own origin (review F07). Both ends are fixed here: the
upload is identified by its magic bytes and renamed to match, and every
download goes out as an attachment with ``nosniff``.
"""
from django.http import FileResponse
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"%PDF-", "application/pdf", "pdf"),
)
HEADER = 16


def sniff(uploaded):
    """(mime, extension) from the first bytes, or (None, None)."""
    try:
        uploaded.seek(0)
        head = uploaded.read(HEADER)
    finally:
        try:
            uploaded.seek(0)
        except Exception:  # noqa: BLE001 - a non-seekable stream just starts over
            pass
    if not head:
        return None, None
    for magic, mime, ext in SIGNATURES:
        if head.startswith(magic):
            return mime, ext
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None, None


def validate_proof(uploaded, *, field="proof", max_bytes, allow_pdf=False):
    """Refuse anything that is not a real PNG/JPEG/WebP (or PDF when allowed)
    and rename the file to its true extension. Returns the sniffed mime."""
    if uploaded.size > max_bytes:
        raise ValidationError(
            {field: _("The file must be under %(mb)s MB.") % {"mb": max_bytes // (1024 * 1024)}}
        )
    mime, ext = sniff(uploaded)
    if mime is None or (mime == "application/pdf" and not allow_pdf):
        message = (
            _("Upload a PNG, JPEG or WebP image or a PDF; other files are not accepted.")
            if allow_pdf
            else _("Upload a PNG, JPEG or WebP image; other files are not accepted.")
        )
        raise ValidationError({field: message})
    stem = (uploaded.name or "proof").rsplit("/", 1)[-1].rsplit(".", 1)[0][:60] or "proof"
    uploaded.name = f"{stem}.{ext}"
    return mime


def proof_response(fieldfile):
    """Download a stored proof as an attachment, typed by its bytes."""
    handle = fieldfile.open("rb")
    mime, _ext = sniff(handle)
    response = FileResponse(
        handle, as_attachment=True, content_type=mime or "application/octet-stream",
        filename=fieldfile.name.rsplit("/", 1)[-1],
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response
