"""What the SEO control page saved, as plain values for the injectors.

Every served page asks for this, so the rows are read once and kept in the
shared cache for a minute (core.seo_inject does the rewriting; this module
only fetches). Saving a setting or an override clears the entry, so the
team sees its change on the next request and everyone else within a
minute. A missing table (an instance served before its migration ran) is
treated as "nothing set" rather than a broken site.
"""
import logging

from django.core.cache import cache
from django.db import DatabaseError

from core.public_media import public_media_url
from core.seo_inject import PageSeo, SiteSeo, public_path_and_language

log = logging.getLogger(__name__)

CACHE_KEY = "seo:state"
CACHE_SECONDS = 60


def invalidate_seo_cache():
    cache.delete(CACHE_KEY)


def _load():
    from website.models import SeoPageOverride, SeoSettings

    settings_row = SeoSettings.objects.filter(pk=SeoSettings.SINGLETON_PK).first()
    site = SiteSeo()
    if settings_row is not None:
        site = SiteSeo(
            google_site_verification=settings_row.google_site_verification.strip(),
            bing_site_verification=settings_row.bing_site_verification.strip(),
            analytics_id=settings_row.analytics_id.strip(),
            default_og_image_url=public_media_url(
                settings_row.default_og_image.name if settings_row.default_og_image else ""
            ),
            robots_extra=settings_row.robots_extra,
            support_whatsapp=settings_row.support_whatsapp.strip(),
            support_phone=settings_row.support_phone.strip(),
            support_email=settings_row.support_email.strip(),
        )
    pages = {
        (row.path, row.language): PageSeo(
            title=row.title.strip(),
            description=row.description.strip(),
            noindex=row.noindex,
            canonical=row.canonical.strip(),
        )
        for row in SeoPageOverride.objects.all()
    }
    return {"site": site, "pages": pages}


def seo_state():
    state = cache.get(CACHE_KEY)
    if state is None:
        try:
            state = _load()
        except DatabaseError:
            log.warning("SEO settings unavailable; serving pages untouched", exc_info=True)
            return {"site": SiteSeo(), "pages": {}}
        cache.set(CACHE_KEY, state, CACHE_SECONDS)
    return state


def site_seo():
    return seo_state()["site"]


def page_seo(path, language):
    """The override for one public path in one language edition: an exact
    language row wins over a "both" row; none means the page's own tags."""
    pages = seo_state()["pages"]
    return pages.get((path, language)) or pages.get((path, "both")) or PageSeo()


def page_seo_for_url(url_path):
    return page_seo(*public_path_and_language(url_path))
