"""Expense categories are one shared vocabulary, and large expenses need an
approver — the two gaps that made budgets unusable and expenses the one
unbounded outflow.
"""

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Role, User
from finance.models import Budget, BudgetLine, Expense
from org.models import Company


class CategoriesAndThresholdTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name="Alpha", payment_approval_threshold=Decimal("1000")
        )
        business = Role.SCOPE_BUSINESS
        finance_role = Role.objects.create(name="Finance Department", scope_level=business)
        owner_role = Role.objects.create(name="Business Owner", scope_level=business)
        self.finance = User.objects.create_user(
            email="fin@alpha.test", password="passw0rd123",
            company=self.company, role=finance_role,
        )
        self.owner = User.objects.create_user(
            email="own@alpha.test", password="passw0rd123",
            company=self.company, role=owner_role,
        )

    def client_for(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def test_categories_merge_expenses_and_budget_lines(self):
        Expense.objects.create(
            company=self.company, category="Rent", amount=Decimal("100"), date="2026-09-01",
        )
        budget = Budget.objects.create(
            company=self.company, name="Q4", period_start="2026-10-01", period_end="2026-12-31",
        )
        BudgetLine.objects.create(budget=budget, category="Marketing", planned_amount=Decimal("50"))
        BudgetLine.objects.create(
            budget=budget, kind=BudgetLine.REVENUE, category="Sales target", planned_amount=1,
        )
        other = Company.objects.create(name="Beta")
        Expense.objects.create(
            company=other, category="Secret", amount=Decimal("1"), date="2026-09-01",
        )
        response = self.client_for(self.finance).get("/api/expenses/categories/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data, ["Marketing", "Rent"])

    def test_large_expense_needs_an_approver(self):
        body = {"category": "Rent", "amount": "1500", "date": "2026-09-01", "method": "cash"}
        denied = self.client_for(self.finance).post("/api/expenses/", body, format="json")
        self.assertEqual(denied.status_code, 400, denied.data)
        self.assertIn("amount", denied.data)
        small = self.client_for(self.finance).post(
            "/api/expenses/", {**body, "amount": "999"}, format="json"
        )
        self.assertEqual(small.status_code, 201, small.data)
        allowed = self.client_for(self.owner).post("/api/expenses/", body, format="json")
        self.assertEqual(allowed.status_code, 201, allowed.data)
