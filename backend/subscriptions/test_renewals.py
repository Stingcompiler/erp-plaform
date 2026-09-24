from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Role, User
from org.models import Company
from subscriptions.models import (
    Plan,
    PlanVersion,
    Subscription,
    SubscriptionEvent,
    SubscriptionInvoice,
    SubscriptionPayment,
)
from subscriptions.renewals import add_months, plan_renewal

KHARTOUM = ZoneInfo("Africa/Khartoum")


def end_of(day):
    return timezone.make_aware(datetime.combine(day, time.max), KHARTOUM)


class RenewOnApprovalTests(APITestCase):
    """A company pays without an invoice; approving the payment renews."""

    def setUp(self):
        owner_role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.company = Company.objects.create(name="nwafih", timezone="Africa/Khartoum")
        self.owner = User.objects.create_user(
            email="owner@nwafih.test", password="long-password",
            company=self.company, role=owner_role,
        )
        self.admin = User.objects.create_superuser(
            email="platform@renew.test", password="long-password"
        )
        plan = Plan.objects.create(code="business", name="business")
        self.version = PlanVersion.objects.create(
            plan=plan, version=3, currency="SDG", price=Decimal("500000.00"),
            billing_cycle=PlanVersion.MONTHLY, modules=["*"], limits={"devices": 2},
            addon_prices={"devices": "20000"}, published_at=timezone.now(),
        )
        self.now = timezone.now()
        self.trial_end = self.now + timedelta(days=11)
        self.subscription = Subscription.objects.create(
            company=self.company, plan_version=self.version, status=Subscription.TRIALING,
            starts_at=self.now - timedelta(days=3), trial_ends_at=self.trial_end,
        )

    def _pay(self, amount="500000.00", currency="SDG", method="cash"):
        return SubscriptionPayment.objects.create(
            company=self.company, amount=Decimal(amount), currency=currency, method=method,
            recorded_by=self.owner,
        )

    def _preview(self, payment):
        self.client.force_authenticate(self.admin)
        response = self.client.get(
            reverse("platform-subscription-payment-renewal", args=[payment.pk])
        )
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def _renew(self, payment, expected=None):
        self.client.force_authenticate(self.admin)
        body = {} if expected is None else {"expected": expected}
        return self.client.post(
            reverse("platform-subscription-payment-renew", args=[payment.pk]), body,
            format="json",
        )

    def test_trial_payment_without_invoice_renews_after_the_trial(self):
        payment = self._pay()
        preview = self._preview(payment)
        first_day = timezone.localtime(self.trial_end, KHARTOUM).date() + timedelta(days=1)
        last_day = add_months(first_day, 1) - timedelta(days=1)
        self.assertTrue(preview["ok"])
        self.assertEqual(len(preview["steps"]), 1)
        step = preview["steps"][0]
        self.assertIsNone(step["invoice_id"])
        self.assertEqual(step["period_start"], first_day.isoformat())
        self.assertEqual(step["period_end"], last_day.isoformat())
        self.assertTrue(step["completes"])
        self.assertEqual(preview["status_after"], Subscription.ACTIVE)

        response = self._renew(payment, preview["key"])
        self.assertEqual(response.status_code, 200, response.data)
        payment.refresh_from_db()
        self.subscription.refresh_from_db()
        self.assertEqual(payment.status, SubscriptionPayment.VERIFIED)
        invoice = SubscriptionInvoice.objects.get(company=self.company)
        self.assertEqual(invoice.status, SubscriptionInvoice.PAID)
        self.assertRegex(invoice.number, r"^VSUB-\d{6}$")
        self.assertEqual(invoice.amount, Decimal("500000.00"))
        self.assertEqual(invoice.line_snapshot[0]["kind"], "renewal")
        self.assertEqual((invoice.period_start, invoice.period_end), (first_day, last_day))
        self.assertIsNotNone(invoice.entitlement_granted_at)
        self.assertEqual(self.subscription.status, Subscription.ACTIVE)
        # The company's end of day, not UTC's, although the admin has no company.
        self.assertEqual(self.subscription.period_ends_at, end_of(last_day))
        self.assertGreater(self.subscription.period_ends_at, self.trial_end)
        self.assertTrue(
            SubscriptionEvent.objects.filter(
                subscription=self.subscription, event_type="payment_renewed"
            ).exists()
        )
        # The owner sees what the payment bought.
        self.client.force_authenticate(self.owner)
        mine = self.client.get(reverse("company-subscription")).data
        self.assertEqual(mine["payments"][0]["allocations"][0]["invoice_number"], invoice.number)
        self.assertEqual(
            mine["subscription"]["next_renewal"]["period_start"],
            (last_day + timedelta(days=1)).isoformat(),
        )

    def test_replayed_approval_grants_once(self):
        payment = self._pay()
        self.assertEqual(self._renew(payment).status_code, 200)
        self.assertEqual(self._renew(payment).status_code, 200)
        self.assertEqual(SubscriptionInvoice.objects.filter(company=self.company).count(), 1)
        self.assertEqual(
            SubscriptionEvent.objects.filter(
                subscription=self.subscription, event_type="invoice_period_granted"
            ).count(),
            1,
        )

    def test_a_rejected_payment_cannot_be_approved_by_manual_allocation(self):
        from subscriptions.services import (
            ValidationError, reject_payment, verify_and_allocate_payment,
        )

        payment = self._pay()
        reject_payment(payment.pk, self.admin, "wrong reference")
        invoice = SubscriptionInvoice.objects.create(
            company=self.company, subscription=self.subscription, number="SUB-T-1",
            amount=Decimal("500000.00"), currency="SDG",
            period_start=date.today(), period_end=date.today() + timedelta(days=30),
            status=SubscriptionInvoice.ISSUED, due_at=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            verify_and_allocate_payment(
                payment.pk, self.admin,
                [{"invoice_id": invoice.pk, "amount": Decimal("500000.00")}],
            )
        payment.refresh_from_db()
        self.assertEqual(payment.status, SubscriptionPayment.REJECTED)

    def test_two_pending_payments_never_buy_the_same_period(self):
        first, second = self._pay(), self._pay()
        first_preview, second_preview = self._preview(first), self._preview(second)
        self.assertEqual(first_preview["other_pending"], 1)
        # Before either is approved both would buy the same next period ...
        self.assertEqual(first_preview["key"], second_preview["key"])
        self.assertEqual(self._renew(first, first_preview["key"]).status_code, 200)
        # ... so the second preview is stale and is refused, not applied.
        stale = self._renew(second, second_preview["key"])
        self.assertEqual(stale.status_code, 400)
        self.assertEqual(str(stale.data["code"]), "renewal_changed")
        second.refresh_from_db()
        self.assertEqual(second.status, SubscriptionPayment.PENDING)
        fresh = self._preview(second)
        granted = SubscriptionInvoice.objects.get(company=self.company)
        self.assertEqual(
            fresh["steps"][0]["period_start"],
            (granted.period_end + timedelta(days=1)).isoformat(),
        )
        self.assertEqual(self._renew(second, fresh["key"]).status_code, 200)
        periods = list(
            SubscriptionInvoice.objects.filter(company=self.company)
            .order_by("period_start").values_list("period_start", "period_end")
        )
        self.assertEqual(periods[1][0], periods[0][1] + timedelta(days=1))
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.period_ends_at, end_of(periods[1][1]))

    def test_several_cycles_and_a_remainder_stay_visible(self):
        payment = self._pay("1250000.00")
        response = self._renew(payment)
        self.assertEqual(response.status_code, 200, response.data)
        invoices = list(SubscriptionInvoice.objects.filter(company=self.company)
                        .order_by("period_start"))
        self.assertEqual(
            [i.status for i in invoices],
            [SubscriptionInvoice.PAID, SubscriptionInvoice.PAID, SubscriptionInvoice.ISSUED],
        )
        self.assertEqual(invoices[1].period_start, invoices[0].period_end + timedelta(days=1))
        self.assertIsNone(invoices[2].entitlement_granted_at)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.period_ends_at, end_of(invoices[1].period_end))
        allocations = response.data["allocations"]
        self.assertEqual(
            [Decimal(row["amount"]) for row in allocations],
            [Decimal("500000"), Decimal("500000"), Decimal("250000")],
        )
        self.assertEqual(allocations[2]["invoice_status"], SubscriptionInvoice.ISSUED)
        # The next payment settles that open invoice first, then moves on.
        follow_up = self._pay("750000.00")
        preview = self._preview(follow_up)
        self.assertEqual(preview["steps"][0]["invoice_id"], invoices[2].pk)
        self.assertEqual(preview["steps"][0]["allocate"], "250000.00")
        self.assertEqual(
            preview["steps"][1]["period_start"],
            (invoices[2].period_end + timedelta(days=1)).isoformat(),
        )
        self.assertEqual(self._renew(follow_up, preview["key"]).status_code, 200)
        invoices[2].refresh_from_db()
        self.assertEqual(invoices[2].status, SubscriptionInvoice.PAID)
        self.assertEqual(
            SubscriptionInvoice.objects.filter(
                company=self.company, status=SubscriptionInvoice.PAID
            ).count(),
            4,
        )

    def test_less_than_a_cycle_leaves_an_open_invoice_and_grants_nothing(self):
        payment = self._pay("200000.00")
        preview = self._preview(payment)
        self.assertFalse(preview["steps"][0]["completes"])
        self.assertEqual(preview["steps"][0]["balance_after"], "300000.00")
        self.assertEqual(preview["status_after"], Subscription.TRIALING)
        self.assertEqual(self._renew(payment).status_code, 200)
        invoice = SubscriptionInvoice.objects.get(company=self.company)
        self.assertEqual(invoice.status, SubscriptionInvoice.ISSUED)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.TRIALING)
        self.assertIsNone(self.subscription.period_ends_at)
        self.client.force_authenticate(self.owner)
        mine = self.client.get(reverse("company-subscription")).data
        self.assertEqual(mine["subscription"]["next_renewal"]["open_balance"], "300000.00")
        self.assertEqual(Decimal(str(mine["invoices"][0]["allocated_amount"])), Decimal("200000"))

    def test_wrong_currency_is_refused_with_a_reason(self):
        payment = self._pay(currency="USD", method="bank_transfer")
        preview = self._preview(payment)
        self.assertFalse(preview["ok"])
        self.assertIn("SDG", preview["reason"])
        response = self._renew(payment)
        self.assertEqual(response.status_code, 400)
        payment.refresh_from_db()
        self.assertEqual(payment.status, SubscriptionPayment.PENDING)
        self.assertFalse(SubscriptionInvoice.objects.filter(company=self.company).exists())

    def test_owner_can_only_submit_in_the_billing_currency(self):
        self.client.force_authenticate(self.owner)
        url = reverse("subscription-payment-list")
        refused = self.client.post(url, {"amount": "500000", "currency": "USD", "method": "cash"})
        self.assertEqual(refused.status_code, 400)
        accepted = self.client.post(url, {"amount": "500000", "currency": "sdg", "method": "cash"})
        self.assertEqual(accepted.status_code, 201, accepted.data)
        self.assertEqual(accepted.data["currency"], "SDG")

    def test_addons_are_part_of_the_renewal_price(self):
        self.subscription.extra_limits = {"devices": 2}
        self.subscription.save(update_fields=["extra_limits"])
        preview = self._preview(self._pay("540000.00"))
        self.assertEqual(preview["cycle_amount"], "540000.00")
        self.assertEqual(len(preview["steps"]), 1)
        self.assertTrue(preview["steps"][0]["completes"])

    def test_lapsed_subscription_renews_from_today(self):
        self.subscription.status = Subscription.READ_ONLY
        self.subscription.period_ends_at = self.now - timedelta(days=20)
        self.subscription.save(update_fields=["status", "period_ends_at"])
        payment = self._pay()
        preview = self._preview(payment)
        self.assertEqual(
            preview["steps"][0]["period_start"],
            timezone.localtime(timezone.now(), KHARTOUM).date().isoformat(),
        )
        self.assertEqual(self._renew(payment).status_code, 200)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.ACTIVE)

    def test_manual_suspension_survives_a_renewal(self):
        self.subscription.status = Subscription.SUSPENDED
        self.subscription.save(update_fields=["status"])
        self.assertEqual(self._renew(self._pay()).status_code, 200)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.SUSPENDED)
        self.assertIsNotNone(self.subscription.period_ends_at)

    def test_grace_follows_the_renewed_period(self):
        end = self.now + timedelta(days=3)
        self.subscription.status = Subscription.ACTIVE
        self.subscription.period_ends_at = end
        self.subscription.grace_ends_at = end + timedelta(days=7)
        self.subscription.save(update_fields=["status", "period_ends_at", "grace_ends_at"])
        self.assertEqual(self._renew(self._pay()).status_code, 200)
        self.subscription.refresh_from_db()
        self.assertEqual(
            self.subscription.grace_ends_at,
            self.subscription.period_ends_at + timedelta(days=7),
        )

    def test_open_renewal_invoice_is_filled_before_a_new_one(self):
        issued = SubscriptionInvoice.objects.create(
            company=self.company, subscription=self.subscription, number="VSUB-MANUAL",
            status=SubscriptionInvoice.ISSUED, period_start=date(2026, 10, 6),
            period_end=date(2026, 11, 5), currency="SDG", amount=Decimal("500000.00"),
            due_at=self.now,
        )
        payment = self._pay()
        preview = self._preview(payment)
        self.assertEqual([s["invoice_id"] for s in preview["steps"]], [issued.pk])
        self.assertEqual(self._renew(payment).status_code, 200)
        issued.refresh_from_db()
        self.assertEqual(issued.status, SubscriptionInvoice.PAID)
        self.assertEqual(SubscriptionInvoice.objects.filter(company=self.company).count(), 1)

    def test_an_implausible_number_of_cycles_is_refused(self):
        plan = plan_renewal(self._pay("50000000.00"))
        self.assertFalse(plan["ok"])
        self.assertTrue(plan["reason"])

    def test_platform_list_carries_the_preview_for_pending_payments(self):
        self._pay()
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse("platform-subscription-payment-list"))
        rows = response.data["results"] if "results" in response.data else response.data
        self.assertTrue(rows[0]["renewal"]["ok"])
