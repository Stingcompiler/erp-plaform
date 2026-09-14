from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from core.models import ActivityLog
from org.models import Company


class DailyScansCommandTests(TestCase):
    def test_runs_all_three_scans_without_a_broker(self):
        Company.objects.create(name="Alpha")
        out = StringIO()
        call_command("run_daily_scans", stdout=out)
        text = out.getvalue()
        for name in ("receivables: ok", "stock: ok", "subscriptions: ok"):
            self.assertIn(name, text)
        # Nothing to report on an empty company: no audit rows, no crash.
        self.assertEqual(ActivityLog.objects.filter(action="scan").count(), 0)

    def test_only_flag_limits_to_one_scan(self):
        out = StringIO()
        call_command("run_daily_scans", only="stock", stdout=out)
        self.assertIn("stock: ok", out.getvalue())
        self.assertNotIn("receivables", out.getvalue())
