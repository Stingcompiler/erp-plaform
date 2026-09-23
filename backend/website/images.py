"""Image handling for the public site: validate, shrink, store as WebP.

A merchant uploads whatever their phone produced — a 6 MB JPEG, a PNG with
an alpha channel, a sideways photo with an EXIF rotation. The page must not
serve that as-is. Every upload goes through `prepare_image`, which proves it
is an image, applies the rotation, bounds the longest side, strips metadata
and re-encodes as WebP. The stored file is therefore always small, upright
and free of anything the merchant did not mean to publish.
"""
import io
import uuid

from django.core.files.base import ContentFile
from django.utils.translation import gettext as _
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import ValidationError

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

# Longest side per purpose. A cover fills the top of the page; a logo is a
# small square; a product or gallery photo sits in a card.
COVER_SIDE = 1800
LOGO_SIDE = 512
PHOTO_SIDE = 1200
WEBP_QUALITY = 82


def prepare_image(uploaded, max_side, *, square=False):
    """Return a ContentFile (WebP) ready for an ImageField, or raise a
    ValidationError the API can show to the merchant."""
    if uploaded is None:
        raise ValidationError({"image": _("Choose an image file.")})
    if uploaded.size > MAX_UPLOAD_BYTES:
        raise ValidationError({"image": _("The image is larger than 8 MB.")})
    try:
        image = Image.open(uploaded)
        image_format = image.format
        image.load()
    except (UnidentifiedImageError, OSError):
        raise ValidationError({"image": _("This file is not a JPEG, PNG or WebP image.")})
    if image_format not in ALLOWED_FORMATS:
        raise ValidationError({"image": _("Use a JPEG, PNG or WebP image.")})

    # Honour the phone's rotation flag, then drop it with the rest of the EXIF.
    image = ImageOps.exif_transpose(image)
    if square:
        image = ImageOps.fit(image, (max_side, max_side))
    else:
        image.thumbnail((max_side, max_side))
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")

    out = io.BytesIO()
    image.save(out, format="WEBP", quality=WEBP_QUALITY, method=4)
    return ContentFile(out.getvalue(), name=f"{uuid.uuid4().hex}.webp")


def replace_image(instance, field_name, content):
    """Store `content` on `instance.<field_name>`, deleting the previous file."""
    old = getattr(instance, field_name)
    if old:
        old.delete(save=False)
    setattr(instance, field_name, content)
    instance.save(update_fields=[field_name])


def clear_image(instance, field_name):
    old = getattr(instance, field_name)
    if old:
        old.delete(save=False)
        setattr(instance, field_name, None)
        instance.save(update_fields=[field_name])
