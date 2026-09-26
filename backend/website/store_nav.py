"""The bottom tab bar a company's public pages show on phones.

Below 768px the header links are hidden, so every place a visitor can go
from the page lives here instead: at most five tabs, the rest in a «المزيد»
sheet. The page's language comes from what the merchant wrote (see
public_pages._language), not from the visitor's locale, so the labels sit in
a per-language table like the category labels do.
"""

MAX_TABS = 5

LABELS = {
    "ar": {
        "home": "الرئيسية",
        "products": "المنتجات",
        "services": "الخدمات",
        "order": "طلبك",
        "track": "تتبّع",
        "contact": "تواصل",
        "more": "المزيد",
        "whatsapp": "واتساب",
        "call": "اتصل بنا",
        "reach": "العنوان وساعات العمل",
        "about": "من نحن",
        "gallery": "الصور",
        "nav": "التنقل في الصفحة",
    },
    "en": {
        "home": "Home",
        "products": "Products",
        "services": "Services",
        "order": "Order",
        "track": "Track",
        "contact": "Contact",
        "more": "More",
        "whatsapp": "WhatsApp",
        "call": "Call us",
        "reach": "Address and hours",
        "about": "About",
        "gallery": "Gallery",
        "nav": "Page navigation",
    },
}


def _tab(key, label, href, icon=None, **extra):
    return {"key": key, "label": label, "href": href, "icon": icon or key, **extra}


def mobile_nav(
    language, *, page, site_path, track_path="", products=False, services=False,
    accept_orders=False, whatsapp="", phone="", about=False, gallery=False,
):
    """Tabs and «more» items for one public page.

    `page` is "site" (the company page, whose sections are anchors on the
    same page), "track" or "pay". Returns {"tabs", "more", "label"}; each
    tab carries the section id it follows while scrolling (`section`) and
    its `aria-current` value when it is where the visitor is (`current`:
    "page" for the tracking page, "location" for the top of the company
    page; the page script moves it as sections scroll by).
    """
    text = LABELS.get(language, LABELS["en"])
    on_site = page == "site"
    anchor = (lambda name: f"#{name}") if on_site else (lambda name: f"{site_path}#{name}")

    tabs = [_tab("home", text["home"], "#top" if on_site else site_path,
                 section="top", current="location" if on_site else "")]
    if products:
        tabs.append(_tab("products", text["products"], anchor("products"), icon="grid",
                         section="products"))
    elif services:
        tabs.append(_tab("services", text["services"], anchor("services"), icon="grid",
                         section="services"))
    # The cart lives in this page's script only, so the order tab belongs to
    # the company page; until something is in the cart it leads to products.
    if accept_orders and on_site:
        tabs.append(_tab("order", text["order"], "#products" if products else "#order",
                         icon="bag", section="order", badge=True))
    if track_path:
        tabs.append(_tab("track", text["track"], track_path, icon="package",
                         current="page" if page == "track" else ""))

    # One tap to reach the shop: WhatsApp, else a call, else the contact block.
    if whatsapp:
        direct = _tab("whatsapp", text["whatsapp"], f"https://wa.me/{whatsapp}", icon="chat",
                      external=True)
    elif phone:
        direct = _tab("call", text["call"], f"tel:{phone}", icon="phone")
    else:
        direct = None
    contact = _tab("contact", text["contact"], direct["href"] if direct else anchor("contact"),
                   icon="chat" if whatsapp else "phone",
                   external=bool(direct and direct.get("external")),
                   section="" if direct else "contact")

    more = []
    if on_site:
        if about:
            more.append(_tab("about", text["about"], "#about", icon="info", section="about"))
        if gallery:
            more.append(_tab("gallery", text["gallery"], "#gallery", icon="image",
                             section="gallery"))
        if direct:
            # The contact tab leaves the page; the block with the address,
            # hours and map stays one tap away in the sheet.
            more.append(_tab("reach", text["reach"], "#contact", icon="pin",
                             section="contact"))

    if len(tabs) + 1 + (1 if more else 0) <= MAX_TABS:
        tabs.append(contact)
    else:
        # No room for a contact tab: its actions head the sheet (the header
        # row keeps its own WhatsApp/call button too).
        head = [direct] if direct else []
        if direct and whatsapp and phone:
            head.append(_tab("call", text["call"], f"tel:{phone}", icon="phone"))
        if not direct:
            head.append(_tab("reach", text["contact"], "#contact", icon="pin",
                             section="contact"))
        more = head + more
    return {"tabs": tabs, "more": more, "label": text["nav"], "more_label": text["more"]}
