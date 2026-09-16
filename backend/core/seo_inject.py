"""Rewrite the <head> of an exported page with what the platform team set.

The marketing site is a static export: its titles, descriptions and robots
tags are decided at build time. The team's overrides (website.SeoSettings,
website.SeoPageOverride) are applied here, while the page is served, so a
change is live without a deploy.

Everything in this module is a pure function of text plus plain values —
no models, no request — so it can be unit-tested on a string of HTML and
called from wherever a page is served (core.frontend for the export,
website.public_pages for the company pages). Only the first <head>…</head>
is touched; a page without a head is returned as it came.
"""
import html
import json
import re
from dataclasses import dataclass

# ISO code the export uses for its second edition; every other page is Arabic.
ENGLISH_PREFIX = "en"


@dataclass(frozen=True)
class SiteSeo:
    """Site-wide values (one row of website.SeoSettings)."""

    google_site_verification: str = ""
    bing_site_verification: str = ""
    analytics_id: str = ""
    default_og_image_url: str = ""
    robots_extra: str = ""

    @property
    def empty(self):
        return not any(
            (
                self.google_site_verification,
                self.bing_site_verification,
                self.analytics_id,
                self.default_og_image_url,
            )
        )


@dataclass(frozen=True)
class PageSeo:
    """Per-page values (one row of website.SeoPageOverride)."""

    title: str = ""
    description: str = ""
    noindex: bool = False
    canonical: str = ""

    @property
    def empty(self):
        return not (self.title or self.description or self.noindex or self.canonical)


_HEAD_END = re.compile(r"</head\s*>", re.IGNORECASE)
_TITLE = re.compile(r"<title(?:\s[^>]*)?>.*?</title\s*>", re.IGNORECASE | re.DOTALL)
_META = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_LINK = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
_ATTR = re.compile(r'([a-zA-Z:-]+)\s*=\s*"([^"]*)"')
# "G-ABC123", "UA-…", "GT-…": letters, digits and dashes only, so the value
# can never break out of the script it is written into.
ANALYTICS_ID = re.compile(r"^[A-Za-z0-9-]{1,32}$")


def _attrs(tag):
    return {name.lower(): value for name, value in _ATTR.findall(tag)}


def _find_tag(head, pattern, key, value):
    """The first <meta>/<link> in `head` whose `key` attribute equals `value`."""
    for match in pattern.finditer(head):
        if _attrs(match.group(0)).get(key) == value:
            return match
    return None


def _set_content(tag, attr, value):
    """Replace attr="…" in one tag; add it before the closing bracket if absent."""
    quoted = html.escape(value, quote=True)
    pattern = re.compile(rf'\b{attr}\s*=\s*"[^"]*"', re.IGNORECASE)
    if pattern.search(tag):
        return pattern.sub(f'{attr}="{quoted}"', tag, count=1)
    close = "/>" if tag.rstrip().endswith("/>") else ">"
    return tag[: -len(close)].rstrip() + f' {attr}="{quoted}"{close}'


def _upsert(head, pattern, key, value, attr, content, *, create):
    """Set `attr` on the tag identified by key=value, or append `create`."""
    match = _find_tag(head, pattern, key, value)
    if match is None:
        return head + create
    return head[: match.start()] + _set_content(match.group(0), attr, content) + head[match.end():]


def _upsert_meta(head, key, value, content):
    quoted = html.escape(content, quote=True)
    return _upsert(
        head, _META, key, value, "content", content,
        create=f'<meta {key}="{value}" content="{quoted}"/>',
    )


def _set_title(head, title):
    quoted = html.escape(title, quote=False)
    if _TITLE.search(head):
        return _TITLE.sub(lambda _: f"<title>{quoted}</title>", head, count=1)
    return head + f"<title>{quoted}</title>"


def analytics_snippet(analytics_id):
    """The GA4 tag for a measurement id; empty for anything malformed."""
    if not ANALYTICS_ID.match(analytics_id or ""):
        return ""
    ident = json.dumps(analytics_id)
    return (
        f'<script async src="https://www.googletagmanager.com/gtag/js?id={analytics_id}"></script>'
        "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}"
        f"gtag('js',new Date());gtag('config',{ident});</script>"
    )


def inject_seo(document, site=None, page=None):
    """Apply `site` and `page` to the first <head> of `document`.

    Site-wide: verification metas and the analytics tag are added (or their
    content replaced when the page already carries one); the default share
    image is added only when the page has no og:image of its own.

    Per page: a non-blank title replaces <title>, og:title and twitter:title;
    a non-blank description replaces the description, og:description and
    twitter:description metas; noindex sets robots to "noindex, nofollow";
    a canonical replaces the canonical link and og:url. Blank values leave
    the page's own tags untouched, so a document with nothing to apply comes
    back byte-for-byte.
    """
    site = site or SiteSeo()
    page = page or PageSeo()
    if site.empty and page.empty:
        return document
    end = _HEAD_END.search(document)
    if end is None:
        return document
    head, rest = document[: end.start()], document[end.start():]

    if page.title:
        head = _set_title(head, page.title)
        head = _upsert_meta(head, "property", "og:title", page.title)
        head = _upsert_meta(head, "name", "twitter:title", page.title)
    if page.description:
        head = _upsert_meta(head, "name", "description", page.description)
        head = _upsert_meta(head, "property", "og:description", page.description)
        head = _upsert_meta(head, "name", "twitter:description", page.description)
    if page.noindex:
        head = _upsert_meta(head, "name", "robots", "noindex, nofollow")
    if page.canonical:
        quoted = html.escape(page.canonical, quote=True)
        head = _upsert(
            head, _LINK, "rel", "canonical", "href", page.canonical,
            create=f'<link rel="canonical" href="{quoted}"/>',
        )
        head = _upsert_meta(head, "property", "og:url", page.canonical)

    if site.google_site_verification:
        head = _upsert_meta(head, "name", "google-site-verification", site.google_site_verification)
    if site.bing_site_verification:
        head = _upsert_meta(head, "name", "msvalidate.01", site.bing_site_verification)
    if site.default_og_image_url and _find_tag(head, _META, "property", "og:image") is None:
        head = _upsert_meta(head, "property", "og:image", site.default_og_image_url)
        if _find_tag(head, _META, "name", "twitter:image") is None:
            head = _upsert_meta(head, "name", "twitter:image", site.default_og_image_url)
    snippet = analytics_snippet(site.analytics_id)
    if snippet and "googletagmanager.com/gtag/js" not in head:
        head = head + snippet
    return head + rest


def append_robots_extra(text, extra):
    """robots.txt with the team's extra lines after the exported ones."""
    extra = (extra or "").strip()
    if not extra:
        return text
    return text.rstrip("\n") + "\n\n" + extra + "\n"


def public_path_and_language(url_path):
    """('/pricing', 'en') for '/en/pricing/', ('/', 'ar') for '/': the key a
    page override is stored under, and the language edition being served."""
    clean = "/" + (url_path or "").strip("/")
    if clean.endswith("/index.html"):
        clean = clean[: -len("/index.html")] or "/"
    elif clean.endswith(".html"):
        clean = clean[: -len(".html")]
    language = "ar"
    if clean == f"/{ENGLISH_PREFIX}" or clean.startswith(f"/{ENGLISH_PREFIX}/"):
        language = "en"
        clean = clean[len(ENGLISH_PREFIX) + 1:] or "/"
    if len(clean) > 1:
        clean = clean.rstrip("/") or "/"
    return clean, language
