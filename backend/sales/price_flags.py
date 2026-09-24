"""The price-review worklist: sales kept although the till should have
refused their price.

An offline till cannot ask a manager, so a sale replayed from the queue
below cost or beyond the discount limit is recorded as it happened and the
audit row `pos_price_unapproved` is flagged `needs_review` (see
POSCheckoutSerializer._enforce_price_rules). This module lists those rows
that no one has reviewed yet — scoped to the company, and to the branch of a
branch manager — and records a review (sales.PriceFlagReview)."""

from django.db.models import CharField, Exists, OuterRef
from django.db.models.functions import Cast

from core.attention import branch_scope

FLAG_ACTION = "pos_price_unapproved"
MAX_ROWS = 200


def _unreviewed_logs(user, since=None):
    from core.models import ActivityLog
    from sales.models import PriceFlagReview

    logs = ActivityLog.objects.filter(
        company_id=user.company_id, action=FLAG_ACTION, entity_type="Invoice"
    )
    if since is not None:
        logs = logs.filter(created_at__gt=since)
    # entity_id is text; the review's invoice id is cast to text (always
    # safe) rather than the other way round.
    reviewed = PriceFlagReview.objects.annotate(
        key=Cast("invoice_id", CharField())
    ).filter(company_id=user.company_id, key=OuterRef("entity_id"))
    return logs.filter(~Exists(reviewed)).order_by("-created_at")


def _scoped_invoices(user, logs):
    from sales.models import Invoice

    ids = {int(log.entity_id) for log in logs if str(log.entity_id).isdigit()}
    invoices = Invoice.objects.filter(company_id=user.company_id, pk__in=ids)
    branch_id = branch_scope(user)
    if branch_id is not None:
        invoices = invoices.filter(branch_id=branch_id)
    return {
        invoice.pk: invoice
        for invoice in invoices.select_related("branch", "created_by")
    }


def unreviewed_flags(user, since=None, limit=MAX_ROWS):
    """[(log, invoice)] newest first, only the invoices this user may see."""
    logs = list(_unreviewed_logs(user, since)[:limit])
    invoices = _scoped_invoices(user, logs)
    return [
        (log, invoices[int(log.entity_id)])
        for log in logs
        if str(log.entity_id).isdigit() and int(log.entity_id) in invoices
    ]


def is_flagged(invoice):
    from core.models import ActivityLog

    return ActivityLog.objects.filter(
        company_id=invoice.company_id, action=FLAG_ACTION,
        entity_type="Invoice", entity_id=str(invoice.pk),
    ).exists()


def _breach_row(breach):
    return {
        "sku": breach.get("sku", ""),
        "rule": breach.get("rule", ""),
        "list": breach.get("list"),
        # Rows written before the list price was logged carry only `price`.
        "sold": breach.get("sold") or breach.get("price"),
        "percent": breach.get("percent"),
    }


def serialize(log, invoice):
    metadata = log.metadata or {}
    breaches = [_breach_row(b) for b in metadata.get("breaches") or [] if isinstance(b, dict)]
    cashier = invoice.created_by
    percents = [b["percent"] for b in breaches if b.get("percent")]
    return {
        "id": log.pk,
        "invoice": invoice.pk,
        "invoice_number": invoice.number_display,
        "is_void": invoice.is_void,
        "issued_at": invoice.issued_at,
        "flagged_at": log.created_at,
        "cashier": (cashier.full_name or cashier.email) if cashier else "",
        "branch": invoice.branch.name if invoice.branch_id else "",
        "total": str(invoice.total),
        "limit": metadata.get("limit"),
        "discount_percent": max(percents, key=lambda value: float(value)) if percents else None,
        "breaches": breaches,
    }
