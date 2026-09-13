"""
Deletion policy tests (PROJECT_RULES Rule #9).

Covers the three tiers in core/deletion.py: tier A records refuse deletion,
tier B master data archives instead of disappearing, and tier C hard deletes
are restricted to a manager-level role.
"""

from datetime import date
from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from core.models import ActivityLog
from finance.models import Budget, BudgetLine, Expense
from hr.models import Deduction, Employee, SalaryAdvance
from inventory.models import Product, StockMovement, Warehouse
from org.models import Branch, Company
from sales.models import Customer


class DeletionPolicyTestCase(APITestCase):
    """Shared cast: an owner (may delete) and a clerk (may not)."""

    def setUp(self):
        self.company = Company.objects.create(name="DelCo")
        self.owner_role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        self.clerk_role = Role.objects.create(
            name="Finance Department", scope_level=Role.SCOPE_BUSINESS
        )
        self.owner = User.objects.create_user(
            email="owner@del.test", password="passw0rd12345",
            company=self.company, role=self.owner_role,
        )
        self.clerk = User.objects.create_user(
            email="clerk@del.test", password="passw0rd12345",
            company=self.company, role=self.clerk_role,
        )
        self.client.force_authenticate(self.owner)


class TierANeverDeletableTests(DeletionPolicyTestCase):
    def test_expense_cannot_be_deleted_even_by_owner(self):
        exp = Expense.objects.create(
            company=self.company, category="Rent",
            amount=Decimal("1000"), date=date.today(),
        )
        resp = self.client.delete(reverse("expense-detail", args=[exp.id]))
        self.assertEqual(resp.status_code, 405, resp.data)
        self.assertTrue(Expense.objects.filter(pk=exp.pk).exists())

    def test_expense_denial_names_the_correcting_action(self):
        """A dead end with no way forward is what pushes people to delete rows
        straight from the Django admin."""
        exp = Expense.objects.create(
            company=self.company, category="Rent",
            amount=Decimal("1"), date=date.today(),
        )
        resp = self.client.delete(reverse("expense-detail", args=[exp.id]))
        self.assertIn("offsetting", resp.data["detail"].lower())

    def test_expense_cannot_be_edited_in_place(self):
        """Financial corrections are new offsetting entries, never rewrites."""
        exp = Expense.objects.create(
            company=self.company, category="Rnet",
            amount=Decimal("50"), date=date.today(),
        )
        resp = self.client.patch(
            reverse("expense-detail", args=[exp.id]),
            {"category": "Rent"}, format="json",
        )
        self.assertEqual(resp.status_code, 405, resp.data)

    def test_deduction_cannot_be_deleted(self):
        emp = Employee.objects.create(
            company=self.company, full_name="Sara", hire_date=date.today()
        )
        ded = Deduction.objects.create(
            company=self.company, employee=emp,
            amount=Decimal("100"), date=date.today(),
        )
        resp = self.client.delete(reverse("deduction-detail", args=[ded.id]))
        self.assertEqual(resp.status_code, 405, resp.data)
        self.assertTrue(Deduction.objects.filter(pk=ded.pk).exists())


class ConditionalDeleteTests(DeletionPolicyTestCase):
    """Some records are disposable until they carry a decision."""

    def _budget(self, status_value=Budget.DRAFT):
        budget = Budget.objects.create(
            company=self.company, name="Plan",
            period_start=date.today(), period_end=date.today(),
            status=status_value,
        )
        BudgetLine.objects.create(
            budget=budget, kind=BudgetLine.EXPENSE,
            category="Rent", planned_amount=Decimal("100"),
        )
        return budget

    def test_draft_budget_can_be_deleted(self):
        budget = self._budget()
        resp = self.client.delete(reverse("budget-detail", args=[budget.id]))
        self.assertEqual(resp.status_code, 204, resp.data)
        self.assertFalse(Budget.objects.filter(pk=budget.pk).exists())

    def test_approved_budget_cannot_be_deleted(self):
        budget = self._budget(Budget.APPROVED)
        resp = self.client.delete(reverse("budget-detail", args=[budget.id]))
        self.assertEqual(resp.status_code, 405, resp.data)
        self.assertTrue(Budget.objects.filter(pk=budget.pk).exists())

    def test_pending_salary_advance_can_be_withdrawn(self):
        emp = Employee.objects.create(
            company=self.company, full_name="Ali", hire_date=date.today()
        )
        adv = SalaryAdvance.objects.create(
            company=self.company, employee=emp, amount=Decimal("500"),
            status=SalaryAdvance.PENDING,
        )
        resp = self.client.delete(reverse("salaryadvance-detail", args=[adv.id]))
        self.assertEqual(resp.status_code, 204, resp.data)

    def test_approved_salary_advance_cannot_be_deleted(self):
        emp = Employee.objects.create(
            company=self.company, full_name="Ali", hire_date=date.today()
        )
        adv = SalaryAdvance.objects.create(
            company=self.company, employee=emp, amount=Decimal("500"),
            status=SalaryAdvance.APPROVED,
        )
        resp = self.client.delete(reverse("salaryadvance-detail", args=[adv.id]))
        self.assertEqual(resp.status_code, 405, resp.data)


class TierBArchiveTests(DeletionPolicyTestCase):
    def test_customer_is_archived_not_removed(self):
        cust = Customer.objects.create(company=self.company, name="Acme")
        resp = self.client.delete(reverse("customer-detail", args=[cust.id]))
        self.assertEqual(resp.status_code, 204, resp.data)
        cust.refresh_from_db()
        self.assertFalse(cust.is_active)

    def test_archive_is_logged_as_archive_not_delete(self):
        cust = Customer.objects.create(company=self.company, name="Acme")
        self.client.delete(reverse("customer-detail", args=[cust.id]))
        log = ActivityLog.objects.filter(
            entity_type="Customer", entity_id=str(cust.pk)
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.action, "archive")

    def test_archiving_twice_is_a_no_op(self):
        """A client retrying after a dropped response must not get an error for
        work that already succeeded."""
        cust = Customer.objects.create(company=self.company, name="Acme")
        url = reverse("customer-detail", args=[cust.id])
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(
            ActivityLog.objects.filter(
                entity_type="Customer", entity_id=str(cust.pk), action="archive"
            ).count(),
            1,
        )

    def test_product_with_stock_history_is_archived_not_blocked(self):
        """PROTECT would refuse a hard delete here; archiving sidesteps that
        while keeping the movement ledger readable."""
        wh = Warehouse.objects.create(company=self.company, name="W")
        product = Product.objects.create(
            company=self.company, sku="P1", name="Widget"
        )
        StockMovement.objects.create(
            company=self.company, product=product, warehouse=wh,
            movement_type=StockMovement.PURCHASE_IN, quantity=Decimal("5"),
        )
        resp = self.client.delete(reverse("product-detail", args=[product.id]))
        self.assertEqual(resp.status_code, 204, resp.data)
        product.refresh_from_db()
        self.assertFalse(product.is_active)
        self.assertEqual(StockMovement.objects.filter(product=product).count(), 1)

    def test_user_is_deactivated_not_deleted(self):
        """Payment.recorded_by is SET_NULL — deleting the row would strip the
        name off every payment this person handled."""
        victim = User.objects.create_user(
            email="temp@del.test", password="passw0rd12345",
            company=self.company, role=self.clerk_role,
        )
        resp = self.client.delete(reverse("user-detail", args=[victim.id]))
        self.assertEqual(resp.status_code, 204, resp.data)
        victim.refresh_from_db()
        self.assertFalse(victim.is_active)

    def test_cannot_deactivate_your_own_account(self):
        resp = self.client.delete(reverse("user-detail", args=[self.owner.id]))
        self.assertEqual(resp.status_code, 400, resp.data)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)

    def test_employee_is_terminated_not_deleted(self):
        emp = Employee.objects.create(
            company=self.company, full_name="Sara", hire_date=date.today()
        )
        resp = self.client.delete(reverse("employee-detail", args=[emp.id]))
        self.assertEqual(resp.status_code, 204, resp.data)
        emp.refresh_from_db()
        self.assertEqual(emp.status, Employee.STATUS_TERMINATED)


class TierCManagerOnlyTests(DeletionPolicyTestCase):
    def test_non_manager_cannot_delete(self):
        """Module write access is not the same as authority to remove a row."""
        budget = Budget.objects.create(
            company=self.company, name="Plan",
            period_start=date.today(), period_end=date.today(),
        )
        self.client.force_authenticate(self.clerk)
        resp = self.client.delete(reverse("budget-detail", args=[budget.id]))
        self.assertEqual(resp.status_code, 403, resp.data)
        self.assertTrue(Budget.objects.filter(pk=budget.pk).exists())

    def test_manager_can_delete(self):
        budget = Budget.objects.create(
            company=self.company, name="Plan",
            period_start=date.today(), period_end=date.today(),
        )
        resp = self.client.delete(reverse("budget-detail", args=[budget.id]))
        self.assertEqual(resp.status_code, 204, resp.data)

    def test_content_records_stay_deletable_by_their_owner(self):
        """The manager gate must not lock the role that owns the work out of
        its own routine edits — an HR officer clearing a mistyped attendance
        line is not performing a supervisory act."""
        branch = Branch.objects.create(company=self.company, name="Main")
        hr_role = Role.objects.create(name="HR Officer", scope_level=Role.SCOPE_BRANCH)
        hr_user = User.objects.create_user(
            email="hr@del.test", password="passw0rd12345",
            company=self.company, branch=branch, role=hr_role,
        )
        emp = Employee.objects.create(
            company=self.company, branch=branch,
            full_name="Sara", hire_date=date.today()
        )
        from hr.models import Attendance

        row = Attendance.objects.create(
            company=self.company, employee=emp, date=date.today(), status="present"
        )
        self.client.force_authenticate(hr_user)
        resp = self.client.delete(reverse("attendance-detail", args=[row.id]))
        self.assertEqual(resp.status_code, 204, resp.data)

    def test_archiving_also_requires_a_manager(self):
        """Archiving is reached through DELETE, so it inherits the same gate."""
        cust = Customer.objects.create(company=self.company, name="Acme")
        self.client.force_authenticate(self.clerk)
        resp = self.client.delete(reverse("customer-detail", args=[cust.id]))
        self.assertEqual(resp.status_code, 403, resp.data)
        cust.refresh_from_db()
        self.assertTrue(cust.is_active)


class ProtectedErrorTests(DeletionPolicyTestCase):
    def test_protected_delete_returns_409_not_500(self):
        """A blocked delete is the database defending history, not a crash."""
        wh = Warehouse.objects.create(company=self.company, name="W")
        product = Product.objects.create(
            company=self.company, sku="P2", name="Gadget"
        )
        StockMovement.objects.create(
            company=self.company, product=product, warehouse=wh,
            movement_type=StockMovement.PURCHASE_IN, quantity=Decimal("5"),
        )
        # Warehouse is tier B, so drive the PROTECT path directly rather than
        # through the archiving endpoint.
        from django.db.models import ProtectedError

        from core.exceptions import api_exception_handler

        try:
            wh.delete()
            self.fail("expected ProtectedError")
        except ProtectedError as exc:
            resp = api_exception_handler(exc, {})

        self.assertEqual(resp.status_code, 409)
        self.assertIn("stock movement", resp.data["detail"].lower())
        self.assertIn("archive", resp.data["detail"].lower())
