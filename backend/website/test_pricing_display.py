"""How /pricing lays out the plans (website.SeoSettings.pricing_*): the
platform API that sets it, who may, what every visitor reads, and the
billing cycles the public plan list really offers."""
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role, User
from core.models import ActivityLog
from org.models import Company
from subscriptions.models import Plan, PlanVersion
from website.models import SeoSettings
from website.test_seo_admin import SeoAdminBase

DEFAULTS = {
    "template": "classic", "show_compare": True, "show_self_hosted": True,
    "default_cycle": "monthly",
}


class PricingDisplayApiTests(SeoAdminBase):
    def test_public_defaults_without_a_saved_row(self):
        response = APIClient().get(reverse("public-plan-display"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), DEFAULTS)
        self.assertIn("max-age=60", response["Cache-Control"])
        # A visitor's read never creates the settings row.
        self.assertEqual(SeoSettings.objects.count(), 0)

    def test_patch_validates_choices_and_reaches_visitors(self):
        url = reverse("platform-pricing-display")
        self.assertEqual(self.client.get(url).data["template"], "classic")
        # Warm the public cache so the save has to clear it.
        APIClient().get(reverse("public-plan-display"))
        for body in ({"template": "carousel"}, {"default_cycle": "weekly"},
                     {"template": ""}, {"show_compare": "maybe"}):
            with self.subTest(body=body):
                bad = self.client.patch(url, body, format="json")
                self.assertEqual(bad.status_code, 400, bad.data)
        good = self.client.patch(
            url,
            {"template": "featured", "show_compare": False, "default_cycle": "yearly"},
            format="json",
        )
        self.assertEqual(good.status_code, 200, good.data)
        self.assertEqual(good.data["template"], "featured")
        public = APIClient().get(reverse("public-plan-display")).json()
        self.assertEqual(public, {
            "template": "featured", "show_compare": False, "show_self_hosted": True,
            "default_cycle": "yearly",
        })
        row = ActivityLog.objects.get(entity_type="PricingDisplay")
        self.assertEqual(row.user, self.root)
        self.assertEqual(row.metadata["fields"], [
            "pricing_default_cycle", "pricing_show_compare", "pricing_template",
        ])
        self.assertEqual(row.metadata["template"], "featured")

    def test_every_template_is_accepted(self):
        url = reverse("platform-pricing-display")
        for template in ("classic", "featured", "table", "compact"):
            with self.subTest(template=template):
                response = self.client.patch(url, {"template": template}, format="json")
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(SeoSettings.load().pricing_template, template)

    def test_seo_settings_endpoint_cannot_change_the_layout(self):
        response = self.client.patch(
            reverse("platform-seo-settings"),
            {"pricing_template": "table", "robots_extra": "Disallow: /x/"}, format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SeoSettings.load().pricing_template, "classic")

    def test_plans_capabilities_gate_the_platform_endpoint(self):
        url = reverse("platform-pricing-display")
        # Marketing Manager reads the price list (plans.view) but cannot change it.
        marketing = self._invite("Marketing Manager")
        # Support Agent has no price list at all.
        support = self._invite("Support Agent")
        client = APIClient()
        client.force_authenticate(marketing)
        self.assertEqual(client.get(url).status_code, 200)
        self.assertEqual(client.patch(url, {"template": "table"}, format="json").status_code, 403)
        client.force_authenticate(support)
        self.assertEqual(client.get(url).status_code, 403)
        self.assertEqual(client.patch(url, {"template": "table"}, format="json").status_code, 403)
        company = Company.objects.create(name="Tenant")
        role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        tenant = User.objects.create_user(
            "owner@tenant.test", "passw0rd123", company=company, role=role
        )
        client.force_authenticate(tenant)
        self.assertEqual(client.get(url).status_code, 403)
        self.assertEqual(client.patch(url, {"template": "table"}, format="json").status_code, 403)
        anonymous = APIClient()
        self.assertIn(anonymous.get(url).status_code, (401, 403))
        self.assertEqual(SeoSettings.load().pricing_template, "classic")

    def test_deleting_the_settings_row_resets_the_layout(self):
        self.client.patch(
            reverse("platform-pricing-display"), {"template": "compact"}, format="json"
        )
        SeoSettings.load().delete()
        self.assertEqual(SeoSettings.load().pricing_template, "classic")


class PublicPlanCyclesTests(SeoAdminBase):
    def _version(self, plan, number, cycle, price, **extra):
        return PlanVersion.objects.create(
            plan=plan, version=number, currency="SDG", price=price, billing_cycle=cycle,
            modules=["sales"], limits={"users": 3}, published_at=timezone.now(), **extra,
        )

    def _rows(self):
        response = APIClient().get(reverse("public-plan-list"))
        self.assertEqual(response.status_code, 200)
        return {row["plan_code"]: row for row in response.json()}

    def test_cycles_list_the_newest_published_version_per_cycle(self):
        both = Plan.objects.create(code="both", name="Both")
        monthly = self._version(both, 1, "monthly", "1000")
        old_yearly = self._version(both, 2, "yearly", "9000")
        yearly = self._version(both, 3, "yearly", "10000")
        # Unpublished and legacy versions are not offers.
        PlanVersion.objects.create(
            plan=both, version=4, currency="SDG", price="1", billing_cycle="monthly",
        )
        only = Plan.objects.create(code="only", name="Only")
        only_monthly = self._version(only, 1, "monthly", "500")
        self._version(only, 2, "yearly", "4000", is_legacy=True)
        only_monthly_newer = self._version(only, 3, "monthly", "600")

        rows = self._rows()
        row = rows["both"]
        # The row itself is still the plan's newest published version.
        self.assertEqual(row["id"], yearly.id)
        self.assertEqual(sorted(row["cycles"]), ["monthly", "yearly"])
        self.assertEqual(row["cycles"]["monthly"]["id"], monthly.id)
        self.assertEqual(row["cycles"]["monthly"]["price"], "1000.00")
        self.assertEqual(row["cycles"]["yearly"]["id"], yearly.id)
        self.assertNotEqual(row["cycles"]["yearly"]["id"], old_yearly.id)
        self.assertEqual(row["cycles"]["monthly"]["limits"], {"users": 3})
        self.assertEqual(sorted(rows["only"]["cycles"]), ["monthly"])
        self.assertEqual(rows["only"]["cycles"]["monthly"]["id"], only_monthly_newer.id)
        self.assertNotEqual(rows["only"]["cycles"]["monthly"]["id"], only_monthly.id)

    @override_settings(
        EMAIL_ENABLED=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
    )
    def test_a_yearly_offer_can_be_requested(self):
        plan = Plan.objects.create(code="p", name="P")
        self._version(plan, 1, "monthly", "1000")
        yearly = self._version(plan, 2, "yearly", "10000")
        monthly_id = self._rows()["p"]["cycles"]["monthly"]["id"]
        for version_id in (monthly_id, yearly.id):
            response = APIClient().post(reverse("registration-request"), {
                "company_name": "Shop", "contact_name": "Ali", "email": f"a{version_id}@x.test",
                "phone": "+249912345678", "delivery_mode": "saas", "plan_version": version_id,
                "privacy_version": "2026-01", "country": "SD",
            }, format="json")
            cache.clear()  # the registration throttle
            # Accepted: the emailed code comes next (website.trial_requests).
            self.assertEqual(response.status_code, 202, response.data)
