import uuid
from decimal import Decimal

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product, StockMovement, Warehouse
from org.models import Branch, Company
from sales.models import Invoice
from sync.models import SyncBatch


class SyncBase(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.owner_role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        self.user = User.objects.create_user(
            email="a@alpha.test",
            password="passw0rd123",
            company=self.company,
            role=self.owner_role,
        )
        self.wh = Warehouse.objects.create(
            company=self.company, branch=self.branch, name="Main"
        )
        self.product = Product.objects.create(
            company=self.company,
            sku="SKU1",
            name="Widget",
            sale_price=Decimal("10"),
        )
        r = self.client.post(
            reverse("auth-login"), {
                "email": "a@alpha.test",
                "password": "passw0rd123",
                "device_id": "TEST",
            }
        )
        assert r.status_code == 200, r.content

    def push(self, operations, batch_uuid=None):
        return self.client.post(
            reverse("sync-push"),
            {
                "device_id": "dev-1",
                "batch_uuid": str(batch_uuid or uuid.uuid4()),
                "operations": operations,
            },
            format="json",
        )

    def movement_op(self, cu, qty="5"):
        return {
            "op_type": "stock_movement",
            "client_uuid": str(cu),
            "payload": {
                "product": self.product.id,
                "warehouse": self.wh.id,
                "movement_type": "adjustment",
                "quantity": qty,
            },
        }

    def checkout_op(self, cu):
        return {
            "op_type": "pos_checkout",
            "client_uuid": str(cu),
            "payload": {
                "client_uuid": str(cu),
                "warehouse": self.wh.id,
                "lines": [{"product": self.product.id, "quantity": "2"}],
                "payment": {"method": "cash", "amount": "20.00"},
            },
        }


class BatchApplyTests(SyncBase):
    def test_batch_applies_each_operation_once(self):
        resp = self.push(
            [self.movement_op(uuid.uuid4()), self.checkout_op(uuid.uuid4())]
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertEqual(resp.data["summary"]["applied"], 2)
        self.assertEqual(
            StockMovement.objects.filter(movement_type="adjustment").count(), 1
        )
        self.assertEqual(Invoice.objects.count(), 1)

    def test_replaying_whole_batch_is_noop(self):
        bu = uuid.uuid4()
        ops = [self.movement_op(uuid.uuid4())]
        r1 = self.push(ops, batch_uuid=bu)
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        r2 = self.push(ops, batch_uuid=bu)
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertTrue(r2.data["replay"])
        self.assertEqual(SyncBatch.objects.count(), 1)
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_completed_batch_can_replay_after_commercial_writes_are_locked(self):
        batch_uuid = uuid.uuid4()
        operations = [self.movement_op(uuid.uuid4())]
        first = self.push(operations, batch_uuid=batch_uuid)
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        with override_settings(SUBSCRIPTION_POLICY="enforce"):
            replay = self.push(operations, batch_uuid=batch_uuid)
            blocked = self.push([self.movement_op(uuid.uuid4())])
        self.assertEqual(replay.status_code, status.HTTP_200_OK)
        self.assertTrue(replay.data["replay"])
        self.assertEqual(blocked.status_code, status.HTTP_403_FORBIDDEN)

    def test_same_op_uuid_in_new_batch_is_duplicate(self):
        cu = uuid.uuid4()
        self.push([self.movement_op(cu)])
        resp = self.push([self.movement_op(cu)])  # new batch, same op uuid
        self.assertEqual(resp.data["summary"]["duplicate"], 1)
        self.assertEqual(resp.data["summary"]["applied"], 0)
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_partial_failure_isolated(self):
        good = self.movement_op(uuid.uuid4())
        bad = {
            "op_type": "stock_movement",
            "client_uuid": str(uuid.uuid4()),
            "payload": {  # a documented type may not be posted raw -> error
                "product": self.product.id,
                "warehouse": self.wh.id,
                "movement_type": "purchase_in",
                "quantity": "5",
            },
        }
        resp = self.push([good, bad])
        self.assertEqual(resp.data["summary"]["applied"], 1)
        self.assertEqual(resp.data["summary"]["error"], 1)
        # The good op still committed despite the bad one.
        self.assertEqual(StockMovement.objects.count(), 1)
        results = {r["index"]: r["status"] for r in resp.data["results"]}
        self.assertEqual(results[0], "applied")
        self.assertEqual(results[1], "error")

    def test_unknown_op_type_errors(self):
        operation_id = str(uuid.uuid4())
        resp = self.push(
            [
                {
                    "op_type": "nonsense",
                    "client_uuid": operation_id,
                    "payload": {"client_uuid": operation_id},
                }
            ]
        )
        self.assertEqual(resp.data["results"][0]["status"], "error")


class SyncRBACTests(SyncBase):
    def test_role_without_module_access_op_forbidden(self):
        # An Inventory Officer may not push a POS checkout (sales write).
        inv_role = Role.objects.create(
            name="Inventory Officer", scope_level=Role.SCOPE_BRANCH
        )
        User.objects.create_user(
            email="inv@alpha.test",
            password="passw0rd123",
            company=self.company,
            branch=self.branch,
            role=inv_role,
        )
        c = self.client_class()
        c.post(
            reverse("auth-login"),
            {"email": "inv@alpha.test", "password": "passw0rd123", "device_id": "TEST"},
        )
        resp = c.post(
            reverse("sync-push"),
            {
                "batch_uuid": str(uuid.uuid4()),
                "operations": [self.checkout_op(uuid.uuid4())],
            },
            format="json",
        )
        self.assertEqual(resp.data["results"][0]["status"], "error")
        self.assertEqual(Invoice.objects.count(), 0)


class SyncPullTests(SyncBase):
    def test_pull_returns_changes_for_readable_modules(self):
        resp = self.client.get(reverse("sync-pull"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("cursor", resp.data)
        self.assertIn("products", resp.data["changes"])
        # Product created in setUp shows up.
        skus = {p["sku"] for p in resp.data["changes"]["products"]}
        self.assertIn("SKU1", skus)

    def test_pull_since_future_returns_empty(self):
        resp = self.client.get(reverse("sync-pull"), {"since": "2999-01-01T00:00:00Z"})
        self.assertEqual(resp.data["changes"]["products"], [])

    def test_missing_batch_uuid_rejected(self):
        resp = self.client.post(reverse("sync-push"), {"operations": []}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class QueuedRefundTests(SyncBase):
    """A refund recorded offline applies through the same serializer as the
    live endpoint — including the drawer movement it writes."""

    def test_queued_cash_refund_applies_with_drawer_movement(self):
        from returns.models import CreditNote
        from sales.models import CashShift, Customer, Invoice, Payment, Refund

        customer = Customer.objects.create(company=self.company, name="Buyer")
        invoice = Invoice.objects.create(
            company=self.company, branch=self.branch, warehouse=self.wh, customer=customer,
            number=1, subtotal=Decimal("40"), total=Decimal("40"),
        )
        # Paid in full, so the credit note below is money the customer can
        # actually take back (an unpaid sale's note only settles the debt).
        Payment.objects.create(
            company=self.company, invoice=invoice, method="cash", amount=Decimal("40"),
            recorded_by=self.user,
        )
        note = CreditNote.objects.create(
            company=self.company, customer=customer, invoice=invoice, amount=Decimal("15"),
            created_by=self.user, number=1,
        )
        shift = CashShift.objects.create(
            company=self.company, branch=self.branch, opened_by=self.user,
            opening_float=Decimal("100"),
        )
        cu = uuid.uuid4()
        response = self.push([{
            "op_type": "refund",
            "client_uuid": str(cu),
            "payload": {
                "client_uuid": str(cu), "credit_note": note.id, "method": "cash",
                "amount": "15.00", "shift": shift.id,
            },
        }])
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["summary"]["applied"], 1, response.data)
        refund = Refund.objects.get(client_uuid=cu)
        self.assertEqual(refund.amount, Decimal("15.00"))
        self.assertEqual(refund.recorded_by, self.user)
        self.assertEqual(shift.drawer_movements.count(), 1)
        self.assertEqual(shift.drawer_movements.get().amount, Decimal("-15.00"))


class QueuedAttendanceTests(SyncBase):
    def test_attendance_marked_twice_offline_lands_as_one_row(self):
        from hr.models import Attendance, Employee

        employee = Employee.objects.create(company=self.company, full_name="Sara", status="active")
        ops = [
            {"op_type": "attendance", "client_uuid": str(uuid.uuid4()),
             "payload": {"employee": employee.id, "date": "2026-09-18", "status": "present"}},
            {"op_type": "attendance", "client_uuid": str(uuid.uuid4()),
             "payload": {"employee": employee.id, "date": "2026-09-18", "status": "half_day",
                         "check_in": "08:30"}},
        ]
        response = self.push(ops)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["summary"]["applied"], 2, response.data)
        rows = Attendance.objects.filter(employee=employee, date="2026-09-18")
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.get().status, "half_day")
        self.assertEqual(str(rows.get().check_in), "08:30:00")


class LateAttendanceMarkTests(SyncBase):
    """An old offline mark synced late must not undo a newer HR correction:
    last writer wins by when the mark was taken, not when it arrived. The
    clock: now is 11:00, HR corrected the day at 10:00."""

    def setUp(self):
        super().setUp()
        from datetime import timedelta

        from django.utils import timezone

        from hr.models import Attendance, Employee

        self.now = timezone.now()
        self.at = lambda hours: self.now - timedelta(hours=hours)
        self.employee = Employee.objects.create(
            company=self.company, full_name="Sara", status="active"
        )
        self.row = Attendance.objects.create(
            company=self.company, employee=self.employee, date="2026-09-18", status="present",
        )
        # HR's live correction to "absent", made at 10:00.
        response = self.client.patch(
            reverse("attendance-detail", args=[self.row.pk]), {"status": "absent"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.row.refresh_from_db()
        self.assertGreaterEqual(self.row.recorded_at, self.now)
        Attendance.objects.filter(pk=self.row.pk).update(recorded_at=self.at(1))

    def mark(self, taken_at):
        return self.push([{
            "op_type": "attendance", "client_uuid": str(uuid.uuid4()),
            "payload": {"employee": self.employee.id, "date": "2026-09-18",
                        "status": "present", "recorded_at": taken_at.isoformat()},
        }])

    def test_mark_taken_before_the_correction_leaves_it_standing(self):
        response = self.mark(self.at(2))  # taken 09:00, synced 11:00
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["summary"]["duplicate"], 1, response.data)
        self.assertEqual(response.data["summary"]["error"], 0, response.data)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, "absent")
        self.assertEqual(self.row.recorded_at, self.at(1))

    def test_mark_taken_after_the_correction_applies(self):
        response = self.mark(self.at(0.5))  # taken 10:30, synced 11:00
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["summary"]["applied"], 1, response.data)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, "present")
        self.assertEqual(self.row.recorded_at, self.at(0.5))

    def test_a_mark_stamped_in_the_future_counts_as_now(self):
        from datetime import timedelta

        self.mark(self.now + timedelta(days=1))
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, "present")
        self.assertLess(self.row.recorded_at, self.now + timedelta(minutes=5))

    def test_row_from_before_recorded_at_existed_is_dated_by_its_creation(self):
        from hr.models import Attendance

        Attendance.objects.filter(pk=self.row.pk).update(recorded_at=None, created_at=self.at(1))
        self.assertEqual(self.mark(self.at(2)).data["summary"]["duplicate"], 1)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, "absent")
        self.assertEqual(self.mark(self.at(0.5)).data["summary"]["applied"], 1)

    def test_live_mark_ignores_a_client_stamp(self):
        # Online writes happen now; a stale device clock cannot backdate one.
        response = self.client.post(
            reverse("attendance-list"),
            {"employee": self.employee.id, "date": "2026-09-18", "status": "half_day",
             "recorded_at": self.at(5).isoformat()},
            format="json",
        )
        self.assertIn(response.status_code, (200, 201), response.data)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, "half_day")
        self.assertGreaterEqual(self.row.recorded_at, self.now)


class PullWideningTests(SyncBase):
    def test_pull_includes_orders_bills_employees_and_caps_old_invoices(self):
        from datetime import timedelta

        from django.utils import timezone

        from hr.models import Employee
        from purchasing.models import Bill, PurchaseOrder, Supplier
        from sales.models import Invoice

        supplier = Supplier.objects.create(company=self.company, name="Acme")
        PurchaseOrder.objects.create(company=self.company, supplier=supplier)
        Bill.objects.create(company=self.company, supplier=supplier, subtotal=1, total=1)
        Employee.objects.create(company=self.company, full_name="Sara", status="active")
        old = Invoice.objects.create(
            company=self.company, branch=self.branch, warehouse=self.wh, number=1,
            subtotal=1, total=1,
        )
        Invoice.objects.filter(pk=old.pk).update(received_at=timezone.now() - timedelta(days=200))
        Invoice.objects.create(
            company=self.company, branch=self.branch, warehouse=self.wh, number=2,
            subtotal=1, total=1,
        )
        response = self.client.get(reverse("sync-pull"))
        self.assertEqual(response.status_code, 200)
        changes = response.data["changes"]
        self.assertEqual(len(changes["purchase_orders"]), 1)
        self.assertEqual(len(changes["bills"]), 1)
        self.assertEqual(len(changes["employees"]), 1)
        self.assertEqual([i["number"] for i in changes["invoices"]], [2])


class ErrorTextTests(SyncBase):
    def test_validation_errors_read_as_sentences(self):
        from sync.services import _stringify
        from rest_framework.exceptions import ErrorDetail

        detail = {
            "employee": [
                ErrorDetail('Invalid pk "2" - object does not exist.', code="does_not_exist")
            ],
            "non_field_errors": [ErrorDetail("Amount must be positive.", code="invalid")],
        }
        text = _stringify(detail)
        self.assertEqual(text, 'Invalid pk "2" - object does not exist. · Amount must be positive.')
        self.assertNotIn("ErrorDetail", text)
        self.assertNotIn("employee", text)
