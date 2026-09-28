"""A company's brand colour, made readable.

The public company page used the owner's chosen colour as-is for links,
prices and icons. A dark navy brand on the dark theme's surface measured
1.1:1 (unreadable); a pale yellow one on white failed too. These filters
keep the hue and move it toward black (light theme) or white (dark theme)
just far enough for WCAG AA text contrast (4.5:1) against every background
it sits on, the way CSS color-mix(in srgb, ...) would mix it.
"""

import re

from django import template

register = template.Library()

HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
AA_TEXT = 4.5


def _rgb(value):
    value = str(value or "").strip()
    if not HEX.match(value):
        return None
    digits = value[1:]
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb):
    return "#" + "".join(f"{round(max(0, min(255, c))):02x}" for c in rgb)


def _luminance(rgb):
    def channel(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _mix(rgb, toward, share):
    """color-mix(in srgb, rgb (1-share), toward share)."""
    return tuple(c + (t - c) * share for c, t in zip(rgb, toward))


def readable(colour, backgrounds, minimum=AA_TEXT):
    """`colour` moved toward black or white (whichever the backgrounds call
    for) until it reaches `minimum` contrast against each background."""
    rgb = _rgb(colour)
    grounds = [g for g in (_rgb(b) for b in backgrounds) if g]
    if rgb is None or not grounds:
        return colour
    dark_ground = sum(_luminance(g) for g in grounds) / len(grounds) < 0.2
    toward = (255, 255, 255) if dark_ground else (0, 0, 0)
    for step in range(0, 101, 2):
        mixed = _mix(rgb, toward, step / 100)
        if all(contrast(mixed, g) >= minimum for g in grounds):
            return _hex(mixed)
    return _hex(toward)


@register.filter
def readable_on(colour, backgrounds):
    """{{ colour|readable_on:"#ffffff,#f6f8f7" }} — text-safe brand colour."""
    return readable(colour, str(backgrounds).split(","))


@register.filter
def text_on(colour):
    """White or ink, whichever reads better ON the brand colour (buttons)."""
    rgb = _rgb(colour)
    if rgb is None:
        return "#ffffff"
    white, ink = (255, 255, 255), (20, 32, 44)
    return "#ffffff" if contrast(rgb, white) >= contrast(rgb, ink) else "#14202c"
