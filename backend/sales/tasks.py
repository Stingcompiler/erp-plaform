"""
Scheduled receivables tasks, run by the `erp-worker` Celery service.

No email/SMS transport is configured in this project, so this task does not
pretend to deliver messages. It scans for invoices that are overdue or falling
due, and records an auditable summary in the ActivityLog. The same data is
served to the UI by the receivables-due endpoint as a collections worklist.
Wiring an actual delivery channel is a configuration step (EMAIL_* settings or
an SMS provider) and is intentionally left out rather than stubbed.
"""
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from core.activity import log_activity

# How far ahead an invoice counts as "due soon".
DUE_SOON_DAYS = 7


def due_invoices(company_id=None, horizon_days=DUE_SOON_DAYS):
    """Unpaid, non-void invoices already overdue or due within the horizon."""
    from sales.models import Invoice

    from sales.querysets import open_invoices

    horizon = timezone.localdate() + timedelta(days=horizon_days)
    qs = Invoice.objects.filter(due_date__lte=horizon).select_related("customer")
    if company_id is not None:
        qs = qs.filter(company_id=company_id)
    # `outstanding` is annotated in SQL, so the filter runs in the database.
    return list(open_invoices(qs))


@shared_task
def scan_due_receivables():
    """Record a per-company summary of overdue / due-soon receivables."""
    from org.models import Company

    summary = {}
    for company in Company.objects.all():
        invoices = due_invoices(company_id=company.id)
        if not invoices:
            continue
        today = timezone.localdate()
        overdue = [i for i in invoices if i.due_date and i.due_date < today]
        total_overdue = sum((i.outstanding for i in overdue), start=0)
        summary[company.id] = {
            "due_or_overdue": len(invoices),
            "overdue": len(overdue),
            "overdue_amount": str(total_overdue),
        }
        log_activity(
            action="reminder_scan",
            company=company,
            entity_type="Invoice",
            metadata=summary[company.id],
        )
    return summary
