"""Orders from the public page: what a visitor may order, how an order is
recorded, who is told, and how the company answers.

The public catalogue is the site's featured products only; each carries the
owner's two choices (price shown? orderable?) and a live "in stock" that is
never a number. An order is a request: prices are what the page showed,
nothing is reserved, the visitor gets a reference and a WhatsApp link to
the branch they chose so the conversation continues where this market
does business. Confirming it creates the customer (matched by phone) and a
confirmed sales order the till already knows how to finish.
"""

import re
import secrets
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from core import mailer
from core.activity import log_activity
from website.models import PublicOrder, PublicOrderLine

REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
MAX_LINES = 30
MAX_QTY = Decimal("9999")


def in_stock(product):
    """True unless stock is tracked and nothing is on hand anywhere."""
    if not product.is_stock_tracked:
        return True
    return product.on_hand() > 0


def catalogue(site):
    """What the public page offers, per featured product."""
    rows = []
    for item in site.featured_products.select_related("product").order_by("order", "id"):
        product = item.product
        if not product.is_active:
            continue
        rows.append({
            "product": product.pk,
            "name": product.name,
            "sku": product.sku,
            "caption": item.caption,
            "price": str(product.sale_price) if item.show_price else None,
            "orderable": bool(item.allow_order),
            "in_stock": in_stock(product),
        })
    return rows


def _new_reference():
    for _attempt in range(20):
        ref = "W" + "".join(secrets.choice(REFERENCE_ALPHABET) for _i in range(6))
        if not PublicOrder.objects.filter(reference=ref).exists():
            return ref
    raise RuntimeError("could not allocate an order reference")


def clean_phone(raw):
    digits = re.sub(r"[^\d+]", "", str(raw or ""))
    if len(re.sub(r"\D", "", digits)) < 8:
        raise ValidationError({"phone": _("Enter a phone number we can reach you on.")})
    return digits[:32]


@transaction.atomic
def place_order(site, payload, request=None):
    """Record a visitor's order. ``payload`` is the public form."""
    if not site.is_published or not site.accept_orders:
        raise ValidationError({"detail": _("This page does not take orders.")})
    company = site.company
    name = str(payload.get("contact_name") or "").strip()[:120]
    if not name:
        raise ValidationError({"contact_name": _("Tell us who to ask for.")})
    phone = clean_phone(payload.get("phone"))
    email = str(payload.get("email") or "").strip()[:254]
    if email and "@" not in email:
        raise ValidationError({"email": _("That email address does not look right.")})
    mode = payload.get("delivery_mode") or PublicOrder.PICKUP
    if mode not in (PublicOrder.PICKUP, PublicOrder.DELIVERY):
        raise ValidationError({"delivery_mode": _("Choose pickup or delivery.")})
    address = str(payload.get("address") or "").strip()[:255]
    if mode == PublicOrder.DELIVERY and not address:
        raise ValidationError({"address": _("Where should we deliver?")})
    branch = None
    branch_id = payload.get("branch")
    branches = company.branches.filter(is_active=True)
    if branch_id:
        branch = branches.filter(pk=branch_id).first()
        if branch is None:
            raise ValidationError({"branch": _("Choose one of the listed branches.")})
    elif branches.count() == 1:
        branch = branches.first()

    offered = {
        item.product_id: item
        for item in site.featured_products.select_related("product")
        if item.allow_order and item.product.is_active
    }
    raw_lines = payload.get("lines") or []
    if not isinstance(raw_lines, list) or not raw_lines:
        raise ValidationError({"lines": _("Add at least one product.")})
    if len(raw_lines) > MAX_LINES:
        raise ValidationError({"lines": _("Too many lines for one order.")})
    lines, total, priced = [], Decimal("0"), True
    for raw in raw_lines:
        try:
            product_id = int(raw.get("product"))
            quantity = Decimal(str(raw.get("quantity", 1)))
        except (TypeError, ValueError, ArithmeticError):
            raise ValidationError({"lines": _("Each line needs a product and a quantity.")})
        item = offered.get(product_id)
        if item is None:
            raise ValidationError({"lines": _("One of the products cannot be ordered here.")})
        if quantity <= 0 or quantity > MAX_QTY:
            raise ValidationError({"lines": _("Quantity must be between 1 and 9999.")})
        price = item.product.sale_price if item.show_price else None
        if price is None:
            priced = False
        else:
            total += price * quantity
        lines.append((item.product, quantity, price))

    visitor = ""
    language = str(payload.get("language") or "")[:8]
    if request is not None:
        from website.analytics import _visitor_hash

        visitor = _visitor_hash(request, timezone.localdate())
    from website.order_payments import is_blocked

    if is_blocked(company, phone, visitor):
        raise ValidationError({"detail": _("This page cannot take your order.")})
    order = PublicOrder.objects.create(
        company=company, website=site, branch=branch, reference=_new_reference(),
        contact_name=name, phone=phone, email=email, delivery_mode=mode, address=address,
        note=str(payload.get("note") or "").strip()[:2000], language=language,
        currency=company.currency, total=total.quantize(Decimal("0.01")) if priced else None,
        visitor_hash=visitor,
    )
    PublicOrderLine.objects.bulk_create([
        PublicOrderLine(order=order, product=product, name=product.name, quantity=qty,
                        unit_price=price)
        for product, qty, price in lines
    ])
    log_activity(
        action="public_order_received", company=company, entity_type="PublicOrder",
        entity_id=order.pk,
        metadata={"reference": order.reference, "branch": branch.pk if branch else None},
    )
    transaction.on_commit(lambda: notify_branch(order))
    if email:
        transaction.on_commit(lambda: email_customer(order))
    return order


def pay_url(order):
    """Absolute link to the public payment page for this order."""
    from website.public_pages import site_url

    return site_url(f"/s/{order.company.slug}/pay/?ref={order.reference}")


def email_customer(order):
    """The visitor's copy: what they ordered, what to pay, where, and the
    link to declare the transfer."""
    from website.order_payments import public_bank_accounts

    lines = [f"{line.name} × {line.quantity:g}" for line in order.lines.all()]
    total = f"{order.total} {order.currency}" if order.total is not None else None
    accounts = public_bank_accounts(order.company)
    shop = order.company.name
    ar = [f"مرحباً {order.contact_name}،", f"وصل طلبك رقم {order.reference} إلى {shop}."]
    en = [f"Hello {order.contact_name},", f"Your order {order.reference} reached {shop}."]
    ar.append("المنتجات: " + "، ".join(lines) + ".")
    en.append("Items: " + ", ".join(lines) + ".")
    if total:
        ar.append(f"الإجمالي: {total}.")
        en.append(f"Total: {total}.")
    else:
        ar.append("سيؤكد المحل المبلغ عند مراجعة الطلب.")
        en.append("The shop will confirm the amount when it reviews the order.")
    if accounts:
        ar.append("حسابات التحويل: " + " · ".join(
            f"{a.bank_name} — {a.account_name} {a.account_number}".strip() for a in accounts) + ".")
        en.append("Bank accounts: " + " · ".join(
            f"{a.bank_name} — {a.account_name} {a.account_number}".strip() for a in accounts) + ".")
        ar.append("بعد التحويل سجّله من الرابط أدناه (البنك وآخر 4 أرقام من رقم العملية).")
        en.append("After transferring, declare it with the link below (bank and last 4 digits).")
    mailer.send_bilingual(
        subject_ar=f"طلبك {order.reference} — {order.company.name}",
        subject_en=f"Your order {order.reference} — {order.company.name}",
        ar=ar, en=en, link=pay_url(order) if accounts else None, recipient=order.email,
        primary="ar" if (order.language or "ar").startswith("ar") else "en",
    )


def whatsapp_number(order):
    """The number the visitor should talk to: the branch's, else the site's."""
    raw = (order.branch.phone if order.branch and order.branch.phone else "") or (
        order.website.contact_phone or ""
    )
    digits = re.sub(r"\D", "", raw)
    return digits if len(digits) >= 8 else ""


def recipients(order):
    """Who is told: the chosen branch's managers; the owners too when the
    site says so (or when there is no manager to tell)."""
    from accounts.models import User

    users = User.objects.filter(company=order.company, is_active=True)
    told = []
    if order.branch_id:
        told = list(users.filter(branch_id=order.branch_id, role__name="Branch Manager"))
    if not told or order.website.order_notify_owners:
        for owner in users.filter(role__name="Business Owner"):
            if owner not in told:
                told.append(owner)
    return told


def extra_emails(order):
    return [
        line.strip() for line in (order.website.order_notify_emails or "").splitlines()
        if "@" in line.strip()
    ]


def notify_branch(order):
    from core import push

    lines = ", ".join(f"{line.name} × {line.quantity:g}" for line in order.lines.all())
    where = order.branch.name if order.branch else order.company.name
    origin = getattr(settings, "PUBLIC_APP_ORIGIN", "") or ""
    path = f"/web-orders/?ref={order.reference}"
    link = f"{origin.rstrip('/')}{path}" if origin else None
    people = recipients(order)
    for user in people:
        push.send_to_user(
            user,
            title=f"طلب جديد {order.reference} · New order",
            body=f"{order.contact_name} · {lines}"[:180],
            url=path,
            tag=f"web-order-{order.reference}",
        )
    for recipient in [u.email for u in people] + extra_emails(order):
        user = next((u for u in people if u.email == recipient), None)
        greeting = (user.full_name or "") if user else ""
        mailer.send_bilingual(
            subject_ar=f"طلب جديد من الموقع {order.reference}",
            subject_en=f"New order from your page {order.reference}",
            ar=[
                f"مرحباً {greeting}،",
                f"وصل طلب جديد إلى {where} من {order.contact_name} ({order.phone}).",
                f"المنتجات: {lines}.",
                "أكّده أو ارفضه من صفحة «الطلبات الخارجية».",
            ],
            en=[
                f"Hello {greeting},",
                f"A new order reached {where} from {order.contact_name} ({order.phone}).",
                f"Items: {lines}.",
                "Confirm or reject it from the “External orders” page.",
            ],
            link=link,
            recipient=recipient,
        )


@transaction.atomic
def confirm(order, actor, note=""):
    """Create the customer and a confirmed sales order; the till finishes it."""
    from sales.models import Customer, SalesOrder, SalesOrderLine
    from sales.serializers import _q2, tax_handler_for

    order = PublicOrder.objects.select_for_update().get(pk=order.pk)
    if order.status != PublicOrder.NEW:
        raise ValidationError({"detail": _("This order was already answered.")})
    company = order.company
    customer = Customer.objects.filter(company=company, phone=order.phone).first()
    if customer is None:
        customer = Customer.objects.create(
            company=company, name=order.contact_name, phone=order.phone,
            address=order.address,
        )
    handler = tax_handler_for(company)
    sales_order = SalesOrder.objects.create(
        company=company, customer=customer, branch=order.branch,
        status=SalesOrder.CONFIRMED, created_by=actor,
    )
    subtotal, tax = Decimal("0"), Decimal("0")
    for line in order.lines.select_related("product"):
        if line.product is None or not line.product.is_active:
            raise ValidationError({
                "detail": _("%(name)s is no longer in the catalogue.") % {"name": line.name},
            })
        price = line.unit_price if line.unit_price is not None else line.product.sale_price
        lt = _q2(line.quantity * price)
        SalesOrderLine.objects.create(
            sales_order=sales_order, product=line.product, description=line.name,
            quantity=line.quantity, unit_price=price, line_total=lt,
        )
        subtotal += lt
        tax += handler.compute_tax(lt, line.product)
    sales_order.subtotal = _q2(subtotal)
    sales_order.tax_amount = _q2(tax)
    sales_order.total = sales_order.subtotal + sales_order.tax_amount
    sales_order.save(update_fields=["subtotal", "tax_amount", "total"])
    order.status = PublicOrder.CONFIRMED
    order.customer = customer
    order.sales_order = sales_order
    order.decided_by = actor
    order.decided_at = timezone.now()
    order.decision_note = note
    order.save()
    return order


@transaction.atomic
def reject(order, actor, note=""):
    order = PublicOrder.objects.select_for_update().get(pk=order.pk)
    if order.status != PublicOrder.NEW:
        raise ValidationError({"detail": _("This order was already answered.")})
    order.status = PublicOrder.REJECTED
    order.decided_by = actor
    order.decided_at = timezone.now()
    order.decision_note = note
    order.save()
    return order
