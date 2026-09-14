from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.models import ActivityLog
from org.models import Company
from subscriptions.models import Plan, PlanVersion, Subscription
from subscriptions.tasks import scan_subscription_expiries


class SubscriptionScanTests(TestCase):
    def test_scan_counts_each_queue_and_logs_once(self):
        plan = Plan.objects.create(code="p", name="P")
        version = PlanVersion.objects.create(plan=plan, version=1, published_at=timezone.now())
        now = timezone.now()
        for name, status, kwargs in (
            ("ending", Subscription.TRIALING, {"trial_ends_at": now + timedelta(days=3)}),
            ("lapsed-trial", Subscription.TRIALING, {"trial_ends_at": now - timedelta(days=1)}),
            ("lapsed-period", Subscription.ACTIVE, {"period_ends_at": now - timedelta(days=1)}),
            ("grace", Subscription.GRACE, {"grace_ends_at": now + timedelta(days=2)}),
            ("fine", Subscription.ACTIVE, {"period_ends_at": now + timedelta(days=90)}),
        ):
            Subscription.objects.create(
                company=Company.objects.create(name=name),
                plan_version=version,
                status=status,
                starts_at=now,
                **kwargs,
            )
        payload = scan_subscription_expiries()
        self.assertEqual(
            payload,
            {"trials_ending_7d": 1, "trials_lapsed": 1, "periods_lapsed": 1, "grace_closing_7d": 1},
        )
        self.assertEqual(ActivityLog.objects.filter(entity_type="SubscriptionExpiries").count(), 1)
