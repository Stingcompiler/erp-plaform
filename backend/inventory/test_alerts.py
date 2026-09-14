from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import Role, User
from core.models import ActivityLog
from inventory.alerts import expiring_batches, negative_stock
from inventory.models import Product, StockBatch, StockMovement, Warehouse
from inventory.tasks import scan_stock_alerts
from org.models import Branch, Company


class StockAlertTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Pharma")
        branch = Branch.objects.create(company=self.company, name="Main")
        self.wh = Warehouse.objects.create(company=self.company, branch=branch, name="WH")
        self.product = Product.objects.create(
            company=self.company, sku="P", name="P", sale_price=1, track_batches=True
        )
        today = timezone.now().date()
        self._lot("SOON", today + timedelta(days=10), 5)
        self._lot("LATER", today + timedelta(days=90), 5)
        self._lot("EMPTY", today + timedelta(days=5), 0)
        self.neg = Product.objects.create(company=self.company, sku="N", name="N", sale_price=1)
        StockMovement.objects.create(
            company=self.company,
            product=self.neg,
            warehouse=self.wh,
            movement_type=StockMovement.SALE_OUT,
            quantity=Decimal("-3"),
        )

    def _lot(self, lot, expiry, qty):
        batch = StockBatch.objects.create(
            company=self.company, product=self.product, lot_number=lot, expiry_date=expiry
        )
        if qty:
            StockMovement.objects.create(
                company=self.company,
                product=self.product,
                warehouse=self.wh,
                batch=batch,
                movement_type=StockMovement.PURCHASE_IN,
                quantity=qty,
            )
        return batch

    def test_expiring_batches_only_counts_lots_with_stock_inside_horizon(self):
        lots = [b.lot_number for b in expiring_batches(self.company.pk)]
        self.assertEqual(lots, ["SOON"])

    def test_negative_stock_lists_ledger_deficits(self):
        self.assertEqual([p.sku for p in negative_stock(self.company.pk)], ["N"])

    def test_daily_scan_logs_a_summary_per_company(self):
        summary = scan_stock_alerts()
        self.assertEqual(summary[self.company.pk]["expiring_batches"], 1)
        self.assertEqual(summary[self.company.pk]["negative_stock"], 1)
        row = ActivityLog.objects.get(entity_type="StockAlerts", company=self.company)
        self.assertEqual(row.metadata["negative_stock"], 1)

    def test_dashboard_exposes_the_counts(self):
        from django.urls import reverse
        from rest_framework.test import APIClient

        owner = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        user = User.objects.create_user("o@p.test", "passw0rd123", company=self.company, role=owner)
        client = APIClient()
        client.force_authenticate(user)
        inventory = client.get(reverse("dashboard")).data["sections"]["inventory"]
        self.assertEqual(inventory["expiring_batch_count"], 1)
        self.assertEqual(inventory["negative_stock_count"], 1)
