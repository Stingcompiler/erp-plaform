"""The 2026-09-24 offline sync review.

Each class pins one finding: something that already happened on a device
(a sale, a payment, a return) is accepted with an audit row instead of being
refused for good, unless accepting it would be a security hole.
"""
import uuid
from datetime import timedelta
from decimal import Decimal

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from core.models import ActivityLog
from inventory.models import StockAdjustment, StockMovement, StockTransfer, Warehouse
from org.models import TaxRateChange, tax_rate_was_in_effect
from sales.models import CashShift, Invoice, Payment, Refund
from sync.models import DiscardedOperation
from sync.test_offline_robustness import OfflineBase


class ReviewBase(OfflineBase):
    def _op(self, cu=None, **payload):
        body = {
            "warehouse": self.wh.pk, "customer": self.customer.pk,
            "lines": [{"product": self.product.pk, "quantity": "1", "unit_price": "10.00"}],
            "payment": {"method": "cash", "amount": "10.00"},
        }
        body.update(payload)
        return {"op_type": "pos_checkout", "client_uuid": str(cu or uuid.uuid4()), "payload": body}

    def _push_as(self, user, operations, **extra):
        self.client.force_authenticate(user)
        body = {
            "batch_uuid": str(uuid.uuid4()),
            "expected_company": self.company.pk, "expected_user": user.pk,
            "expected_branch": user.branch_id, "operations": operations,
        }
        body.update(extra)
        return self.client.post(reverse("sync-push"), body, format="json")


class SharedTillReferenceTests(ReviewBase):
    """Two cashiers on one tablet printed the same provisional reference."""

    REF = "MAIN-AB12-000001"

    def setUp(self):
        super().setUp()
        self.other = User.objects.create_user(
            email="till2@alpha.test", password="passw0rd123",
            company=self.company, role=self.sales_role, branch=self.branch,
        )

    def test_the_second_sale_is_kept_under_a_suffixed_reference(self):
        first = self._push_as(self.cashier, [self._op(local_reference=self.REF)])
        self.assertEqual(first.data["results"][0]["status"], "applied")
        cu = uuid.uuid4()
        second = self._push_as(self.other, [self._op(cu, local_reference=self.REF)])
        self.assertEqual(second.data["results"][0]["status"], "applied", second.data)
        kept = Invoice.objects.get(client_uuid=cu)
        self.assertEqual(kept.local_reference, f"{self.REF}-2")
        log = ActivityLog.objects.get(action="local_reference_renumbered")
        self.assertEqual(log.metadata["printed"], self.REF)
        self.assertEqual(Invoice.objects.filter(local_reference=self.REF).count(), 1)

    def test_a_third_collision_takes_the_next_suffix(self):
        for user in (self.cashier, self.other, self.owner):
            self.assertEqual(
                self._push_as(user, [self._op(local_reference=self.REF)])
                .data["results"][0]["status"], "applied",
            )
        self.assertEqual(
            sorted(Invoice.objects.values_list("local_reference", flat=True)),
            [self.REF, f"{self.REF}-2", f"{self.REF}-3"],
        )

    def test_online_checkout_with_a_taken_reference_does_not_fail(self):
        self._push_as(self.cashier, [self._op(local_reference=self.REF)])
        self.client.force_authenticate(self.other)
        response = self._checkout(uuid.uuid4(), local_reference=self.REF)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["local_reference"], f"{self.REF}-2")

    def test_a_replay_of_the_same_sale_is_still_a_duplicate(self):
        op = self._op(local_reference=self.REF)
        self._push_as(self.cashier, [op])
        again = self._push_as(self.cashier, [op])
        self.assertEqual(again.data["results"][0]["status"], "duplicate")
        self.assertEqual(Invoice.objects.count(), 1)


class TaxRateHistoryTests(ReviewBase):
    def setUp(self):
        super().setUp()
        profile = self.company.tax_profile
        profile.flat_tax_rate = Decimal("10.00")
        profile.save(update_fields=["flat_tax_rate"])

    def test_every_rate_change_is_recorded(self):
        rates = list(
            TaxRateChange.objects.filter(company=self.company)
            .order_by("effective_from", "pk").values_list("rate", flat=True)
        )
        self.assertEqual(rates[-1], Decimal("10.00"))
        profile = self.company.tax_profile
        profile.save()  # unchanged: no new row
        self.assertEqual(TaxRateChange.objects.filter(company=self.company).count(), len(rates))

    def test_a_rate_the_company_never_had_is_refused(self):
        cu = uuid.uuid4()
        res = self._push_as(self.cashier, [self._op(
            cu, tax_rate="3.00", occurred_at=timezone.now().isoformat(),
            payment={"method": "cash", "amount": "10.30"},
        )])
        result = res.data["results"][0]
        self.assertEqual(result["status"], "error", result)
        self.assertEqual(result["error_field"], "tax_rate")
        self.assertFalse(Invoice.objects.filter(client_uuid=cu).exists())

    def test_the_rate_before_a_recent_change_is_kept_with_an_audit_row(self):
        profile = self.company.tax_profile
        profile.flat_tax_rate = Decimal("15.00")
        profile.save()
        cu = uuid.uuid4()
        res = self._push_as(self.cashier, [self._op(
            cu, tax_rate="10.00", occurred_at=timezone.now().isoformat(),
            payment={"method": "cash", "amount": "11.00"},
        )])
        self.assertEqual(res.data["results"][0]["status"], "applied", res.data)
        self.assertEqual(Invoice.objects.get(client_uuid=cu).tax_amount, Decimal("1.00"))
        self.assertTrue(ActivityLog.objects.filter(action="tax_rate_mismatch").exists())

    def test_a_rate_that_ended_before_the_backdate_window_is_refused(self):
        TaxRateChange.objects.filter(company=self.company).update(
            effective_from=timezone.now() - timedelta(days=90)
        )
        TaxRateChange.objects.create(
            company=self.company, rate=Decimal("7.00"),
            effective_from=timezone.now() - timedelta(days=200),
        )
        self.assertFalse(tax_rate_was_in_effect(self.company.pk, Decimal("7.00"), timezone.now()))
        self.assertTrue(tax_rate_was_in_effect(
            self.company.pk, Decimal("7.00"), timezone.now() - timedelta(days=120)
        ))


class DiscardAppliedTests(ReviewBase):
    def test_discarding_an_op_that_already_landed_answers_already_applied(self):
        cu = uuid.uuid4()
        op = self._op(cu)
        self.assertEqual(
            self._push_as(self.cashier, [op]).data["results"][0]["status"], "applied"
        )
        res = self.client.post(reverse("sync-discard"), {
            "client_uuid": str(cu), "op_type": "pos_checkout",
            "payload": op["payload"], "reason": "kept failing", "error": "__no_confirmation__",
        }, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["status"], "already_applied")
        self.assertEqual(res.data["id"], Invoice.objects.get(client_uuid=cu).pk)
        self.assertFalse(DiscardedOperation.objects.filter(client_uuid=cu).exists())

    def test_an_op_that_never_landed_is_still_discarded(self):
        cu = uuid.uuid4()
        res = self.client.post(reverse("sync-discard"), {
            "client_uuid": str(cu), "op_type": "pos_checkout",
            "payload": self._op(cu)["payload"], "reason": "wrong", "error": "x",
        }, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(DiscardedOperation.objects.filter(client_uuid=cu).exists())


class ClockTests(ReviewBase):
    def test_a_reset_clock_stamp_is_recorded_at_arrival_with_an_audit_row(self):
        stamped = timezone.now() - timedelta(days=400)
        cu = uuid.uuid4()
        res = self._push_as(self.cashier, [self._op(cu, occurred_at=stamped.isoformat())],
                            sent_at=timezone.now().isoformat())
        self.assertEqual(res.data["results"][0]["status"], "applied", res.data)
        invoice = Invoice.objects.get(client_uuid=cu)
        self.assertLess(abs((invoice.issued_at - timezone.now()).total_seconds()), 120)
        log = ActivityLog.objects.get(action="device_time_out_of_window")
        self.assertEqual(log.metadata["device_time"][:10], stamped.isoformat()[:10])
        self.assertEqual(log.entity_id, str(invoice.pk))

    def test_a_stamp_far_in_the_future_is_recorded_now_not_refused(self):
        cu = uuid.uuid4()
        ahead = timezone.now() + timedelta(days=3)
        res = self._push_as(self.cashier, [self._op(cu, occurred_at=ahead.isoformat())])
        self.assertEqual(res.data["results"][0]["status"], "applied", res.data)
        self.assertLessEqual(Invoice.objects.get(client_uuid=cu).issued_at, timezone.now())
        self.assertTrue(ActivityLog.objects.filter(action="device_time_out_of_window").exists())

    def test_the_offset_measured_at_capture_beats_the_upload_time_offset(self):
        # Sale at a correct time; a reboot then set the clock a day ahead
        # before the flush. The item's own offset (0) is used, not the
        # batch's (-1 day).
        cu = uuid.uuid4()
        real = timezone.now() - timedelta(hours=1)
        op = self._op(cu, occurred_at=real.isoformat())
        op["clock_offset_ms"] = 0
        res = self._push_as(self.cashier, [op],
                            sent_at=(timezone.now() + timedelta(days=1)).isoformat())
        self.assertEqual(res.data["results"][0]["status"], "applied", res.data)
        issued = Invoice.objects.get(client_uuid=cu).issued_at
        self.assertLess(abs((issued - real).total_seconds()), 5)

    def test_an_items_own_offset_corrects_its_time(self):
        cu = uuid.uuid4()
        real = timezone.now() - timedelta(hours=2)
        device = real - timedelta(hours=5)  # the clock was 5 hours slow
        op = self._op(cu, occurred_at=device.isoformat())
        op["clock_offset_ms"] = 5 * 3600 * 1000
        res = self._push_as(self.cashier, [op], sent_at=timezone.now().isoformat())
        self.assertEqual(res.data["results"][0]["status"], "applied", res.data)
        issued = Invoice.objects.get(client_uuid=cu).issued_at
        self.assertLess(abs((issued - real).total_seconds()), 5)


@override_settings(SUBSCRIPTION_POLICY="enforce")
class SubscriptionLapseTests(ReviewBase):
    def setUp(self):
        super().setUp()
        from subscriptions.models import Plan, PlanVersion, Subscription

        now = timezone.now()
        plan = Plan.objects.create(code="all", name="All")
        version = PlanVersion.objects.create(plan=plan, version=1, modules=["*"], published_at=now)
        self.subscription = Subscription.objects.create(
            company=self.company, plan_version=version, status=Subscription.ACTIVE,
            starts_at=now - timedelta(days=30), period_ends_at=now - timedelta(hours=3),
        )

    def test_sales_rung_before_the_lapse_upload_after_it(self):
        cu = uuid.uuid4()
        res = self._push_as(self.cashier, [self._op(
            cu, occurred_at=(timezone.now() - timedelta(hours=5)).isoformat()
        )])
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["results"][0]["status"], "applied", res.data)
        self.assertTrue(ActivityLog.objects.filter(action="synced_while_read_only").exists())

    def test_a_sale_rung_after_the_lapse_is_refused_with_the_reason(self):
        cu = uuid.uuid4()
        res = self._push_as(self.cashier, [self._op(
            cu, occurred_at=(timezone.now() - timedelta(hours=1)).isoformat()
        )])
        result = res.data["results"][0]
        self.assertEqual(result["status"], "error", result)
        self.assertEqual(result["error_field"], "subscription")
        self.assertFalse(Invoice.objects.filter(client_uuid=cu).exists())

    def test_a_state_set_by_hand_counts_from_when_it_was_set(self):
        from subscriptions.models import Subscription

        Subscription.objects.filter(pk=self.subscription.pk).update(
            status=Subscription.SUSPENDED, period_ends_at=timezone.now() + timedelta(days=5),
            updated_at=timezone.now() - timedelta(hours=2),
        )
        before, after = uuid.uuid4(), uuid.uuid4()
        res = self._push_as(self.cashier, [
            self._op(before, occurred_at=(timezone.now() - timedelta(hours=4)).isoformat()),
            self._op(after, occurred_at=(timezone.now() - timedelta(minutes=30)).isoformat()),
        ])
        statuses = [r["status"] for r in res.data["results"]]
        self.assertEqual(statuses, ["applied", "error"], res.data)

    def test_new_work_online_is_still_blocked(self):
        response = self._checkout(uuid.uuid4())
        self.assertEqual(response.status_code, 403)


class OccurredAtTests(ReviewBase):
    def setUp(self):
        super().setUp()
        self.other_wh = Warehouse.objects.create(company=self.company, branch=self.branch, name="B")

    def _push_owner(self, ops):
        return self._push_as(self.owner, ops)

    def test_an_adjustment_is_dated_when_it_happened(self):
        when = timezone.now() - timedelta(days=2)
        cu = uuid.uuid4()
        res = self._push_owner([{"op_type": "stock_adjustment", "client_uuid": str(cu), "payload": {
            "product": self.product.pk, "warehouse": self.wh.pk, "quantity": "5",
            "reason": "found", "reason_code": "count",
            "occurred_at": when.isoformat(),
        }}])
        self.assertEqual(res.data["results"][0]["status"], "applied", res.data)
        adjustment = StockAdjustment.objects.get(client_uuid=cu)
        self.assertLess(abs((adjustment.created_at - when).total_seconds()), 2)
        self.assertLess(abs((adjustment.movement.created_at - when).total_seconds()), 2)
        self.assertIsNotNone(adjustment.received_at)
        self.assertGreater(adjustment.received_at, adjustment.created_at)

    def test_a_transfer_is_dated_when_it_happened(self):
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.PURCHASE_IN, quantity=Decimal("10"),
            unit_cost=Decimal("4"),
        )
        when = timezone.now() - timedelta(days=1)
        cu = uuid.uuid4()
        res = self._push_owner([{"op_type": "stock_transfer", "client_uuid": str(cu), "payload": {
            "product": self.product.pk, "source_warehouse": self.wh.pk,
            "dest_warehouse": self.other_wh.pk, "quantity": "2",
            "occurred_at": when.isoformat(),
        }}])
        self.assertEqual(res.data["results"][0]["status"], "applied", res.data)
        transfer = StockTransfer.objects.get(client_uuid=cu)
        for moment in (transfer.created_at, transfer.source_movement.created_at,
                       transfer.dest_movement.created_at):
            self.assertLess(abs((moment - when).total_seconds()), 2)

    def test_a_future_time_is_clamped_to_now_online(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(reverse("stockadjustment-list"), {
            "product": self.product.pk, "warehouse": self.wh.pk, "quantity": "1",
            "reason": "found", "reason_code": "count",
            "occurred_at": (timezone.now() + timedelta(minutes=5)).isoformat(),
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        adjustment = StockAdjustment.objects.get(pk=response.data["id"])
        self.assertLessEqual(adjustment.created_at, timezone.now())

    def test_a_sales_return_is_dated_when_it_happened(self):
        from returns.models import SalesReturn

        self.client.force_authenticate(self.owner)
        sale = self._checkout(uuid.uuid4())
        self.assertEqual(sale.status_code, 201, sale.data)
        invoice = Invoice.objects.get(pk=sale.data["id"])
        line = invoice.lines.first()
        when = timezone.now() - timedelta(hours=6)
        cu = uuid.uuid4()
        res = self._push_owner([{"op_type": "sales_return", "client_uuid": str(cu), "payload": {
            "invoice": invoice.pk, "reason": "broken", "occurred_at": when.isoformat(),
            "lines": [{"invoice_line": line.pk, "product": self.product.pk, "quantity": "1"}],
        }}])
        self.assertEqual(res.data["results"][0]["status"], "applied", res.data)
        sales_return = SalesReturn.objects.get(client_uuid=cu)
        self.assertLess(abs((sales_return.created_at - when).total_seconds()), 2)
        self.assertIsNotNone(sales_return.received_at)


class ClosedShiftMoneyTests(ReviewBase):
    def _shift(self, opened_hours_ago, closed_minutes_ago=None, user=None):
        shift = CashShift.objects.create(
            company=self.company, branch=self.branch, opened_by=user or self.cashier,
            opening_float=Decimal("0"),
        )
        CashShift.objects.filter(pk=shift.pk).update(
            opened_at=timezone.now() - timedelta(hours=opened_hours_ago)
        )
        if closed_minutes_ago is not None:
            CashShift.objects.filter(pk=shift.pk).update(
                status=CashShift.CLOSED, counted_cash=0,
                closed_at=timezone.now() - timedelta(minutes=closed_minutes_ago),
            )
        shift.refresh_from_db()
        return shift

    def _invoice(self):
        return Invoice.objects.create(
            company=self.company, branch=self.branch, warehouse=self.wh, customer=self.customer,
            number=901, subtotal=Decimal("50"), total=Decimal("50"),
        )

    def _payment(self, shift, recorded_at):
        return {"op_type": "payment", "client_uuid": str(uuid.uuid4()), "payload": {
            "invoice": self._invoice().pk, "method": "cash", "amount": "50.00",
            "shift": shift.pk, "recorded_at": recorded_at.isoformat(),
        }}

    def test_a_payment_after_its_drawer_closed_is_kept_outside_any_drawer(self):
        shift = self._shift(8, closed_minutes_ago=60)
        op = self._payment(shift, timezone.now() - timedelta(minutes=10))
        result = self._push_as(self.cashier, [op]).data["results"][0]
        self.assertEqual(result["status"], "applied", result)
        self.assertIsNone(Payment.objects.get(client_uuid=op["client_uuid"]).shift_id)
        self.assertTrue(ActivityLog.objects.filter(action="money_outside_closed_shift").exists())

    def test_it_lands_in_the_drawer_that_was_open_at_the_time(self):
        old = self._shift(8, closed_minutes_ago=60)
        current = self._shift(0.5)
        op = self._payment(old, timezone.now() - timedelta(minutes=10))
        result = self._push_as(self.cashier, [op]).data["results"][0]
        self.assertEqual(result["status"], "applied", result)
        self.assertEqual(Payment.objects.get(client_uuid=op["client_uuid"]).shift_id, current.pk)

    def test_online_a_closed_drawer_is_still_refused(self):
        shift = self._shift(8, closed_minutes_ago=60)
        op = self._payment(shift, timezone.now())
        self.client.force_authenticate(self.cashier)
        response = self.client.post(reverse("payment-list"), op["payload"], format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("shift", response.data)

    def test_a_cash_refund_after_its_drawer_closed_is_kept(self):
        from returns.models import CreditNote

        shift = self._shift(8, closed_minutes_ago=60, user=self.owner)
        note = CreditNote.objects.create(
            company=self.company, customer=self.customer, amount=Decimal("15"),
            created_by=self.owner, reason="Returned item",
        )
        cu = uuid.uuid4()
        op = {"op_type": "refund", "client_uuid": str(cu), "payload": {
            "credit_note": note.pk, "method": "cash", "amount": "15.00", "shift": shift.pk,
            "recorded_at": (timezone.now() - timedelta(minutes=5)).isoformat(),
        }}
        result = self._push_as(self.owner, [op]).data["results"][0]
        self.assertEqual(result["status"], "applied", result)
        self.assertIsNone(Refund.objects.get(client_uuid=cu).shift_id)
