"""Security review 2 (2026-09-28): the offline queue must not be a way
around a suspension, a read-only subscription, the till's price rule, the
plan's modules, or the tenant wall."""

import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User
from core.models import ActivityLog
from integration.base import IntegrationBase
from sales.models import Customer, Invoice
from subscriptions.models import Plan, PlanVersion, Subscription
from sync.models import DiscardedOperation

PW = "passw0rd123"


class SyncSecurityBase(IntegrationBase):
    def setUp(self):
        cache.clear()
        call_command("seed_roles", verbosity=0)
        self.A = self.make_company("Alpha")
        self.B = self.make_company("Beta")
        now = timezone.now()
        plan = Plan.objects.create(code="all", name="All")
        self.pv_all = PlanVersion.objects.create(
            plan=plan, version=1, modules=["*"], published_at=now
        )
        for company in (self.A, self.B):
            Subscription.objects.create(
                company=company, plan_version=self.pv_all, status=Subscription.ACTIVE,
                starts_at=now - timedelta(days=60), period_ends_at=now + timedelta(days=30),
            )
        self.whA = self.warehouse(self.A)
        self.pA = self.product(self.A, sku="A-1", cost="40", price="100")
        self.pB = self.product(self.B, sku="SECRET-B-SKU", cost="40", price="100")
        self.custA = Customer.objects.create(company=self.A, name="CA")

        def role(name):
            return Role.objects.get(name=name)

        self.make_user(self.A, role("Business Owner"), "owner@a.test")
        self.make_user(self.A, role("Sales Officer"), "cash@a.test")
        self.make_user(self.A, role("Viewer"), "view@a.test")
        self.root = User.objects.create_superuser("root@vezano.test", PW)

    def sale(self, **extra):
        payload = {
            "warehouse": self.whA.pk, "customer": self.custA.pk,
            "lines": [{"product": self.pA.pk, "quantity": "1", "unit_price": "100.00"}],
            "payment": {"method": "cash", "amount": "100.00"},
        }
        payload.update(extra.pop("payload", {}))
        op = {"op_type": "pos_checkout", "client_uuid": str(uuid.uuid4()), "payload": payload}
        op.update(extra)
        return op

    def push(self, client, ops):
        return client.post(
            reverse("sync-push"), {"batch_uuid": str(uuid.uuid4()), "operations": ops},
            format="json",
        )

    @staticmethod
    def ago(**delta):
        return (timezone.now() - timedelta(**delta)).isoformat()


class SuspendedCompanyTests(SyncSecurityBase):
    def _suspend(self, since=None):
        from subscriptions.tenant_controls import suspend_until_payment

        suspend_until_payment(self.A, self.root, "unpaid")
        if since is not None:
            Subscription.objects.filter(company=self.A).update(suspended_at=since)

    def _result(self, client, op):
        response = self.push(client, [op])
        self.assertEqual(response.status_code, 201, response.data)
        return response.data["results"][0]

    def test_a_sale_dated_past_the_backdate_limit_is_refused(self):
        client = self.client_for("cash@a.test")
        self._suspend()
        result = self._result(client, self.sale(payload={"occurred_at": self.ago(days=40)}))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_field"], "subscription")
        self.assertEqual(Invoice.objects.filter(company=self.A).count(), 0)

    def test_a_sale_with_only_a_queue_time_is_refused(self):
        client = self.client_for("cash@a.test")
        self._suspend()
        queued = int((timezone.now() - timedelta(days=1)).timestamp() * 1000)
        result = self._result(client, self.sale(queued_at=queued))
        self.assertEqual(result["status"], "error")
        self.assertEqual(Invoice.objects.filter(company=self.A).count(), 0)

    def test_an_invented_clock_offset_cannot_move_a_new_sale_into_the_past(self):
        client = self.client_for("cash@a.test")
        self._suspend()
        result = self._result(client, self.sale(
            payload={"occurred_at": timezone.now().isoformat()},
            clock_offset_ms=-2 * 86400 * 1000,
        ))
        self.assertEqual(result["status"], "error")

    def test_a_sale_after_the_suspension_is_refused(self):
        client = self.client_for("cash@a.test")
        self._suspend(since=timezone.now() - timedelta(hours=2))
        result = self._result(client, self.sale(payload={"occurred_at": self.ago(hours=1)}))
        self.assertEqual(result["status"], "error")

    def test_a_sale_captured_before_the_suspension_still_uploads_in_the_window(self):
        client = self.client_for("cash@a.test")
        self._suspend(since=timezone.now() - timedelta(hours=10))
        result = self._result(client, self.sale(payload={"occurred_at": self.ago(hours=12)}))
        self.assertEqual(result["status"], "applied", result)

    @override_settings(VEZANO_LOCKED_SYNC_WINDOW_HOURS=72)
    def test_past_the_window_nothing_uploads(self):
        client = self.client_for("cash@a.test")
        self._suspend(since=timezone.now() - timedelta(hours=73))
        result = self._result(client, self.sale(payload={"occurred_at": self.ago(hours=80)}))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_field"], "subscription")

    def test_normal_company_keeps_settling_old_times(self):
        client = self.client_for("cash@a.test")
        result = self._result(client, self.sale(payload={"occurred_at": self.ago(days=40)}))
        self.assertEqual(result["status"], "applied", result)


@override_settings(SUBSCRIPTION_POLICY="enforce")
class ReadOnlyCompanyTests(SyncSecurityBase):
    def _lapse(self, grace_ended):
        now = timezone.now()
        Subscription.objects.filter(company=self.A).update(
            period_ends_at=grace_ended - timedelta(days=7), grace_ends_at=grace_ended,
        )
        return now

    def test_live_checkout_is_refused_and_a_backdated_sale_too(self):
        now = self._lapse(timezone.now() - timedelta(days=3))
        client = self.client_for("cash@a.test")
        live = client.post(reverse("pos-checkout"), self.sale()["payload"], format="json")
        self.assertEqual(live.status_code, 403)
        response = self.push(client, [self.sale(payload={
            "occurred_at": (now - timedelta(days=40)).isoformat(),
        })])
        self.assertEqual(response.data["results"][0]["status"], "error")

    def test_before_the_lapse_but_past_the_window_is_refused(self):
        self._lapse(timezone.now() - timedelta(days=4))
        client = self.client_for("cash@a.test")
        response = self.push(client, [self.sale(payload={"occurred_at": self.ago(days=5)})])
        self.assertEqual(response.data["results"][0]["status"], "error")

    def test_before_the_lapse_within_the_window_uploads(self):
        self._lapse(timezone.now() - timedelta(days=1))
        client = self.client_for("cash@a.test")
        response = self.push(client, [self.sale(payload={"occurred_at": self.ago(days=2)})])
        self.assertEqual(response.data["results"][0]["status"], "applied", response.data)


class PriceRuleThroughSyncTests(SyncSecurityBase):
    def cheap(self, **payload):
        body = {
            "lines": [{"product": self.pA.pk, "quantity": "1", "unit_price": "41.00"}],
            "payment": {"method": "cash", "amount": "41.00"},
        }
        body.update(payload)
        return self.sale(payload=body)

    def test_a_discount_past_the_limit_pushed_while_online_is_refused(self):
        client = self.client_for("cash@a.test")
        live = client.post(reverse("pos-checkout"), self.cheap()["payload"], format="json")
        self.assertEqual(live.status_code, 400)
        result = self.push(client, [self.cheap()]).data["results"][0]
        self.assertEqual(result["status"], "error")
        result = self.push(client, [self.cheap(occurred_at=timezone.now().isoformat())])
        self.assertEqual(result.data["results"][0]["status"], "error")
        self.assertEqual(Invoice.objects.filter(company=self.A).count(), 0)

    def test_below_cost_pushed_while_online_is_refused(self):
        client = self.client_for("cash@a.test")
        op = self.sale(payload={
            "lines": [{"product": self.pA.pk, "quantity": "5", "unit_price": "0.01"}],
            "payment": {"method": "cash", "amount": "0.05"},
            "occurred_at": timezone.now().isoformat(),
        })
        self.assertEqual(self.push(client, [op]).data["results"][0]["status"], "error")

    def test_a_sale_captured_while_the_till_was_offline_is_kept_and_flagged(self):
        client = self.client_for("cash@a.test")
        # Two hours ago the device had not talked to the server at all.
        result = self.push(client, [self.cheap(occurred_at=self.ago(hours=2))])
        result = result.data["results"][0]
        self.assertEqual(result["status"], "applied", result)
        self.assertEqual(Invoice.objects.get(pk=result["id"]).total, Decimal("41.00"))
        flag = ActivityLog.objects.get(action="pos_price_unapproved")
        self.assertTrue(flag.metadata["needs_review"])


@override_settings(SUBSCRIPTION_POLICY="enforce")
class PlanModuleTests(SyncSecurityBase):
    def setUp(self):
        super().setUp()
        version = PlanVersion.objects.create(
            plan=self.pv_all.plan, version=2, modules=["sales", "inventory"],
            published_at=timezone.now(),
        )
        Subscription.objects.filter(company=self.A).update(plan_version=version)

    def test_a_module_outside_the_plan_is_refused_on_push(self):
        supplier = self.supplier(self.A)
        client = self.client_for("owner@a.test")
        payload = {
            "supplier": supplier.pk, "warehouse": self.whA.pk,
            "lines": [{"product": self.pA.pk, "quantity": "3", "unit_cost": "40"}],
        }
        self.assertEqual(
            client.post(reverse("receiving-create"), payload, format="json").status_code, 403
        )
        response = self.push(client, [{
            "op_type": "goods_receipt", "client_uuid": str(uuid.uuid4()), "payload": payload,
        }, self.sale()])
        receipt, sale = response.data["results"]
        self.assertEqual(receipt["status"], "error")
        self.assertEqual(receipt["error_field"], "subscription")
        self.assertEqual(sale["status"], "applied", sale)

    def test_pull_leaves_out_modules_outside_the_plan(self):
        client = self.client_for("owner@a.test")
        changes = client.get(reverse("sync-pull")).data["changes"]
        for key in ("suppliers", "purchase_orders", "bills", "employees"):
            self.assertNotIn(key, changes)
        self.assertIn("products", changes)
        self.assertIn("invoices", changes)


class TenantAndRoleTests(SyncSecurityBase):
    def test_a_receipt_error_never_names_another_company_sku(self):
        client = self.client_for("owner@a.test")
        supplier = self.supplier(self.A)
        yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
        payload = {
            "supplier": supplier.pk, "warehouse": self.whA.pk,
            "lines": [{"product": self.pB.pk, "quantity": "1", "expiry_date": yesterday}],
        }
        result = self.push(client, [{
            "op_type": "goods_receipt", "client_uuid": str(uuid.uuid4()), "payload": payload,
        }]).data["results"][0]
        self.assertEqual(result["status"], "error")
        self.assertNotIn("SECRET-B-SKU", result["error"])
        live = client.post(reverse("receiving-create"), payload, format="json")
        self.assertEqual(live.status_code, 400)
        self.assertNotIn("SECRET-B-SKU", str(live.data))

    def test_a_viewer_cannot_file_a_discard(self):
        client = self.client_for("view@a.test")
        response = client.post(reverse("sync-discard"), {
            "client_uuid": str(uuid.uuid4()), "op_type": "pos_checkout",
            "payload": {"x": 1}, "reason": "gave up",
        }, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(DiscardedOperation.objects.exists())

    def test_a_cashier_can_discard_a_sale_but_not_an_unknown_op(self):
        client = self.client_for("cash@a.test")
        ok = client.post(reverse("sync-discard"), {
            "client_uuid": str(uuid.uuid4()), "op_type": "pos_checkout",
            "payload": {"x": 1}, "reason": "gave up",
        }, format="json")
        self.assertEqual(ok.status_code, 201, ok.data)
        unknown = client.post(reverse("sync-discard"), {
            "client_uuid": str(uuid.uuid4()), "op_type": "nonsense",
            "payload": {"x": 1}, "reason": "gave up",
        }, format="json")
        self.assertEqual(unknown.status_code, 400)
