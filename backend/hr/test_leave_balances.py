from datetime import date
from decimal import Decimal
from django.urls import reverse
from hr.tests import HrBase
from hr.models import LeaveAllowance, LeaveRequest
from hr.leave_balances import balance, days_in_year


class LeaveBalanceTests(HrBase):
    def allocate(self, days=10, year=2026, carried=0):
        response = self.client.post(
            reverse("leaveallowance-list"),
            {
                "employee": self.emp_a.pk,
                "year": year,
                "leave_type": "annual",
                "entitled_days": days,
                "carried_days": carried,
                "note": "Reviewed allocation",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return LeaveAllowance.objects.get(pk=response.data["id"])

    def request_leave(self, start="2026-09-10", end="2026-09-12"):
        response = self.client.post(
            reverse("leaverequest-list"),
            {
                "employee": self.emp_a.pk,
                "start_date": start,
                "end_date": end,
                "leave_type": "annual",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response.data["id"]

    def test_approval_consumes_and_cancellation_restores(self):
        allowance = self.allocate(days=5, carried=2)
        pk = self.request_leave()
        self.assertEqual(balance(allowance)["pending_days"], 3)
        self.assertEqual(balance(allowance)["remaining_days"], 7)
        self.assertEqual(
            self.client.post(reverse("leaverequest-approve", args=[pk])).status_code, 200
        )
        self.assertEqual(balance(allowance)["remaining_days"], 4)
        self.assertEqual(
            self.client.post(
                reverse("leaverequest-cancel", args=[pk]),
                {"reason": "Cancelled trip"},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(balance(allowance)["remaining_days"], 7)

    def test_insufficient_balance_blocks_approval_without_attendance(self):
        self.allocate(days=2)
        pk = self.request_leave()
        response = self.client.post(reverse("leaverequest-approve", args=[pk]))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "insufficient_leave_balance")
        self.assertEqual(LeaveRequest.objects.get(pk=pk).status, "pending")
        self.assertEqual(self.emp_a.attendance.count(), 0)

    def test_cross_year_leave_charges_each_year(self):
        first, second = self.allocate(days=2), self.allocate(days=2, year=2027)
        pk = self.request_leave("2026-12-31", "2027-01-02")
        self.assertEqual(
            self.client.post(reverse("leaverequest-approve", args=[pk])).status_code, 200
        )
        self.assertEqual(balance(first)["used_days"], 1)
        self.assertEqual(balance(second)["used_days"], 2)
        self.assertEqual(days_in_year(date(2024, 2, 28), date(2024, 3, 1), 2024), Decimal(3))

    def test_cannot_reduce_below_usage_or_delete_allocation(self):
        allowance = self.allocate()
        pk = self.request_leave()
        self.client.post(reverse("leaverequest-approve", args=[pk]))
        url = reverse("leaveallowance-detail", args=[allowance.pk])
        self.assertEqual(
            self.client.patch(
                url, {"entitled_days": 1, "note": "Reduction"}, format="json"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.patch(
                url, {"entitled_days": 8, "note": "Reviewed adjustment"}, format="json"
            ).status_code,
            200,
        )
        self.assertEqual(self.client.delete(url).status_code, 405)

    def test_validation_and_company_isolation(self):
        allowance = self.allocate()
        payload = {
            "employee": self.emp_a.pk,
            "year": 2026,
            "leave_type": "annual",
            "entitled_days": 5,
            "note": "duplicate",
        }
        self.assertEqual(
            self.client.post(reverse("leaveallowance-list"), payload, format="json").status_code,
            400,
        )
        payload.update(employee=self.emp_b.pk, year=2027)
        self.assertEqual(
            self.client.post(reverse("leaveallowance-list"), payload, format="json").status_code,
            400,
        )
        url = reverse("leaveallowance-detail", args=[allowance.pk])
        self.assertEqual(
            self.client.patch(
                url, {"entitled_days": -1, "note": "Invalid"}, format="json"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.patch(url, {"entitled_days": 20}, format="json").status_code, 400
        )
        other = LeaveAllowance.objects.create(
            company=self.company_b,
            employee=self.emp_b,
            year=2026,
            leave_type="annual",
            entitled_days=10,
            note="Other company",
        )
        self.assertEqual(
            self.client.get(reverse("leaveallowance-detail", args=[other.pk])).status_code, 404
        )

    def test_unconfigured_balance_preserves_existing_workflow(self):
        pk = self.request_leave()
        self.assertEqual(
            self.client.post(reverse("leaverequest-approve", args=[pk])).status_code, 200
        )
