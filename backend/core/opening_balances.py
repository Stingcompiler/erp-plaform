"""Opening balances for customers and suppliers.

A company that moves to Vezano brings debts with it. Rather than a stored
"opening balance" number that every report would have to remember to add,
the balance is recorded as a document the rest of the system already
understands — a line-less invoice or a receipt-less bill dated the day the
books started — so the debt ledger, aging, statements, collection and
supplier payments see it with no special case, and revenue / purchase
totals skip it by its flag. One per account; correcting it is a credit or
debit note like any other document.
"""

from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import PermissionDenied, ValidationError

from core.rbac import can_approve_high_value


def parse_request(data, user):
    if not can_approve_high_value(user):
        raise PermissionDenied(_("Only a manager or owner may record an opening balance."))
    try:
        amount = Decimal(str(data.get("amount", ""))).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValidationError({"amount": [_("Enter a valid amount.")]})
    if amount <= 0:
        raise ValidationError({"amount": [_("Amount must be positive.")]})
    as_of = data.get("as_of") or timezone.localdate().isoformat()
    try:
        as_of = date.fromisoformat(str(as_of))
    except ValueError:
        raise ValidationError({"as_of": [_("Enter a valid date.")]})
    if as_of > timezone.localdate():
        raise ValidationError({"as_of": [_("An opening balance cannot be dated in the future.")]})
    return amount, as_of, str(data.get("note") or "")[:255]


@transaction.atomic
def record_customer_opening_balance(customer, user, data):
    from inventory.models import Warehouse
    from sales.models import Invoice
    from sales.numbering import allocate_invoice_number

    amount, as_of, note = parse_request(data, user)
    if customer.invoices.filter(is_opening_balance=True, is_void=False).exists():
        raise ValidationError(
            {"detail": _("This customer already has an opening balance. Correct it with a "
                         "credit note instead of adding another.")}
        )
    branch = getattr(user, "branch", None) or customer.company.branches.order_by("pk").first()
    warehouses = Warehouse.objects.filter(company=customer.company).order_by("pk")
    warehouse = (
        warehouses.filter(branch=branch).first() if branch is not None else None
    ) or warehouses.first()
    if warehouse is None:
        raise ValidationError({"detail": _("Create a warehouse before recording balances.")})
    issued_at = timezone.make_aware(
        datetime.combine(as_of, time.min), timezone.get_current_timezone()
    )
    return Invoice.objects.create(
        company=customer.company, customer=customer, branch=branch, warehouse=warehouse,
        number=allocate_invoice_number(customer.company_id),
        subtotal=amount, total=amount, issued_at=issued_at, due_date=as_of,
        payment_terms_days=0, is_opening_balance=True, created_by=user,
        local_reference=note[:48],
    )


@transaction.atomic
def record_supplier_opening_balance(supplier, user, data):
    from purchasing.models import Bill

    amount, as_of, note = parse_request(data, user)
    if supplier.bills.filter(is_opening_balance=True, is_void=False).exists():
        raise ValidationError(
            {"detail": _("This supplier already has an opening balance. Correct it with a "
                         "debit note instead of adding another.")}
        )
    company = supplier.company
    return Bill.objects.create(
        company=company, supplier=supplier,
        supplier_invoice_number=(note or f"OPENING-{as_of.isoformat()}")[:64],
        subtotal=amount, total=amount, due_date=as_of, payment_terms_days=0,
        currency=getattr(company, "currency", "") or "", exchange_rate=Decimal("1"),
        is_opening_balance=True, created_by=user,
    )
