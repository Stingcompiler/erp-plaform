"""A plan is priced in one of the ISO 4217 codes the app supports. A new
"SD" (production's bs-2) is refused with a message in the reader's
language; a version saved before the rule stays readable, untouched."""
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone, translation
from rest_framework.test import APIClient

from accounts.models import User
from subscriptions.models import PLAN_CURRENCIES, Plan, PlanVersion, plan_currency_error


class PlanCurrencyTests(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(code="bs-2", name="BS 2")
        self.admin = User.objects.create_superuser("platform@example.test", "secure-password")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def _post(self, currency, version=1):
        return self.client.post("/api/platform/plan-versions/", {
            "plan": self.plan.pk, "version": version, "currency": currency, "price": "1000",
            "billing_cycle": "monthly", "modules": ["sales", "inventory"], "limits": {},
        }, format="json")

    def test_the_supported_set_is_small_and_iso(self):
        self.assertIn("SDG", PLAN_CURRENCIES)
        self.assertIn("USD", PLAN_CURRENCIES)
        for code in PLAN_CURRENCIES:
            self.assertRegex(code, r"^[A-Z]{3}$")

    def test_api_refuses_a_code_outside_the_set(self):
        for code in ("SD", "SDD", "XYZ", "", "ج.س"):
            with self.subTest(code=code):
                response = self._post(code)
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn("currency", response.data)
        self.assertFalse(PlanVersion.objects.filter(plan=self.plan).exists())

    def test_api_accepts_a_supported_code_in_any_case(self):
        response = self._post(" sdg ")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(PlanVersion.objects.get(plan=self.plan).currency, "SDG")

    def test_model_clean_refuses_it_too(self):
        with self.assertRaises(ValidationError) as caught:
            PlanVersion.objects.create(plan=self.plan, version=1, currency="SD", price=1)
        self.assertIn("currency", caught.exception.message_dict)

    def test_error_is_bilingual(self):
        with translation.override("en"):
            self.assertIn("supported currency codes", plan_currency_error())
        with translation.override("ar"):
            message = plan_currency_error()
        self.assertIn("رموز العملات المدعومة", message)
        self.assertIn("SDG", message)

    def test_a_version_saved_before_the_rule_stays_readable(self):
        # Written the way production's row was: before validation existed.
        PlanVersion.objects.bulk_create([PlanVersion(
            plan=self.plan, version=1, currency="SD", price=1000, billing_cycle="monthly",
            modules=["sales", "inventory"], limits={}, published_at=timezone.now(),
        )])
        legacy = PlanVersion.objects.get(plan=self.plan)
        # Saving it unchanged (no rewrite) still works…
        legacy.save()
        legacy.refresh_from_db()
        self.assertEqual(legacy.currency, "SD")
        # …and the public list and the plans page still read it as stored.
        public = APIClient().get("/api/public/plans/")
        self.assertEqual(public.status_code, 200)
        row = next(row for row in public.json() if row["plan_code"] == "bs-2")
        self.assertEqual(row["currency"], "SD")
        listing = self.client.get("/api/platform/plans/")
        self.assertEqual(listing.status_code, 200)
        # A new version must pick a supported code.
        self.assertEqual(self._post("SD", version=2).status_code, 400)
        self.assertEqual(self._post("SDG", version=2).status_code, 201)
