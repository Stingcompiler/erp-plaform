from datetime import date
from decimal import Decimal

from django.urls import reverse

from hr.models import Employee, LeaveAccrualPolicy, LeaveAllowance
from hr.tests import HrBase


class LeavePolicyTests(HrBase):
    def policy(self, **overrides):
        data = {
            "leave_type": "annual",
            "annual_days": "24",
            "minimum_service_months": 0,
            "prorate_first_year": True,
            "carryover_limit": "5",
            **overrides,
        }
        response = self.client.post(reverse("leaveaccrualpolicy-list"), data, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def generate(self, year):
        return self.client.post(
            reverse("leaveaccrualpolicy-generate"), {"year": year}, format="json"
        )

    def test_generates_prorated_hire_year_and_preserves_existing_balances(self):
        self.emp_a.hire_date = date(2026, 7, 1)
        self.emp_a.save(update_fields=["hire_date"])
        self.policy()
        response = self.generate(2026)
        self.assertEqual(response.status_code, 200, response.data)
        allowance = LeaveAllowance.objects.get(employee=self.emp_a, year=2026, leave_type="annual")
        self.assertEqual(allowance.entitled_days, Decimal("12.10"))
        self.assertEqual(allowance.carried_days, Decimal("0"))
        self.assertEqual(response.data["created"], 1)
        allowance.entitled_days = Decimal("30")
        allowance.note = "Manual agreement"
        allowance.save()
        response = self.generate(2026)
        self.assertEqual(response.data["created"], 0)
        self.assertEqual(response.data["skipped"], 1)
        allowance.refresh_from_db()
        self.assertEqual(allowance.entitled_days, Decimal("30"))
        self.assertEqual(allowance.note, "Manual agreement")

    def test_carryover_is_capped_and_only_previous_remaining_is_carried(self):
        self.emp_a.hire_date = date(2020, 1, 1)
        self.emp_a.save(update_fields=["hire_date"])
        self.policy(annual_days="20", carryover_limit="5")
        LeaveAllowance.objects.create(
            company=self.company_a,
            employee=self.emp_a,
            year=2025,
            leave_type="annual",
            entitled_days=20,
            carried_days=0,
            note="Previous year",
        )
        self.client.post(
            reverse("leaverequest-list"),
            {
                "employee": self.emp_a.pk,
                "leave_type": "annual",
                "start_date": "2025-12-01",
                "end_date": "2025-12-10",
            },
            format="json",
        )
        leave = self.emp_a.leave_requests.get()
        self.client.post(reverse("leaverequest-approve", args=[leave.pk]))
        self.generate(2026)
        allowance = LeaveAllowance.objects.get(employee=self.emp_a, year=2026, leave_type="annual")
        self.assertEqual(allowance.entitled_days, Decimal("20"))
        self.assertEqual(allowance.carried_days, Decimal("5"))

    def test_minimum_service_and_inactive_policy_do_not_generate(self):
        self.emp_a.hire_date = date(2026, 9, 1)
        self.emp_a.save(update_fields=["hire_date"])
        self.policy(minimum_service_months=6)
        response = self.generate(2026)
        self.assertEqual(response.data["created"], 0)
        self.assertEqual(response.data["ineligible"], 1)
        LeaveAccrualPolicy.objects.update(is_active=False)
        response = self.generate(2027)
        self.assertEqual(response.data["created"], 0)

    def test_policy_validation_generation_is_scoped_and_archiving_keeps_history(self):
        policy = self.policy()
        duplicate = self.client.post(
            reverse("leaveaccrualpolicy-list"),
            {
                "leave_type": "annual",
                "annual_days": "10",
                "carryover_limit": "0",
            },
            format="json",
        )
        self.assertEqual(duplicate.status_code, 400)
        invalid = self.client.patch(
            reverse("leaveaccrualpolicy-detail", args=[policy["id"]]),
            {"annual_days": "-1"},
            format="json",
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(self.generate("bad").status_code, 400)
        self.assertEqual(
            self.client.delete(
                reverse("leaveaccrualpolicy-detail", args=[policy["id"]])
            ).status_code,
            204,
        )
        self.assertFalse(LeaveAccrualPolicy.objects.get(pk=policy["id"]).is_active)

    def test_terminated_people_are_excluded(self):
        self.emp_a.status = Employee.STATUS_TERMINATED
        self.emp_a.hire_date = date(2020, 1, 1)
        self.emp_a.save(update_fields=["status", "hire_date"])
        self.policy()
        response = self.generate(2026)
        self.assertEqual(response.data["created"], 0)
