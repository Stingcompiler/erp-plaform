"""HR money reaches the books: approving payroll or an advance posts an
Expense, once, for the right amount, and the income statement moves.
"""

from datetime import date
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User
from finance.models import Expense
from hr.models import PayrollRun, SalaryAdvance
from hr.postings import payroll_expense_amount
from hr.tests import HrBase


class PostingBase(HrBase):
    def setUp(self):
        super().setUp()
        self.pos_a.base_salary = Decimal("1000.00")
        self.pos_a.save(update_fields=["base_salary"])
        cfo_role = Role.objects.create(
            name="Chief Financial Officer", scope_level=Role.SCOPE_BUSINESS
        )
        cfo = User.objects.create_user(
            email="cfo-post@alpha.test", password="passw0rd123",
            company=self.company_a, role=cfo_role,
        )
        self.cfo = self.client_class()
        self.cfo.force_authenticate(cfo)

    def _run(self, period="2026-09"):
        create = self.client.post(reverse("payrollrun-list"), {"period": period}, format="json")
        self.assertEqual(create.status_code, 201, create.content)
        return create.data["id"]

    def _advance(self, amount):
        create = self.client.post(
            reverse("salaryadvance-list"),
            {"employee": self.emp_a.id, "amount": amount, "reason": "x"}, format="json",
        )
        self.assertEqual(create.status_code, 201, create.content)
        return create.data["id"]


class PayrollPostingTests(PostingBase):
    def test_approving_payroll_posts_one_expense_for_net_pay(self):
        run_id = self._run()
        self.assertEqual(Expense.objects.count(), 0)

        approved = self.cfo.post(reverse("payrollrun-approve", args=[run_id]))
        self.assertEqual(approved.status_code, 200, approved.content)

        expense = Expense.objects.get()
        self.assertEqual(expense.category, Expense.CATEGORY_PAYROLL)
        self.assertEqual(expense.amount, Decimal("1000.00"))
        self.assertEqual(expense.date, date(2026, 9, 1))
        self.assertEqual(expense.payroll_run_id, run_id)
        self.assertEqual(PayrollRun.objects.get(pk=run_id).expense, expense)

    def test_approving_twice_does_not_post_twice(self):
        run_id = self._run()
        self.cfo.post(reverse("payrollrun-approve", args=[run_id]))
        self.cfo.post(reverse("payrollrun-approve", args=[run_id]))
        self.assertEqual(Expense.objects.filter(payroll_run_id=run_id).count(), 1)

    def test_draft_run_posts_nothing(self):
        self._run()
        self.assertEqual(Expense.objects.count(), 0)

    def test_hr_cannot_link_expenses_by_hand(self):
        run_id = self._run()
        resp = self.cfo.post(
            reverse("expense-list"),
            {"category": "Payroll", "amount": "1", "date": "2026-09-01",
             "method": "cash", "payroll_run": run_id},
            format="json",
        )
        # The link field is read-only: the row is created but never linked.
        if resp.status_code == 201:
            self.assertIsNone(Expense.objects.get(pk=resp.data["id"]).payroll_run_id)


class AdvancePostingTests(PostingBase):
    def test_approved_advance_is_expensed_and_rejected_is_not(self):
        approved_id = self._advance("300.00")
        rejected_id = self._advance("999.00")
        approve = self.cfo.post(reverse("salaryadvance-approve", args=[approved_id]))
        reject = self.cfo.post(reverse("salaryadvance-reject", args=[rejected_id]))
        self.assertEqual((approve.status_code, reject.status_code), (200, 200))

        expense = Expense.objects.get()
        self.assertEqual(expense.category, Expense.CATEGORY_SALARY_ADVANCE)
        self.assertEqual(expense.amount, Decimal("300.00"))
        self.assertEqual(expense.salary_advance_id, approved_id)
        self.assertEqual(expense.date, timezone.localdate())

    def test_advance_recovered_by_payroll_is_counted_once(self):
        # Advance paid out this month (expensed on approval) and recovered
        # by this month's payroll: the month costs 1000 in total, on two rows.
        adv_id = self._advance("300.00")
        self.cfo.post(reverse("salaryadvance-approve", args=[adv_id]))
        SalaryAdvance.objects.filter(pk=adv_id).update(
            reviewed_at=timezone.make_aware(timezone.datetime(2026, 9, 5, 10, 0))
        )
        run_id = self._run("2026-09")
        run = PayrollRun.objects.get(pk=run_id)
        entry = run.entries.get()
        self.assertEqual(entry.advances_total, Decimal("300.00"))
        self.assertEqual(entry.net_salary, Decimal("700.00"))
        self.assertEqual(payroll_expense_amount(run), Decimal("700.00"))

        self.cfo.post(reverse("payrollrun-approve", args=[run_id]))
        total = sum(Expense.objects.values_list("amount", flat=True), Decimal("0"))
        self.assertEqual(total, Decimal("1000.00"))

    def test_advance_from_an_earlier_month_is_not_subtracted(self):
        # Paid in August (expensed then), recovered in September: September's
        # cost is the full 1000 of work, so its payroll expense is net + recovered.
        adv_id = self._advance("300.00")
        self.cfo.post(reverse("salaryadvance-approve", args=[adv_id]))
        SalaryAdvance.objects.filter(pk=adv_id).update(
            reviewed_at=timezone.make_aware(timezone.datetime(2026, 8, 20, 10, 0))
        )
        run_id = self._run("2026-09")
        run = PayrollRun.objects.get(pk=run_id)
        # September's recalculation only recovers advances approved in September.
        self.assertEqual(run.entries.get().advances_total, Decimal("0.00"))
        self.assertEqual(payroll_expense_amount(run), Decimal("1000.00"))


class IncomeStatementTests(PostingBase):
    def test_payroll_lowers_net_profit(self):
        before = self.cfo.get(
            reverse("report-income-statement"), {"start": "2026-09-01", "end": "2026-09-30"}
        )
        self.assertEqual(before.status_code, 200, before.content)
        run_id = self._run("2026-09")
        self.cfo.post(reverse("payrollrun-approve", args=[run_id]))
        after = self.cfo.get(
            reverse("report-income-statement"), {"start": "2026-09-01", "end": "2026-09-30"}
        )
        delta = Decimal(str(before.data["net_profit"])) - Decimal(str(after.data["net_profit"]))
        self.assertEqual(delta, Decimal("1000.00"))
        categories = {
            row["category"]: Decimal(str(row["amount"]))
            for row in after.data["expenses_by_category"]
        }
        self.assertEqual(categories.get("Payroll"), Decimal("1000.00"))


class BackfillCommandTests(PostingBase):
    """Documents approved before postings existed get their expense once."""

    def _approved_without_expense(self):
        # Simulate history: approve, then delete the expense the approval posted.
        run_id = self._run("2026-08")
        self.cfo.post(reverse("payrollrun-approve", args=[run_id]))
        adv_id = self._advance("200.00")
        self.cfo.post(reverse("salaryadvance-approve", args=[adv_id]))
        Expense.objects.all().delete()
        return run_id, adv_id

    def test_dry_run_writes_nothing(self):
        from io import StringIO

        from django.core.management import call_command

        self._approved_without_expense()
        out = StringIO()
        call_command("backfill_hr_postings", stdout=out)
        self.assertIn("Dry run: 1 payroll run(s) and 1 advance(s)", out.getvalue())
        self.assertEqual(Expense.objects.count(), 0)

    def test_yes_posts_once_and_is_idempotent(self):
        from io import StringIO

        from django.core.management import call_command

        run_id, adv_id = self._approved_without_expense()
        call_command("backfill_hr_postings", "--yes", stdout=StringIO())
        self.assertEqual(Expense.objects.filter(payroll_run_id=run_id).count(), 1)
        self.assertEqual(Expense.objects.filter(salary_advance_id=adv_id).count(), 1)
        self.assertEqual(Expense.objects.get(payroll_run_id=run_id).amount, Decimal("1000.00"))

        out = StringIO()
        call_command("backfill_hr_postings", "--yes", stdout=out)
        self.assertIn("Posted 0 payroll run(s) and 0 advance(s)", out.getvalue())
        self.assertEqual(Expense.objects.count(), 2)

    def test_company_scope_is_respected(self):
        from io import StringIO

        from django.core.management import call_command

        self._approved_without_expense()
        out = StringIO()
        call_command("backfill_hr_postings", "--yes", "--company", "999999", stdout=out)
        self.assertEqual(Expense.objects.count(), 0)
