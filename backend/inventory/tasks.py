"""Daily stock scan, run by the `erp-worker` Celery beat.

Records one auditable summary per company (low stock, expiring batches,
negative balances). No message transport is configured in this project, so
nothing is "sent"; the dashboard shows the same figures live, and the
ActivityLog row is the durable trail that the scan happened and what it saw.
"""

from celery import shared_task
from django.utils import timezone

from core.activity import log_activity


@shared_task
def scan_stock_alerts():
    from inventory.alerts import expiring_batches, low_stock, negative_stock
    from org.models import Company

    today = timezone.now().date()
    summary = {}
    for company in Company.objects.filter(is_active=True):
        expiring = list(expiring_batches(company.pk))
        payload = {
            "low_stock": low_stock(company.pk).count(),
            "expiring_batches": len(expiring),
            "expired_with_stock": sum(1 for batch in expiring if batch.expiry_date < today),
            "negative_stock": negative_stock(company.pk).count(),
        }
        if any(payload.values()):
            log_activity(
                action="scan",
                company=company,
                entity_type="StockAlerts",
                entity_id=company.pk,
                metadata=payload,
            )
        summary[company.pk] = payload
    return summary
