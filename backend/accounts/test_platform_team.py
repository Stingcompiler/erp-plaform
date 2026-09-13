from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import PlatformInvitation, Role, User
from org.models import Company


class PlatformTeamTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("root@vezano.test", "secure-password")
        self.client.force_authenticate(self.admin)

    def _invite(self, email="ops@vezano.test", name="Ops Person"):
        response = self.client.post(
            reverse("platform-team-list"), {"email": email, "full_name": name}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_invite_creates_companyless_platform_member_with_one_time_link(self):
        data = self._invite()
        member = User.objects.get(email="ops@vezano.test")
        self.assertIsNone(member.company_id)
        self.assertEqual(member.role.scope_level, Role.SCOPE_PLATFORM)
        self.assertTrue(member.is_platform_admin)
        self.assertFalse(member.has_usable_password())
        self.assertFalse(data["activated"])
        self.assertIsNotNone(data["invitation_expires_at"])
        token = data["invitation_token"]

        self.client.force_authenticate(None)
        accept_url = reverse("platform-invitation-accept")
        accepted = self.client.post(
            accept_url, {"token": token, "password": "a-sufficiently-secure-password"},
            format="json",
        )
        self.assertEqual(accepted.status_code, 200, accepted.data)
        member.refresh_from_db()
        self.assertTrue(member.check_password("a-sufficiently-secure-password"))
        # Single use.
        again = self.client.post(
            accept_url, {"token": token, "password": "another-secure-password"}, format="json"
        )
        self.assertEqual(again.status_code, 400)
        # The new member can now use platform endpoints.
        self.client.force_authenticate(member)
        self.assertEqual(self.client.get(reverse("platform-team-list")).status_code, 200)

    def test_duplicate_email_is_refused(self):
        Company.objects.create(name="Tenant")
        User.objects.create_user("taken@vezano.test", "secure-password")
        response = self.client.post(
            reverse("platform-team-list"),
            {"email": "Taken@vezano.test", "full_name": "Dup"}, format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_expired_link_can_be_reissued_and_old_one_dies(self):
        data = self._invite()
        member = User.objects.get(email="ops@vezano.test")
        PlatformInvitation.objects.filter(user=member).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        reissued = self.client.post(
            reverse("platform-team-reissue-invitation", args=[member.pk]), {}, format="json"
        )
        self.assertEqual(reissued.status_code, 201, reissued.data)
        self.assertNotEqual(reissued.data["invitation_token"], data["invitation_token"])
        self.client.force_authenticate(None)
        accept_url = reverse("platform-invitation-accept")
        old = self.client.post(
            accept_url,
            {"token": data["invitation_token"], "password": "a-sufficiently-secure-password"},
            format="json",
        )
        self.assertEqual(old.status_code, 400)
        new = self.client.post(
            accept_url,
            {
                "token": reissued.data["invitation_token"],
                "password": "a-sufficiently-secure-password",
            },
            format="json",
        )
        self.assertEqual(new.status_code, 200, new.data)

    def test_cannot_deactivate_self_or_last_active_admin(self):
        me = self.client.post(
            reverse("platform-team-deactivate", args=[self.admin.pk]), {}, format="json"
        )
        self.assertEqual(me.status_code, 400)
        self._invite()
        member = User.objects.get(email="ops@vezano.test")
        # Deactivate the newcomer: fine, root remains.
        off = self.client.post(
            reverse("platform-team-deactivate", args=[member.pk]), {}, format="json"
        )
        self.assertEqual(off.status_code, 200, off.data)
        self.assertFalse(off.data["is_active"])
        self.assertFalse(
            PlatformInvitation.objects.filter(user=member, revoked_at__isnull=True).exists()
        )
        # Now act as the newcomer after reactivation and try to remove root.
        on = self.client.post(
            reverse("platform-team-activate", args=[member.pk]), {}, format="json"
        )
        self.assertEqual(on.status_code, 200)
        self.client.force_authenticate(member)
        self.admin.refresh_from_db()
        root_off = self.client.post(
            reverse("platform-team-deactivate", args=[self.admin.pk]), {}, format="json"
        )
        self.assertEqual(root_off.status_code, 200, root_off.data)
        # And then the newcomer is the last one standing.
        self.client.force_authenticate(member)
        last = self.client.post(
            reverse("platform-team-deactivate", args=[member.pk]), {}, format="json"
        )
        self.assertEqual(last.status_code, 400)

    def test_tenant_owner_cannot_see_or_invite_platform_team(self):
        company = Company.objects.create(name="Tenant")
        owner_role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        owner = User.objects.create_user(
            "owner@tenant.test", "secure-password", company=company, role=owner_role
        )
        self.client.force_authenticate(owner)
        self.assertEqual(self.client.get(reverse("platform-team-list")).status_code, 403)
        response = self.client.post(
            reverse("platform-team-list"),
            {"email": "sneak@vezano.test", "full_name": "Sneak"}, format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(email="sneak@vezano.test").exists())
