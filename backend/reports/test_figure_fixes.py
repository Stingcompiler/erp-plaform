"""Report figures that were wrong or silently missing (review 2026-09-24).

Each test names the number an owner would have been shown and the one the
books support.
"""

from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Role, User
from finance.models import Expense
from inventory.costing import company_totals
from inventory.models import Product, StockMovement, Warehouse
from org.models import Branch, Company
from purchasing.models import Bill, Supplier, SupplierPayment
from returns.models import CreditNote, SalesReturn, SalesReturnLine
from sales.models import CashShift, Customer, Invoice, InvoiceLine


class ReportFigureTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Figures")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        role = Role.objects.create(name="Business Owner", scope_level="business")
        self.user = User.objects.create_user(
            email="owner@figures.test", password="Asecurepass123",
            company=self.company, role=role,
        )
        self.client.force_authenticate(self.user)
        self.product = Product.objects.create(
            company=self.company, name="Widget", sku="W", cost_price=6,
        )
        self.wh = Warehouse.objects.create(company=self.company, branch=self.branch, name="Main")
        self.customer = Customer.objects.create(company=self.company, name="Customer")
        self.invoice = Invoice.objects.create(
            company=self.company, warehouse=self.wh, customer=self.customer, number=1,
            subtotal=100, total=100,
        )
        self.line = InvoiceLine.objects.create(
            invoice=self.invoice, product=self.product, quantity=10, unit_price=10,
            line_subtotal=100, line_total=100,
        )

    def revenue(self):
        return Decimal(self.client.get("/api/reports/income-statement/").data["revenue"])

    def test_correcting_an_opening_balance_does_not_lower_revenue(self):
        opening = Invoice.objects.create(
            company=self.company, warehouse=self.wh, customer=self.customer, number=2,
            subtotal=500, total=500, is_opening_balance=True,
        )
        CreditNote.objects.create(
            company=self.company, customer=self.customer, invoice=opening, amount=50,
            created_by=self.user,
        )
        self.assertEqual(self.revenue(), Decimal("100.00"))

    def test_a_return_whose_credit_note_was_voided_counts_as_sold_again(self):
        sales_return = SalesReturn.objects.create(
            company=self.company, invoice=self.invoice, customer=self.customer,
            created_by=self.user,
        )
        SalesReturnLine.objects.create(
            sales_return=sales_return, invoice_line=self.line, product=self.product,
            quantity=2,
        )
        note = CreditNote.objects.create(
            company=self.company, customer=self.customer, invoice=self.invoice,
            sales_return=sales_return, amount=20, created_by=self.user,
        )
        self.assertEqual(self.revenue(), Decimal("80.00"))
        note.is_void = True
        note.save(update_fields=["is_void"])
        self.assertEqual(self.revenue(), Decimal("100.00"))

    def test_a_foreign_currency_supplier_payment_is_converted(self):
        supplier = Supplier.objects.create(company=self.company, name="Importer")
        bill = Bill.objects.create(
            company=self.company, supplier=supplier, currency="USD",
            exchange_rate=Decimal("600"), total=Decimal("10"),
        )
        SupplierPayment.objects.create(
            company=self.company, supplier=supplier, bill=bill, method="cash",
            amount=Decimal("10"), currency="USD", exchange_rate=Decimal("600"),
            recorded_by=self.user,
        )
        data = self.client.get("/api/reports/cash-flow/").data
        self.assertEqual(Decimal(data["supplier_payments"]), Decimal("6000"))

    def test_petty_cash_from_the_till_reaches_expenses_and_cash_flow(self):
        shift = CashShift.objects.create(
            company=self.company, branch=self.branch, opened_by=self.user,
            opening_float=Decimal("100"),
        )
        response = self.client.post(
            reverse("drawermovement-list"),
            {"shift": shift.id, "kind": "petty", "amount": "-25", "reason": "Transport"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        expense = Expense.objects.get(category=Expense.CATEGORY_PETTY_CASH)
        self.assertEqual(expense.amount, Decimal("25"))
        self.assertEqual(shift.expected_cash(), Decimal("75"))  # drawer counted once
        cash_flow = self.client.get("/api/reports/cash-flow/").data
        self.assertEqual(Decimal(cash_flow["expenses"]), Decimal("25"))

    def test_a_voided_sale_costs_nothing_in_any_period_under_fifo(self):
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.PURCHASE_IN, quantity=10, unit_cost=6,
        )
        void = Invoice.objects.create(
            company=self.company, warehouse=self.wh, customer=self.customer, number=3,
            subtotal=40, total=40, is_void=True,
        )
        # Sold last month, voided today: before the fix FIFO/average charged
        # 24 of cost last month and credited it back this month.
        last_month = timezone.now() - timedelta(days=35)
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.SALE_OUT, quantity=-4, unit_cost=6,
            reference_type="Invoice", reference_id=str(void.pk), created_at=last_month,
        )
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.SALES_RETURN_IN, quantity=4, unit_cost=6,
            reference_type="InvoiceVoid", reference_id=str(void.pk),
        )
        today = timezone.localdate()
        sold_on = timezone.localtime(last_month).date()
        for method in ("standard", "average", "fifo"):
            for day in (sold_on, today):
                totals = company_totals(self.company.id, method=method, start=day, end=day)
                self.assertEqual(totals["cogs"], Decimal("0"), f"{method} {day}")
