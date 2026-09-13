from django.conf import settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role, User
from core.models import ActivityLog
from org.models import Branch, Company

ACCESS_COOKIE = settings.SIMPLE_JWT["AUTH_COOKIE"]
REFRESH_COOKIE = settings.SIMPLE_JWT["AUTH_COOKIE_REFRESH"]


class BaseTenantSetup(APITestCase):
    def setUp(self):
        self.company_a = Company.objects.create(name="Alpha Trading")
        self.company_b = Company.objects.create(name="Beta Supplies")

        self.branch_a = Branch.objects.create(company=self.company_a, name="A-Main")
        self.branch_b = Branch.objects.create(company=self.company_b, name="B-Main")

        self.owner_role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )

        self.user_a = User.objects.create_user(
            email="a@alpha.test", password="passw0rd123", company=self.company_a,
            role=self.owner_role,
        )
        self.user_b = User.objects.create_user(
            email="b@beta.test", password="passw0rd123", company=self.company_b,
            role=self.owner_role,
        )

    def login(self, email, password="passw0rd123"):
        url = reverse("auth-login")
        resp = self.client.post(url, {"email": email, "password": password})
        assert resp.status_code == 200, resp.content
        # APIClient stores Set-Cookie responses, so subsequent requests are
        # authenticated via the HttpOnly cookie automatically.
        return resp


class CookieAuthTests(BaseTenantSetup):
    def test_login_sets_httponly_access_cookie(self):
        resp = self.login("a@alpha.test")
        self.assertIn(ACCESS_COOKIE, resp.cookies)
        self.assertTrue(resp.cookies[ACCESS_COOKIE]["httponly"])
        self.assertIn(REFRESH_COOKIE, resp.cookies)

    def test_me_requires_auth(self):
        resp = self.client.get(reverse("auth-me"))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_current_user_after_login(self):
        self.login("a@alpha.test")
        resp = self.client.get(reverse("auth-me"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["email"], "a@alpha.test")
        self.assertEqual(resp.data["company"], self.company_a.id)

    def test_bad_credentials_rejected(self):
        resp = self.client.post(
            reverse("auth-login"), {"email": "a@alpha.test", "password": "wrong"}
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class ActivityLogTests(BaseTenantSetup):
    def test_login_and_logout_are_audited(self):
        self.login("a@alpha.test")
        login_rows = ActivityLog.objects.filter(action="login", user=self.user_a)
        self.assertEqual(login_rows.count(), 1)
        row = login_rows.first()
        self.assertEqual(row.company, self.company_a)
        self.assertIsNotNone(row.created_at)

        self.client.post(reverse("auth-logout"))
        self.assertEqual(
            ActivityLog.objects.filter(action="logout", user=self.user_a).count(), 1
        )

    def test_crud_writes_activity_log(self):
        self.login("a@alpha.test")
        self.client.post(reverse("branch-list"), {"name": "A-Second"})
        self.assertTrue(
            ActivityLog.objects.filter(
                action="create", entity_type="Branch", company=self.company_a
            ).exists()
        )


class CrossCompanyIsolationTests(BaseTenantSetup):
    """The core Rule #1 acceptance proof."""

    def test_branch_list_only_returns_own_company(self):
        self.login("a@alpha.test")
        resp = self.client.get(reverse("branch-list"))
        self.assertEqual(resp.status_code, 200)
        names = {b["name"] for b in resp.data["results"]}
        self.assertIn("A-Main", names)
        self.assertNotIn("B-Main", names)

    def test_cannot_retrieve_other_company_branch_by_id(self):
        # User A guesses Company B's branch ID directly -> must 404, not leak.
        self.login("a@alpha.test")
        url = reverse("branch-detail", args=[self.branch_b.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_update_other_company_branch_by_id(self):
        self.login("a@alpha.test")
        url = reverse("branch-detail", args=[self.branch_b.id])
        resp = self.client.patch(url, {"name": "hijacked"})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.branch_b.refresh_from_db()
        self.assertEqual(self.branch_b.name, "B-Main")

    def test_cannot_delete_other_company_branch_by_id(self):
        self.login("a@alpha.test")
        url = reverse("branch-detail", args=[self.branch_b.id])
        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Branch.objects.filter(pk=self.branch_b.id).exists())

    def test_create_branch_is_forced_into_own_company(self):
        # Even if the payload names Company B, the branch must land in A.
        self.login("a@alpha.test")
        resp = self.client.post(
            reverse("branch-list"), {"name": "A-New", "company": self.company_b.id}
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        created = Branch.objects.get(name="A-New")
        self.assertEqual(created.company, self.company_a)

    def test_company_detail_of_other_company_is_404(self):
        self.login("a@alpha.test")
        url = reverse("company-detail", args=[self.company_b.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_list_is_company_scoped(self):
        self.login("a@alpha.test")
        resp = self.client.get(reverse("user-list"))
        self.assertEqual(resp.status_code, 200)
        emails = {u["email"] for u in resp.data["results"]}
        self.assertIn("a@alpha.test", emails)
        self.assertNotIn("b@beta.test", emails)


class TaxProfileAutoCreateTests(APITestCase):
    def test_company_gets_default_tax_profile(self):
        # Rule #7: every company has a TaxProfile from M1 onward.
        company = Company.objects.create(name="Gamma Co")
        self.assertTrue(hasattr(company, "tax_profile"))
        self.assertEqual(company.tax_profile.invoice_format, "simple")


class OwnerAppointmentTests(BaseTenantSetup):
    """The "add another owner" action in the users page: only an existing
    owner may appoint one, and the company can never lose its last owner."""

    def setUp(self):
        super().setUp()
        self.gm_role = Role.objects.create(
            name="General Manager", scope_level=Role.SCOPE_BUSINESS
        )
        self.gm_a = User.objects.create_user(
            email="gm@alpha.test", password="passw0rd123", company=self.company_a,
            role=self.gm_role,
        )

    def _new_owner_payload(self):
        return {
            "email": "owner2@alpha.test", "full_name": "Second Owner",
            "role": self.owner_role.id, "is_active": True, "password": "Sup3r-secret-pw",
        }

    def test_owner_can_appoint_another_owner(self):
        self.login("a@alpha.test")
        resp = self.client.post(reverse("user-list"), self._new_owner_payload())
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        created = User.objects.get(email="owner2@alpha.test")
        self.assertEqual(created.company, self.company_a)
        self.assertEqual(created.role, self.owner_role)

    def test_general_manager_cannot_appoint_owner(self):
        self.login("gm@alpha.test")
        resp = self.client.post(reverse("user-list"), self._new_owner_payload())
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertFalse(User.objects.filter(email="owner2@alpha.test").exists())

    def test_general_manager_sees_assign_owner_flag_off(self):
        self.login("gm@alpha.test")
        self.assertFalse(self.client.get(reverse("auth-me")).data["capabilities"]["users.assign_owner"])
        self.login("a@alpha.test")
        self.assertTrue(self.client.get(reverse("auth-me")).data["capabilities"]["users.assign_owner"])

    def test_last_active_owner_cannot_be_demoted(self):
        self.login("a@alpha.test")
        self.client.post(reverse("user-list"), self._new_owner_payload())
        second = User.objects.get(email="owner2@alpha.test")
        # Two owners: demoting one is fine.
        resp = self.client.patch(
            reverse("user-detail", args=[second.id]), {"role": self.gm_role.id}
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        # Back to a single owner: the survivor cannot be demoted by anyone.
        self.login("owner2@alpha.test", "Sup3r-secret-pw")
        resp = self.client.patch(
            reverse("user-detail", args=[self.user_a.id]), {"is_active": False}
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.user_a.refresh_from_db()
        self.assertTrue(self.user_a.is_active)
