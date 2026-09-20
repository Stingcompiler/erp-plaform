"""Sign-in fills last_login; authenticated requests keep last_seen_at fresh
(throttled); the team pages show who is online; the migration backfills
both from the audit trail for accounts that signed in before this existed."""
from datetime import timedelta
from importlib import import_module

from django.apps import apps
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from accounts.presence import ONLINE_WINDOW, TOUCH_INTERVAL, is_online, touch_last_seen
from core.models import ActivityLog


class PresenceTests(APITestCase):
    def setUp(self):
        self.root = User.objects.create_superuser("root@vezano.test", "secure-password")

    def _login(self, email, password):
        return self.client.post(reverse("auth-login"), {"email": email, "password": password,
                                                        "device_id": "TEST"})

    def test_login_records_last_login_and_last_seen(self):
        self.assertIsNone(self.root.last_login)
        before = timezone.now()
        response = self._login("root@vezano.test", "secure-password")
        self.assertEqual(response.status_code, 200, response.data)
        self.root.refresh_from_db()
        self.assertIsNotNone(self.root.last_login)
        self.assertGreaterEqual(self.root.last_login, before)
        self.assertGreaterEqual(self.root.last_seen_at, before)
        self.assertTrue(is_online(self.root))

    def test_authenticated_request_touches_last_seen_at_most_every_interval(self):
        stale = timezone.now() - ONLINE_WINDOW - timedelta(minutes=1)
        User.objects.filter(pk=self.root.pk).update(last_seen_at=stale)
        self.client.cookies[settings.SIMPLE_JWT["AUTH_COOKIE"]] = str(
            RefreshToken.for_user(self.root).access_token
        )
        self.assertEqual(self.client.get(reverse("auth-me")).status_code, 200)
        self.root.refresh_from_db()
        first = self.root.last_seen_at
        self.assertGreater(first, stale)
        self.assertTrue(is_online(self.root))
        # A second request right away is not another write.
        self.assertEqual(self.client.get(reverse("auth-me")).status_code, 200)
        self.root.refresh_from_db()
        self.assertEqual(self.root.last_seen_at, first)
        # Once the interval has passed, the next request writes again.
        User.objects.filter(pk=self.root.pk).update(
            last_seen_at=first - TOUCH_INTERVAL - timedelta(seconds=1)
        )
        self.assertEqual(self.client.get(reverse("auth-me")).status_code, 200)
        self.root.refresh_from_db()
        self.assertGreater(self.root.last_seen_at, first - timedelta(seconds=1))

    def test_touch_does_not_bump_updated_at(self):
        updated = self.root.updated_at
        self.assertTrue(touch_last_seen(self.root, force=True))
        self.root.refresh_from_db()
        self.assertEqual(self.root.updated_at, updated)

    def test_team_list_and_overview_show_who_is_online(self):
        self.client.force_authenticate(self.root)
        invited = self.client.post(
            reverse("platform-team-list"),
            {"email": "agent@vezano.test", "full_name": "Agent", "role": "Support Agent"},
            format="json",
        ).data
        agent = User.objects.get(pk=invited["id"])
        touch_last_seen(self.root, force=True)
        User.objects.filter(pk=agent.pk).update(
            last_seen_at=timezone.now() - ONLINE_WINDOW - timedelta(minutes=10),
            last_login=timezone.now() - timedelta(days=2),
        )
        listed = self.client.get(reverse("platform-team-list")).data
        rows = {row["email"]: row for row in listed.get("results", listed)}
        self.assertTrue(rows["root@vezano.test"]["online"])
        self.assertFalse(rows["agent@vezano.test"]["online"])
        self.assertIsNotNone(rows["agent@vezano.test"]["last_seen_at"])
        overview = self.client.get(reverse("platform-overview")).data
        self.assertEqual([row["email"] for row in overview["team"]][0], "root@vezano.test")
        self.assertEqual(len(overview["team"]), 2)
        # A member without the team view gets no team block at all.
        agent.set_password("agent-secure-password")
        agent.save()
        self.client.force_authenticate(agent)
        self.assertNotIn("team", self.client.get(reverse("platform-overview")).data)

    def test_migration_backfills_from_the_audit_trail(self):
        old = User.objects.create_user("old@vezano.test", "secure-password")
        never = User.objects.create_user("never@vezano.test", "secure-password")
        first = timezone.now() - timedelta(days=5)
        latest_login = timezone.now() - timedelta(days=1)
        later_action = timezone.now() - timedelta(hours=3)
        for when, action in ((first, "login"), (latest_login, "login"), (later_action, "update")):
            row = ActivityLog.objects.create(action=action, user=old)
            ActivityLog.objects.filter(pk=row.pk).update(created_at=when)
        User.objects.filter(pk__in=[old.pk, never.pk]).update(last_login=None, last_seen_at=None)

        migration = import_module("accounts.migrations.0004_user_last_seen_at")
        migration.backfill_from_activity(apps, None)

        old.refresh_from_db()
        never.refresh_from_db()
        self.assertEqual(old.last_login, latest_login)
        self.assertEqual(old.last_seen_at, later_action)
        self.assertIsNone(never.last_login)
        self.assertIsNone(never.last_seen_at)
