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
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.html import strip_tags
from django.utils.text import Truncator
from django.utils.xmlutils import SimplerXMLGenerator
from django.views.decorators.cache import cache_control
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from org.models import Company
from website.models import Website, normalize_seo_path, service_lines
from core.public_media import stored_public_url
from core.seo_inject import analytics_snippet
from website.seo import page_seo, site_seo
from website.serializers import PublicSiteSerializer

HEX_COLOUR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
ARABIC = re.compile(r"[؀-ۿ]")
CACHE_SECONDS = 300


def site_url(path=""):
    return f"https://{settings.VEZANO_CANONICAL_HOST}{path}"


def absolute(url, request=None):
    """Media URLs are site-relative; crawlers, Open Graph and JSON-LD need
    absolute ones. On the canonical host in production; on whatever host is
    serving in development so a local page shows its images."""
    if not url or not url.startswith("/"):
        return url
    if settings.DEBUG and request is not None:
        return request.build_absolute_uri(url)
    return site_url(url)


CATEGORY_LABELS = {
    "ar": {
        "grocery": "مواد غذائية",
        "pharmacy": "صيدلية",
        "wholesale": "جملة وتوزيع",
        "electronics": "إلكترونيات",
        "fashion": "أزياء وملابس",
        "cosmetics": "تجميل وعطور",
        "hardware": "عدد ومواد بناء",
        "restaurant": "مطعم ومقهى",
        "services": "خدمات",
        "other": "أخرى",
    },
}


def public_site_path(slug):
    return f"/s/{slug}/"


def seo_context(path, language, *, title, description, url, noindex=False, request=None):
    """What the <head> of a Django-rendered public page shows once the
    platform team's SEO settings are applied (website.seo): the page's own
    title, description and canonical unless an override for `path` in this
    `language` says otherwise, plus the site-wide verification tags,
    analytics tag and default share image."""
    override = page_seo(normalize_seo_path(path), language)
    site = site_seo()
    return {
        "title": override.title or title,
        "description": override.description or description,
        "canonical": override.canonical or url,
        "noindex": noindex or override.noindex,
        "google_site_verification": site.google_site_verification,
        "bing_site_verification": site.bing_site_verification,
        "analytics": analytics_snippet(site.analytics_id),
        "default_og_image": absolute(site.default_og_image_url, request),
    }


def published_sites():
    """Sites that are published *and* agreed to be listed. The page itself is
    reachable by URL whenever it is published; the directory, the sitemap and
    the platform's marketing sections need the merchant's consent too."""
    return (
        Website.objects.filter(
            is_published=True, company__is_active=True, list_in_directory=True
        )
        .select_related("company")
        .order_by("business_name", "company__name")
    )


def is_complete(site):
    """A site with enough substance for the platform to show it off."""
    from website.serializers import completeness

    return not completeness(site)


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
    logo = data["logo_image_url"] or (
        data["logo_url"] if data["logo_url"].startswith(("http://", "https://")) else ""
    )
    if logo:
        business["logo"] = logo
    images = [u for u in [data["cover_image_url"], logo] if u]
    images += [g["url"] for g in data["gallery"]]
    if images:
        business["image"] = images
    if data["opening_hours"]:
        business["openingHours"] = _lines(data["opening_hours"])
    if data["map_url"].startswith(("http://", "https://")):
        business["hasMap"] = data["map_url"]
    if data["contact_phone"]:
        business["telephone"] = data["contact_phone"]
    if data["contact_email"]:
        business["email"] = data["contact_email"]
    if data["address"] or data["city"]:
        address = {"@type": "PostalAddress"}
        if data["address"]:
            address["streetAddress"] = data["address"]
        if data["city"]:
            address["addressLocality"] = data["city"]
        business["address"] = address
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
                            **({"image": product["image_url"]} if product["image_url"] else {}),
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


def _layout(data):
    """Split the merchant's sections into the slots of the landing page: the
    first hero/products/about/gallery/contact section fills its slot; any
    further section, and every custom one, renders as a free block."""
    slots = {"hero": None, "products": None, "about": None, "gallery": None, "contact": None}
    custom = []
    # The starter sections are created with English placeholder titles; an
    # untouched one takes the page's own localised heading instead.
    starter_titles = {"About us", "Contact", "Products", "Gallery"}
    for section in data["sections"]:
        if section["title"] in starter_titles:
            section = {**section, "title": ""}
        kind = section["type"]
        if kind in slots and slots[kind] is None:
            slots[kind] = section
        else:
            custom.append(section)
    about = slots["about"]
    about_text = (about["content"].get("text") if about else "") or data["about_text"]
    return {
        "hero": slots["hero"] or {"title": "", "content": {}},
        "products_section": slots["products"] or {"title": "", "content": {}},
        "about_section": about or {"title": "", "content": {}},
        "gallery_section": slots["gallery"] or {"title": "", "content": {}},
        "contact_section": slots["contact"] or {"title": "", "content": {}},
        "about_text": about_text,
        "custom_sections": [s for s in custom if s["title"] or s["content"].get("text")],
    }


def _company_taxed(company):
    """True when the company charges tax, so the cart can say its sum is
    before tax (the order is then quoted tax-inclusive)."""
    from sales.serializers import tax_handler_for

    return tax_handler_for(company).rate() > 0


def _lines(text):
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def _http_url(value):
    return value if (value or "").startswith(("http://", "https://")) else ""


def _site_or_404(slug):
    # `from None`: an unknown slug is an ordinary 404, and chaining
    # DoesNotExist onto it only adds a misleading "during handling of the
    # above exception" block to the log.
    try:
        company = Company.objects.get(slug=slug, is_active=True)
    except Company.DoesNotExist:
        raise Http404 from None
    site = getattr(company, "website", None)
    if site is None or not site.is_published:
        raise Http404
    return site


def render_site(request, site, *, preview=False):
    """The landing page for `site`. `preview` renders an unpublished draft for
    its owner: same template, but noindex and never cached."""
    slug = site.company.slug
    data = PublicSiteSerializer(site).data
    data["cover_image_url"] = absolute(data["cover_image_url"], request)
    data["logo_image_url"] = absolute(data["logo_image_url"], request)
    for photo in data["gallery"]:
        photo["url"] = absolute(photo["url"], request)
    for product in data["featured_products"]:
        product["image_url"] = absolute(product["image_url"], request)
    language = _language(site, data)
    url = site_url(public_site_path(slug))
    colour = data["primary_color"] if HEX_COLOUR.match(data["primary_color"] or "") else "#111827"
    whatsapp = re.sub(r"\D", "", data["contact_phone"] or "")
    logo = data["logo_image_url"] or (
        data["logo_url"] if data["logo_url"].startswith(("http://", "https://")) else ""
    )
    name = _display_name(site)
    context = {
        "site": site,
        "data": data,
        "name": name,
        "description": _description(site, data),
        "seo": seo_context(
            public_site_path(slug), language,
            title=f"{name} — {data['tagline']}" if data["tagline"] else name,
            description=_description(site, data), url=url, noindex=preview, request=request,
        ),
        "language": language,
        "dir": "rtl" if language == "ar" else "ltr",
        "url": url,
        "colour": colour,
        "logo": logo,
        "cover": data["cover_image_url"],
        "gallery": data["gallery"],
        "hours": _lines(data["opening_hours"]),
        "map_url": _http_url(data["map_url"]),
        "category_label": CATEGORY_LABELS.get(language, {}).get(data["category"])
        or dict(Website.CATEGORY_CHOICES).get(data["category"], ""),
        "social": _social_links(data),
        "whatsapp": whatsapp if len(whatsapp) >= 8 else "",
        "currency": site.company.currency,
        "json_ld": _json_ld(site, data, url, language),
        **_layout(data),
        "products": data["featured_products"],
        "services": data["services"],
        "accept_orders": bool(data.get("accept_orders")) and not preview,
        "order_instructions": _lines(data.get("order_instructions") or ""),
        "branches": list(
            site.company.branches.filter(is_active=True).values("id", "name", "phone")
        ) if data.get("accept_orders") else [],
        "order_api": f"/api/public/site/{slug}/orders/",
        # Customers who ordered find their orders here, even after the page
        # stopped taking new ones.
        "track_path": f"/s/{slug}/track/"
        if data.get("accept_orders") or site.public_orders.exists() else "",
        # The cart sums shown prices; the order itself is quoted with tax.
        "order_taxed": bool(data.get("accept_orders")) and _company_taxed(site.company),
        "platform_url": site_url("/"),
        "preview": preview,
        # A platform sample tenant: the page says so, above the fold.
        "is_demo": site.company.is_demo,
    }
    if not preview:
        from website.analytics import record

        record(
            request, public_site_path(slug), page_kind="public_site",
            company_id=site.company_id, language=language,
        )
    response = render(request, "website/public_site.html", context)
    if preview:
        response["Cache-Control"] = "no-store"
        response["X-Robots-Tag"] = "noindex"
    return response


@require_GET
@cache_control(public=True, max_age=CACHE_SECONDS)
def public_site_page(request, slug):
    return render_site(request, _site_or_404(slug))


def site_card(site, request=None):
    """What the directory and the platform's showcase show for one site."""
    logo = stored_public_url(site.logo_image) or (
        site.logo_url if site.logo_url.startswith(("http://", "https://")) else ""
    )
    cover = stored_public_url(site.cover_image)
    # "What they offer": the merchant's own services list, else the names of
    # their featured products, so a card never says nothing about the business.
    offers = service_lines(site.services) or [
        fp.product.name for fp in site.featured_products.select_related("product")[:3]
    ]
    colour = site.primary_color if HEX_COLOUR.match(site.primary_color or "") else "#111827"
    return {
        "name": _display_name(site),
        "initial": (_display_name(site) or "?")[:1],
        "colour": colour,
        "offers": offers[:3],
        "more_offers": max(len(offers) - 3, 0),
        "tagline": site.tagline,
        "address": ", ".join(part for part in (site.address, site.city) if part),
        "category": site.category,
        "category_label": CATEGORY_LABELS["ar"].get(site.category, ""),
        "city": site.city,
        "path": public_site_path(site.company.slug),
        "url": site_url(public_site_path(site.company.slug)),
        "logo": absolute(logo, request),
        "cover": absolute(cover, request),
        "complete": is_complete(site),
        # Sample tenants carry a visible "demo company" label wherever the
        # platform shows them off, so no one reads them as a real customer.
        "is_demo": site.company.is_demo,
    }


def showcase_sites(limit=None):
    """Complete, listed, published sites — the ones the platform shows off."""
    sites = [site for site in published_sites() if is_complete(site)]
    return sites[:limit] if limit else sites


@require_GET
@cache_control(public=True, max_age=CACHE_SECONDS)
def public_site_directory(request):
    category = request.GET.get("category", "")
    if category not in dict(Website.CATEGORY_CHOICES):
        category = ""
    cards = [site_card(site, request) for site in published_sites()]
    if category:
        cards = [card for card in cards if card["category"] == category]
    present = {card["category"] for card in cards if card["category"]}
    categories = [
        (key, CATEGORY_LABELS["ar"][key])
        for key, _ in Website.CATEGORY_CHOICES
        if key in present or key == category
    ]
    # Every listed site gets a card; the complete ones lead.
    cards.sort(key=lambda card: not card["complete"])
    from website.analytics import record

    record(request, "/s/", page_kind="directory", language="ar")
    return render(
        request,
        "website/public_directory.html",
        {
            "cards": cards,
            "featured": [card for card in cards if card["complete"]],
            "others": [card for card in cards if not card["complete"]],
            "categories": categories,
            "category": category,
            "url": site_url("/s/"),
            "platform_url": site_url("/"),
            "seo": seo_context(
                "/s/", "ar",
                title="الشركات والمتاجر التي تعمل بفيزانو — الدليل",
                description=(
                    "الشركات التجارية والموزعون وسلاسل المتاجر التي تدير أعمالها على فيزانو "
                    "وتنشر صفحتها العامة هنا: من هم، وماذا يقدمون، وأين، وكيف تتواصل معهم."
                ),
                url=site_url("/s/"), request=request,
            ),
        },
    )


@require_GET
@cache_control(public=True, max_age=CACHE_SECONDS)
def public_showcase(request):
    """JSON for the marketing site's "stores on Vezano" strip: complete,
    listed sites only, newest published first, at most twelve."""
    sites = sorted(showcase_sites(), key=lambda s: s.published_at or s.updated_at, reverse=True)
    return JsonResponse({"sites": [site_card(site, request) for site in sites[:12]]})


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


@require_GET
def public_pay_page(request, slug):
    """/s/<slug>/pay/?ref=… — where a visitor declares a bank transfer for
    an order. Never cached, never indexed: it is one person's order."""
    site = _site_or_404(slug)
    data = PublicSiteSerializer(site).data
    language = _language(site, data)
    colour = data["primary_color"] if HEX_COLOUR.match(data["primary_color"] or "") else "#111827"
    logo = absolute(data["logo_image_url"], request) or (
        data["logo_url"] if (data["logo_url"] or "").startswith(("http://", "https://")) else ""
    )
    response = render(request, "website/public_pay.html", {
        "name": _display_name(site), "language": language,
        "dir": "rtl" if language == "ar" else "ltr", "colour": colour, "logo": logo,
        "site_path": public_site_path(slug),
        "api_base": f"/api/public/site/{slug}/orders/",
    })
    return _private(response)


def _order_page_context(request, site):
    """What every per-order public page (tracking) shows of the shop: name,
    logo, colour and language."""
    slug = site.company.slug
    data = PublicSiteSerializer(site).data
    language = _language(site, data)
    colour = data["primary_color"] if HEX_COLOUR.match(data["primary_color"] or "") else "#111827"
    logo = absolute(data["logo_image_url"], request) or (
        data["logo_url"] if (data["logo_url"] or "").startswith(("http://", "https://")) else ""
    )
    return {
        "name": _display_name(site), "language": language,
        "dir": "rtl" if language == "ar" else "ltr", "colour": colour, "logo": logo,
        "site_path": public_site_path(slug),
        "track_path": f"/s/{slug}/track/",
        "is_demo": site.company.is_demo,
    }


def _private(response):
    """One person's order: never cached, never indexed."""
    response["Cache-Control"] = "no-store"
    response["X-Robots-Tag"] = "noindex"
    return response


@csrf_exempt
@require_http_methods(["GET", "POST"])
def public_track_page(request, slug):
    """/s/<slug>/track/ — a customer finds their recent orders by reference,
    email or exact name (website.tracking says what is shown and why).

    The search is a POST so an email or a name never lands in a URL, a
    browser history or an access log. It changes nothing, so it carries no
    CSRF token, and a visitor whose browser blocks cookies can still use it.
    """
    from website import tracking

    site = _site_or_404(slug)
    context = _order_page_context(request, site)
    query = ""
    searched, limited, results = False, False, []
    if request.method == "POST":
        query = str(request.POST.get("q") or "").strip()[:254]
        if query:
            searched = True
            limited = tracking.rate_limited(request)
            if not limited:
                who, orders = tracking.lookup(site, query)
                results = [
                    tracking.public_view(order, context["language"], who=who)
                    for order in orders
                ]
                kind = (tracking.classify(query) or ("none",))[0]
                tracking.log_lookup(site, kind, len(results))
    context.update({
        "query": query, "searched": searched, "limited": limited, "results": results,
        "lookup_days": tracking.LOOKUP_DAYS, "single": False,
    })
    return _private(render(request, "website/public_track.html", context))


@require_GET
def public_track_order_page(request, slug, token):
    """/s/<slug>/track/<token>/ — the customer's private link to one order."""
    from website import tracking
    from website.models import PublicOrder

    site = _site_or_404(slug)
    context = _order_page_context(request, site)
    order = None
    limited = tracking.rate_limited(request, count=False)
    if not limited:
        order = (
            PublicOrder.objects.filter(website=site, tracking_token=str(token)[:48])
            .select_related("branch", "company", "website")
            .prefetch_related("lines", "payments", "events")
            .first()
        )
        if order is None:
            # A wrong token costs the address a lookup, like a failed search.
            tracking.rate_limited(request)
    results = []
    if order is not None:
        results = [tracking.public_view(order, context["language"], who="first", full=True)]
    context.update({
        "query": "", "searched": True, "limited": limited, "results": results,
        "lookup_days": tracking.LOOKUP_DAYS, "single": True,
    })
    response = render(
        request, "website/public_track.html", context, status=200 if order else 404
    )
    return _private(response)
