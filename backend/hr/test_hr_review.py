"""HR review 2026-09-24: advances recovered whatever month they are approved
in and however large they are, deductions locked once their payroll is
approved, payroll paying only for the days actually employed, salaries kept
from roles without payroll access, attendance refusing impossible days, and
no payroll for a month that has not started."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.urls import reverse

from accounts.models import Role, User
from finance.models import Expense
from hr.leave_sync import refresh_employee_leave_statuses
from hr.models import (
    Attendance,
    Deduction,
    Employee,
    LeaveRequest,
    PayrollRun,
    SalaryAdvance,
)
from hr.postings import company_today, post_salary_advance_expense
from hr.test_postings import PostingBase

KHARTOUM = ZoneInfo("Africa/Khartoum")


class ReviewBase(PostingBase):
    def approve_run(self, period):
        run_id = self._run(period)
        response = self.cfo.post(reverse("payrollrun-approve", args=[run_id]))
        self.assertEqual(response.status_code, 200, response.data)
        return PayrollRun.objects.get(pk=run_id)

    def approved_advance(self, amount, recover_period, employee=None):
        advance = SalaryAdvance.objects.create(
            company=self.company_a, employee=employee or self.emp_a, amount=Decimal(amount),
            status=SalaryAdvance.APPROVED, recover_period=recover_period,
            reviewed_at=datetime.combine(recover_period, datetime.min.time(), tzinfo=KHARTOUM)
            + timedelta(days=4),
        )
        post_salary_advance_expense(advance)
        return advance

    def entry(self, run, employee=None):
        return run.entries.get(employee=employee or self.emp_a)


class LateAdvanceTests(ReviewBase):
    def test_advance_approved_after_its_month_was_approved_is_recovered_next_month(self):
        self.approve_run("2026-07")
        adv_id = self._advance("300.00")
        late = datetime(2026, 7, 28, 10, 0, tzinfo=KHARTOUM)
        with patch("django.utils.timezone.now", return_value=late):
            response = self.cfo.post(reverse("salaryadvance-approve", args=[adv_id]))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["recover_period"], "2026-08-01")
        advance = SalaryAdvance.objects.get(pk=adv_id)
        self.assertEqual(advance.expense.date, date(2026, 7, 28))

        august = self.approve_run("2026-08")
        entry = self.entry(august)
        self.assertEqual(
            (entry.advances_total, entry.advances_recovered, entry.net_salary),
            (Decimal("300.00"), Decimal("300.00"), Decimal("700.00")),
        )
        self.assertEqual(august.expense.amount, Decimal("700.00"))

    def test_advance_approved_before_its_month_is_approved_is_recovered_that_month(self):
        adv_id = self._advance("300.00")
        with patch(
            "django.utils.timezone.now",
            return_value=datetime(2026, 7, 10, 10, 0, tzinfo=KHARTOUM),
        ):
            self.cfo.post(reverse("salaryadvance-approve", args=[adv_id]))
        self.assertEqual(SalaryAdvance.objects.get(pk=adv_id).recover_period, date(2026, 7, 1))
        july = self.approve_run("2026-07")
        self.assertEqual(self.entry(july).advances_recovered, Decimal("300.00"))
        # Recovered once: August owes nothing more.
        august = self.approve_run("2026-08")
        self.assertEqual(self.entry(august).advances_total, Decimal("0.00"))


class AdvanceCarryTests(ReviewBase):
    def test_advance_larger_than_net_pay_carries_the_rest_to_next_month(self):
        self.approved_advance("1500.00", date(2026, 7, 1))
        july = self.approve_run("2026-07")
        entry = self.entry(july)
        self.assertEqual(
            (entry.advances_total, entry.advances_recovered, entry.net_salary),
            (Decimal("1500.00"), Decimal("1000.00"), Decimal("0.00")),
        )
        # Nothing paid out in July: the whole month was advanced already.
        self.assertIsNone(getattr(july, "expense", None))

        august = self.approve_run("2026-08")
        entry = self.entry(august)
        self.assertEqual(
            (entry.advances_total, entry.advances_recovered, entry.net_salary),
            (Decimal("500.00"), Decimal("500.00"), Decimal("500.00")),
        )
        self.assertEqual(august.expense.amount, Decimal("500.00"))
        # Two months of 1000 cost 2000 in cash, counted once.
        self.assertEqual(
            sum(Expense.objects.values_list("amount", flat=True), Decimal("0")),
            Decimal("2000.00"),
        )

        september = self.approve_run("2026-09")
        self.assertEqual(self.entry(september).advances_total, Decimal("0.00"))

    def test_deductions_are_taken_before_advances(self):
        self.approved_advance("950.00", date(2026, 7, 1))
        Deduction.objects.create(
            company=self.company_a, employee=self.emp_a, amount="100", date=date(2026, 7, 3)
        )
        july = self.approve_run("2026-07")
        entry = self.entry(july)
        self.assertEqual(
            (entry.advances_recovered, entry.net_salary), (Decimal("900.00"), Decimal("0.00"))
        )
        self.assertEqual(self.entry(self.approve_run("2026-08")).advances_total, Decimal("50.00"))


class DeductionLockTests(ReviewBase):
    def post(self, **data):
        return self.client.post(
            reverse("deduction-list"), {"employee": self.emp_a.pk, **data}, format="json"
        )

    def test_amount_must_be_positive(self):
        for amount in ("0", "-50"):
            self.assertEqual(self.post(amount=amount, date="2026-08-03").status_code, 400)

    def test_cannot_date_a_deduction_into_an_approved_month(self):
        self.approve_run("2026-07")
        refused = self.post(amount="50", date="2026-07-15")
        self.assertEqual(refused.status_code, 400, refused.data)
        self.assertIn("date", refused.data)
        self.assertEqual(self.post(amount="50", date="2026-08-02").status_code, 201)

    def test_deduction_in_an_approved_payroll_cannot_be_edited(self):
        created = self.post(amount="50", date="2026-08-05")
        self.assertEqual(created.status_code, 201, created.data)
        url = reverse("deduction-detail", args=[created.data["id"]])
        self.assertEqual(
            self.client.patch(url, {"note": "typo"}, format="json").status_code, 200
        )
        august = self.approve_run("2026-08")
        self.assertEqual(self.entry(august).deductions_total, Decimal("50.00"))
        for change in ({"amount": "10"}, {"date": "2026-09-05"}, {"note": "later"}):
            response = self.client.patch(url, change, format="json")
            self.assertEqual(response.status_code, 400, (change, response.data))
        self.assertEqual(Deduction.objects.get(pk=created.data["id"]).amount, Decimal("50.00"))

    def test_undated_deduction_belongs_to_the_month_it_was_recorded(self):
        deduction = Deduction.objects.create(
            company=self.company_a, employee=self.emp_a, amount="20"
        )
        Deduction.objects.filter(pk=deduction.pk).update(
            created_at=datetime(2026, 7, 9, 12, 0, tzinfo=KHARTOUM)
        )
        self.approve_run("2026-07")
        response = self.client.patch(
            reverse("deduction-detail", args=[deduction.pk]), {"amount": "5"}, format="json"
        )
        self.assertEqual(response.status_code, 400, response.data)


class ProrationTests(ReviewBase):
    def test_hire_after_the_first_is_paid_for_the_days_employed(self):
        self.emp_a.hire_date = date(2026, 7, 16)
        self.emp_a.save(update_fields=["hire_date"])
        entry = self.entry(PayrollRun.objects.get(pk=self._run("2026-07")))
        self.assertEqual(entry.days_employed, 16)
        self.assertEqual(entry.monthly_salary, Decimal("1000.00"))
        self.assertEqual(entry.base_salary, Decimal("516.13"))  # 1000 × 16/31

    def test_leaver_is_paid_to_termination_and_settles_advances_then_drops_out(self):
        self.approved_advance("200.00", date(2026, 8, 1))  # due from August…
        self.emp_a.status = Employee.STATUS_TERMINATED
        self.emp_a.termination_date = date(2026, 7, 10)
        self.emp_a.save(update_fields=["status", "termination_date"])
        july = self.approve_run("2026-07")
        entry = self.entry(july)
        self.assertEqual((entry.days_employed, entry.base_salary),
                         (10, Decimal("322.58")))
        # …but July is their last month: the whole balance is settled now.
        self.assertEqual(
            (entry.advances_recovered, entry.net_salary), (Decimal("200.00"), Decimal("122.58"))
        )
        august = PayrollRun.objects.get(pk=self._run("2026-08"))
        self.assertFalse(august.entries.filter(employee=self.emp_a).exists())

    def test_terminated_without_a_date_is_not_paid(self):
        self.emp_a.status = Employee.STATUS_TERMINATED
        self.emp_a.save(update_fields=["status"])
        run = PayrollRun.objects.get(pk=self._run("2026-07"))
        self.assertFalse(run.entries.exists())

    def test_unpaid_leave_reduces_pay_and_absences_are_only_counted(self):
        LeaveRequest.objects.create(
            company=self.company_a, employee=self.emp_a, leave_type=LeaveRequest.UNPAID,
            start_date=date(2026, 7, 6), end_date=date(2026, 7, 10),
            status=LeaveRequest.APPROVED,
        )
        LeaveRequest.objects.create(
            company=self.company_a, employee=self.emp_a, leave_type=LeaveRequest.ANNUAL,
            start_date=date(2026, 7, 20), end_date=date(2026, 7, 21),
            status=LeaveRequest.APPROVED,
        )
        for day in (1, 2):
            Attendance.objects.create(
                company=self.company_a, employee=self.emp_a, date=date(2026, 7, day),
                status=Attendance.ABSENT,
            )
        entry = self.entry(PayrollRun.objects.get(pk=self._run("2026-07")))
        self.assertEqual((entry.unpaid_leave_days, entry.absent_days), (5, 2))
        self.assertEqual(entry.base_salary, Decimal("838.71"))  # 1000 × 26/31
        self.assertEqual(entry.net_salary, Decimal("838.71"))

    def test_draft_for_a_leaver_is_stale(self):
        run_id = self._run("2026-07")
        self.emp_a.status = Employee.STATUS_TERMINATED
        self.emp_a.termination_date = date(2026, 6, 30)
        self.emp_a.save(update_fields=["status", "termination_date"])
        refused = self.cfo.post(reverse("payrollrun-approve", args=[run_id]))
        self.assertEqual(refused.status_code, 400, refused.data)
        self.assertEqual(refused.data["code"], "payroll_stale")
        self.assertIn("Amina Ali", str(refused.data["detail"]))

    def test_termination_records_the_day(self):
        owner_role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        owner = User.objects.create_user(
            email="owner-t@alpha.test", password="passw0rd123",
            company=self.company_a, role=owner_role,
        )
        self.client.force_authenticate(owner)
        response = self.client.patch(
            reverse("employee-detail", args=[self.emp_a.pk]), {"status": "terminated"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            response.data["termination_date"], company_today(self.company_a).isoformat()
        )
        other = Employee.objects.create(
            company=self.company_a, branch=self.branch_a, full_name="Leaver Two"
        )
        self.client.delete(reverse("employee-detail", args=[other.pk]))
        other.refresh_from_db()
        self.assertEqual(
            (other.status, other.termination_date),
            (Employee.STATUS_TERMINATED, company_today(self.company_a)),
        )
        # Reinstated: the termination date is cleared.
        response = self.client.patch(
            reverse("employee-detail", args=[self.emp_a.pk]), {"status": "active"}, format="json"
        )
        self.assertIsNone(response.data["termination_date"])


class SalaryVisibilityTests(ReviewBase):
    def test_branch_manager_sees_staff_but_not_salaries(self):
        self.emp_a.base_salary_override = Decimal("1200.00")
        self.emp_a.save(update_fields=["base_salary_override"])
        manager_role = Role.objects.create(name="Branch Manager", scope_level=Role.SCOPE_BRANCH)
        manager = User.objects.create_user(
            email="bm@alpha.test", password="passw0rd123", company=self.company_a,
            branch=self.branch_a, role=manager_role,
        )
        client = self.client_class()
        client.force_authenticate(manager)
        employees = client.get(reverse("employee-list"))
        self.assertEqual(employees.status_code, 200, employees.data)
        row = employees.data["results"][0]
        self.assertEqual(row["full_name"], "Amina Ali")
        self.assertNotIn("base_salary_override", row)
        positions = client.get(reverse("position-list"))
        self.assertEqual(positions.status_code, 200, positions.data)
        self.assertNotIn("base_salary", positions.data["results"][0])
        detail = client.get(reverse("employee-detail", args=[self.emp_a.pk]))
        self.assertNotIn("base_salary_override", detail.data)

        # HR keeps seeing them.
        hr_row = self.client.get(reverse("employee-list")).data["results"][0]
        self.assertEqual(hr_row["base_salary_override"], "1200.00")
        self.assertEqual(
            self.client.get(reverse("position-list")).data["results"][0]["base_salary"],
            "1000.00",
        )


class AttendanceRuleTests(ReviewBase):
    def mark(self, day, employee=None, status="present"):
        return self.client.post(
            reverse("attendance-list"),
            {"employee": (employee or self.emp_a).pk, "date": str(day), "status": status},
            format="json",
        )

    def test_future_day_is_refused(self):
        today = company_today(self.company_a)
        self.assertEqual(self.mark(today + timedelta(days=1)).status_code, 400)
        self.assertEqual(self.mark(today).status_code, 201)

    def test_day_before_hire_is_refused(self):
        self.emp_a.hire_date = date(2026, 8, 10)
        self.emp_a.save(update_fields=["hire_date"])
        self.assertEqual(self.mark(date(2026, 8, 9)).status_code, 400)
        self.assertEqual(self.mark(date(2026, 8, 10)).status_code, 201)

    def test_terminated_employee_only_up_to_termination(self):
        self.emp_a.status = Employee.STATUS_TERMINATED
        self.emp_a.termination_date = date(2026, 8, 20)
        self.emp_a.save(update_fields=["status", "termination_date"])
        self.assertEqual(self.mark(date(2026, 8, 21)).status_code, 400)
        self.assertEqual(self.mark(date(2026, 8, 20)).status_code, 201)
        undated = Employee.objects.create(
            company=self.company_a, branch=self.branch_a, full_name="Old Leaver",
            status=Employee.STATUS_TERMINATED,
        )
        self.assertEqual(self.mark(date(2026, 8, 3), undated).status_code, 400)

    def test_manual_leave_mark_is_refused(self):
        response = self.mark(date(2026, 8, 3), status="leave")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("status", response.data)


class FutureMonthTests(ReviewBase):
    def test_future_month_cannot_be_created_or_approved(self):
        future = company_today(self.company_a).replace(day=1) + timedelta(days=40)
        response = self.client.post(
            reverse("payrollrun-list"), {"period": future.strftime("%Y-%m")}, format="json"
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data["code"], "payroll_future_month")
        run = PayrollRun.objects.create(company=self.company_a, period=future.replace(day=1))
        refused = self.cfo.post(reverse("payrollrun-approve", args=[run.pk]))
        self.assertEqual(refused.status_code, 400, refused.data)
        self.assertEqual(PayrollRun.objects.get(pk=run.pk).status, PayrollRun.DRAFT)
        # The current month may be prepared.
        current = company_today(self.company_a).strftime("%Y-%m")
        self.assertEqual(
            self.client.post(
                reverse("payrollrun-list"), {"period": current}, format="json"
            ).status_code,
            201,
        )


class LeaveStatusDayTests(ReviewBase):
    def test_leave_starting_today_in_the_company_calendar_counts(self):
        LeaveRequest.objects.create(
            company=self.company_a, employee=self.emp_a, leave_type=LeaveRequest.ANNUAL,
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 3),
            status=LeaveRequest.APPROVED,
        )
        # 23:30 UTC on 31 July is 01:30 on 1 August in Khartoum.
        with patch(
            "django.utils.timezone.now",
            return_value=datetime(2026, 7, 31, 23, 30, tzinfo=ZoneInfo("UTC")),
        ):
            refresh_employee_leave_statuses(self.company_a.pk)
        self.emp_a.refresh_from_db()
        self.assertEqual(self.emp_a.status, Employee.STATUS_ON_LEAVE)
