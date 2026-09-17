"""Read-only customer receivables queries.

The customer debt screen is deliberately derived from invoices, payments and
credit notes.  It does not persist a second editable balance, so a list, a
statement and a printed export use the same source of truth.
"""
from datetime import datetime, time
from decimal import Decimal

from django.db.models import Prefetch, Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from returns.models import CreditNote
from sales.models import Customer, Invoice, Payment, Refund

ZERO = Decimal("0")


def _branch_id(user):
    role = getattr(user, "role", None)
    if role and role.scope_level == "branch":
        return getattr(user, "branch_id", None)
    return None


def _branch_filter(branch_id, prefix=""):
    if branch_id is None:
        return Q()
    return Q(**{f"{prefix}branch_id": branch_id})


def _invoice_queryset(user):
    """Invoices visible to a user, with every monetary child prefetched."""
    qs = Invoice.objects.filter(
        company_id=user.company_id,
        customer__isnull=False,
        is_void=False,
    ).filter(_branch_filter(_branch_id(user)))
    return qs.prefetch_related(
        Prefetch("payments", queryset=Payment.objects.order_by("recorded_at", "pk")),
        Prefetch(
            "credit_notes",
            queryset=CreditNote.objects.filter(is_void=False)
            .order_by("created_at", "pk")
            .prefetch_related(
                Prefetch("refunds", queryset=Refund.objects.order_by("recorded_at", "pk"))
            ),
        ),
    )


def _standalone_credits(user):
    qs = CreditNote.objects.filter(
        company_id=user.company_id,
        is_void=False,
        invoice__isnull=True,
    )
    # A standalone note carries no branch. It is an executive-only financial
    # row until it can be assigned to a branch, so a branch user never sees it.
    if _branch_id(user) is not None:
        return qs.none()
    return qs.order_by("created_at", "pk")


def _money(value):
    return str(value.quantize(Decimal("0.01")))


def _invoice_balance(invoice):
    payments = sum((payment.amount for payment in invoice.payments.all()), ZERO)
    credits = ZERO
    refunds = ZERO
    for note in invoice.credit_notes.all():
        credits += note.amount
        refunds += sum((refund.amount for refund in note.refunds.all()), ZERO)
    return invoice.total - payments - credits + refunds


def _by_customer(invoices):
    """Group once, so a page of customers costs O(invoices), not
    O(customers × invoices)."""
    grouped = {}
    for invoice in invoices:
        grouped.setdefault(invoice.customer_id, []).append(invoice)
    return grouped


def _customer_events(customer, invoices, standalone_credits):
    """Return statement events in ascending financial order.

    Invoices debit the account; payments and credit notes credit it.  A single
    event shape keeps statement, CSV and future print documents consistent.
    """
    events = []
    for invoice in invoices:
        if invoice.customer_id != customer.id:
            continue
        events.append({
            "date": invoice.issued_at,
            "type": "invoice",
            "reference": invoice.number_display,
            "debit": invoice.total,
            "credit": ZERO,
            "due_date": invoice.due_date,
        })
        for payment in invoice.payments.all():
            events.append({
                "date": payment.recorded_at,
                "type": "payment",
                "reference": invoice.number_display,
                "debit": ZERO,
                "credit": payment.amount,
                "method": payment.method,
            })
        for note in invoice.credit_notes.all():
            events.append({
                "date": note.created_at,
                "type": "credit_note",
                "reference": note.number_display,
                "debit": ZERO,
                "credit": note.amount,
                "reason": note.reason,
            })
            for refund in note.refunds.all():
                events.append({
                    "date": refund.recorded_at,
                    "type": "refund",
                    "reference": note.number_display,
                    "debit": refund.amount,
                    "credit": ZERO,
                    "method": refund.method,
                })
    for note in standalone_credits:
        if note.customer_id == customer.id:
            events.append({
                "date": note.created_at,
                "type": "credit_note",
                "reference": note.number_display,
                "debit": ZERO,
                "credit": note.amount,
                "reason": note.reason,
            })
    return sorted(events, key=lambda row: (row["date"], row["type"], row["reference"]))


def _customer_totals(customer, invoices, standalone_credits):
    outstanding = ZERO
    credit_balance = ZERO
    overdue = ZERO
    today = timezone.localdate()
    for invoice in invoices:
        if invoice.customer_id != customer.id:
            continue
        due = _invoice_balance(invoice)
        if due > ZERO:
            outstanding += due
            if invoice.due_date and invoice.due_date < today:
                overdue += due
        elif due < ZERO:
            credit_balance += -due
    credit_balance += sum(
        (note.amount for note in standalone_credits if note.customer_id == customer.id), ZERO
    )
    return outstanding, overdue, credit_balance


def _date_param(params, key, end=False):
    raw = params.get(key)
    if not raw:
        return None
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValidationError({key: "Use a valid YYYY-MM-DD date."}) from exc
    return timezone.make_aware(datetime.combine(parsed, time.max if end else time.min))


def statement(user, customer):
    invoices = list(_invoice_queryset(user).filter(customer_id=customer.id))
    credits = list(_standalone_credits(user).filter(customer_id=customer.id))
    return _customer_events(customer, invoices, credits)


def statement_for_period(user, customer, params):
    start = _date_param(params, "start")
    end = _date_param(params, "end", end=True)
    if start and end and start > end:
        raise ValidationError({"end": "End date must not precede start date."})
    opening = ZERO
    rows = []
    for event in statement(user, customer):
        delta = event["debit"] - event["credit"]
        if start and event["date"] < start:
            opening += delta
            continue
        if end and event["date"] > end:
            continue
        rows.append({**event, "delta": delta})
    balance = opening
    result = []
    for event in rows:
        balance += event["delta"]
        result.append({
            **event,
            "date": event["date"].isoformat(),
            "debit": _money(event["debit"]),
            "credit": _money(event["credit"]),
            "balance": _money(balance),
        })
    return {
        "opening_balance": _money(opening),
        "closing_balance": _money(balance),
        "events": result,
    }


def customer_debts(user, params):
    """Page the debt list after calculating the same totals used by statements."""
    query = (params.get("search") or "").strip()
    status = params.get("status") or ""
    try:
        page = max(int(params.get("page", 1)), 1)
    except (TypeError, ValueError):
        raise ValidationError({"page": "Use a positive integer."})
    try:
        page_size = min(max(int(params.get("page_size", 50)), 1), 100)
    except (TypeError, ValueError):
        raise ValidationError({"page_size": "Use a positive integer."})
    customers = Customer.objects.filter(company_id=user.company_id, is_active=True)
    if query:
        customers = customers.filter(Q(name__icontains=query) | Q(phone__icontains=query))
    grouped = _by_customer(_invoice_queryset(user))
    credits = list(_standalone_credits(user))
    rows = []
    for customer in customers.order_by("name", "pk"):
        outstanding, overdue, credit = _customer_totals(
            customer, grouped.get(customer.id, []), credits
        )
        row_status = (
            "overdue" if overdue else "owing" if outstanding
            else "credit" if credit else "settled"
        )
        if outstanding == ZERO and credit == ZERO:
            continue
        if status and row_status != status:
            continue
        rows.append({
            "id": customer.id,
            "name": customer.name,
            "phone": customer.phone,
            "outstanding": _money(outstanding),
            "overdue": _money(overdue),
            "credit_balance": _money(credit),
            "status": row_status,
        })
    count = len(rows)
    offset = (page - 1) * page_size
    return {
        "count": count,
        "page": page,
        "page_size": page_size,
        "results": rows[offset:offset + page_size],
    }


def debt_summary(user):
    grouped = _by_customer(_invoice_queryset(user))
    credits = list(_standalone_credits(user))
    customers = Customer.objects.filter(company_id=user.company_id, is_active=True)
    outstanding = overdue = credit_balance = ZERO
    debtor_count = 0
    for customer in customers:
        due, late, credit = _customer_totals(customer, grouped.get(customer.id, []), credits)
        outstanding += due
        overdue += late
        credit_balance += credit
        debtor_count += int(due > ZERO)
    return {
        "outstanding": _money(outstanding),
        "overdue": _money(overdue),
        "credit_balance": _money(credit_balance),
        "debtor_count": debtor_count,
    }
