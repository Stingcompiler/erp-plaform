"""Security review 2 (2026-09-28): account takeover between peers,
branch-scoped departments, a 404 (not 500) for someone else's quotation,
the password-reset email off the request path, and the CSP header on the
exported app pages."""

from unittest import mock

from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import Role, User
from core.csp import _inline_script_hashes
from org.models import Branch, Company, Department

PW = "passw0rd123-Long"


class LadderBase(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.company = Company.objects.create(name="Alpha")
        self.main = Branch.objects.create(company=self.company, name="Main")
        self.north = Branch.objects.create(company=self.company, name="North")

    def user(self, email, role, branch=None):
        return User.objects.create_user(
            email=email, password=PW, company=self.company,
            role=Role.objects.get(name=role), branch=branch or self.main,
        )

    def client_as(self, user):
        client = APIClient(raise_request_exception=False)
        client.force_authenticate(user)
        return client


class PeerTakeoverTests(LadderBase):
    def setUp(self):
        super().setUp()
        self.owner = self.user("owner@a.test", "Business Owner")
        self.owner2 = self.user("owner2@a.test", "Business Owner")
        self.gm1 = self.user("gm1@a.test", "General Manager")
        self.gm2 = self.user("gm2@a.test", "General Manager")
        self.cfo = self.user("cfo@a.test", "Chief Financial Officer")

    def test_a_general_manager_cannot_take_over_another(self):
        client = self.client_as(self.gm1)
        for change in ({"password": "Taken-over-pass-99"}, {"email": "attacker@evil.test"},
                       {"is_active": False}, {"full_name": "x"}):
            response = client.patch(f"/api/users/{self.gm2.pk}/", change, format="json")
            self.assertEqual(response.status_code, 400, change)
        self.assertEqual(client.delete(f"/api/users/{self.gm2.pk}/").status_code, 400)
        self.gm2.refresh_from_db()
        self.assertTrue(self.gm2.check_password(PW))
        self.assertEqual(self.gm2.email, "gm2@a.test")
        self.assertTrue(self.gm2.is_active)

    def test_a_general_manager_still_administers_those_below(self):
        client = self.client_as(self.gm1)
        response = client.patch(
            f"/api/users/{self.cfo.pk}/", {"full_name": "Chief"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)

    def test_an_owner_administers_general_managers_and_other_owners(self):
        client = self.client_as(self.owner)
        response = client.patch(
            f"/api/users/{self.gm2.pk}/", {"password": "Owner-set-pass-99"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        response = client.patch(
            f"/api/users/{self.owner2.pk}/", {"full_name": "Co-owner"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)

    def test_a_branch_manager_cannot_touch_a_peer(self):
        bm1 = self.user("bm1@a.test", "Branch Manager")
        bm2 = self.user("bm2@a.test", "Branch Manager")
        response = self.client_as(bm1).patch(
            f"/api/users/{bm2.pk}/", {"full_name": "x"}, format="json"
        )
        self.assertEqual(response.status_code, 400)


class DepartmentBranchTests(LadderBase):
    def setUp(self):
        super().setUp()
        self.hr_main = self.user("hr@a.test", "HR Officer", self.main)
        self.owner = self.user("owner@a.test", "Business Owner")
        self.mine = Department.objects.create(company=self.company, branch=self.main, name="M")
        self.theirs = Department.objects.create(
            company=self.company, branch=self.north, name="N"
        )
        self.shared = Department.objects.create(company=self.company, name="Shared")

    def test_a_branch_hr_officer_sees_their_branch_and_shared_departments(self):
        response = self.client_as(self.hr_main).get("/api/departments/")
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual({row["name"] for row in rows}, {"M", "Shared"})

    def test_a_branch_hr_officer_changes_only_their_branch(self):
        client = self.client_as(self.hr_main)
        self.assertEqual(
            client.patch(f"/api/departments/{self.theirs.pk}/", {"name": "x"},
                         format="json").status_code, 404,
        )
        self.assertEqual(
            client.patch(f"/api/departments/{self.shared.pk}/", {"name": "x"},
                         format="json").status_code, 400,
        )
        self.assertEqual(
            client.patch(f"/api/departments/{self.mine.pk}/", {"branch": self.north.pk},
                         format="json").status_code, 400,
        )
        self.assertEqual(
            client.patch(f"/api/departments/{self.mine.pk}/", {"name": "Main dept"},
                         format="json").status_code, 200,
        )
        created = client.post("/api/departments/", {"name": "New"}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(Department.objects.get(name="New").branch_id, self.main.pk)

    def test_the_owner_sees_everything(self):
        response = self.client_as(self.owner).get("/api/departments/")
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(rows), 3)


class ForeignQuotationTests(LadderBase):
    def test_convert_to_order_on_a_missing_or_foreign_quotation_is_404(self):
        from sales.models import Customer, Quotation

        owner = self.user("owner@a.test", "Business Owner")
        other = Company.objects.create(name="Beta")
        customer = Customer.objects.create(company=other, name="C")
        foreign = Quotation.objects.create(company=other, customer=customer)
        client = self.client_as(owner)
        for pk in (foreign.pk, 999999):
            response = client.post(f"/api/quotations/{pk}/convert_to_order/", {}, format="json")
            self.assertEqual(response.status_code, 404, pk)


class PasswordResetTimingTests(TestCase):
    def test_the_email_is_sent_off_the_request_path(self):
        from accounts import password_reset

        ran = []
        with override_settings(PASSWORD_RESET_EMAIL_BACKGROUND=True), \
                mock.patch("accounts.password_reset.threading.Thread") as thread:
            password_reset._in_background(lambda: ran.append(1))
        thread.assert_called_once()
        thread.return_value.start.assert_called_once()
        self.assertEqual(ran, [])
        with override_settings(PASSWORD_RESET_EMAIL_BACKGROUND=False):
            password_reset._in_background(lambda: ran.append(1))
        self.assertEqual(ran, [1])


class ContentSecurityPolicyTests(TestCase):
    def test_inline_scripts_are_hashed_and_data_blocks_skipped(self):
        body = (
            b'<script>a()</script><script src="/x.js"></script>'
            b'<script type="application/ld+json">{"a":1}</script>'
            b'<script type="module">b()</script>'
        )
        hashes = _inline_script_hashes(body)
        self.assertEqual(len(hashes), 2)
        self.assertTrue(all(h.startswith("'sha256-") for h in hashes))

    def test_exported_app_pages_carry_the_policy(self):
        from core.frontend import FRONTEND_DIST, serve_frontend

        if not (FRONTEND_DIST / "index.html").is_file():
            self.skipTest("frontend/out is not built")
        from core.csp import ContentSecurityPolicyMiddleware

        middleware = ContentSecurityPolicyMiddleware(
            lambda request: serve_frontend(request, "")
        )
        response = middleware(RequestFactory().get("/"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("script-src 'self' 'unsafe-inline'", response["Content-Security-Policy"])
        strict = response["Content-Security-Policy-Report-Only"]
        script_src = strict.split("script-src ", 1)[1].split(";", 1)[0]
        self.assertIn("'sha256-", script_src)
        self.assertNotIn("unsafe-inline", script_src)
