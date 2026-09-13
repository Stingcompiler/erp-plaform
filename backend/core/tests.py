from io import StringIO

from django.core.management import call_command
from django.urls import resolve, reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from org.models import Company


class PlatformAdminCreateGuardTests(APITestCase):
    """Platform operators use dedicated APIs and cannot mutate tenant data."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="root@platform.test", password="passw0rd12345"
        )
        self.client.force_authenticate(self.admin)

    def test_company_less_platform_admin_is_denied_tenant_create(self):
        resp = self.client.post(
            reverse("supplier-list"),
            {"name": "Acme", "phone": "", "email": "", "address": ""},
            format="json",
        )
        self.assertEqual(resp.status_code, 403, resp.data)

    def test_company_user_can_create(self):
        company = Company.objects.create(name="Alpha")
        role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd12345",
            company=company, role=role,
        )
        self.client.force_authenticate(owner)
        resp = self.client.post(
            reverse("supplier-list"),
            {"name": "Acme", "phone": "", "email": "", "address": ""},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["company"], company.id)


class HealthCheckTests(APITestCase):
    def test_health_check_returns_200(self):
        response = self.client.get(reverse("health-check"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "ok")

    def test_health_check_is_unauthenticated(self):
        # Must be reachable with no credentials at all — it's what Render
        # and CI hit to confirm the service is alive.
        response = self.client.get(reverse("health-check"))
        self.assertNotEqual(response.status_code, 401)
        self.assertNotEqual(response.status_code, 403)

    def test_health_check_skips_jwt_authentication(self):
        view = resolve(reverse("health-check")).func.cls
        self.assertEqual(view.authentication_classes, [])


class BackupCronCommandTests(APITestCase):
    def test_run_scheduled_backup_command_executes_without_error(self):
        # The erp-backup-cron command is fully implemented (M10): it reports a
        # completion summary. With no companies it processes zero and still
        # exits cleanly.
        out = StringIO()
        call_command("run_scheduled_backup", stdout=out)
        self.assertIn("Scheduled backup complete", out.getvalue())


class AuditLogAccessTests(APITestCase):
    """The audit trail must be readable only by administrators, and a company
    admin must never see another company's activity."""

    def setUp(self):
        from core.models import ActivityLog
        self.alpha = Company.objects.create(name="Alpha")
        self.beta = Company.objects.create(name="Beta")
        self.owner_role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        self.hr_role = Role.objects.create(
            name="HR Officer", scope_level=Role.SCOPE_BRANCH
        )
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd12345",
            full_name="Amal Yousif", company=self.alpha, role=self.owner_role,
        )
        self.hr = User.objects.create_user(
            email="hr@alpha.test", password="passw0rd12345",
            company=self.alpha, role=self.hr_role,
        )
        ActivityLog.objects.create(company=self.alpha, user=self.owner, action="create",
                                   entity_type="Product", entity_id="1")
        ActivityLog.objects.create(company=self.beta, action="delete",
                                   entity_type="Product", entity_id="99")

    def test_admin_can_read_audit_log(self):
        self.client.force_authenticate(self.owner)
        resp = self.client.get(reverse("activitylog-list"))
        self.assertEqual(resp.status_code, 200, resp.data)

    def test_non_admin_is_denied(self):
        self.client.force_authenticate(self.hr)
        resp = self.client.get(reverse("activitylog-list"))
        self.assertEqual(resp.status_code, 403, resp.data)

    def test_company_admin_cannot_see_other_company_activity(self):
        self.client.force_authenticate(self.owner)
        resp = self.client.get(reverse("activitylog-list"))
        entity_ids = [r["entity_id"] for r in resp.data["results"]]
        self.assertIn("1", entity_ids)
        self.assertNotIn("99", entity_ids)

    def test_action_filter(self):
        self.client.force_authenticate(self.owner)
        resp = self.client.get(reverse("activitylog-list"), {"action": "create"})
        self.assertTrue(all(r["action"] == "create" for r in resp.data["results"]))

    def test_log_row_carries_actor_name_and_role(self):
        """The audit trail must show who acted and with what authority, not just
        an email address."""
        self.client.force_authenticate(self.owner)
        resp = self.client.get(reverse("activitylog-list"))
        row = next(r for r in resp.data["results"] if r["entity_id"] == "1")
        self.assertEqual(row["user_name"], "Amal Yousif")
        self.assertEqual(row["user_role"], "Business Owner")
        self.assertEqual(row["user_email"], "owner@alpha.test")

    def test_search_matches_actor_full_name(self):
        self.client.force_authenticate(self.owner)
        resp = self.client.get(reverse("activitylog-list"), {"search": "Amal"})
        entity_ids = [r["entity_id"] for r in resp.data["results"]]
        self.assertIn("1", entity_ids)

    def test_system_action_has_no_actor(self):
        """A row with no user (a scheduled task, the Beta delete) must serialise
        cleanly rather than erroring on the role join."""
        self.client.force_authenticate(self.owner)
        # The Beta delete has no user; confirm nulls come back, not a 500.
        from core.models import ActivityLog
        ActivityLog.objects.create(
            company=self.alpha, action="reminder_scan", entity_type="Invoice"
        )
        resp = self.client.get(reverse("activitylog-list"))
        self.assertEqual(resp.status_code, 200, resp.data)
        row = next(r for r in resp.data["results"] if r["action"] == "reminder_scan")
        self.assertIsNone(row["user_name"])
        self.assertIsNone(row["user_role"])
