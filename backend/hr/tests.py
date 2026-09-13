from django.urls import reverse
from datetime import date, datetime, timedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role, User
from hr.models import Employee, LeaveRequest, Position
from org.models import Branch, Company


class HrBase(APITestCase):
    def setUp(self):
        self.company_a = Company.objects.create(name="Alpha")
        self.company_b = Company.objects.create(name="Beta")
        self.branch_a = Branch.objects.create(company=self.company_a, name="Main")
        self.branch_b = Branch.objects.create(company=self.company_b, name="Main")
        self.role = Role.objects.create(name="HR Officer", scope_level=Role.SCOPE_BRANCH)
        self.user_a = User.objects.create_user(
            email="a@alpha.test",
            password="passw0rd123",
            company=self.company_a,
            branch=self.branch_a,
            role=self.role,
        )
        self.pos_a = Position.objects.create(company=self.company_a, title="Cashier")
        self.emp_a = Employee.objects.create(
            company=self.company_a, branch=self.branch_a, full_name="Amina Ali", position=self.pos_a
        )
        self.emp_b = Employee.objects.create(
            company=self.company_b, branch=self.branch_b, full_name="Beta Person"
        )
        self.client.force_authenticate(self.user_a)


class EmployeeTests(HrBase):
    def test_create_employee_forces_company(self):
        resp = self.client.post(
            reverse("employee-list"),
            {"full_name": "New Hire", "position": self.pos_a.id, "status": "active"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        emp = Employee.objects.get(pk=resp.data["id"])
        self.assertEqual(emp.company_id, self.company_a.id)

    def test_list_is_company_scoped(self):
        resp = self.client.get(reverse("employee-list"))
        names = [row["full_name"] for row in resp.data["results"]]
        self.assertIn("Amina Ali", names)
        self.assertNotIn("Beta Person", names)

    def test_cannot_attach_other_company_position(self):
        pos_b = Position.objects.create(company=self.company_b, title="Manager")
        resp = self.client.post(
            reverse("employee-list"),
            {"full_name": "X", "position": pos_b.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)


class AttendanceLeavePerfTests(HrBase):
    def test_attendance_unique_per_day(self):
        payload = {"employee": self.emp_a.id, "date": "2026-08-01", "status": "present"}
        first = self.client.post(reverse("attendance-list"), payload, format="json")
        self.assertEqual(first.status_code, 201, first.content)
        second = self.client.post(reverse("attendance-list"), payload, format="json")
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)

    def test_leave_request_approve_action(self):
        today = date.today()
        create = self.client.post(
            reverse("leaverequest-list"),
            {"employee": self.emp_a.id, "start_date": today, "end_date": today + timedelta(days=2)},
            format="json",
        )
        self.assertEqual(create.status_code, 201, create.content)
        lid = create.data["id"]
        approve = self.client.post(reverse("leaverequest-approve", args=[lid]))
        self.assertEqual(approve.status_code, 200, approve.content)
        lr = LeaveRequest.objects.get(pk=lid)
        self.assertEqual(lr.status, "approved")
        self.assertIsNotNone(lr.reviewed_at)
        self.assertEqual(lr.reviewed_by_id, self.user_a.id)
        self.assertEqual(self.emp_a.attendance.filter(status="leave").count(), 3)
        self.emp_a.refresh_from_db()
        self.assertEqual(self.emp_a.status, Employee.STATUS_ON_LEAVE)

    def test_leave_rejects_bad_date_range(self):
        resp = self.client.post(
            reverse("leaverequest-list"),
            {"employee": self.emp_a.id, "start_date": "2026-08-12", "end_date": "2026-08-10"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_performance_rating_bounds(self):
        bad = self.client.post(
            reverse("performancerecord-list"),
            {"employee": self.emp_a.id, "review_date": "2026-08-01", "rating": 9},
            format="json",
        )
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)
        ok = self.client.post(
            reverse("performancerecord-list"),
            {"employee": self.emp_a.id, "review_date": "2026-08-01", "rating": 4},
            format="json",
        )
        self.assertEqual(ok.status_code, 201, ok.content)
        # Reviewer is taken from the request user, never the request body.
        from hr.models import PerformanceRecord

        self.assertEqual(
            PerformanceRecord.objects.get(pk=ok.data["id"]).reviewer_id, self.user_a.id
        )


class HrRbacTests(HrBase):
    def test_sales_officer_denied_hr(self):
        # A non-HR role must not reach HR endpoints (RBAC matrix).
        sales_role = Role.objects.create(name="Sales Officer", scope_level=Role.SCOPE_BRANCH)
        sales_user = User.objects.create_user(
            email="s@alpha.test",
            password="passw0rd123",
            company=self.company_a,
            role=sales_role,
        )
        client = self.client_class()
        client.force_authenticate(sales_user)
        resp = client.get(reverse("employee-list"))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class HrExpansionTests(HrBase):
    def test_position_carries_base_salary(self):
        resp = self.client.post(
            reverse("position-list"),
            {"title": "Manager", "base_salary": "5000.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["base_salary"], "5000.00")

    def test_leave_request_requires_typed_leave(self):
        resp = self.client.post(
            reverse("leaverequest-list"),
            {
                "employee": self.emp_a.id,
                "start_date": "2026-08-01",
                "end_date": "2026-08-03",
                "leave_type": "annual",
                "reason": "trip",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["leave_type"], "annual")
        self.assertEqual(resp.data["has_report"], False)

    def test_salary_advance_approval_flow(self):
        create = self.client.post(
            reverse("salaryadvance-list"),
            {"employee": self.emp_a.id, "amount": "800.00", "reason": "emergency"},
            format="json",
        )
        self.assertEqual(create.status_code, 201, create.content)
        adv_id = create.data["id"]
        # HR creates the request but cannot decide an obligation against salary.
        denied = self.client.post(reverse("salaryadvance-approve", args=[adv_id]))
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

        cfo_role = Role.objects.create(
            name="Chief Financial Officer", scope_level=Role.SCOPE_BUSINESS
        )
        cfo = User.objects.create_user(
            email="cfo@alpha.test",
            password="passw0rd123",
            company=self.company_a,
            role=cfo_role,
        )
        cfo_client = self.client_class()
        cfo_client.force_authenticate(cfo)
        approve = cfo_client.post(reverse("salaryadvance-approve", args=[adv_id]))
        self.assertEqual(approve.status_code, 200, approve.content)
        self.assertEqual(approve.data["status"], "approved")

    def test_hr_can_generate_payroll_and_cfo_can_approve_it(self):
        self.pos_a.base_salary = "1000.00"
        self.pos_a.save(update_fields=["base_salary"])
        self.emp_a.base_salary_override = "1200.00"
        self.emp_a.save(update_fields=["base_salary_override"])
        from hr.models import Deduction, PayrollRun

        Deduction.objects.create(
            company=self.company_a, employee=self.emp_a, amount="50.00", date=date(2026, 9, 10)
        )
        create = self.client.post(reverse("payrollrun-list"), {"period": "2026-09"}, format="json")
        self.assertEqual(create.status_code, status.HTTP_201_CREATED, create.content)
        entry = create.data["entries"][0]
        self.assertEqual(entry["base_salary"], "1200.00")
        self.assertEqual(entry["deductions_total"], "50.00")
        self.assertEqual(entry["net_salary"], "1150.00")

        denied = self.client.post(reverse("payrollrun-approve", args=[create.data["id"]]))
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        cfo_role = Role.objects.create(
            name="Chief Financial Officer", scope_level=Role.SCOPE_BUSINESS
        )
        cfo = User.objects.create_user(
            email="payroll-cfo@alpha.test",
            password="passw0rd123",
            company=self.company_a,
            role=cfo_role,
        )
        client = self.client_class()
        client.force_authenticate(cfo)
        approved = client.post(reverse("payrollrun-approve", args=[create.data["id"]]))
        self.assertEqual(approved.status_code, status.HTTP_200_OK, approved.content)
        self.assertEqual(PayrollRun.objects.get(pk=create.data["id"]).status, PayrollRun.APPROVED)

    def test_draft_payroll_refreshes_and_approved_payroll_stays_locked(self):
        self.pos_a.base_salary = "1000.00"
        self.pos_a.save(update_fields=["base_salary"])
        create = self.client.post(reverse("payrollrun-list"), {"period": "2026-09"}, format="json")
        self.assertEqual(create.status_code, status.HTTP_201_CREATED, create.content)
        run_id = create.data["id"]
        self.assertEqual(create.data["entries"][0]["net_salary"], "1000.00")

        self.emp_a.base_salary_override = "1400.00"
        self.emp_a.save(update_fields=["base_salary_override"])
        refreshed = self.client.post(reverse("payrollrun-refresh", args=[run_id]))
        self.assertEqual(refreshed.status_code, status.HTTP_200_OK, refreshed.content)
        self.assertEqual(refreshed.data["entries"][0]["base_salary"], "1400.00")

        cfo_role = Role.objects.create(
            name="Chief Financial Officer", scope_level=Role.SCOPE_BUSINESS
        )
        cfo = User.objects.create_user(
            email="refresh-cfo@alpha.test",
            password="passw0rd123",
            company=self.company_a,
            role=cfo_role,
        )
        cfo_client = self.client_class()
        cfo_client.force_authenticate(cfo)
        self.assertEqual(
            cfo_client.post(reverse("payrollrun-approve", args=[run_id])).status_code,
            status.HTTP_200_OK,
        )
        locked = self.client.post(reverse("payrollrun-refresh", args=[run_id]))
        self.assertEqual(locked.status_code, status.HTTP_400_BAD_REQUEST, locked.content)

    def test_payroll_includes_undated_deduction_in_its_recorded_month(self):
        self.pos_a.base_salary = "1000.00"
        self.pos_a.save(update_fields=["base_salary"])
        from hr.models import Deduction

        deduction = Deduction.objects.create(
            company=self.company_a, employee=self.emp_a, amount="75.00"
        )
        Deduction.objects.filter(pk=deduction.pk).update(
            created_at=timezone.make_aware(datetime(2026, 9, 12))
        )
        create = self.client.post(reverse("payrollrun-list"), {"period": "2026-09"}, format="json")
        self.assertEqual(create.status_code, status.HTTP_201_CREATED, create.content)
        self.assertEqual(create.data["entries"][0]["net_salary"], "925.00")

    def test_work_policy_and_deduction(self):
        pol = self.client.post(
            reverse("workpolicy-list"),
            {
                "name": "Late arrival",
                "violation_type": "tardiness",
                "description": "Arriving after 9am",
            },
            format="json",
        )
        self.assertEqual(pol.status_code, 201, pol.content)
        ded = self.client.post(
            reverse("deduction-list"),
            {
                "employee": self.emp_a.id,
                "policy": pol.data["id"],
                "amount": "50.00",
                "note": "Late 3 days",
            },
            format="json",
        )
        self.assertEqual(ded.status_code, 201, ded.content)
        self.assertEqual(ded.data["policy_name"], "Late arrival")

    def test_cannot_attach_other_company_policy_to_deduction(self):
        from hr.models import WorkPolicy

        other_pol = WorkPolicy.objects.create(
            company=self.company_b, name="Beta policy", violation_type="misconduct"
        )
        resp = self.client.post(
            reverse("deduction-list"),
            {"employee": self.emp_a.id, "policy": other_pol.id, "amount": "10"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.data)
