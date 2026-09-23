"""Offline robustness: replays, races, discards and the pull cursor.

Rule #2 says a queued branch write must be safe to replay. These tests pin
the edges where that used to break: two requests racing on one
client_uuid (a 500 instead of the same document), a batch pushed twice at
once, a rejected operation with no way out, and a delta cursor keyed on
business time that skipped every backdated offline sale.
"""
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Role, User
from core.models import ActivityLog
from inventory.models import Product, StockMovement, Warehouse
from org.models import Branch, Company
from sales.models import Customer, Invoice
from sync.models import DiscardedOperation, SyncBatch


class OfflineBase(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.owner_role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        self.sales_role = Role.objects.create(
            name="Sales Officer", scope_level=Role.SCOPE_BRANCH
        )
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=self.owner_role,
        )
        self.cashier = User.objects.create_user(
            email="till@alpha.test", password="passw0rd123",
            company=self.company, role=self.sales_role, branch=self.branch,
        )
        self.wh = Warehouse.objects.create(company=self.company, branch=self.branch, name="WH")
        self.product = Product.objects.create(
            company=self.company, sku="SKU1", name="Widget",
            sale_price=Decimal("10"), cost_price=Decimal("4"),
        )
        self.customer = Customer.objects.create(company=self.company, name="Ahmed")
        self.client.force_authenticate(self.cashier)

    def _checkout(self, client_uuid, **extra):
        body = {
            "client_uuid": str(client_uuid), "warehouse": self.wh.pk,
            "customer": self.customer.pk,
            "lines": [{"product": self.product.pk, "quantity": "1"}],
            "payment": {"method": "cash", "amount": "10.00"},
        }
        body.update(extra)
        return self.client.post(reverse("pos-checkout"), body, format="json")

    def _push(self, operations, batch_uuid=None, **extra):
        body = {
            "batch_uuid": str(batch_uuid or uuid.uuid4()),
            "expected_company": self.company.pk,
            "expected_user": self.cashier.pk,
            "expected_branch": self.branch.pk,
            "operations": operations,
        }
        body.update(extra)
        return self.client.post(reverse("sync-push"), body, format="json")


class DirectEndpointReplayTests(OfflineBase):
    def test_uuid_race_on_pos_checkout_returns_the_first_invoice(self):
        cu = uuid.uuid4()
        first = self._checkout(cu)
        self.assertEqual(first.status_code, 201, first.data)
        # Simulate the pre-check missing the row (the other request committed
        # between the SELECT and the INSERT): force the insert to collide.
        with mock.patch(
            "sales.views.Invoice.objects.filter",
            side_effect=[Invoice.objects.none(), Invoice.objects.filter(pk=first.data["id"])],
        ):
            with mock.patch(
                "sales.serializers.POSCheckoutSerializer.save",
                side_effect=IntegrityError("duplicate key"),
            ):
                second = self._checkout(cu)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(second.data["id"], first.data["id"])
        self.assertEqual(Invoice.objects.count(), 1)

    def test_local_reference_is_unique_per_company(self):
        self._checkout(uuid.uuid4(), local_reference="MAIN-AB12-000001")
        with self.assertRaises(IntegrityError):
            Invoice.objects.create(
                company=self.company, warehouse=self.wh, number=99,
                local_reference="MAIN-AB12-000001",
            )


class BatchRaceTests(OfflineBase):
    def _op(self, cu=None):
        return {
            "op_type": "pos_checkout", "client_uuid": str(cu or uuid.uuid4()),
            "payload": {
                "warehouse": self.wh.pk, "customer": self.customer.pk,
                "lines": [{"product": self.product.pk, "quantity": "1"}],
                "payment": {"method": "cash", "amount": "10.00"},
            },
        }

    def test_a_partial_identity_pair_is_refused(self):
        response = self.client.post(
            reverse("sync-push"),
            {"batch_uuid": str(uuid.uuid4()), "expected_company": self.company.pk,
             "operations": [self._op()]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_concurrent_same_batch_gets_409_not_500(self):
        batch = uuid.uuid4()
        with mock.patch(
            "sync.views.SyncBatch.objects.create", side_effect=IntegrityError("dup")
        ):
            response = self._push([self._op()], batch_uuid=batch)
        self.assertEqual(response.status_code, 409)

    def test_synced_operation_is_written_to_the_activity_log(self):
        cu = uuid.uuid4()
        response = self._push([self._op(cu)])
        self.assertEqual(response.status_code, 201, response.data)
        invoice = Invoice.objects.get(client_uuid=cu)
        self.assertTrue(
            ActivityLog.objects.filter(
                entity_type="Invoice", entity_id=str(invoice.pk), metadata__via="sync"
            ).exists()
        )

    def test_duplicate_identifier_error_does_not_leak_constraint_names(self):
        cu = uuid.uuid4()
        self._push([self._op(cu)])
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        with mock.patch(
            "sync.services.POSCheckoutSerializer.save", side_effect=IntegrityError("x")
        ):
            with mock.patch("sync.services.Invoice.objects.filter") as flt:
                flt.return_value.first.return_value = None
                response = self._push([self._op(uuid.uuid4())])
        error = response.data["results"][0]["error"]
        self.assertIn("identifier", error)
        self.assertNotIn("constraint", error.lower())


class DiscardTests(OfflineBase):
    def _discard(self, cu, **extra):
        body = {
            "client_uuid": str(cu), "op_type": "pos_checkout",
            "payload": {"warehouse": self.wh.pk, "lines": []},
            "error": "Sales are recorded in the company currency.",
            "reason": "customer paid cash, re-keyed by hand", "device_id": "AB12",
        }
        body.update(extra)
        return self.client.post(reverse("sync-discard"), body, format="json")

    def test_discard_records_evidence_once_and_needs_a_reason(self):
        cu = uuid.uuid4()
        missing = self._discard(cu, reason="")
        self.assertEqual(missing.status_code, 400)
        first = self._discard(cu)
        self.assertEqual(first.status_code, 201, first.data)
        again = self._discard(cu)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(DiscardedOperation.objects.count(), 1)
        record = DiscardedOperation.objects.get()
        self.assertEqual(record.user, self.cashier)
        self.assertEqual(record.branch, self.branch)
        self.assertEqual(record.device_id, "AB12")
        self.assertTrue(ActivityLog.objects.filter(action="discard").exists())

    def test_managers_see_and_resolve_discards_staff_cannot(self):
        self._discard(uuid.uuid4())
        blocked = self.client.get(reverse("sync-discarded"))
        self.assertEqual(blocked.status_code, 403)
        self.client.force_authenticate(self.owner)
        listed = self.client.get(reverse("sync-discarded"), {"open": "1"})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.data), 1)
        badge = self.client.get(reverse("attention"))
        self.assertEqual(badge.status_code, 200)
        resolved = self.client.post(
            reverse("sync-discarded-resolve", args=[listed.data[0]["id"]]),
            {"resolution": "adjusted stock, sale re-keyed as INV-000012"},
            format="json",
        )
        self.assertEqual(resolved.status_code, 200, resolved.data)
        self.assertEqual(
            self.client.get(reverse("sync-discarded"), {"open": "1"}).data, []
        )


class PullCursorTests(OfflineBase):
    def test_backdated_offline_sale_still_appears_in_the_delta(self):
        # A device pulls, then another device syncs a sale that happened two
        # days ago (business time in the past, received now).
        first = self.client.get(reverse("sync-pull"))
        self.assertEqual(first.status_code, 200)
        cursor = first.data["cursor"]
        sold_at = timezone.now() - timedelta(days=2)
        response = self._checkout(uuid.uuid4(), occurred_at=sold_at.isoformat())
        self.assertEqual(response.status_code, 201, response.data)
        second = self.client.get(reverse("sync-pull"), {"since": cursor})
        invoice_ids = {row["id"] for row in second.data["changes"]["invoices"]}
        self.assertIn(response.data["id"], invoice_ids)
        movement_ids = {row["id"] for row in second.data["changes"]["stock_movements"]}
        sold = StockMovement.objects.get(movement_type=StockMovement.SALE_OUT)
        self.assertIn(sold.pk, movement_ids)


class BatchSlotTests(APITestCase):
    def test_sync_operation_slots_are_unique_per_batch(self):
        from sync.models import SyncOperation

        company = Company.objects.create(name="Alpha")
        batch = SyncBatch.objects.create(
            company=company, batch_uuid=uuid.uuid4(), operation_count=1
        )
        SyncOperation.objects.create(batch=batch, index=0, op_type="x", status="applied")
        with self.assertRaises(IntegrityError):
            SyncOperation.objects.create(batch=batch, index=0, op_type="x", status="applied")


class TwoTillsSameStockTests(OfflineBase):
    """M7 acceptance: two tills offline at the same time sell the same last
    units. When both reconnect, the total must not be corrupted by whichever
    synced last, and the conflict must be surfaced rather than silently
    resolved. The ledger keeps both sales (the goods did leave the shop), so
    on-hand is exactly the sum of every movement — and a below-zero product is
    raised to the owner as a stock alert to reconcile."""

    def setUp(self):
        super().setUp()
        # Attention counts are cached per user id, and ids repeat between
        # tests; a count cached by an earlier test must not answer here.
        cache.clear()
        self.second_till = User.objects.create_user(
            email="till2@alpha.test", password="passw0rd123",
            company=self.company, role=self.sales_role, branch=self.branch,
        )
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.ADJUSTMENT, quantity=Decimal("3"),
        )

    def _sale(self, quantity):
        return {
            "op_type": "pos_checkout", "client_uuid": str(uuid.uuid4()),
            "payload": {
                "warehouse": self.wh.pk, "customer": self.customer.pk,
                "lines": [{"product": self.product.pk, "quantity": str(quantity)}],
                "payment": {"method": "cash", "amount": f"{quantity * 10}.00"},
            },
        }

    def _push_as(self, user, operations):
        self.client.force_authenticate(user)
        return self.client.post(
            reverse("sync-push"),
            {
                "batch_uuid": str(uuid.uuid4()), "expected_company": self.company.pk,
                "expected_user": user.pk, "expected_branch": self.branch.pk,
                "operations": operations,
            },
            format="json",
        )

    def test_both_offline_sales_keep_the_total_exact_and_the_deficit_is_raised(self):
        from inventory.alerts import negative_stock

        # Three on the shelf; each till sold two while the internet was down.
        first = self._push_as(self.cashier, [self._sale(2)])
        second = self._push_as(self.second_till, [self._sale(2)])
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 201, second.data)

        # Neither sale overwrote the other: both are in the ledger, and
        # on-hand is exactly 3 - 2 - 2, not "whatever the last sync said".
        sold = StockMovement.objects.filter(
            product=self.product, movement_type=StockMovement.SALE_OUT
        )
        self.assertEqual(sold.count(), 2)
        self.assertEqual(self.product.on_hand(), Decimal("-1"))
        self.assertEqual(Invoice.objects.filter(company=self.company).count(), 2)

        # Surfaced, not silently resolved: the product is on the negative
        # stock list the owner's dashboard reads.
        negative = negative_stock(self.company.pk).values_list("pk", flat=True)
        self.assertIn(self.product.pk, negative)
        self.client.force_authenticate(self.owner)
        counts = self.client.get(reverse("attention")).data["counts"]
        self.assertGreaterEqual(counts.get("stock", 0), 1)


class RepairableRefusalTests(OfflineBase):
    """A queued sale refused for a reason the cashier can fix says which
    field it was, so the till can offer the repair instead of only discard;
    an unexpected failure never sends Python's own text to the cashier."""

    _op = BatchRaceTests._op

    def test_an_unpaid_sale_without_customer_names_the_customer_field(self):
        op = self._op()
        op["payload"]["customer"] = None
        op["payload"]["payment"]["amount"] = "4.00"  # less than the total
        result = self._push([op]).data["results"][0]
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_field"], "customer")
        # Repaired in place (same client_uuid) and sent again: applied once.
        op["payload"]["customer"] = self.customer.pk
        again = self._push([op]).data["results"][0]
        self.assertEqual(again["status"], "applied", again)
        self.assertEqual(Invoice.objects.filter(client_uuid=op["client_uuid"]).count(), 1)

    def test_an_unexpected_failure_is_reported_in_words(self):
        with mock.patch(
            "sync.services.POSCheckoutSerializer.save", side_effect=RuntimeError("boom internals")
        ):
            result = self._push([self._op()]).data["results"][0]
        self.assertEqual(result["status"], "error")
        self.assertNotIn("boom", result["error"])
