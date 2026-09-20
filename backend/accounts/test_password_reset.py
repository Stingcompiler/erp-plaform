from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from org.models import Company


class AdminPasswordResetTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        owner_role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=owner_role,
        )
        self.member = User.objects.create_user(
            email="member@alpha.test", password="oldpassw0rd1",
            company=self.company, role=owner_role,
        )
        r = self.client.post(
            reverse("auth-login"),
            {"email": "owner@alpha.test", "password": "passw0rd123", "device_id": "TEST"},
        )
        assert r.status_code == 200, r.content

    def test_admin_can_reset_member_password(self):
        # Admin sets a new password on another user.
        resp = self.client.patch(
            reverse("user-detail", args=[self.member.id]),
            {"password": "brandnewpass99"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)

        # The member can now log in with the new password (fresh client).
        fresh = self.client_class()
        good = fresh.post(
            reverse("auth-login"),
            {"email": "member@alpha.test", "password": "brandnewpass99", "device_id": "TEST"},
        )
        self.assertEqual(good.status_code, 200)

        # ...and the old password no longer works.
        fresh2 = self.client_class()
        bad = fresh2.post(
            reverse("auth-login"),
            {"email": "member@alpha.test", "password": "oldpassw0rd1", "device_id": "TEST"},
        )
        self.assertEqual(bad.status_code, 400)

    def test_short_reset_password_is_rejected(self):
        resp = self.client.patch(
            reverse("user-detail", args=[self.member.id]),
            {"password": "short1"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
