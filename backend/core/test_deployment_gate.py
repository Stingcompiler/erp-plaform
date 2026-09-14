from django.test import TestCase, override_settings

from accounts.models import Role, User
from org.models import Company


class StandaloneSurfaceGateTests(TestCase):
    """On a customer's server the SaaS surface does not exist."""

    SAAS_ONLY = [
        "/api/platform/overview/",
        "/api/platform/team/",
        "/api/platform/registration-requests/",
        "/api/platform/subscriptions/",
        "/api/public/plans/",
        "/api/public/registration-requests/",
        "/api/public/demo-requests/",
        "/api/public/owner-invitations/accept/",
        "/api/public/platform-invitations/accept/",
    ]

    def setUp(self):
        self.root = User.objects.create_superuser("root@x.test", "secure-password")
        company = Company.objects.create(name="C")
        owner = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.owner = User.objects.create_user(
            "o@c.test", "passw0rd123", company=company, role=owner
        )

    @override_settings(VEZANO_DEPLOYMENT_MODE="standalone")
    def test_saas_routes_are_404_even_for_a_superuser(self):
        self.client.force_login(self.root)
        for path in self.SAAS_ONLY:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)
                self.assertEqual(
                    self.client.post(path, {}, content_type="application/json").status_code, 404
                )

    @override_settings(VEZANO_DEPLOYMENT_MODE="standalone")
    def test_customer_routes_keep_working(self):
        self.client.force_login(self.owner)
        for path in ("/api/health/", "/api/license/", "/api/products/", "/api/public/site/nope/"):
            with self.subTest(path=path):
                self.assertNotEqual(self.client.get(path).status_code, 500)
                self.assertIn(
                    self.client.get(path).status_code,
                    (200, 401, 403, 404 if "site" in path else 200),
                )

    @override_settings(VEZANO_DEPLOYMENT_MODE="saas")
    def test_saas_mode_is_untouched(self):
        self.assertEqual(self.client.get("/api/public/plans/").status_code, 200)

    @override_settings(VEZANO_DEPLOYMENT_MODE="standalone")
    def test_health_reports_installation_and_licence_state(self):
        from licensing.models import Installation

        installation = Installation.objects.create(organisation_name="C")
        data = self.client.get("/api/health/").json()
        self.assertEqual(data["deployment_mode"], "standalone")
        self.assertEqual(data["installation_id"], str(installation.installation_id))
        self.assertEqual(data["licence"]["state"], "unlicensed")
        self.assertFalse(data["licence"]["allow_writes"])
        self.assertIn("version", data)
