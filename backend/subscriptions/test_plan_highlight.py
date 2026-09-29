"""Only one plan carries the pricing page's "most popular" badge, and the
public list reads in the order the operator set, cheapest first on ties."""
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from subscriptions.models import Plan, PlanVersion


class SingleHighlightTests(TestCase):
    def test_highlighting_a_plan_clears_the_previous_one(self):
        first = Plan.objects.create(code="a", name="A", is_highlighted=True)
        second = Plan.objects.create(code="b", name="B", is_highlighted=True)
        first.refresh_from_db()
        self.assertFalse(first.is_highlighted)
        self.assertTrue(second.is_highlighted)
        first.is_highlighted = True
        first.save()
        self.assertEqual(list(Plan.objects.filter(is_highlighted=True)), [first])

    def test_saving_an_unhighlighted_plan_leaves_the_badge_alone(self):
        badge = Plan.objects.create(code="a", name="A", is_highlighted=True)
        other = Plan.objects.create(code="b", name="B")
        other.name = "B2"
        other.save()
        badge.refresh_from_db()
        self.assertTrue(badge.is_highlighted)

    def test_a_form_may_highlight_another_plan(self):
        Plan.objects.create(code="a", name="A", is_highlighted=True)
        other = Plan(code="b", name="B", is_highlighted=True)
        other.full_clean()  # the Django admin's check; save() then moves the badge
        other.save()
        self.assertEqual(list(Plan.objects.filter(is_highlighted=True)), [other])

    def test_the_database_refuses_a_second_badge_that_bypasses_save(self):
        Plan.objects.create(code="a", name="A", is_highlighted=True)
        other = Plan.objects.create(code="b", name="B")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Plan.objects.filter(pk=other.pk).update(is_highlighted=True)

    def test_platform_api_moves_the_badge(self):
        admin = User.objects.create_superuser("platform@example.test", "secure-password")
        client = APIClient()
        client.force_authenticate(admin)
        first = Plan.objects.create(code="a", name="A", is_highlighted=True)
        second = Plan.objects.create(code="b", name="B")
        response = client.patch(
            f"/api/platform/plans/{second.pk}/", {"is_highlighted": True}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        first.refresh_from_db()
        self.assertFalse(first.is_highlighted)
        listing = client.get("/api/platform/plans/")
        rows = listing.data.get("results", listing.data) if isinstance(listing.data, dict) else listing.data
        self.assertEqual([row["code"] for row in rows if row["is_highlighted"]], ["b"])


class PublicPlanListTests(TestCase):
    def _plan(self, code, price, sort_order=100, highlighted=False, **extra):
        plan = Plan.objects.create(
            code=code, name=code.title(), sort_order=sort_order,
            is_highlighted=highlighted, **extra,
        )
        return PlanVersion.objects.create(
            plan=plan, version=1, currency="SDG", price=price,
            modules=["inventory", "sales"], limits={"users": 2},
            published_at=timezone.now(),
        )

    def test_order_is_sort_order_then_price_and_one_plan_is_highlighted(self):
        self._plan("zeta", 500, highlighted=True)
        self._plan("alpha", 900)
        self._plan("mid", 200, highlighted=True)
        self._plan("first", 5000, sort_order=1)
        self._plan("hidden", 1, is_public=False)
        response = APIClient().get("/api/public/plans/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row["plan_code"] for row in response.data], ["first", "mid", "zeta", "alpha"]
        )
        highlighted = [
            row["plan_code"] for row in response.data if row["display"]["is_highlighted"]
        ]
        self.assertEqual(highlighted, ["mid"])

    def test_public_rows_carry_the_real_limits_and_modules(self):
        self._plan("basic", 100)
        row = APIClient().get("/api/public/plans/").data[0]
        self.assertEqual(row["limits"], {"users": 2})
        self.assertEqual(row["modules"], ["inventory", "sales"])
        self.assertEqual(row["currency"], "SDG")
        # Pricing and capacity only: nothing the platform keeps to itself.
        self.assertNotIn("addon_prices", row)
        self.assertNotIn("description", row)
