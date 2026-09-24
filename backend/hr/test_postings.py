"""HR money reaches the books: approving payroll or an advance posts an
Expense, once, for the right amount, and the income statement moves.
"""

from datetime import date, datetime
from datetime import timezone as dt_timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User
from finance.models import Expense
from hr.models import Employee, PayrollRun, SalaryAdvance
from hr.postings import payroll_expense_amount, post_salary_advance_expense
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
        # The company's day (Khartoum by default), not the server's UTC one.
        self.assertEqual(expense.date, timezone.localdate(timezone=ZoneInfo("Africa/Khartoum")))

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


class AdvanceTimingTests(PostingBase):
    """Cash leaves in the month it really leaves, and each advance is counted
    once — on its own row — whichever payroll run recovers it (review
    2026-09-24: a run used to subtract every advance approved in its month,
    company-wide, recovered or not, and advances were dated in UTC)."""

    KHARTOUM = ZoneInfo("Africa/Khartoum")

    def _approved_advance(self, when, employee=None):
        advance = SalaryAdvance.objects.create(
            company=self.company_a, employee=employee or self.emp_a,
            amount=Decimal("300.00"), status=SalaryAdvance.APPROVED, reviewed_at=when,
        )
        post_salary_advance_expense(advance)
        return advance

    def _approve_run(self, period):
        run_id = self._run(period)
        self.cfo.post(reverse("payrollrun-approve", args=[run_id]))
        return PayrollRun.objects.get(pk=run_id)

    def _cash_out(self, start, end):
        return sum(
            Expense.objects.filter(
                company=self.company_a, date__gte=start, date__lte=end
            ).values_list("amount", flat=True),
            Decimal("0"),
        )

    def test_an_advance_approved_after_the_draft_blocks_approval_until_recalculated(self):
        # March's payroll is calculated on the 15th; an advance of 300 is
        # paid on the 20th, after the snapshot. Approving that draft used to
        # book the advance with nobody recovering it from salary. Now the
        # approval is refused until the draft is recalculated, and March then
        # recovers it: expense 700 (net pay), March cash out 300 + 700.
        march_id = self._run("2026-03")
        advance = self._approved_advance(datetime(2026, 3, 20, 10, 0, tzinfo=self.KHARTOUM))
        self.assertEqual(advance.expense.date, date(2026, 3, 20))
        refused = self.cfo.post(reverse("payrollrun-approve", args=[march_id]))
        self.assertEqual(refused.status_code, 400, refused.data)
        self.assertEqual(PayrollRun.objects.get(pk=march_id).status, PayrollRun.DRAFT)

        self.client.post(reverse("payrollrun-refresh", args=[march_id]))  # HR recalculates
        approved = self.cfo.post(reverse("payrollrun-approve", args=[march_id]))
        self.assertEqual(approved.status_code, 200, approved.data)
        march = PayrollRun.objects.get(pk=march_id)
        entry = march.entries.get()
        self.assertEqual((entry.advances_total, entry.net_salary),
                         (Decimal("300.00"), Decimal("700.00")))
        self.assertEqual(march.expense.amount, Decimal("700.00"))
        self.assertEqual(self._cash_out(date(2026, 3, 1), date(2026, 3, 31)), Decimal("1000.00"))

    def test_advance_paid_just_after_midnight_belongs_to_april_and_is_counted_once(self):
        # 00:30 on 1 April in Khartoum is still 31 March in UTC. The advance
        # was paid in April: it is dated 1 April, April's run recovers it,
        # and April's cash out is 300 (advance) + 700 (net pay) = 1000.
        paid = datetime(2026, 4, 1, 0, 30, tzinfo=self.KHARTOUM)
        self.assertEqual(paid.astimezone(dt_timezone.utc).date(), date(2026, 3, 31))
        advance = self._approved_advance(paid)
        self.assertEqual(advance.expense.date, date(2026, 4, 1))

        march = self._approve_run("2026-03")
        self.assertEqual(march.entries.get().advances_total, Decimal("0.00"))
        self.assertEqual(march.expense.amount, Decimal("1000.00"))
        self.assertEqual(self._cash_out(date(2026, 3, 1), date(2026, 3, 31)), Decimal("1000.00"))

        april = self._approve_run("2026-04")
        entry = april.entries.get()
        self.assertEqual((entry.advances_total, entry.net_salary),
                         (Decimal("300.00"), Decimal("700.00")))
        self.assertEqual(april.expense.amount, Decimal("700.00"))
        self.assertEqual(self._cash_out(date(2026, 4, 1), date(2026, 4, 30)), Decimal("1000.00"))

    def test_advance_of_an_employee_outside_the_run_is_not_subtracted(self):
        # Paid to someone terminated before payroll: the run never recovers
        # it, so it must not shrink the run's expense.
        leaver = Employee.objects.create(
            company=self.company_a, branch=self.branch_a, full_name="Left Early",
            status=Employee.STATUS_TERMINATED,
        )
        self._approved_advance(datetime(2026, 3, 10, 9, 0, tzinfo=self.KHARTOUM), leaver)
        march = self._approve_run("2026-03")
        self.assertEqual(march.expense.amount, Decimal("1000.00"))
        self.assertEqual(self._cash_out(date(2026, 3, 1), date(2026, 3, 31)), Decimal("1300.00"))


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
