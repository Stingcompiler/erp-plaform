"""An administrator setting someone's password is a security event, not a
profile edit: it gets its own audit row naming who did it, the person is
told by email, and the password they were handed works only long enough to
replace it."""

from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import Role, User
from core.models import ActivityLog
from org.models import Company

EMAIL = {
    "EMAIL_ENABLED": True,
    "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
}


@override_settings(**EMAIL)
class AdminPasswordResetTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha", business_type="enterprise")
        owner_role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        clerk_role = Role.objects.create(name="Sales Officer", scope_level=Role.SCOPE_BUSINESS)
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="Owner-passw0rd!x", company=self.company,
            role=owner_role, full_name="Owner One",
        )
        self.clerk = User.objects.create_user(
            email="clerk@alpha.test", password="Clerk-passw0rd!x", company=self.company,
            role=clerk_role, full_name="Clerk Two",
        )
        self.client = APIClient()

    def _login(self, email, password):
        client = APIClient()
        response = client.post(
            "/api/auth/login/", {"email": email, "password": password}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        return client

    def _admin_resets_clerk(self, password="Handed-passw0rd!9", **extra):
        admin = self._login("owner@alpha.test", "Owner-passw0rd!x")
        response = admin.patch(
            f"/api/users/{self.clerk.pk}/", {"password": password, **extra}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        return admin

    def test_reset_is_its_own_audit_event_naming_the_administrator(self):
        self._admin_resets_clerk()
        rows = ActivityLog.objects.filter(entity_type="User", entity_id=str(self.clerk.pk))
        actions = list(rows.values_list("action", flat=True))
        self.assertIn("password_reset_by_admin", actions)
        # Only the password changed: no empty "update" row beside it.
        self.assertNotIn("update", actions)
        row = rows.get(action="password_reset_by_admin")
        self.assertEqual(row.user_id, self.owner.pk)
        self.assertEqual(row.metadata["target_email"], "clerk@alpha.test")
        self.assertNotIn("Handed-passw0rd!9", str(row.metadata))

    def test_reset_with_other_fields_keeps_the_update_row_too(self):
        self._admin_resets_clerk(full_name="Clerk Renamed")
        actions = set(
            ActivityLog.objects.filter(entity_type="User", entity_id=str(self.clerk.pk))
            .values_list("action", flat=True)
        )
        self.assertEqual(actions, {"update", "password_reset_by_admin"})

    def test_the_person_is_emailed_who_changed_it(self):
        self._admin_resets_clerk()
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["clerk@alpha.test"])
        self.assertIn("Owner One", message.body)
        self.assertNotIn("Handed-passw0rd!9", message.body)

    def test_handed_password_only_opens_the_change_screen(self):
        self._admin_resets_clerk()
        self.clerk.refresh_from_db()
        self.assertTrue(self.clerk.must_change_password)

        clerk = self._login("clerk@alpha.test", "Handed-passw0rd!9")
        me = clerk.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertTrue(me.data["must_change_password"])
        self.assertEqual(clerk.get("/api/rbac/access/").status_code, 200)

        blocked = clerk.get("/api/customers/")
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.data["code"], "password_change_required")

        wrong = clerk.post(
            "/api/auth/change-password/",
            {"current_password": "nope", "new_password": "Mine-only-passw0rd!"}, format="json",
        )
        self.assertEqual(wrong.status_code, 400)

        changed = clerk.post(
            "/api/auth/change-password/",
            {"current_password": "Handed-passw0rd!9", "new_password": "Mine-only-passw0rd!"},
            format="json",
        )
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertFalse(changed.data["must_change_password"])
        # Same client keeps working on the fresh cookies it was handed.
        self.assertEqual(clerk.get("/api/customers/").status_code, 200)
        self.clerk.refresh_from_db()
        self.assertTrue(self.clerk.check_password("Mine-only-passw0rd!"))
        self.assertIn(
            "password_changed",
            set(ActivityLog.objects.filter(user=self.clerk).values_list("action", flat=True)),
        )

    def test_changing_your_own_password_is_not_provisional(self):
        owner = self._login("owner@alpha.test", "Owner-passw0rd!x")
        response = owner.patch(
            f"/api/users/{self.owner.pk}/", {"password": "Owner-new-passw0rd!"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.must_change_password)
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(
            ActivityLog.objects.filter(action="password_reset_by_admin").exists()
        )
