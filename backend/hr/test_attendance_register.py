"""The attendance register: a day view and a month summary per employee."""

from datetime import date

from hr.models import Attendance
from hr.tests import HrBase


class AttendanceRegisterTests(HrBase):
    def setUp(self):
        super().setUp()
        for day, status_value in ((1, "present"), (2, "present"), (3, "absent"), (4, "half_day")):
            Attendance.objects.create(
                company=self.company_a, employee=self.emp_a,
                date=date(2026, 9, day), status=status_value,
            )
        # Another company's rows never leak into the summary.
        Attendance.objects.create(
            company=self.company_b, employee=self.emp_b, date=date(2026, 9, 1), status="present",
        )

    def test_month_summary_counts_days_per_status(self):
        response = self.client.get("/api/attendance/summary/", {"month": "2026-09"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["start"], "2026-09-01")
        self.assertEqual(response.data["end"], "2026-09-30")
        self.assertEqual(len(response.data["rows"]), 1)
        row = response.data["rows"][0]
        self.assertEqual(row["employee"], self.emp_a.id)
        counts = (row["present"], row["absent"], row["leave"], row["half_day"])
        self.assertEqual(counts, (2, 1, 0, 1))

    def test_bad_month_is_a_400(self):
        response = self.client.get("/api/attendance/summary/", {"month": "september"})
        self.assertEqual(response.status_code, 400)

    def test_range_filter(self):
        response = self.client.get("/api/attendance/", {"start": "2026-09-02", "end": "2026-09-03"})
        self.assertEqual(response.status_code, 200)
        days = sorted(r["date"] for r in response.data["results"])
        self.assertEqual(days, ["2026-09-02", "2026-09-03"])
