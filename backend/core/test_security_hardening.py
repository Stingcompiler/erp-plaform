"""Regression tests for the September 2026 security hardening batch.

Each test pins one closed hole: credential material in the audit trail, a
cross-tenant restore, authority escalation inside a company, refresh tokens
that never rotated, a forwarded-header throttle bypass, unvalidated medical
uploads, the admin surface, and the export archive carrying password hashes.
"""
from decimal import Decimal
from io import BytesIO
from unittest import mock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import Role, User
from core.activity import get_client_ip
from core.models import ActivityLog
from inventory.models import Product, Warehouse
from ops.models import BackupRecord
from org.models import Branch, Company


def _roles():
    owner = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
    gm = Role.objects.create(name="General Manager", scope_level=Role.SCOPE_BUSINESS)
    bm = Role.objects.create(name="Branch Manager", scope_level=Role.SCOPE_BRANCH)
    sales = Role.objects.create(name="Sales Officer", scope_level=Role.SCOPE_BRANCH)
    hr = Role.objects.create(name="HR Officer", scope_level=Role.SCOPE_BUSINESS)
    return owner, gm, bm, sales, hr


class AuditTrailRedactionTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.company = Company.objects.create(name="Alpha")
        self.owner_role, _, _, self.sales_role, _ = _roles()
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=self.owner_role,
        )
        self.staff = User.objects.create_user(
            email="staff@alpha.test", password="passw0rd123",
            company=self.company, role=self.sales_role, branch=self.branch,
        )

    def test_admin_password_reset_leaves_no_credential_in_the_log(self):
        self.client.force_authenticate(self.owner)
        response = self.client.patch(
            reverse("user-detail", args=[self.staff.pk]),
            {"password": "Fresh-Passw0rd!2026", "full_name": "Renamed"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        row = ActivityLog.objects.filter(entity_type="User", action="update").latest("id")
        serialized = str(row.metadata)
        self.assertNotIn("password", serialized)
        self.assertNotIn("pbkdf2", serialized)
        self.assertNotIn("Fresh-Passw0rd", serialized)
        self.assertEqual(row.metadata["changes"]["full_name"]["after"], "Renamed")

    def test_password_change_ends_existing_sessions(self):
        old_refresh = RefreshToken.for_user(self.staff)
        self.client.force_authenticate(self.owner)
        self.client.patch(
            reverse("user-detail", args=[self.staff.pk]),
            {"password": "Fresh-Passw0rd!2026"},
            format="json",
        )
        self.client.force_authenticate(None)
        self.client.cookies["refresh_token"] = str(old_refresh)
        response = self.client.post(reverse("auth-refresh"))
        self.assertEqual(response.status_code, 401)


class RestoreScopeTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.other = Company.objects.create(name="Beta")
        owner_role, *_ = _roles()
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=owner_role,
        )
        BackupRecord.objects.create(
            company=self.other, kind=BackupRecord.SCHEDULED,
            status=BackupRecord.SUCCESS, storage_key="backups/2/x-scheduled.json",
        )
        self.client.force_authenticate(self.owner)

    def test_another_companys_storage_key_is_not_found(self):
        with mock.patch("ops.storage.download_backup") as download:
            response = self.client.post(
                reverse("ops-restore"),
                {"storage_key": "backups/2/x-scheduled.json"},
                format="json",
            )
        self.assertEqual(response.status_code, 404)
        download.assert_not_called()


class AuthorityLadderTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.owner_role, self.gm_role, self.bm_role, self.sales_role, _ = _roles()
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=self.owner_role,
        )
        self.gm = User.objects.create_user(
            email="gm@alpha.test", password="passw0rd123",
            company=self.company, role=self.gm_role, branch=self.branch,
        )
        self.bm = User.objects.create_user(
            email="bm@alpha.test", password="passw0rd123",
            company=self.company, role=self.bm_role, branch=self.branch,
        )
        self.peer_bm = User.objects.create_user(
            email="bm2@alpha.test", password="passw0rd123",
            company=self.company, role=self.bm_role, branch=self.branch,
        )
        self.cashier = User.objects.create_user(
            email="cashier@alpha.test", password="passw0rd123",
            company=self.company, role=self.sales_role, branch=self.branch,
        )

    def _patch(self, actor, target, body):
        self.client.force_authenticate(actor)
        return self.client.patch(reverse("user-detail", args=[target.pk]), body, format="json")

    def test_branch_manager_cannot_demote_or_reset_a_general_manager(self):
        response = self._patch(
            self.bm, self.gm,
            {"role": self.sales_role.pk, "branch": self.branch.pk, "password": "Taken-0ver!2026"},
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.gm.refresh_from_db()
        self.assertEqual(self.gm.role, self.gm_role)
        self.assertTrue(self.gm.check_password("passw0rd123"))

    def test_branch_manager_cannot_touch_a_peer_branch_manager(self):
        response = self._patch(self.bm, self.peer_bm, {"full_name": "X"})
        self.assertEqual(response.status_code, 400)

    def test_branch_manager_still_manages_own_branch_staff(self):
        response = self._patch(self.bm, self.cashier, {"full_name": "Renamed"})
        self.assertEqual(response.status_code, 200, response.data)

    def test_general_manager_cannot_promote_anyone_to_owner(self):
        response = self._patch(self.gm, self.cashier, {"role": self.owner_role.pk})
        self.assertEqual(response.status_code, 400)

    def test_general_manager_cannot_modify_the_owner(self):
        response = self._patch(self.gm, self.owner, {"full_name": "X"})
        self.assertEqual(response.status_code, 400)

    def test_owner_manages_everyone(self):
        response = self._patch(self.owner, self.gm, {"full_name": "Renamed GM"})
        self.assertEqual(response.status_code, 200, response.data)


class RefreshRotationTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.company = Company.objects.create(name="Alpha")
        owner_role, *_ = _roles()
        self.user = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=owner_role,
        )

    def test_refresh_rotates_and_blacklists_the_presented_token(self):
        login = self.client.post(
            reverse("auth-login"), {"email": "owner@alpha.test", "password": "passw0rd123"}
        )
        self.assertEqual(login.status_code, 200, login.content)
        first = self.client.cookies["refresh_token"].value
        refreshed = self.client.post(reverse("auth-refresh"))
        self.assertEqual(refreshed.status_code, 200)
        second = self.client.cookies["refresh_token"].value
        self.assertNotEqual(first, second)
        # Replaying the token that was just rotated must fail.
        self.client.cookies["refresh_token"] = first
        replay = self.client.post(reverse("auth-refresh"))
        self.assertEqual(replay.status_code, 401)
        # The rotated one keeps working.
        self.client.cookies["refresh_token"] = second
        self.assertEqual(self.client.post(reverse("auth-refresh")).status_code, 200)

    def test_inactive_user_cannot_refresh(self):
        token = RefreshToken.for_user(self.user)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.client.cookies["refresh_token"] = str(token)
        self.assertEqual(self.client.post(reverse("auth-refresh")).status_code, 401)


@override_settings(LOGIN_LOCKOUT_ATTEMPTS=3)
class LoginLockoutTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.company = Company.objects.create(name="Alpha")
        owner_role, *_ = _roles()
        User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=owner_role,
        )

    def _login(self, password, forwarded=None):
        extra = {"HTTP_X_FORWARDED_FOR": forwarded} if forwarded else {}
        return self.client.post(
            reverse("auth-login"),
            {"email": "owner@alpha.test", "password": password},
            **extra,
        )

    def test_account_locks_after_repeated_failures_regardless_of_ip(self):
        for i in range(3):
            response = self._login("wrong", forwarded=f"10.0.0.{i}, 203.0.113.9")
            self.assertEqual(response.status_code, 400)
        locked = self._login("passw0rd123", forwarded="10.0.0.99, 203.0.113.9")
        self.assertEqual(locked.status_code, 429)
        self.assertEqual(locked.data["code"], "account_locked")
        self.assertTrue(
            ActivityLog.objects.filter(
                action="login_blocked", metadata__reason="account_locked"
            ).exists()
        )

    def test_successful_login_clears_the_counter(self):
        self._login("wrong")
        self._login("wrong")
        self.assertEqual(self._login("passw0rd123").status_code, 200)
        self._login("wrong")
        self._login("wrong")
        self.assertEqual(self._login("passw0rd123").status_code, 200)


class ForwardedHeaderTests(APITestCase):
    def test_client_ip_is_the_hop_our_proxy_appended(self):
        request = RequestFactory().get(
            "/", HTTP_X_FORWARDED_FOR="1.2.3.4, 198.51.100.7", REMOTE_ADDR="10.0.0.1"
        )
        self.assertEqual(get_client_ip(request), "198.51.100.7")

    def test_falls_back_to_remote_addr(self):
        request = RequestFactory().get("/", REMOTE_ADDR="10.0.0.1")
        self.assertEqual(get_client_ip(request), "10.0.0.1")


class MedicalReportUploadTests(APITestCase):
    def setUp(self):
        from hr.models import Employee

        self.company = Company.objects.create(name="Alpha")
        _, _, _, _, hr_role = _roles()
        self.hr = User.objects.create_user(
            email="hr@alpha.test", password="passw0rd123",
            company=self.company, role=hr_role,
        )
        self.employee = Employee.objects.create(
            company=self.company, full_name="Worker", hire_date="2026-01-01",
        )
        self.client.force_authenticate(self.hr)

    def _upload(self, name, content_type, body=b"data"):
        return self.client.post(
            reverse("leaverequest-list"),
            {
                "employee": self.employee.pk,
                "start_date": "2026-10-01",
                "end_date": "2026-10-02",
                "leave_type": "sick",
                "medical_report": SimpleUploadedFile(name, body, content_type=content_type),
            },
            format="multipart",
        )

    def test_html_upload_is_refused(self):
        response = self._upload("report.html", "text/html", b"<script>alert(1)</script>")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("medical_report", response.data)

    def test_oversized_upload_is_refused(self):
        big = BytesIO(b"0" * (10 * 1024 * 1024 + 1)).getvalue()
        response = self._upload("report.pdf", "application/pdf", big)
        self.assertEqual(response.status_code, 400, response.data)

    def test_pdf_upload_is_served_as_a_typed_attachment(self):
        response = self._upload("report.pdf", "application/pdf", b"%PDF-1.4")
        self.assertEqual(response.status_code, 201, response.data)
        download = self.client.get(
            reverse("leaverequest-report", args=[response.data["id"]])
        )
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download["Content-Type"], "application/pdf")
        self.assertIn("attachment", download["Content-Disposition"])


class AdminGateTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.staff = User.objects.create_user(
            email="staff@alpha.test", password="passw0rd123",
            company=self.company, is_staff=True,
        )
        self.root = User.objects.create_superuser(
            email="root@platform.test", password="passw0rd123"
        )

    def test_staff_without_superuser_gets_404(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get("/admin/").status_code, 404)

    def test_superuser_reaches_the_admin(self):
        self.client.force_login(self.root)
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    @override_settings(ADMIN_ALLOWED_IPS=["203.0.113.9"])
    def test_ip_allow_list_hides_the_admin_from_other_addresses(self):
        self.client.force_login(self.root)
        self.assertEqual(self.client.get("/admin/", REMOTE_ADDR="10.0.0.1").status_code, 404)
        self.assertEqual(self.client.get("/admin/", REMOTE_ADDR="203.0.113.9").status_code, 200)


class TransferExportTests(APITestCase):
    def test_export_archive_carries_no_password_hashes(self):
        from ops.transfer import export_company

        company = Company.objects.create(name="Alpha")
        owner_role, *_ = _roles()
        User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=company, role=owner_role,
        )
        Warehouse.objects.create(company=company, name="Main")
        Product.objects.create(company=company, sku="S", name="P", cost_price=Decimal("1"))
        payload, _ = export_company(company, include_media=False)
        rows = payload["objects"]["accounts.User"]
        self.assertEqual(len(rows), 1)
        self.assertNotIn("password", rows[0])
        self.assertNotIn("last_login", rows[0])
        self.assertNotIn("pbkdf2", str(payload))


class PlatformOwnerGateTests(APITestCase):
    def test_platform_admin_is_not_a_company_owner(self):
        root = User.objects.create_superuser(email="root@platform.test", password="passw0rd123")
        self.client.force_authenticate(root)
        response = self.client.get(reverse("company-subscription"))
        self.assertIn(response.status_code, (403, 404))
