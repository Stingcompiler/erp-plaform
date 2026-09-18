"""The supplier-payments list carries what a ledger screen needs.

Filters mirror the customer side (`?unverified=1`, `?method=`), and the row
names the supplier, bill and people so the screen never has to join them.
"""

from decimal import Decimal

from purchasing.models import Bill, SupplierPayment
from purchasing.tests import PurchasingBase


class SupplierPaymentLedgerTests(PurchasingBase):
    def setUp(self):
        super().setUp()
        self.bill = Bill.objects.create(
            company=self.company_a, supplier=self.supplier, supplier_invoice_number="B-1",
            subtotal=Decimal("300"), total=Decimal("300"),
        )
        self.cash = SupplierPayment.objects.create(
            company=self.company_a, supplier=self.supplier, bill=self.bill,
            method="cash", amount=Decimal("100"), recorded_by=self.user_a,
        )
        self.bank = SupplierPayment.objects.create(
            company=self.company_a, supplier=self.supplier, bill=self.bill,
            method="bank_transfer", amount=Decimal("50"), recorded_by=self.user_a,
            from_bank_account=self.bank_a,
        )

    def _rows(self, **params):
        response = self.client.get("/api/supplier-payments/", params)
        self.assertEqual(response.status_code, 200)
        return response.data["results"]

    def test_rows_carry_display_names(self):
        row = next(r for r in self._rows() if r["id"] == self.bank.id)
        self.assertEqual(row["supplier_name"], "Acme")
        self.assertEqual(row["bill_number"], "B-1")
        self.assertEqual(row["from_bank_account_name"], self.bank_a.bank_name)
        self.assertEqual(row["recorded_by_name"], self.user_a.full_name)
        self.assertIsNone(row["verified_by_name"])

    def test_method_and_unverified_filters(self):
        self.assertEqual([r["id"] for r in self._rows(method="cash")], [self.cash.id])
        self.assertEqual(len(self._rows(unverified="1")), 2)
        SupplierPayment.objects.filter(pk=self.cash.pk).update(verified_by=self.user_a)
        from django.utils import timezone
        SupplierPayment.objects.filter(pk=self.cash.pk).update(verified_at=timezone.now())
        self.assertEqual([r["id"] for r in self._rows(unverified="1")], [self.bank.id])
