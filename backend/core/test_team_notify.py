"""Platform-team notices: who gets them, each event sends once, replays and
mail outages are harmless, and push reaches platform members' browsers."""

from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock
from uuid import uuid4

from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role, User
from core import platform_roles, team_notify
from core.models import ActivityLog
from org.models import Branch, Company
from subscriptions.models import Plan, PlanVersion, Subscription
from subscriptions.tasks import scan_subscription_expiries
from website.models import PushSubscription

MAIL = dict(
    EMAIL_ENABLED=True,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PUBLIC_APP_ORIGIN="https://vezano.test",
    PLATFORM_NOTIFY_EMAILS=[],
    TEAM_NOTIFY_BACKGROUND=False,
)


class TeamFixture:
    def make_team(self):
        roles = platform_roles.ensure_platform_roles()
        self.root = User.objects.create_superuser(email="root@vezano.test", password="x" * 12)
        self.sales = User.objects.create_user(
            email="sales@vezano.test", password=None, role=roles["Subscription Manager"],
        )
        self.billing = User.objects.create_user(
            email="billing@vezano.test", password=None, role=roles["Billing Reviewer"],
        )
        self.marketing = User.objects.create_user(
            email="marketing@vezano.test", password=None, role=roles["Marketing Manager"],
        )
        self.support = User.objects.create_user(
            email="support@vezano.test", password=None, role=roles["Support Agent"],
        )
        self.gone = User.objects.create_user(
            email="gone@vezano.test", password=None, role=roles["Subscription Manager"],
            is_active=False,
        )

    def sent_to(self):
        return sorted(address for message in mail.outbox for address in message.to)


@override_settings(**MAIL)
class RecipientTests(TeamFixture, TestCase):
    def setUp(self):
        self.make_team()

    def emails(self, capability):
        members, extras = team_notify.recipients(capability)
        return sorted(u.email for u in members), extras

    def test_capability_decides_and_superusers_always_count(self):
        self.assertEqual(
            self.emails(platform_roles.REGISTRATIONS_REVIEW)[0],
            ["root@vezano.test", "sales@vezano.test"],
        )
        self.assertEqual(
            self.emails(platform_roles.BILLING_REVIEW)[0],
            ["billing@vezano.test", "root@vezano.test", "sales@vezano.test"],
        )
        self.assertEqual(
            self.emails(platform_roles.LEADS_MANAGE)[0],
            ["marketing@vezano.test", "root@vezano.test", "sales@vezano.test",
             "support@vezano.test"],
        )

    def test_inactive_and_tenant_users_are_left_out(self):
        company = Company.objects.create(name="Tenant")
        owner = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        User.objects.create_user(email="owner@tenant.test", password=None,
                                 company=company, role=owner)
        members = self.emails(platform_roles.SUBSCRIPTIONS_MANAGE)[0]
        self.assertNotIn("gone@vezano.test", members)
        self.assertNotIn("owner@tenant.test", members)

    @override_settings(PLATFORM_NOTIFY_EMAILS=[
        "inbox@vezano.test", "ROOT@vezano.test", "inbox@vezano.test", "not-an-address",
    ])
    def test_extra_addresses_are_added_once(self):
        members, extras = self.emails(platform_roles.REGISTRATIONS_REVIEW)
        self.assertEqual(members, ["root@vezano.test", "sales@vezano.test"])
        self.assertEqual(extras, ["inbox@vezano.test"])

    def test_each_address_gets_one_bilingual_email_with_the_admin_link(self):
        with self.captureOnCommitCallbacks(execute=True):
            team_notify.notify_platform_team(
                "x", subject_ar="ع", subject_en="E", ar=["سطر"], en=["line"],
                link_path="/platform-leads/", capability=platform_roles.LEADS_MANAGE,
            )
        self.assertEqual(len(mail.outbox), 4)
        self.assertIn("https://vezano.test/platform-leads/", mail.outbox[0].body)

    def test_nothing_is_sent_when_the_transaction_rolls_back(self):
        from django.db import transaction

        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            try:
                with transaction.atomic():
                    team_notify.notify_platform_team(
                        "x", subject_ar="ع", subject_en="E", ar=[], en=[],
                        link_path="/", capability=platform_roles.LEADS_MANAGE,
                    )
                    raise RuntimeError
            except RuntimeError:
                pass
        self.assertEqual(callbacks, [])


@override_settings(**MAIL)
class PushTests(TeamFixture, TestCase):
    def setUp(self):
        self.make_team()

    @override_settings(VAPID_PUBLIC_KEY="pub", VAPID_PRIVATE_KEY="priv", WEB_PUSH_ENABLED=True)
    def test_platform_member_can_subscribe_and_is_pushed(self):
        client = APIClient()
        client.force_authenticate(self.billing)
        response = client.post("/api/push/subscription/", {
            "endpoint": "https://fcm.googleapis.com/fcm/send/abc",
            "keys": {"p256dh": "k", "auth": "a"},
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(PushSubscription.objects.get().company_id)
        with mock.patch("core.push.send_to_user", return_value=1) as push:
            sent = team_notify.deliver(
                "x", subject_ar="ع", subject_en="E", ar=[], en=[],
                link_path="/platform-subscriptions/", capability=platform_roles.BILLING_REVIEW,
                push_title="t", push_body="b", tag="team-x",
            )
        pushed = sorted(call.args[0].email for call in push.call_args_list)
        self.assertEqual(
            pushed, ["billing@vezano.test", "root@vezano.test", "sales@vezano.test"]
        )
        self.assertEqual(push.call_args.kwargs["url"], "/platform-subscriptions/")
        self.assertEqual(sent, {"emails": 3, "pushes": 3})

    def test_a_push_failure_does_not_stop_the_emails(self):
        with mock.patch("core.push.send_to_user", side_effect=RuntimeError("down")):
            sent = team_notify.deliver(
                "x", subject_ar="ع", subject_en="E", ar=[], en=[],
                link_path="/", capability=platform_roles.BILLING_REVIEW,
            )
        self.assertEqual(sent["emails"], 3)


@override_settings(**MAIL)
class PublicEventTests(TeamFixture, TestCase):
    def setUp(self):
        cache.clear()
        self.make_team()
        plan = Plan.objects.create(code="p", name="Shop")
        self.version = PlanVersion.objects.create(
            plan=plan, version=1, currency="SDG", price=Decimal("1000"),
            published_at=timezone.now(),
        )

    def register(self, request_uuid):
        cache.clear()
        with self.captureOnCommitCallbacks(execute=True):
            return APIClient().post("/api/public/registration-requests/", {
                "request_uuid": request_uuid, "company_name": "Nile Shop",
                "contact_name": "Ali", "email": "ali@visitor.test", "phone": "+249912345678",
                "delivery_mode": "saas", "plan_version": self.version.pk,
                "privacy_version": "2026-01", "country": "SD",
            }, format="json")

    def test_registration_emails_reviewers_once_and_replays_stay_quiet(self):
        ref = str(uuid4())
        first = self.register(ref)
        self.assertEqual(first.status_code, 201, first.data)
        team = [m for m in mail.outbox if "ali@visitor.test" not in m.to]
        self.assertEqual(
            sorted(m.to[0] for m in team), ["root@vezano.test", "sales@vezano.test"]
        )
        self.assertIn("/platform-registrations/", team[0].body)
        self.assertIn("Nile Shop", team[0].subject)
        # The visitor's contact details stay on the admin page.
        self.assertNotIn("ali@visitor.test", team[0].body)
        self.assertNotIn("912345678", team[0].body)
        mail.outbox.clear()
        again = self.register(ref)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(mail.outbox, [])

    def demo(self, request_uuid):
        cache.clear()
        with self.captureOnCommitCallbacks(execute=True):
            return APIClient().post("/api/public/demo-requests/", {
                "request_uuid": request_uuid, "name": "Sara", "email": "sara@visitor.test",
                "phone": "+249911111111", "preferred_channel": "call",
            }, format="json")

    def test_demo_request_emails_leads_once(self):
        ref = str(uuid4())
        self.assertEqual(self.demo(ref).status_code, 201)
        self.assertEqual(self.sent_to(), [
            "marketing@vezano.test", "root@vezano.test", "sales@vezano.test",
            "support@vezano.test",
        ])
        body = mail.outbox[0].body
        self.assertIn("/platform-leads/", body)
        self.assertIn("Phone call", body)
        self.assertNotIn("sara@visitor.test", body)
        self.assertNotIn("911111111", body)
        mail.outbox.clear()
        self.assertEqual(self.demo(ref).status_code, 201)
        self.assertEqual(mail.outbox, [])

    @override_settings(PLATFORM_NOTIFY_EMAILS=["inbox@vezano.test"])
    def test_extra_inbox_gets_the_notice_too(self):
        self.demo(str(uuid4()))
        self.assertIn("inbox@vezano.test", self.sent_to())

    def test_mail_failure_does_not_break_the_endpoint(self):
        with mock.patch(
            "django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("smtp down")
        ):
            self.assertEqual(self.demo(str(uuid4())).status_code, 201)
            self.assertEqual(self.register(str(uuid4())).status_code, 201)
        with mock.patch.object(team_notify, "recipients", side_effect=RuntimeError("db")):
            self.assertEqual(self.demo(str(uuid4())).status_code, 201)


@override_settings(**MAIL)
class CompanyEventTests(TeamFixture, TestCase):
    def setUp(self):
        self.make_team()
        now = timezone.now()
        self.company = Company.objects.create(name="Alpha Stores", business_type="enterprise")
        Branch.objects.create(company=self.company, name="Main")
        owner_role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password=None, company=self.company, role=owner_role,
        )
        basic = Plan.objects.create(code="basic", name="Basic", sort_order=1)
        pro = Plan.objects.create(code="pro", name="Pro", sort_order=2)
        self.basic = PlanVersion.objects.create(
            plan=basic, version=1, modules=["*"], currency="SDG", price=Decimal("100000"),
            limits={"devices": 2}, published_at=now,
        )
        self.pro = PlanVersion.objects.create(
            plan=pro, version=1, modules=["*"], currency="SDG", price=Decimal("200000"),
            limits={"devices": 5}, published_at=now,
        )
        Subscription.objects.create(
            company=self.company, plan_version=self.basic, status=Subscription.ACTIVE,
            starts_at=now - timedelta(days=15), period_ends_at=now + timedelta(days=15),
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def pay(self, client_uuid):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post("/api/subscription/payments/", {
                "amount": "100000", "currency": "SDG", "method": "cash",
                "client_uuid": client_uuid,
            })

    def test_payment_emails_billing_reviewers_once(self):
        ref = str(uuid4())
        self.assertEqual(self.pay(ref).status_code, 201)
        self.assertEqual(
            self.sent_to(), ["billing@vezano.test", "root@vezano.test", "sales@vezano.test"]
        )
        self.assertIn("Alpha Stores", mail.outbox[0].subject)
        self.assertIn("100000.00 SDG", mail.outbox[0].body)
        self.assertIn("/platform-subscriptions/", mail.outbox[0].body)
        mail.outbox.clear()
        self.assertEqual(self.pay(ref).status_code, 200)
        self.assertEqual(mail.outbox, [])

    def test_payment_survives_a_mail_outage(self):
        with mock.patch(
            "django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("smtp down")
        ):
            self.assertEqual(self.pay(str(uuid4())).status_code, 201)

    def change(self):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                "/api/subscription/plan-changes/", {"to_version": self.pro.pk}, format="json"
            )

    def test_plan_change_emails_subscription_managers_once(self):
        self.assertEqual(self.change().status_code, 201)
        self.assertEqual(self.sent_to(), ["root@vezano.test", "sales@vezano.test"])
        self.assertIn("Pro", mail.outbox[0].body)
        mail.outbox.clear()
        self.assertEqual(self.change().status_code, 400)  # one open request at a time
        self.assertEqual(mail.outbox, [])


@override_settings(**MAIL)
class TrialEndingTests(TeamFixture, TestCase):
    def setUp(self):
        self.make_team()
        plan = Plan.objects.create(code="t", name="Trial")
        version = PlanVersion.objects.create(plan=plan, version=1, published_at=timezone.now())
        now = timezone.now()
        for name, days in (("Soon", 2), ("Later", 6)):
            Subscription.objects.create(
                company=Company.objects.create(name=name), plan_version=version,
                status=Subscription.TRIALING, starts_at=now,
                trial_ends_at=now + timedelta(days=days),
            )

    def test_trials_ending_within_three_days_are_announced_once(self):
        # The cron runs outside a transaction, so on_commit fires at once;
        # inside a TestCase the callbacks are captured and run here.
        with self.captureOnCommitCallbacks(execute=True):
            payload = scan_subscription_expiries()
        self.assertEqual(payload["trial_notices_sent"], 1)
        self.assertEqual(self.sent_to(), ["root@vezano.test", "sales@vezano.test"])
        self.assertIn("Soon", mail.outbox[0].subject)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(scan_subscription_expiries()["trial_notices_sent"], 0)
            call_command("run_daily_scans", "--only", "subscriptions", stdout=StringIO())
        self.assertEqual(mail.outbox, [])
        self.assertEqual(
            ActivityLog.objects.filter(action=team_notify.TRIAL_NOTICE_ACTION).count(), 1
        )

    def test_an_extended_trial_is_announced_for_its_new_date(self):
        scan_subscription_expiries()
        mail.outbox.clear()
        sub = Subscription.objects.get(company__name="Soon")
        sub.trial_ends_at += timedelta(hours=12)
        sub.save(update_fields=["trial_ends_at"])
        self.assertEqual(scan_subscription_expiries()["trial_notices_sent"], 1)

    def test_a_failing_notice_does_not_fail_the_scan(self):
        with mock.patch.object(team_notify, "notify_trials_ending", side_effect=RuntimeError):
            payload = scan_subscription_expiries()
        self.assertEqual(payload["trial_notices_sent"], 0)


class NoMigrationTests(TestCase):
    def test_no_model_changes_are_pending(self):
        out = StringIO()
        call_command("makemigrations", "--check", "--dry-run", stdout=out, stderr=out)
