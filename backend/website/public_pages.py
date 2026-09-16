"""The public, indexable face of a customer's website.

`/api/public/site/<slug>/` has served the site as JSON since the module was
built, which nothing outside the product could show or index. These views
render the same published data as plain HTML on the platform's own domain:

- /s/<slug>/         one company's page, with title/description, Open Graph,
                     canonical and JSON-LD (LocalBusiness + its featured
                     products), so a search for the shop's name finds it.
- /s/                a directory of every published site, so crawlers reach
                     each page by a link and not only through the sitemap.
- /sitemap-sites.xml every published site with its last update, referenced
                     from robots.txt next to the marketing sitemap.

Only what PublicSiteSerializer already exposes is used; nothing internal is
added. Everything is escaped by the template engine, the accent colour is
validated before it reaches a stylesheet, and the logo is only embedded
when it is an http(s) URL.
"""
import json
import re

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils.html import strip_tags
from django.utils.text import Truncator
from django.utils.xmlutils import SimplerXMLGenerator
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

from org.models import Company
from website.models import Website
from website.serializers import PublicSiteSerializer

HEX_COLOUR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
ARABIC = re.compile(r"[؀-ۿ]")
CACHE_SECONDS = 300


def site_url(path=""):
    return f"https://{settings.VEZANO_CANONICAL_HOST}{path}"


def public_site_path(slug):
    return f"/s/{slug}/"


def published_sites():
    return (
        Website.objects.filter(is_published=True, company__is_active=True)
        .select_related("company")
        .order_by("business_name", "company__name")
    )


def _display_name(site):
    return site.business_name or site.company.name


def _language(site, data):
    """Arabic when the merchant wrote Arabic; the page chrome follows."""
    sample = " ".join(
        [data["business_name"], data["tagline"], data["about_text"]]
        + [section["title"] for section in data["sections"]]
    )
    return "ar" if ARABIC.search(sample) else "en"


def _description(site, data):
    text = data["tagline"] or strip_tags(data["about_text"]) or _display_name(site)
    return Truncator(" ".join(text.split())).chars(160)


def _social_links(data):
    links = data.get("social_links") or {}
    if not isinstance(links, dict):
        return []
    return [
        (str(name), str(url))
        for name, url in links.items()
        if isinstance(url, str) and url.startswith(("http://", "https://"))
    ]


def _json_ld(site, data, url, language):
    company = site.company
    business = {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "@id": f"{url}#business",
        "name": _display_name(site),
        "description": _description(site, data),
        "url": url,
        "inLanguage": language,
    }
    if data["logo_url"].startswith(("http://", "https://")):
        business["logo"] = data["logo_url"]
        business["image"] = data["logo_url"]
    if data["contact_phone"]:
        business["telephone"] = data["contact_phone"]
    if data["contact_email"]:
        business["email"] = data["contact_email"]
    if data["address"]:
        business["address"] = {"@type": "PostalAddress", "streetAddress": data["address"]}
    same_as = [link for _, link in _social_links(data)]
    if same_as:
        business["sameAs"] = same_as
    blocks = [business]
    if data["featured_products"]:
        blocks.append(
            {
                "@context": "https://schema.org",
                "@type": "ItemList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": index + 1,
                        "item": {
                            "@type": "Product",
                            "name": product["name"],
                            "sku": product["sku"],
                            "description": product["caption"] or product["name"],
                            "offers": {
                                "@type": "Offer",
                                "price": str(product["price"]),
                                "priceCurrency": company.currency,
                                "availability": "https://schema.org/InStock",
                                "seller": {"@id": f"{url}#business"},
                            },
                        },
                    }
                    for index, product in enumerate(data["featured_products"])
                ],
            }
        )
    # "<" escaped so a value can never close the script tag early.
    return [json.dumps(block, ensure_ascii=False).replace("<", "\\u003c") for block in blocks]


def _sections_with_about(data):
    """The merchant's sections; the profile's about text becomes an "about"
    block right after the opening one when no such section exists."""
    sections = list(data["sections"])
    if data["about_text"] and not any(s["type"] == "about" for s in sections):
        block = {"type": "about", "title": "", "order": 0, "content": {"text": data["about_text"]}}
        position = 1 if sections and sections[0]["type"] == "hero" else 0
        sections.insert(position, block)
    return sections


def _site_or_404(slug):
    try:
        company = Company.objects.get(slug=slug, is_active=True)
    except Company.DoesNotExist:
        raise Http404
    site = getattr(company, "website", None)
    if site is None or not site.is_published:
        raise Http404
    return site


@require_GET
@cache_control(public=True, max_age=CACHE_SECONDS)
def public_site_page(request, slug):
    site = _site_or_404(slug)
    data = PublicSiteSerializer(site).data
    language = _language(site, data)
    url = site_url(public_site_path(slug))
    colour = data["primary_color"] if HEX_COLOUR.match(data["primary_color"] or "") else "#111827"
    whatsapp = re.sub(r"\D", "", data["contact_phone"] or "")
    context = {
        "site": site,
        "data": data,
        "name": _display_name(site),
        "description": _description(site, data),
        "language": language,
        "dir": "rtl" if language == "ar" else "ltr",
        "url": url,
        "colour": colour,
        "logo": data["logo_url"] if data["logo_url"].startswith(("http://", "https://")) else "",
        "social": _social_links(data),
        "whatsapp": whatsapp if len(whatsapp) >= 8 else "",
        "currency": site.company.currency,
        "json_ld": _json_ld(site, data, url, language),
        "sections": _sections_with_about(data),
        "products": data["featured_products"],
        "has_products_section": any(s["type"] == "products" for s in data["sections"]),
        "platform_url": site_url("/"),
        "directory_url": site_url("/s/"),
    }
    return render(request, "website/public_site.html", context)


@require_GET
@cache_control(public=True, max_age=CACHE_SECONDS)
def public_site_directory(request):
    sites = [
        {
            "name": _display_name(site),
            "tagline": site.tagline,
            "path": public_site_path(site.company.slug),
        }
        for site in published_sites()
    ]
    return render(
        request,
        "website/public_directory.html",
        {"sites": sites, "url": site_url("/s/"), "platform_url": site_url("/")},
    )


@require_GET
@cache_control(public=True, max_age=CACHE_SECONDS)
def public_sites_sitemap(request):
    response = HttpResponse(content_type="application/xml; charset=utf-8")
    xml = SimplerXMLGenerator(response, "utf-8")
    xml.startDocument()
    xml.startElement("urlset", {"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"})
    xml.startElement("url", {})
    xml.addQuickElement("loc", site_url("/s/"))
    xml.addQuickElement("changefreq", "daily")
    xml.endElement("url")
    for site in published_sites():
        xml.startElement("url", {})
        xml.addQuickElement("loc", site_url(public_site_path(site.company.slug)))
        xml.addQuickElement("lastmod", site.updated_at.date().isoformat())
        xml.addQuickElement("changefreq", "weekly")
        xml.endElement("url")
    xml.endElement("urlset")
    xml.endDocument()
    return response
