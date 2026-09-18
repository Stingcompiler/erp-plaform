"""Payables reported in the company currency, not in a mix of document
currencies. A bill records its own currency and the day's rate; every
company-level figure converts at that rate. The bill itself still settles
in its own currency, so "amount due" on the document is unchanged.
"""

from decimal import Decimal

from django.urls import reverse
from rest_framework import status

from purchasing.models import Bill, SupplierPayment
from purchasing.querysets import open_bills, payable_total
from purchasing.tests import PurchasingBase


class ApCurrencyTests(PurchasingBase):
    def setUp(self):
        super().setUp()
        # 100 USD at 600 SDG/USD, 40 USD already paid at the same rate.
        self.usd = Bill.objects.create(
            company=self.company_a, supplier=self.supplier, supplier_invoice_number="B-USD",
            subtotal=Decimal("100"), total=Decimal("100"),
            currency="USD", exchange_rate=Decimal("600"),
        )
        SupplierPayment.objects.create(
            company=self.company_a, supplier=self.supplier, bill=self.usd,
            method="cash", amount=Decimal("40"), currency="USD",
            exchange_rate=Decimal("600"), recorded_by=self.user_a,
        )
        # 500 SDG bill, untouched.
        self.sdg = Bill.objects.create(
            company=self.company_a, supplier=self.supplier, supplier_invoice_number="B-SDG",
            subtotal=Decimal("500"), total=Decimal("500"),
            currency="SDG", exchange_rate=Decimal("1"),
        )

    def test_document_balance_stays_in_its_currency(self):
        self.assertEqual(self.usd.amount_due(), Decimal("60"))
        row = open_bills(Bill.objects.filter(pk=self.usd.pk)).get()
        self.assertEqual(row.outstanding, Decimal("60"))
        self.assertEqual(row.outstanding_base, Decimal("36000"))

    def test_company_totals_convert(self):
        self.assertEqual(
            payable_total(Bill.objects.filter(company=self.company_a)), Decimal("36500")
        )
        self.assertEqual(self.supplier.ap_balance(), Decimal("36500.00"))

    def test_reports_read_the_converted_figure(self):
        aging = self.client.get(reverse("report-ap-aging"))
        self.assertEqual(aging.status_code, status.HTTP_200_OK, aging.content)
        self.assertIn("36500", str(aging.data))
        self.assertNotIn("\"560", str(aging.data))  # never the raw 60 + 500 mix
        due = self.client.get(reverse("report-payables-due"))
        self.assertEqual(due.status_code, status.HTTP_200_OK, due.content)
        self.assertIn("36000", str(due.data))
