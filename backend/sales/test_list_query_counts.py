"""Review F20: list endpoints must not issue a query per row.

The invoice list once cost 24 queries for one invoice and 195 for ten.
These tests pin a constant bound: the same number of queries for one
invoice as for ten, each with lines, payments and credit notes — and the
same for the costed valuation report across products.
"""
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product, StockMovement, Warehouse
from org.models import Branch, Company
from returns.models import CreditNote
from sales.models import Customer, Invoice, InvoiceLine, Payment, Refund


class ListQueryCountTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        owner = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=owner,
        )
        self.wh = Warehouse.objects.create(company=self.company, branch=self.branch, name="WH")
        self.customer = Customer.objects.create(company=self.company, name="Ahmed")
        self.products = [
            Product.objects.create(
                company=self.company, sku=f"S{i}", name=f"P{i}",
                cost_price=Decimal("5"), sale_price=Decimal("10"),
            )
            for i in range(10)
        ]
        self.client.force_authenticate(self.owner)

    def _invoice(self, number):
        invoice = Invoice.objects.create(
            company=self.company, customer=self.customer, warehouse=self.wh,
            branch=self.branch, number=number, subtotal=Decimal("100"), total=Decimal("100"),
        )
        for product in self.products[:3]:
            InvoiceLine.objects.create(
                invoice=invoice, product=product, quantity=Decimal("2"),
                unit_price=Decimal("10"), line_subtotal=Decimal("20"), line_total=Decimal("20"),
            )
            StockMovement.objects.create(
                company=self.company, product=product, warehouse=self.wh,
                movement_type=StockMovement.SALE_OUT, quantity=Decimal("-2"),
                unit_cost=Decimal("5"), reference_type="Invoice", reference_id=str(invoice.pk),
            )
        Payment.objects.create(
            company=self.company, invoice=invoice, method="cash", amount=Decimal("30"),
        )
        Payment.objects.create(
            company=self.company, invoice=invoice, method="cash", amount=Decimal("20"),
        )
        note = CreditNote.objects.create(
            company=self.company, customer=self.customer, invoice=invoice,
            amount=Decimal("10"),
        )
        Refund.objects.create(
            company=self.company, credit_note=note, method="cash", amount=Decimal("5"),
        )
        return invoice

    def _count(self, url, params=None):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(url, params or {})
        self.assertEqual(response.status_code, 200, response.data)
        return len(captured), response

    def test_invoice_list_queries_do_not_grow_with_invoices(self):
        self._invoice(1)
        one, response = self._count(reverse("invoice-list"))
        rows = response.data.get("results", response.data)
        self.assertEqual(len(rows), 1)
        self.assertEqual(Decimal(rows[0]["amount_due"]), Decimal("45"))
        for number in range(2, 11):
            self._invoice(number)
        ten, response = self._count(reverse("invoice-list"))
        rows = response.data.get("results", response.data)
        self.assertEqual(len(rows), 10)
        self.assertEqual({Decimal(r["amount_due"]) for r in rows}, {Decimal("45")})
        self.assertEqual({r["status"] for r in rows}, {"partially_paid"})
        self.assertEqual(ten, one, f"{one} queries for one invoice, {ten} for ten")
        self.assertLessEqual(ten, 8)

    def test_valuation_report_queries_do_not_grow_with_products(self):
        for product in self.products:
            StockMovement.objects.create(
                company=self.company, product=product, warehouse=self.wh,
                movement_type=StockMovement.PURCHASE_IN, quantity=Decimal("4"),
                unit_cost=Decimal("5"),
            )
        self._invoice(1)
        url = reverse("report-inventory-valuation")
        for method in ("average", "fifo"):
            with self.subTest(method=method):
                ten, response = self._count(url, {"method": method})
                self.assertEqual(len(response.data["items"]), 10)
                self.assertLessEqual(ten, 5, f"{ten} queries for ten products")
