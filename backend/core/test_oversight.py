"""
Two policy fixes found by auditing every real user's access.

1. The Website Manager landed on a completely blank dashboard — the one role
   with exactly one job had no section of its own.
2. The audit log was gated on `settings: write`, which shut out the General
   Manager: the person most responsible for day-to-day operations could not see
   what happened in them.
"""

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from core.rbac import AUDIT_VIEWER_ROLES, can_view_audit_log
from org.models import Company
from website.models import Section, Website


class WebsiteDashboardTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.role = Role.objects.create(
            name="Landing Page Manager", scope_level=Role.SCOPE_BRANCH
        )
        self.user = User.objects.create_user(
            email="web@alpha.test", password="passw0rd12345",
            company=self.company, role=self.role,
        )
        self.client.force_authenticate(self.user)

    def test_website_manager_dashboard_is_not_empty(self):
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertIn("website", resp.data["sections"])

    def test_unpublished_site_reports_draft(self):
        Website.objects.create(company=self.company, is_published=False)
        resp = self.client.get(reverse("dashboard"))
        self.assertFalse(resp.data["sections"]["website"]["is_published"])

    def test_published_site_and_section_count(self):
        site = Website.objects.create(company=self.company, is_published=True)
        Section.objects.create(company=self.company, website=site, type=Section.HERO)
        Section.objects.create(company=self.company, website=site, type=Section.ABOUT)
        resp = self.client.get(reverse("dashboard"))
        block = resp.data["sections"]["website"]
        self.assertTrue(block["is_published"])
        self.assertEqual(block["section_count"], 2)

    def test_missing_site_does_not_break_the_dashboard(self):
        """A company that never opened the website builder has no Website row."""
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["sections"]["website"]["is_published"])
        self.assertEqual(resp.data["sections"]["website"]["section_count"], 0)

    def test_section_counts_are_company_scoped(self):
        other = Company.objects.create(name="Beta")
        other_site = Website.objects.create(company=other)
        Section.objects.create(company=other, website=other_site, type=Section.HERO)
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.data["sections"]["website"]["section_count"], 0)

    def test_role_without_website_gets_no_website_section(self):
        hr_role = Role.objects.create(name="HR Officer", scope_level=Role.SCOPE_BRANCH)
        hr = User.objects.create_user(
            email="hr@alpha.test", password="passw0rd12345",
            company=self.company, role=hr_role,
        )
        self.client.force_authenticate(hr)
        resp = self.client.get(reverse("dashboard"))
        self.assertNotIn("website", resp.data["sections"])


class AuditViewerTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.client_ = self.client

    def _user(self, role_name, scope=Role.SCOPE_BUSINESS):
        role, _ = Role.objects.get_or_create(
            name=role_name, defaults={"scope_level": scope}
        )
        return User.objects.create_user(
            email=f"{role_name.replace(' ', '').lower()}@alpha.test",
            password="passw0rd12345", company=self.company, role=role,
        )

    def test_general_manager_can_read_the_audit_log(self):
        self.client.force_authenticate(self._user("General Manager"))
        resp = self.client.get(reverse("activitylog-list"))
        self.assertEqual(resp.status_code, 200, resp.data)

    def test_business_owner_still_can(self):
        self.client.force_authenticate(self._user("Business Owner"))
        self.assertEqual(
            self.client.get(reverse("activitylog-list")).status_code, 200
        )

    def test_officer_roles_are_still_denied(self):
        """Widening this to oversight roles must not leak the trail to the
        people it exists to observe."""
        for name in ("Sales Officer", "Purchasing Officer", "Inventory Officer",
                     "HR Officer", "Finance Department", "Viewer"):
            user = self._user(name, scope=Role.SCOPE_BRANCH)
            self.client.force_authenticate(user)
            resp = self.client.get(reverse("activitylog-list"))
            self.assertEqual(resp.status_code, 403, f"{name} got {resp.status_code}")

    def test_cfo_is_not_an_audit_viewer(self):
        """The CFO controls money, which is exactly why they are one of the
        subjects of the trail rather than its reader."""
        self.client.force_authenticate(self._user("Chief Financial Officer"))
        self.assertEqual(
            self.client.get(reverse("activitylog-list")).status_code, 403
        )

    def test_helper_agrees_with_the_endpoint(self):
        gm = self._user("General Manager")
        officer = self._user("Sales Officer", scope=Role.SCOPE_BRANCH)
        self.assertTrue(can_view_audit_log(gm))
        self.assertFalse(can_view_audit_log(officer))

    def test_roleless_user_is_denied(self):
        user = User.objects.create_user(
            email="norole@alpha.test", password="passw0rd12345",
            company=self.company,
        )
        self.client.force_authenticate(user)
        self.assertEqual(
            self.client.get(reverse("activitylog-list")).status_code, 403
        )

    def test_viewer_role_list_is_the_documented_three(self):
        self.assertEqual(
            AUDIT_VIEWER_ROLES,
            {"Super Administrator", "Business Owner", "General Manager"},
        )
