from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product, StockAdjustment, StockCount, StockMovement, Warehouse
from org.models import Branch, Company


class StockCountTests(APITestCase):
    """Count → submit (freezes ledger) → approve by someone else (posts
    adjustments). The count never touches the ledger directly."""

    def setUp(self):
        self.company = Company.objects.create(name="Store")
        branch = Branch.objects.create(company=self.company, name="Main")
        self.wh = Warehouse.objects.create(company=self.company, branch=branch, name="WH")
        officer_role = Role.objects.create(name="Inventory Officer", scope_level=Role.SCOPE_BRANCH)
        manager_role = Role.objects.create(name="General Manager", scope_level=Role.SCOPE_BUSINESS)
        self.officer = User.objects.create_user(
            "officer@store.test",
            "passw0rd123",
            company=self.company,
            branch=branch,
            role=officer_role,
        )
        self.manager = User.objects.create_user(
            "gm@store.test", "passw0rd123", company=self.company, role=manager_role
        )
        self.a = Product.objects.create(company=self.company, sku="A", name="A", sale_price=1)
        self.b = Product.objects.create(company=self.company, sku="B", name="B", sale_price=1)
        for product, qty in ((self.a, 10), (self.b, 4)):
            StockMovement.objects.create(
                company=self.company,
                product=product,
                warehouse=self.wh,
                movement_type=StockMovement.PURCHASE_IN,
                quantity=qty,
            )

    def _create(self, client):
        return client.post(
            reverse("stockcount-list"),
            {
                "warehouse": self.wh.id,
                "note": "Month end",
                "lines": [
                    {"product": self.a.id, "counted_quantity": "8"},  # 2 missing
                    {"product": self.b.id, "counted_quantity": "4"},  # exact
                ],
            },
            format="json",
        )

    def test_full_workflow_posts_only_the_variances(self):
        self.client.force_authenticate(self.officer)
        created = self._create(self.client)
        self.assertEqual(created.status_code, 201, created.data)
        count_id = created.data["id"]
        # A later sale must not change what the counter saw once submitted.
        submitted = self.client.post(reverse("stockcount-submit", args=[count_id]))
        self.assertEqual(submitted.status_code, 200, submitted.data)
        expected = {row["product"]: row["expected_quantity"] for row in submitted.data["lines"]}
        self.assertEqual(Decimal(expected[self.a.id]), Decimal("10"))
        StockMovement.objects.create(
            company=self.company,
            product=self.a,
            warehouse=self.wh,
            movement_type=StockMovement.SALE_OUT,
            quantity=-1,
        )
        # The counter cannot approve their own count.
        own = self.client.post(reverse("stockcount-approve", args=[count_id]))
        self.assertEqual(own.status_code, 400)
        # A manager can.
        self.client.force_authenticate(self.manager)
        approved = self.client.post(reverse("stockcount-approve", args=[count_id]))
        self.assertEqual(approved.status_code, 200, approved.data)
        self.assertEqual(approved.data["status"], "approved")
        adjustments = StockAdjustment.objects.filter(reason__startswith="Stock count")
        self.assertEqual(adjustments.count(), 1)  # only product A had a variance
        self.assertEqual(adjustments.get().quantity, Decimal("-2"))
        # Ledger: 10 - 1 (sale) - 2 (count variance) = 7; B untouched.
        self.assertEqual(self.a.on_hand(warehouse=self.wh), Decimal("7"))
        self.assertEqual(self.b.on_hand(warehouse=self.wh), Decimal("4"))
        # Approved counts are frozen.
        edit = self.client.patch(
            reverse("stockcount-detail", args=[count_id]), {"note": "x"}, format="json"
        )
        self.assertEqual(edit.status_code, 400)

    def test_officer_cannot_approve_and_empty_count_cannot_be_submitted(self):
        self.client.force_authenticate(self.officer)
        # An empty count is refused when saved (it used to save and fail only
        # at submit); a count stripped of its lines still cannot be submitted.
        empty = StockCount.objects.create(company=self.company, warehouse=self.wh)
        self.assertEqual(
            self.client.post(reverse("stockcount-submit", args=[empty.id])).status_code, 400,
        )
        full = self._create(self.client).data["id"]
        self.client.post(reverse("stockcount-submit", args=[full]))
        other_officer = User.objects.create_user(
            "officer2@store.test",
            "passw0rd123",
            company=self.company,
            branch=self.wh.branch,
            role=self.officer.role,
        )
        self.client.force_authenticate(other_officer)
        self.assertEqual(
            self.client.post(reverse("stockcount-approve", args=[full])).status_code, 400
        )

    def test_count_is_company_scoped(self):
        other = Company.objects.create(name="Other")
        other_branch = Branch.objects.create(company=other, name="B")
        other_wh = Warehouse.objects.create(company=other, branch=other_branch, name="OW")
        self.client.force_authenticate(self.manager)
        response = self.client.post(
            reverse("stockcount-list"),
            {"warehouse": other_wh.id, "lines": [{"product": self.a.id, "counted_quantity": "1"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(StockCount.objects.count(), 0)

    # Rules added after a production report: an empty draft that could only
    # fail at submit, and buttons that disagreed with what the server accepts.

    def test_an_empty_count_is_refused_at_save(self):
        self.client.force_authenticate(self.officer)
        response = self.client.post(
            reverse("stockcount-list"), {"warehouse": self.wh.id, "lines": []}, format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("lines", response.data)
        self.assertEqual(StockCount.objects.count(), 0)

    def test_an_archived_product_cannot_be_counted(self):
        self.a.is_active = False
        self.a.save()
        self.client.force_authenticate(self.officer)
        self.assertEqual(self._create(self.client).status_code, 400)

    def test_only_one_count_per_warehouse_awaits_approval(self):
        self.client.force_authenticate(self.officer)
        first = self._create(self.client).data["id"]
        second = self._create(self.client).data["id"]
        self.assertEqual(
            self.client.post(reverse("stockcount-submit", args=[first])).status_code, 200,
        )
        refused = self.client.post(reverse("stockcount-submit", args=[second]))
        self.assertEqual(refused.status_code, 400)

    def test_buttons_follow_the_server_rules(self):
        self.client.force_authenticate(self.officer)
        count_id = self._create(self.client).data["id"]
        self.client.post(reverse("stockcount-submit", args=[count_id]))
        mine = self.client.get(reverse("stockcount-detail", args=[count_id])).data
        self.assertFalse(mine["can_approve"])  # the counter never approves
        self.assertTrue(mine["can_cancel"])  # but may withdraw their count
        self.client.force_authenticate(self.manager)
        theirs = self.client.get(reverse("stockcount-detail", args=[count_id])).data
        self.assertTrue(theirs["can_approve"])

    def test_a_stranger_cannot_cancel_and_a_cancelled_count_stays_cancelled(self):
        self.client.force_authenticate(self.officer)
        count_id = self._create(self.client).data["id"]
        other = User.objects.create_user(
            "other@store.test", "passw0rd123", company=self.company,
            branch=self.officer.branch, role=self.officer.role,
        )
        self.client.force_authenticate(other)
        refused = self.client.post(reverse("stockcount-cancel", args=[count_id]))
        self.assertEqual(refused.status_code, 400)
        self.client.force_authenticate(self.officer)
        self.assertEqual(
            self.client.post(reverse("stockcount-cancel", args=[count_id])).status_code, 200,
        )
        again = self.client.post(reverse("stockcount-cancel", args=[count_id]))
        self.assertEqual(again.status_code, 400)

    def test_a_sale_between_counting_and_submitting_is_not_a_surplus(self):
        # Counted at nine (8 of A on the shelf, ledger 10), one sold before
        # submit: the difference is still -2, not -1, and the sale survives.
        self.client.force_authenticate(self.officer)
        count_id = self._create(self.client).data["id"]
        StockMovement.objects.create(
            company=self.company, product=self.a, warehouse=self.wh,
            movement_type=StockMovement.SALE_OUT, quantity=-1,
        )
        submitted = self.client.post(reverse("stockcount-submit", args=[count_id])).data
        line = next(row for row in submitted["lines"] if row["product"] == self.a.id)
        self.assertEqual(Decimal(line["expected_quantity"]), Decimal("10"))
        self.assertEqual(Decimal(line["variance"]), Decimal("-2"))
        self.assertEqual(submitted["moved_since"], 1)  # told to the approver
        self.client.force_authenticate(self.manager)
        self.client.post(reverse("stockcount-approve", args=[count_id]))
        # 10 received - 1 sold - 2 missing = 7.
        self.assertEqual(self.a.on_hand(warehouse=self.wh), Decimal("7"))

    def test_a_lot_tracked_product_is_counted_per_lot(self):
        from inventory.models import StockBatch

        self.a.track_batches = True
        self.a.save()
        lot = StockBatch.objects.create(company=self.company, product=self.a, lot_number="L1")
        StockMovement.objects.create(
            company=self.company, product=self.a, warehouse=self.wh, batch=lot,
            movement_type=StockMovement.PURCHASE_IN, quantity=5,
        )
        self.client.force_authenticate(self.officer)
        without_lot = self._create(self.client)
        self.assertEqual(without_lot.status_code, 400)
        self.assertIn("lines", without_lot.data)
        created = self.client.post(
            reverse("stockcount-list"),
            {"warehouse": self.wh.id, "lines": [
                {"product": self.a.id, "batch": lot.id, "counted_quantity": "4"},
            ]},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        count_id = created.data["id"]
        self.client.post(reverse("stockcount-submit", args=[count_id]))
        self.client.force_authenticate(self.manager)
        self.client.post(reverse("stockcount-approve", args=[count_id]))
        adjustment = StockAdjustment.objects.get()
        self.assertEqual(adjustment.batch_id, lot.id)  # the difference stays in its lot
        self.assertEqual(adjustment.quantity, Decimal("-1"))

    def test_lots_can_be_listed_for_one_product(self):
        from inventory.models import StockBatch

        StockBatch.objects.create(company=self.company, product=self.a, lot_number="LA")
        StockBatch.objects.create(company=self.company, product=self.b, lot_number="LB")
        self.client.force_authenticate(self.officer)
        rows = self.client.get(reverse("stockbatch-list"), {"product": self.a.id}).data
        rows = rows.get("results", rows)
        self.assertEqual([row["lot_number"] for row in rows], ["LA"])
