"""
Till sessions and drawer reconciliation.

This is the control that makes cash accountable: every other money path names a
person, but notes in a drawer name nobody. These tests cover the arithmetic
(expected is derived, never stored), the boundaries (only cash counts, only your
own shift, one drawer per person), and the segregation of duties on sign-off.
"""

from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product, Warehouse
from org.models import Branch, Company
from sales.models import (
    CashDrawerMovement,
    CashShift,
    Customer,
    Invoice,
    Payment,
)


class CashShiftTestCase(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Shop")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.warehouse = Warehouse.objects.create(company=self.company, name="Store")
        self.product = Product.objects.create(
            company=self.company, sku="P1", name="Rice",
            sale_price=Decimal("100"),
        )
        self.customer = Customer.objects.create(company=self.company, name="C")

        self.cashier_role = Role.objects.create(
            name="Sales Officer", scope_level=Role.SCOPE_BRANCH
        )
        self.owner_role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        self.cashier = User.objects.create_user(
            email="cashier@shop.test", password="passw0rd12345",
            full_name="Zainab", company=self.company, role=self.cashier_role,
            branch=self.branch,
        )
        self.owner = User.objects.create_user(
            email="owner@shop.test", password="passw0rd12345",
            full_name="Omar", company=self.company, role=self.owner_role,
        )
        self.client.force_authenticate(self.cashier)

    def _open(self, float_amount="200"):
        return self.client.post(
            reverse("cashshift-list"),
            {"opening_float": float_amount, "branch": self.branch.id},
            format="json",
        )

    def _shift(self, float_amount="200"):
        return CashShift.objects.create(
            company=self.company, branch=self.branch, opened_by=self.cashier,
            opening_float=Decimal(float_amount),
        )

    def _sell(self, shift, amount="100", method="cash", number=1):
        """A completed till sale attached to a shift."""
        inv = Invoice.objects.create(
            company=self.company, customer=self.customer, branch=self.branch,
            warehouse=self.warehouse, number=number,
            subtotal=Decimal(amount), total=Decimal(amount),
        )
        return Payment.objects.create(
            company=self.company, invoice=inv, method=method,
            amount=Decimal(amount), shift=shift, recorded_by=self.cashier,
            **({} if method == "cash" else {
                "sender_bank_name": "X", "reference_last4": "1234"
            }),
        )


class OpenCloseTests(CashShiftTestCase):
    def test_cashier_can_open_a_shift(self):
        resp = self._open("200")
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["status"], "open")
        self.assertEqual(resp.data["opened_by_name"], "Zainab")
        self.assertEqual(resp.data["expected_cash"], "200.00")
        self.assertIsNone(resp.data["variance"])

    def test_only_one_open_shift_per_person(self):
        """Two open drawers would make every takings figure ambiguous."""
        self.assertEqual(self._open().status_code, 201)
        resp = self._open()
        self.assertEqual(resp.status_code, 400, resp.data)

    def test_a_second_person_can_open_their_own(self):
        self._open()
        self.client.force_authenticate(self.owner)
        resp = self._open("50")
        self.assertEqual(resp.status_code, 201, resp.data)

    def test_current_returns_the_callers_open_shift(self):
        opened = self._open().data["id"]
        resp = self.client.get(reverse("cashshift-current"))
        self.assertEqual(resp.data["id"], opened)

    def test_current_is_null_with_no_open_shift(self):
        resp = self.client.get(reverse("cashshift-current"))
        self.assertIsNone(resp.data["shift"])

    def test_current_does_not_leak_another_persons_drawer(self):
        self.client.force_authenticate(self.owner)
        self._open("999")
        self.client.force_authenticate(self.cashier)
        resp = self.client.get(reverse("cashshift-current"))
        self.assertIsNone(resp.data["shift"])

    def test_close_records_the_count(self):
        shift = self._shift("200")
        resp = self.client.post(
            reverse("cashshift-close", args=[shift.id]),
            {"counted_cash": "200"}, format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["status"], "closed")
        self.assertEqual(resp.data["counted_cash"], "200.00")
        self.assertEqual(resp.data["variance"], "0.00")
        self.assertEqual(resp.data["closed_by_name"], "Zainab")

    def test_close_requires_an_actual_count(self):
        """No default is offered: pre-filling the expected figure invites
        confirming it without counting."""
        shift = self._shift()
        resp = self.client.post(
            reverse("cashshift-close", args=[shift.id]), {}, format="json"
        )
        self.assertEqual(resp.status_code, 400, resp.data)
        shift.refresh_from_db()
        self.assertEqual(shift.status, CashShift.OPEN)

    def test_close_rejects_nonsense(self):
        shift = self._shift()
        for bad in ("abc", "-5"):
            resp = self.client.post(
                reverse("cashshift-close", args=[shift.id]),
                {"counted_cash": bad}, format="json",
            )
            self.assertEqual(resp.status_code, 400, f"{bad}: {resp.data}")

    def test_a_closed_shift_cannot_reopen(self):
        """Append-only: a miscount is corrected by a new entry, not by editing
        the record."""
        shift = self._shift()
        self.client.post(
            reverse("cashshift-close", args=[shift.id]),
            {"counted_cash": "200"}, format="json",
        )
        resp = self.client.post(
            reverse("cashshift-close", args=[shift.id]),
            {"counted_cash": "999"}, format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.data)
        shift.refresh_from_db()
        self.assertEqual(shift.counted_cash, Decimal("200"))

    def test_shifts_cannot_be_edited_or_deleted(self):
        shift = self._shift()
        url = reverse("cashshift-detail", args=[shift.id])
        self.assertEqual(self.client.patch(url, {"opening_float": "5"}).status_code, 405)
        self.assertEqual(self.client.delete(url).status_code, 405)


class ExpectedCashTests(CashShiftTestCase):
    def test_cash_sales_raise_the_expectation(self):
        shift = self._shift("200")
        self._sell(shift, "150", number=1)
        self._sell(shift, "50", number=2)
        self.assertEqual(shift.expected_cash(), Decimal("400"))

    def test_bank_transfers_never_touch_the_drawer(self):
        """Money that arrived in the bank must not be expected in the till."""
        shift = self._shift("200")
        self._sell(shift, "500", method="bank_transfer", number=1)
        self.assertEqual(shift.expected_cash(), Decimal("200"))
        self.assertEqual(shift.cash_sales(), Decimal("0"))

    def test_another_shifts_takings_are_not_counted(self):
        mine = self._shift("200")
        other = CashShift.objects.create(
            company=self.company, opened_by=self.owner, opening_float=Decimal("0")
        )
        self._sell(other, "1000", number=1)
        self.assertEqual(mine.expected_cash(), Decimal("200"))

    def test_payments_with_no_shift_are_ignored(self):
        """Office receipts and pre-shift history legitimately belong to none."""
        shift = self._shift("200")
        self._sell(None, "750", number=1)
        self.assertEqual(shift.expected_cash(), Decimal("200"))

    def test_variance_is_none_until_closed(self):
        self.assertIsNone(self._shift().variance())

    def test_shortfall_is_negative(self):
        shift = self._shift("200")
        self._sell(shift, "100", number=1)
        resp = self.client.post(
            reverse("cashshift-close", args=[shift.id]),
            {"counted_cash": "280"}, format="json",
        )
        self.assertEqual(resp.data["expected_cash"], "300.00")
        self.assertEqual(resp.data["variance"], "-20.00")

    def test_surplus_is_positive(self):
        shift = self._shift("200")
        resp = self.client.post(
            reverse("cashshift-close", args=[shift.id]),
            {"counted_cash": "215"}, format="json",
        )
        self.assertEqual(resp.data["variance"], "15.00")

    def test_money_amounts_are_uniformly_two_decimals(self):
        shift = self._shift("200")
        resp = self.client.get(reverse("cashshift-detail", args=[shift.id]))
        for field in ("cash_sales", "drawer_movements_total", "expected_cash"):
            self.assertRegex(resp.data[field], r"^-?\d+\.\d{2}$", field)


class DrawerMovementTests(CashShiftTestCase):
    def _move(self, shift, kind, amount, expect=201):
        resp = self.client.post(
            reverse("drawermovement-list"),
            {"shift": shift.id, "kind": kind, "amount": amount, "reason": "t"},
            format="json",
        )
        self.assertEqual(resp.status_code, expect, resp.data)
        return resp

    def test_a_refund_lowers_the_expectation(self):
        """Without this a walk-in refund hands money back with nothing recording
        it, and the drawer can never reconcile."""
        shift = self._shift("200")
        self._sell(shift, "100", number=1)
        self._move(shift, CashDrawerMovement.REFUND, "-40")
        self.assertEqual(shift.expected_cash(), Decimal("260"))

    def test_a_drop_to_the_safe_lowers_the_expectation(self):
        shift = self._shift("500")
        self._move(shift, CashDrawerMovement.DROP, "-300")
        self.assertEqual(shift.expected_cash(), Decimal("200"))

    def test_adding_a_float_raises_it(self):
        shift = self._shift("100")
        self._move(shift, CashDrawerMovement.FLOAT_ADD, "50")
        self.assertEqual(shift.expected_cash(), Decimal("150"))

    def test_a_refund_cannot_be_entered_as_positive(self):
        """The sign carries the meaning — a typo must not turn money out into
        money in and hide a shortfall."""
        shift = self._shift()
        self._move(shift, CashDrawerMovement.REFUND, "40", expect=400)

    def test_a_float_cannot_be_entered_as_negative(self):
        shift = self._shift()
        self._move(shift, CashDrawerMovement.FLOAT_ADD, "-40", expect=400)

    def test_zero_is_rejected(self):
        shift = self._shift()
        self._move(shift, CashDrawerMovement.CORRECTION, "0", expect=400)

    def test_a_correction_may_go_either_way(self):
        shift = self._shift("100")
        self._move(shift, CashDrawerMovement.CORRECTION, "-10")
        self._move(shift, CashDrawerMovement.CORRECTION, "5")
        self.assertEqual(shift.expected_cash(), Decimal("95"))

    def test_cash_cannot_move_in_a_closed_drawer(self):
        shift = self._shift()
        self.client.post(
            reverse("cashshift-close", args=[shift.id]),
            {"counted_cash": "200"}, format="json",
        )
        self._move(shift, CashDrawerMovement.DROP, "-10", expect=400)

    def test_movements_cannot_reach_another_company(self):
        other = Company.objects.create(name="Beta")
        other_user = User.objects.create_user(
            email="x@beta.test", password="passw0rd12345",
            company=other, role=self.owner_role,
        )
        foreign = CashShift.objects.create(
            company=other, opened_by=other_user, opening_float=Decimal("0")
        )
        self._move(foreign, CashDrawerMovement.DROP, "-10", expect=400)

    def test_movements_are_append_only(self):
        shift = self._shift()
        mid = self._move(shift, CashDrawerMovement.DROP, "-10").data["id"]
        url = reverse("drawermovement-detail", args=[mid])
        self.assertEqual(self.client.patch(url, {"amount": "-1"}).status_code, 405)
        self.assertEqual(self.client.delete(url).status_code, 405)


class ReviewTests(CashShiftTestCase):
    def _closed_shift(self, counted="200", by=None):
        shift = self._shift("200")
        self.client.force_authenticate(by or self.cashier)
        self.client.post(
            reverse("cashshift-close", args=[shift.id]),
            {"counted_cash": counted}, format="json",
        )
        shift.refresh_from_db()
        return shift

    def test_manager_can_sign_off(self):
        shift = self._closed_shift()
        self.client.force_authenticate(self.owner)
        resp = self.client.post(reverse("cashshift-review", args=[shift.id]))
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["reviewed_by_name"], "Omar")

    def test_the_person_who_counted_cannot_sign_off(self):
        """Same principle as payment verification: a count with no independent
        witness is not a control."""
        shift = self._closed_shift()
        self.client.force_authenticate(self.cashier)
        resp = self.client.post(reverse("cashshift-review", args=[shift.id]))
        self.assertEqual(resp.status_code, 403, resp.data)

    def test_a_cashier_cannot_sign_off_someone_elses_either(self):
        shift = self._closed_shift()
        other_cashier = User.objects.create_user(
            email="c2@shop.test", password="passw0rd12345",
            company=self.company, role=self.cashier_role, branch=self.branch,
        )
        self.client.force_authenticate(other_cashier)
        resp = self.client.post(reverse("cashshift-review", args=[shift.id]))
        self.assertEqual(resp.status_code, 403, resp.data)

    def test_an_open_shift_cannot_be_reviewed(self):
        shift = self._shift()
        self.client.force_authenticate(self.owner)
        resp = self.client.post(reverse("cashshift-review", args=[shift.id]))
        self.assertEqual(resp.status_code, 400, resp.data)

    def test_review_happens_once(self):
        shift = self._closed_shift()
        self.client.force_authenticate(self.owner)
        self.client.post(reverse("cashshift-review", args=[shift.id]))
        resp = self.client.post(reverse("cashshift-review", args=[shift.id]))
        self.assertEqual(resp.status_code, 400, resp.data)


class ScopingAndAuditTests(CashShiftTestCase):
    def test_shifts_are_company_scoped(self):
        other = Company.objects.create(name="Beta")
        other_user = User.objects.create_user(
            email="y@beta.test", password="passw0rd12345",
            company=other, role=self.owner_role,
        )
        CashShift.objects.create(
            company=other, opened_by=other_user, opening_float=Decimal("50")
        )
        self._shift("200")
        resp = self.client.get(reverse("cashshift-list"))
        self.assertEqual(len(resp.data["results"]), 1)
        self.assertEqual(resp.data["results"][0]["opening_float"], "200.00")

    def test_closing_writes_the_variance_to_the_audit_log(self):
        """The owner must be able to see a shortfall after the fact."""
        from core.models import ActivityLog

        shift = self._shift("200")
        self.client.post(
            reverse("cashshift-close", args=[shift.id]),
            {"counted_cash": "180"}, format="json",
        )
        log = ActivityLog.objects.filter(
            entity_type="CashShift", entity_id=str(shift.pk)
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.metadata["variance"], "-20.00")
        self.assertEqual(log.metadata["counted"], "180")

    def test_a_role_without_sales_cannot_touch_the_till(self):
        hr_role = Role.objects.create(name="HR Officer", scope_level=Role.SCOPE_BRANCH)
        hr = User.objects.create_user(
            email="hr@shop.test", password="passw0rd12345",
            company=self.company, role=hr_role,
        )
        self.client.force_authenticate(hr)
        self.assertEqual(self.client.get(reverse("cashshift-list")).status_code, 403)
        self.assertEqual(self._open().status_code, 403)


class PosIntegrationTests(CashShiftTestCase):
    def test_a_till_sale_lands_in_the_open_drawer(self):
        shift = self._shift("100")
        resp = self.client.post(
            reverse("pos-checkout"),
            {
                "warehouse": self.warehouse.id,
                "shift": shift.id,
                "lines": [{"product": self.product.id, "quantity": "2"}],
                "payment": {"method": "cash", "amount": "200"},
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        payment = Payment.objects.get(invoice_id=resp.data["id"])
        self.assertEqual(payment.shift_id, shift.id)
        self.assertEqual(shift.expected_cash(), Decimal("300"))

    def test_a_sale_without_a_shift_still_works(self):
        """Shifts must stay optional — an existing deployment that never opens
        one cannot be blocked from selling."""
        resp = self.client.post(
            reverse("pos-checkout"),
            {
                "warehouse": self.warehouse.id,
                "lines": [{"product": self.product.id, "quantity": "1"}],
                "payment": {"method": "cash", "amount": "100"},
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertIsNone(Payment.objects.get(invoice_id=resp.data["id"]).shift_id)

    def test_a_sale_cannot_be_rung_into_a_closed_drawer(self):
        shift = self._shift("100")
        self.client.post(
            reverse("cashshift-close", args=[shift.id]),
            {"counted_cash": "100"}, format="json",
        )
        resp = self.client.post(
            reverse("pos-checkout"),
            {
                "warehouse": self.warehouse.id,
                "shift": shift.id,
                "lines": [{"product": self.product.id, "quantity": "1"}],
                "payment": {"method": "cash", "amount": "100"},
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.data)

    def test_a_sale_cannot_be_rung_into_another_companys_drawer(self):
        other = Company.objects.create(name="Beta")
        other_user = User.objects.create_user(
            email="z@beta.test", password="passw0rd12345",
            company=other, role=self.owner_role,
        )
        foreign = CashShift.objects.create(
            company=other, opened_by=other_user, opening_float=Decimal("0")
        )
        resp = self.client.post(
            reverse("pos-checkout"),
            {
                "warehouse": self.warehouse.id,
                "shift": foreign.id,
                "lines": [{"product": self.product.id, "quantity": "1"}],
                "payment": {"method": "cash", "amount": "100"},
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.data)
