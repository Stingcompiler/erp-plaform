"""The dashboard and the income statement report one revenue figure.

The overview used to sum invoice totals (gross, tax-inclusive, returns
ignored) while the P&L netted returns and price-correction notes before
tax — two numbers for the same period. Both now come from one formula.
"""

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Role, User
from inventory.models import Product, Warehouse
from org.models import Branch, Company
from returns.models import CreditNote
from sales.models import Customer, Invoice, InvoiceLine


class RevenueParityTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        branch = Branch.objects.create(company=self.company, name="Main")
        role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123", company=self.company, role=role,
        )
        wh = Warehouse.objects.create(company=self.company, branch=branch, name="W")
        product = Product.objects.create(company=self.company, sku="P", name="Thing")
        customer = Customer.objects.create(company=self.company, name="Buyer")
        invoice = Invoice.objects.create(
            company=self.company, customer=customer, branch=branch, warehouse=wh, number=1,
            subtotal=Decimal("100"), tax_amount=Decimal("0"), total=Decimal("100"),
        )
        InvoiceLine.objects.create(
            invoice=invoice, product=product, quantity=Decimal("2"), unit_price=Decimal("50"),
            line_subtotal=Decimal("100"), line_total=Decimal("100"),
        )
        # A goodwill / price-correction note (tax-free company, so 23 net).
        CreditNote.objects.create(
            company=self.company, customer=customer, invoice=invoice,
            amount=Decimal("23"), created_by=self.owner,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_dashboard_matches_income_statement(self):
        dashboard = self.client.get("/api/dashboard/")
        self.assertEqual(dashboard.status_code, 200, dashboard.data)
        statement = self.client.get("/api/reports/income-statement/")
        self.assertEqual(statement.status_code, 200, statement.data)
        overview = Decimal(dashboard.data["sections"]["sales"]["revenue_total"])
        pnl = Decimal(statement.data["revenue"])
        self.assertEqual(overview, pnl)
        # Net of the note — not the bare invoice total.
        self.assertEqual(pnl, Decimal("77.00"))
