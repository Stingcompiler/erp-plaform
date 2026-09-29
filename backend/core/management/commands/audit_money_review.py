"""Read-only count of rows written before the 2026-09-28 money review fixes.

Nothing is changed: historic rows are reported so the owner can decide on
each. Costing figures (FIFO/average returns, voids and purchase returns)
are derived by replaying the ledger, so they correct themselves and need no
data change; they are counted only to show how many documents move.

    python manage.py audit_money_review [--company <id>]
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Count historic rows affected by the 2026-09-28 money review (read-only)."

    def add_arguments(self, parser):
        parser.add_argument("--company", type=int, default=None)

    def handle(self, *args, **options):
        from core.timezone import company_zone
        from inventory.models import StockMovement
        from purchasing.models import Bill
        from subscriptions.models import SubscriptionInvoice
        from subscriptions.services import period_end_at

        scope = {"company_id": options["company"]} if options["company"] else {}

        returns = StockMovement.objects.filter(
            movement_type=StockMovement.SALES_RETURN_IN,
            reference_type__in=("SalesReturn", "InvoiceVoid"), **scope,
        ).count()
        purchase_returns = StockMovement.objects.filter(
            movement_type=StockMovement.PURCHASE_RETURN_OUT, **scope,
        ).count()
        counts_without_cost = StockMovement.objects.filter(
            reference_type="StockCount", unit_cost__isnull=True, **scope,
        ).count()

        early_bills = 0
        for bill in Bill.objects.filter(due_date__isnull=False, **scope).select_related(
            "company"
        ).iterator():
            local = timezone.localtime(bill.created_at, company_zone(bill.company)).date()
            expected = local + timedelta(days=bill.payment_terms_days or 0)
            if bill.due_date == expected - timedelta(days=1):
                early_bills += 1

        past_periods = 0
        for invoice in SubscriptionInvoice.objects.filter(
            entitlement_granted_at__isnull=False, **scope,
        ).select_related("company").iterator():
            if period_end_at(invoice.company, invoice.period_end) < invoice.entitlement_granted_at:
                past_periods += 1

        rows = [
            ("return/void stock movements re-valued by FIFO/average replay "
             "(derived, no change needed)", returns),
            ("purchase-return movements re-valued by FIFO/average replay "
             "(derived, no change needed)", purchase_returns),
            ("stock-count adjustments with no unit_cost (costed at today's price)",
             counts_without_cost),
            ("bills whose due date is one day early (UTC date)", early_bills),
            ("subscription invoices granted after their period had ended", past_periods),
        ]
        for label, count in rows:
            self.stdout.write(f"{count:>8}  {label}")
