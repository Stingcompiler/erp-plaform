"""Badges on the sales page tabs: drawers waiting for sign-off (Till) and
quotes/orders waiting for their next step (Quotes & orders)."""
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from sales.models import CashShift, Quotation, SalesOrder
from sales.test_pos_review import POSBase


class SalesTabBadgeTests(POSBase):
    def setUp(self):
        super().setUp()
        # Counts are cached per user id, and ids repeat between tests.
        cache.clear()

    def counts(self, user):
        self.client.force_authenticate(user)
        return self.client.get(reverse("attention")).data["counts"]

    def test_closed_unreviewed_shift_badges_the_till_tab_for_an_approver(self):
        CashShift.objects.create(
            company=self.company, branch=self.branch, opened_by=self.cashier,
            status=CashShift.CLOSED, closed_at=timezone.now(), closed_by=self.cashier,
        )
        self.assertEqual(self.counts(self.owner).get("till"), 1)
        # The cashier cannot sign a count off, so is not nudged.
        self.assertNotIn("till", self.counts(self.cashier))

        CashShift.objects.update(reviewed_at=timezone.now(), reviewed_by=self.owner)
        cache.clear()
        self.assertNotIn("till", self.counts(self.owner))

    def test_open_quotes_and_orders_by_someone_else_badge_the_quotes_tab(self):
        Quotation.objects.create(
            company=self.company, customer=self.customer, branch=self.branch,
            created_by=self.cashier,
        )
        SalesOrder.objects.create(
            company=self.company, customer=self.customer, branch=self.branch,
            status=SalesOrder.CONFIRMED, created_by=self.cashier,
        )
        # Finished work is not waiting for anyone.
        SalesOrder.objects.create(
            company=self.company, customer=self.customer, branch=self.branch,
            status=SalesOrder.FULFILLED, created_by=self.cashier,
        )
        self.assertEqual(self.counts(self.owner).get("quotes"), 2)
        # Your own quotes are not news to you.
        self.assertNotIn("quotes", self.counts(self.cashier))

        self.client.force_authenticate(self.owner)
        self.client.post(reverse("attention-seen"), {"key": "quotes"}, format="json")
        self.assertNotIn("quotes", self.counts(self.owner))
