"""Order tracking and fulfilment stages for orders from the public page.

Stages. An order is received (``new``), then confirmed (which creates the
customer and the sales order — website.orders.confirm), then preparing,
then ready for pickup or out for delivery depending on how the customer
chose to receive it, then completed (picked up / delivered). It may be
rejected (only while new) or cancelled (until completed), always with a
reason. Only the stages in ``allowed_next`` may follow each other; every
change writes a ``PublicOrderEvent`` and emails the customer when they left
an email. Stages after confirmation never touch stock or money.

Lookup. The owner chose to let customers find their orders by reference,
email or name. The exposure is kept small on purpose:

- one company's page only, orders of the last 90 days, at most 10;
- reference and email match exactly (case-insensitive); a name matches
  exactly after trimming, collapsing spaces and folding Arabic spelling
  variants (``core.arabic.fold_arabic``) — never "contains";
- results never show the phone, the email or the address, and show the
  customer only as initials (email/name search) or first name (reference);
- every miss reads the same, and each address may look up 20 times in
  10 minutes.

Each order also has an unguessable ``tracking_token``: the link in the
confirmation page and emails, which shows that one order in full detail
(still without phone or email, and only the first line of the address).
"""

import logging
import re
import secrets
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from core.activity import get_client_ip, log_activity
from core.arabic import fold_arabic

logger = logging.getLogger(__name__)

LOOKUP_DAYS = 90
LOOKUP_LIMIT = 10
RATE_LIMIT = 20
RATE_WINDOW = 600  # seconds
REFERENCE = re.compile(r"^W[A-Z0-9]{6}$")


# ---------------------------------------------------------------- helpers

def new_tracking_token():
    return secrets.token_urlsafe(24)


def new_reference(prefix, taken):
    """``prefix`` + 6 unambiguous characters (the web-order alphabet) that
    ``taken(ref)`` says is free."""
    from website.orders import REFERENCE_ALPHABET

    for _attempt in range(20):
        ref = prefix + "".join(secrets.choice(REFERENCE_ALPHABET) for _i in range(6))
        if not taken(ref):
            return ref
    raise RuntimeError("could not allocate a reference")


def name_key(name):
    """The form a name is compared in: trimmed, single-spaced, Arabic
    spelling folded, case-folded. Exact equality on this is the name match."""
    return fold_arabic(" ".join(str(name or "").split())).casefold()[:120]


# The subscriber part of a phone number: the last 9 digits (a Sudanese
# mobile number without the 0 or +249, and enough to tell numbers apart
# anywhere). "0912 345 678", "+249912345678", "00249 91 234 5678" and
# "912345678" all give "912345678"; the WhatsApp number is the same number.
PHONE_KEY_DIGITS = 9
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def phone_key(phone):
    digits = "".join(ch for ch in str(phone or "").translate(_ARABIC_DIGITS) if ch.isdigit())
    return digits[-PHONE_KEY_DIGITS:] if len(digits) >= PHONE_KEY_DIGITS else ""


def first_name(name):
    parts = str(name or "").split()
    return parts[0] if parts else ""


def initials(name):
    parts = str(name or "").split()
    return " ".join(f"{part[0]}." for part in parts[:3])


def address_first_line(address):
    """Enough of the delivery address for the customer to recognise it."""
    head = re.split(r"[\n,،]", str(address or ""), maxsplit=1)[0].strip()
    return head[:24] + ("…" if len(head) > 24 else "")


def tracking_path(order):
    return f"/s/{order.company.slug}/track/{order.tracking_token}/"


def tracking_url(order):
    from website.public_pages import site_url

    return site_url(tracking_path(order))


# ---------------------------------------------------------------- stages

def allowed_next(order):
    """The stages ``order`` may move to now, in the order a person would
    take them (the first one is the "next step")."""
    from website.models import PublicOrder as PO

    handover = PO.DELIVERING if order.delivery_mode == PO.DELIVERY else PO.READY
    return {
        PO.NEW: [PO.CONFIRMED, PO.REJECTED, PO.CANCELLED],
        PO.CONFIRMED: [PO.PREPARING, PO.CANCELLED],
        PO.PREPARING: [handover, PO.CANCELLED],
        PO.READY: [PO.COMPLETED, PO.CANCELLED],
        PO.DELIVERING: [PO.COMPLETED, PO.CANCELLED],
    }.get(order.status, [])


def record_stage(order, from_status, actor, note="", *, notify=True):
    """History row, activity log and customer email for a stage change that
    was just saved on ``order``. Called inside the caller's transaction."""
    from website.models import PublicOrderEvent

    PublicOrderEvent.objects.create(
        company_id=order.company_id, order=order, from_status=from_status or "",
        to_status=order.status, note=note or "", actor=actor,
    )
    if not from_status:
        return  # the order was just placed; place_order logs and emails it
    log_activity(
        action="public_order_stage", company=order.company, entity_type="PublicOrder",
        entity_id=order.pk,
        metadata={"reference": order.reference, "from": from_status, "to": order.status},
    )
    if notify and order.email:
        order_id, stage = order.pk, order.status
        transaction.on_commit(lambda: email_stage(order_id, stage))


@transaction.atomic
def change_stage(order, actor, to_status, note=""):
    """Move ``order`` to ``to_status`` if the stage machine allows it."""
    from website.models import PublicOrder
    from website.orders import confirm, reject

    note = str(note or "").strip()[:1000]
    if to_status == PublicOrder.CONFIRMED and order.status == PublicOrder.NEW:
        return confirm(order, actor, note)
    if to_status == PublicOrder.REJECTED and order.status == PublicOrder.NEW:
        return reject(order, actor, note)
    order = PublicOrder.objects.select_for_update().get(pk=order.pk)
    if to_status not in allowed_next(order):
        raise ValidationError({"status": _("This order cannot move to that stage now.")})
    if to_status == PublicOrder.CANCELLED and not note:
        raise ValidationError({"note": _("Give the reason for cancelling; the customer sees it.")})
    from_status = order.status
    order.status = to_status
    if from_status == PublicOrder.NEW:
        # Cancelling before anyone confirmed it is the company's answer.
        order.decided_by = actor
        order.decided_at = timezone.now()
        order.decision_note = note
    order.save()
    if to_status == PublicOrder.CANCELLED and order.sales_order_id:
        # Not yet rung up: the till must not finish a cancelled order. An
        # invoiced one keeps its invoice — money goes back through a return.
        from sales.models import SalesOrder

        SalesOrder.objects.filter(
            pk=order.sales_order_id, status=SalesOrder.CONFIRMED
        ).update(status=SalesOrder.CANCELLED)
    record_stage(order, from_status, actor, note)
    return order


# ---------------------------------------------------------------- emails

def _stage_lines(order, stage, note):
    """(ar, en) sentences for the email about ``stage``."""
    from website.models import PublicOrder as PO

    ref, shop = order.reference, order.company.name
    where = order.branch.name if order.branch else shop
    texts = {
        PO.CONFIRMED: (f"أكّد {shop} طلبك رقم {ref}.", f"{shop} confirmed your order {ref}."),
        PO.PREPARING: (
            f"بدأ {shop} تجهيز طلبك رقم {ref}.", f"{shop} started preparing your order {ref}.",
        ),
        PO.READY: (
            f"طلبك رقم {ref} جاهز للاستلام من {where}.",
            f"Your order {ref} is ready for pickup at {where}.",
        ),
        PO.DELIVERING: (f"طلبك رقم {ref} خرج للتوصيل.", f"Your order {ref} is out for delivery."),
        PO.COMPLETED: (
            (f"تم توصيل طلبك رقم {ref}. شكراً لك!", f"Your order {ref} was delivered. Thank you!")
            if order.delivery_mode == PO.DELIVERY else
            (f"استلمت طلبك رقم {ref}. شكراً لك!", f"You picked up your order {ref}. Thank you!")
        ),
        PO.REJECTED: (
            f"نعتذر، لم يتمكن {shop} من تنفيذ طلبك رقم {ref}.",
            f"Sorry, {shop} could not fulfil your order {ref}.",
        ),
        PO.CANCELLED: (f"أُلغي طلبك رقم {ref}.", f"Your order {ref} was cancelled."),
    }
    ar, en = texts.get(stage, (f"تغيّرت حالة طلبك رقم {ref}.", f"Your order {ref} changed."))
    ar, en = [ar], [en]
    if stage in (PO.REJECTED, PO.CANCELLED) and note:
        ar.append(f"السبب: {note}")
        en.append(f"Reason: {note}")
    return ar, en


def email_stage(order_id, stage):
    """Tell the customer about a stage change. Never raises: the change is
    already saved and a mail failure must not undo or block it."""
    from core import mailer
    from website.models import PublicOrder

    try:
        order = PublicOrder.objects.select_related("company", "branch").get(pk=order_id)
        if not order.email:
            return False
        event = order.events.filter(to_status=stage).order_by("-created_at", "-id").first()
        ar, en = _stage_lines(order, stage, event.note if event else "")
        name = first_name(order.contact_name)
        return mailer.send_bilingual(
            subject_ar=f"طلبك {order.reference} — {stage_label(stage, 'ar', order)}",
            subject_en=f"Your order {order.reference} — {stage_label(stage, 'en', order)}",
            ar=[f"مرحباً {name}،", *ar, "تابع طلبك من الرابط أدناه."],
            en=[f"Hello {name},", *en, "Follow your order with the link below."],
            link=tracking_url(order), recipient=order.email,
            primary="ar" if (order.language or "ar").startswith("ar") else "en",
        )
    except Exception:  # noqa: BLE001 - the stage change stands regardless
        logger.exception("Could not email the stage change of web order %s", order_id)
        return False


# ---------------------------------------------------------------- public view

STAGE_LABELS = {
    "new": ("وصل الطلب", "Received"),
    "confirmed": ("تم التأكيد", "Confirmed"),
    "preparing": ("قيد التجهيز", "Preparing"),
    "ready": ("جاهز للاستلام", "Ready for pickup"),
    "delivering": ("خرج للتوصيل", "Out for delivery"),
    "completed": ("تم الاستلام", "Picked up"),
    "completed_delivery": ("تم التوصيل", "Delivered"),
    "rejected": ("مرفوض", "Rejected"),
    "cancelled": ("ملغى", "Cancelled"),
}


def stage_label(stage, language, order=None):
    key = stage
    if stage == "completed" and order is not None and order.delivery_mode == "delivery":
        key = "completed_delivery"
    ar, en = STAGE_LABELS.get(key, (stage, stage))
    return ar if language == "ar" else en


def _timeline(order, events, language):
    """Every stage of this order's path, done or still to come."""
    from website.models import PublicOrder as PO

    reached = {}
    for event in events:
        reached[event.to_status] = event.created_at
    reached.setdefault(PO.NEW, order.created_at)
    handover = PO.DELIVERING if order.delivery_mode == PO.DELIVERY else PO.READY
    path = [PO.NEW, PO.CONFIRMED, PO.PREPARING, handover, PO.COMPLETED]
    closed = order.status in (PO.REJECTED, PO.CANCELLED)
    steps = []
    for stage in path:
        if closed and stage not in reached:
            continue
        steps.append({
            "label": stage_label(stage, language, order), "at": reached.get(stage),
            "done": stage in reached, "current": stage == order.status,
        })
    if closed:
        steps.append({
            "label": stage_label(order.status, language, order),
            "at": reached.get(order.status) or order.decided_at, "done": True,
            "current": True, "closed": True,
        })
    return steps


def payment_state(order):
    """What the customer may know about their transfers: verified, being
    checked, or not verified; None when nothing was declared."""
    from website.models import PublicOrderPayment as P

    states = {claim.status for claim in order.payments.all()}
    if P.CONFIRMED in states:
        return "verified"
    if P.VERIFYING in states:
        return "pending"
    return "not_verified" if states else None


def closing_reason(order, events):
    from website.models import PublicOrder as PO

    if order.status not in (PO.REJECTED, PO.CANCELLED):
        return ""
    for event in reversed(events):
        if event.to_status == order.status and event.note:
            return event.note
    return order.decision_note


_POUND = {"SDG", "SD", "SDD"}


def money_display(amount, currency, language):
    code = (currency or "").upper()
    if code in _POUND:
        code = "ج.س" if language == "ar" else "SDG"
    return f"{Decimal(str(amount)):,.2f} {code}".strip()


def public_view(order, language, *, who, full=False):
    """What the tracking page shows for one order. ``who`` is "initials"
    (email/name search) or "first" (reference search, private link)."""
    from website.order_payments import public_bank_accounts, paid_so_far
    from website.models import PublicOrder as PO

    events = list(order.events.all())
    branch = order.branch
    view = {
        "reference": order.reference,
        "created_at": order.created_at,
        "status": order.status,
        "status_label": stage_label(order.status, language, order),
        "closed": order.status in (PO.REJECTED, PO.CANCELLED),
        "delivery": order.delivery_mode == PO.DELIVERY,
        "customer": initials(order.contact_name) if who == "initials"
        else first_name(order.contact_name),
        "lines": [
            {"name": line.name, "quantity": f"{Decimal(line.quantity).normalize():f}"}
            for line in order.lines.all()
        ],
        # Strings, so the page shows 1000.00 whatever the active locale's
        # decimal separator (the same form the order page and emails use).
        "total": str(order.total) if order.total is not None else None,
        "tax_amount": str(order.tax_amount) if order.tax_amount else "",
        "currency": order.currency,
        # The app's money rule (frontend lib/money.js): grouped, 2 decimals,
        # Latin digits, the pound as "ج.س" in Arabic and "SDG" in English.
        "total_display": money_display(order.total, order.currency, language)
        if order.total is not None else "",
        "payment": payment_state(order),
        "branch_name": branch.name if branch else "",
        "branch_phone": (branch.phone if branch and branch.phone else "")
        or (order.website.contact_phone or ""),
        "reason": closing_reason(order, events),
        "timeline": _timeline(order, events, language),
        "track_path": tracking_path(order) if full else "",
    }
    if full:
        view["address_hint"] = (
            address_first_line(order.address) if order.delivery_mode == PO.DELIVERY else ""
        )
        can_pay = (
            order.status in PO.PAYABLE and order.total is not None
            and bool(public_bank_accounts(order.company)) and paid_so_far(order) < order.total
        )
        view["pay_path"] = f"/s/{order.company.slug}/pay/?ref={order.reference}" if can_pay else ""
    return view


# ---------------------------------------------------------------- lookup

def rate_limited(request, *, count=True):
    """True once this address used up its lookups for the window."""
    key = f"order-track:{get_client_ip(request) or 'unknown'}"
    if not count:
        return (cache.get(key) or 0) >= RATE_LIMIT
    cache.add(key, 0, RATE_WINDOW)
    try:
        used = cache.incr(key)
    except ValueError:  # expired between add and incr
        cache.set(key, 1, RATE_WINDOW)
        used = 1
    return used > RATE_LIMIT


def classify(query, reference=REFERENCE):
    """("reference" | "email" | "phone" | "name", normalised value) or None.
    ``reference`` is the pattern a reference must match (web orders by
    default; vezano.app/track/ also takes registration and demo ones)."""
    text = " ".join(str(query or "").split())[:254]
    if len(text) < 2:
        return None
    if "@" in text:
        return "email", text.replace(" ", "")
    # A phone / WhatsApp number: only digits and the usual separators.
    if re.fullmatch(r"[+\d\s\-().٠-٩۰-۹]+", text) and phone_key(text):
        return "phone", phone_key(text)
    compact = text.lstrip("#").replace(" ", "").upper()
    if reference.match(compact):
        return "reference", compact
    return "name", name_key(text)


def _window(site):
    from website.models import PublicOrder

    since = timezone.now() - timedelta(days=LOOKUP_DAYS)
    return (
        PublicOrder.objects.filter(website=site, company_id=site.company_id, created_at__gte=since)
        .select_related("branch", "company", "website")
        .prefetch_related("lines", "payments", "events")
        .order_by("-created_at", "-id")
    )


def lookup(site, query):
    """(kind, orders) for a visitor's search on ``site``'s tracking page.
    kind is how the customer is shown: "first" or "initials"."""
    found = classify(query)
    if found is None:
        return "initials", []
    kind, value = found
    orders = _window(site)
    if kind == "reference":
        hits = list(orders.filter(reference__iexact=value)[:1])
        if hits:
            return "first", hits
        # "William" looks like a reference too; a miss falls back to names.
        kind, value = "name", name_key(query)
    if kind == "email":
        hits = orders.filter(email__iexact=value)
    elif kind == "phone":
        hits = orders.filter(lookup_phone=value)
    else:
        hits = orders.filter(lookup_name=value) if value else orders.none()
    return "initials", list(hits[:LOOKUP_LIMIT])


def log_lookup(site, kind, hits):
    """A count, never the query: how the tracking page is used."""
    logger.info("order-track lookup company=%s kind=%s hits=%d", site.company_id, kind, hits)
