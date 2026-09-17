"""First-party visit recording: what gets counted, what never does.

The rules under test: marketing pages and public company pages are
recorded server-side; the signed-in workspace, assets, bots and logged-in
people are not; the visitor hash cannot link one person across days; the
nightly rollup is idempotent and prunes the hot table; and a failing
insert never breaks the page being served.
"""

from datetime import timedelta
from unittest import mock

from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from website import analytics
from website.models import DailyPageStat, PageVisit

UA_PHONE = "Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36"
UA_DESKTOP = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) AppleWebKit/537.36"
UA_BOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"


def _get(path="/", ua=UA_DESKTOP, referer="", ip="203.0.113.9", cookies=None):
    request = RequestFactory().get(path, HTTP_USER_AGENT=ua, REMOTE_ADDR=ip)
    if referer:
        request.META["HTTP_REFERER"] = referer
    for key, value in (cookies or {}).items():
        request.COOKIES[key] = value
    return request


class MarketingClassificationTests(TestCase):
    def test_marketing_paths_in_both_languages(self):
        self.assertEqual(analytics.marketing_kind_for(""), ("marketing", "ar"))
        self.assertEqual(analytics.marketing_kind_for("pricing"), ("marketing", "ar"))
        self.assertEqual(analytics.marketing_kind_for("en"), ("marketing", "en"))
        self.assertEqual(
            analytics.marketing_kind_for("en/guides/collect-customer-debts"),
            ("marketing", "en"),
        )

    def test_workspace_and_auth_paths_are_not_marketing(self):
        for path in ("dashboard", "sales", "login", "activate-owner", "platform", "users"):
            self.assertIsNone(analytics.marketing_kind_for(path), path)


class RecordTests(TestCase):
    def test_records_a_marketing_visit(self):
        analytics.record(
            _get("/pricing/", referer="https://google.com/search"),
            "pricing", page_kind="marketing", language="ar",
        )
        visit = PageVisit.objects.get()
        self.assertEqual(visit.path, "/pricing")
        self.assertEqual(visit.referrer_host, "google.com")
        self.assertEqual(visit.device, "desktop")
        self.assertFalse(visit.is_bot)

    def test_signed_in_users_are_not_visitors(self):
        analytics.record(
            _get("/", cookies={"access_token": "x"}), "", page_kind="marketing"
        )
        self.assertEqual(PageVisit.objects.count(), 0)

    def test_bots_are_flagged(self):
        analytics.record(_get("/", ua=UA_BOT), "", page_kind="marketing")
        self.assertTrue(PageVisit.objects.get().is_bot)

    def test_own_host_referrals_are_direct(self):
        analytics.record(
            _get("/", referer="https://www.vezano.app/pricing/"), "", page_kind="marketing"
        )
        self.assertEqual(PageVisit.objects.get().referrer_host, "")

    def test_phone_is_detected(self):
        analytics.record(_get("/", ua=UA_PHONE), "", page_kind="marketing")
        self.assertEqual(PageVisit.objects.get().device, "phone")

    def test_same_visitor_same_day_same_hash_different_ip_differs(self):
        analytics.record(_get("/"), "", page_kind="marketing")
        analytics.record(_get("/pricing/"), "pricing", page_kind="marketing")
        analytics.record(_get("/", ip="198.51.100.7"), "", page_kind="marketing")
        hashes = list(PageVisit.objects.values_list("visitor_hash", flat=True))
        self.assertEqual(hashes[0], hashes[1])
        self.assertNotEqual(hashes[0], hashes[2])

    def test_hash_is_unlinkable_across_days(self):
        request = _get("/")
        today = timezone.localdate()
        self.assertNotEqual(
            analytics._visitor_hash(request, today),
            analytics._visitor_hash(request, today - timedelta(days=1)),
        )

    def test_insert_failure_never_raises(self):
        with mock.patch(
            "website.models.PageVisit.objects", side_effect=RuntimeError
        ) as objects:
            objects.create.side_effect = RuntimeError("db down")
            analytics.record(_get("/"), "", page_kind="marketing")  # must not raise


class ServeIntegrationTests(TestCase):
    """The export-serving path records marketing pages and nothing else."""

    @override_settings(DEBUG=False)
    def test_marketing_page_is_recorded_and_workspace_is_not(self):
        from core.frontend import serve_frontend

        for path in ("pricing", "dashboard", "_next/static/x.css"):
            try:
                serve_frontend(_get(f"/{path}/"), path)
            except Exception:
                pass  # missing files 404 in a bare test tree; recording happens first
        paths = list(PageVisit.objects.values_list("path", flat=True))
        self.assertEqual(paths, ["/pricing"])


class RollupTests(TestCase):
    def _visit(self, days_ago, path="/pricing", **kwargs):
        analytics.record(
            _get(path + "/", **kwargs), path.strip("/"), page_kind="marketing", language="ar"
        )
        visit = PageVisit.objects.latest("id")
        PageVisit.objects.filter(pk=visit.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago)
        )

    def test_rollup_aggregates_prunes_and_reruns_cleanly(self):
        self._visit(1)
        self._visit(1, referer="https://google.com/")
        self._visit(1, ip="198.51.100.7", ua=UA_PHONE)
        self._visit(1, ua=UA_BOT)
        self._visit(8, path="/product")  # old enough to be pruned after rollup
        self._visit(0)  # today: untouched

        result = analytics.rollup()

        stat = DailyPageStat.objects.get(path="/pricing")
        self.assertEqual(stat.visits, 3)
        self.assertEqual(stat.visitors, 2)
        self.assertEqual(stat.bot_visits, 1)
        self.assertEqual(stat.referrers.get("google.com"), 1)
        self.assertEqual(stat.devices.get("phone"), 1)
        self.assertEqual(result["pruned"], 1)
        # Today's visit stays hot; a re-run changes nothing.
        self.assertEqual(PageVisit.objects.filter(created_at__date=timezone.localdate()).count(), 1)
        analytics.rollup()
        self.assertEqual(DailyPageStat.objects.filter(path="/pricing").count(), 1)
        self.assertEqual(DailyPageStat.objects.get(path="/pricing").visits, 3)
