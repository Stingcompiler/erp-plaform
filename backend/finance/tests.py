from datetime import date, timedelta
from decimal import Decimal

from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from finance.models import Expense
from inventory.models import Warehouse
from org.models import Company
from sales.models import CompanyBankAccount, Customer, Invoice, Payment


class FinanceTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.other = Company.objects.create(name="Beta")
        self.role = Role.objects.create(
            name="Finance Department", scope_level=Role.SCOPE_BUSINESS
        )
        self.user = User.objects.create_user(
            email="fin@alpha.test", password="passw0rd12345",
            company=self.company, role=self.role,
        )
        self.client.force_authenticate(self.user)

    def test_finance_role_can_record_expense(self):
        resp = self.client.post(
            reverse("expense-list"),
            {"category": "Rent", "amount": "1500.00", "date": "2026-07-01"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        exp = Expense.objects.get(pk=resp.data["id"])
        self.assertEqual(exp.company_id, self.company.id)
        self.assertEqual(exp.recorded_by_id, self.user.id)

    def test_expenses_are_company_scoped(self):
        Expense.objects.create(
            company=self.other, category="Rent", amount="9", date="2026-07-01"
        )
        self.client.post(
            reverse("expense-list"),
            {"category": "Utilities", "amount": "300", "date": "2026-07-02"},
            format="json",
        )
        resp = self.client.get(reverse("expense-list"))
        cats = [r["category"] for r in resp.data["results"]]
        self.assertIn("Utilities", cats)
        self.assertNotIn("Rent", cats)

    def test_summary_returns_revenue_expenses_net(self):
        Expense.objects.create(
            company=self.company, category="Rent", amount="1000", date="2026-07-01"
        )
        resp = self.client.get(reverse("expense-summary"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["expenses"], "1000.00")
        self.assertIn("revenue", resp.data)
        self.assertIn("net", resp.data)

    def test_non_finance_role_denied(self):
        hr_role = Role.objects.create(name="HR Officer", scope_level=Role.SCOPE_BRANCH)
        hr_user = User.objects.create_user(
            email="hr@alpha.test", password="passw0rd12345",
            company=self.company, role=hr_role,
        )
        self.client.force_authenticate(hr_user)
        resp = self.client.post(
            reverse("expense-list"),
            {"category": "Rent", "amount": "1", "date": "2026-07-01"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403, resp.data)


class BudgetTests(APITestCase):
    """Budgets are category-level and only bite once an approver activates them."""

    def setUp(self):
        self.company = Company.objects.create(name="BudgetCo")
        self.clerk_role = Role.objects.create(
            name="Finance Department", scope_level=Role.SCOPE_BUSINESS
        )
        self.cfo_role = Role.objects.create(
            name="Chief Financial Officer", scope_level=Role.SCOPE_BUSINESS
        )
        self.clerk = User.objects.create_user(
            email="clerk@budget.test", password="passw0rd12345",
            company=self.company, role=self.clerk_role,
        )
        self.cfo = User.objects.create_user(
            email="cfo@budget.test", password="passw0rd12345",
            company=self.company, role=self.cfo_role,
        )
        self.start = date.today().replace(day=1)
        self.end = self.start + timedelta(days=27)
        self.client.force_authenticate(self.clerk)

    def _create(self, lines=None):
        return self.client.post(
            reverse("budget-list"),
            {
                "name": "Plan",
                "period_start": str(self.start),
                "period_end": str(self.end),
                "lines": lines if lines is not None else [
                    {"kind": "expense", "category": "Rent", "planned_amount": "1000"}
                ],
            },
            format="json",
        )

    def test_created_as_draft(self):
        resp = self._create()
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["status"], "draft")

    def test_status_cannot_be_set_directly(self):
        budget_id = self._create().data["id"]
        resp = self.client.patch(
            reverse("budget-detail", args=[budget_id]),
            {"status": "approved"}, format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "draft")  # read-only field ignored

    def test_non_approver_cannot_approve(self):
        budget_id = self._create().data["id"]
        resp = self.client.post(reverse("budget-approve", args=[budget_id]))
        self.assertEqual(resp.status_code, 403, resp.data)

    def test_cfo_can_approve(self):
        budget_id = self._create().data["id"]
        self.client.force_authenticate(self.cfo)
        resp = self.client.post(reverse("budget-approve", args=[budget_id]))
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["status"], "approved")
        self.assertEqual(resp.data["approved_by_name"], self.cfo.email)

    def test_empty_budget_cannot_be_approved(self):
        budget_id = self._create(lines=[]).data["id"]
        self.client.force_authenticate(self.cfo)
        resp = self.client.post(reverse("budget-approve", args=[budget_id]))
        self.assertEqual(resp.status_code, 400, resp.data)

    def test_period_end_must_follow_start(self):
        resp = self.client.post(
            reverse("budget-list"),
            {
                "name": "Bad", "period_start": str(self.end),
                "period_end": str(self.start),
                "lines": [{"kind": "expense", "category": "X", "planned_amount": "1"}],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_variance_signs_are_correct(self):
        Expense.objects.create(
            company=self.company, category="Rent",
            amount=Decimal("1200"), date=date.today(),
        )
        budget_id = self._create().data["id"]
        resp = self.client.get(reverse("budget-variance", args=[budget_id]))
        self.assertEqual(resp.status_code, 200, resp.data)
        row = resp.data["rows"][0]
        # Planned 1000, spent 1200 -> over budget, therefore unfavourable.
        self.assertEqual(row["actual"], "1200.00")
        self.assertEqual(row["variance"], "-200.00")
        self.assertFalse(row["favourable"])


class BankBalanceTests(APITestCase):
    """Bank balances are derived from recorded movements, never stored."""

    def setUp(self):
        self.company = Company.objects.create(name="BankCo")
        self.role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        self.user = User.objects.create_user(
            email="own@bank.test", password="passw0rd12345",
            company=self.company, role=self.role,
        )
        self.account = CompanyBankAccount.objects.create(
            company=self.company, bank_name="B", account_name="A",
            opening_balance=Decimal("10000"),
        )
        self.client.force_authenticate(self.user)

    def test_balance_is_opening_plus_in_minus_out(self):
        from purchasing.models import Bill, Supplier, SupplierPayment
        wh = Warehouse.objects.create(company=self.company, name="W")
        cust = Customer.objects.create(company=self.company, name="C")
        inv = Invoice.objects.create(
            company=self.company, customer=cust, warehouse=wh, number=1,
            subtotal=Decimal("3000"), total=Decimal("3000"),
        )
        Payment.objects.create(
            company=self.company, invoice=inv, method="bank_transfer",
            company_bank_account=self.account, amount=Decimal("3000"),
            sender_bank_name="X", reference_last4="1234",
        )
        sup = Supplier.objects.create(company=self.company, name="S")
        bill = Bill.objects.create(
            company=self.company, supplier=sup, total=Decimal("1500")
        )
        SupplierPayment.objects.create(
            company=self.company, supplier=sup, bill=bill, method="bank_transfer",
            from_bank_account=self.account, amount=Decimal("1500"),
            reference_last4="9999",
        )
        self.assertEqual(self.account.balance(), Decimal("11500"))

    def test_balance_exposed_on_api(self):
        resp = self.client.get(reverse("bankaccount-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["results"][0]["balance"], "10000.00")


class CashFlowForecastTests(APITestCase):
    """The forecast projects committed documents only — nothing modelled."""

    def setUp(self):
        self.company = Company.objects.create(name="FcCo")
        self.role = Role.objects.create(
            name="Chief Financial Officer", scope_level=Role.SCOPE_BUSINESS
        )
        self.user = User.objects.create_user(
            email="cfo@fc.test", password="passw0rd12345",
            company=self.company, role=self.role,
        )
        self.wh = Warehouse.objects.create(company=self.company, name="W")
        self.customer = Customer.objects.create(company=self.company, name="C")
        self.client.force_authenticate(self.user)

    def _invoice(self, number, total, due_offset_days):
        inv = Invoice.objects.create(
            company=self.company, customer=self.customer, warehouse=self.wh,
            number=number, subtotal=Decimal(total), total=Decimal(total),
        )
        Invoice.objects.filter(pk=inv.pk).update(
            due_date=date.today() + timedelta(days=due_offset_days)
        )
        return inv

    def test_upcoming_invoice_appears_in_forecast(self):
        self._invoice(1, "500", 3)
        resp = self.client.get(reverse("report-cash-flow-forecast"), {"weeks": 4})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["closing_position"], "500.00")

    def test_overdue_invoice_lands_in_overdue_bucket(self):
        self._invoice(2, "700", -20)
        resp = self.client.get(reverse("report-cash-flow-forecast"))
        self.assertEqual(resp.data["rows"][0]["bucket"], "overdue")
        self.assertEqual(resp.data["rows"][0]["inflow"], "700.00")

    def test_paid_invoice_is_not_forecast(self):
        inv = self._invoice(3, "900", 5)
        Payment.objects.create(
            company=self.company, invoice=inv, method="cash", amount=Decimal("900"),
        )
        resp = self.client.get(reverse("report-cash-flow-forecast"))
        self.assertEqual(resp.data["closing_position"], "0.00")
