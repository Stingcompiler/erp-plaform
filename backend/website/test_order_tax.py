"""A web order is quoted with tax, so what the page and the email say is
what the confirmation invoices; a transfer above what is owed is not cut
down silently — the manager decides."""

from decimal import Decimal

from django.core import mail
from django.test import TestCase, override_settings

from core.models import ActivityLog
from sales.models import Invoice, Payment
from website.models import PublicOrder, PublicOrderPayment
from website import test_order_payments as base


@override_settings(
    EMAIL_ENABLED=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    VEZANO_CANONICAL_HOST="vezano.app",
)
class OrderTaxTests(TestCase):
    setUp = base.OrderPaymentTests.setUp
    _order = base.OrderPaymentTests._order

    def _tax(self, rate):
        profile = self.company.tax_profile
        profile.flat_tax_rate = Decimal(rate)
        profile.save(update_fields=["flat_tax_rate"])

    def _declare(self, ref, amount, last4="4321"):
        response = self.visitor.post(
            f"/api/public/site/bakery/orders/{ref}/",
            {"bank_account": self.bank.pk, "sender_bank_name": "Faisal",
             "reference_last4": last4, "amount": amount},
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response.data["id"]

    def _confirm(self, order, claim_id, **extra):
        return self.staff.post(
            f"/api/web-orders/{order.pk}/payments/{claim_id}/confirm/", extra, format="json"
        )

    def test_taxed_order_total_is_the_invoice_total(self):
        self._tax("15")
        data = self._order(email="amal@example.com")
        # 2 x 500 = 1000, 15% tax = 150.
        self.assertEqual(data["total"], "1150.00")
        self.assertEqual(data["tax_amount"], "150.00")
        customer_mail = next(m for m in mail.outbox if m.to == ["amal@example.com"])
        self.assertIn("1150.00 SDG", customer_mail.body)
        order = PublicOrder.objects.get(reference=data["reference"])
        detail = self.staff.get(f"/api/web-orders/{order.pk}/").data
        self.assertEqual(detail["total"], "1150.00")
        self.assertEqual(detail["tax_amount"], "150.00")

        claim_id = self._declare(data["reference"], "1150")
        confirmed = self._confirm(order, claim_id)
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        invoice = Invoice.objects.get(pk=PublicOrderPayment.objects.get(pk=claim_id).invoice_id)
        order.refresh_from_db()
        self.assertEqual(invoice.total, order.total)
        self.assertEqual(invoice.tax_amount, Decimal("150.00"))
        self.assertEqual(invoice.amount_due(), Decimal("0"))
        self.assertEqual(invoice.customer.ar_balance(), Decimal("0"))
        page = self.visitor.get(f"/api/public/site/bakery/orders/{data['reference']}/").data
        self.assertEqual(page["paid"], "1150.00")
        self.assertFalse(page["can_pay"])

    def test_order_quoted_before_tax_is_repriced_at_confirmation(self):
        ref = self._order()["reference"]
        self._tax("15")
        order = PublicOrder.objects.get(reference=ref)
        self.assertEqual(order.total, Decimal("1000.00"))
        self.staff.post(f"/api/web-orders/{order.pk}/confirm/", {}, format="json")
        order.refresh_from_db()
        # The page now asks for what the invoice will charge.
        self.assertEqual(order.total, Decimal("1150.00"))
        self.assertEqual(order.sales_order.total, order.total)
        self.assertTrue(ActivityLog.objects.filter(action="public_order_repriced").exists())
        page = self.visitor.get(f"/api/public/site/bakery/orders/{ref}/").data
        self.assertEqual(page["total"], "1150.00")

    def test_overpayment_is_refused_until_the_manager_decides(self):
        ref = self._order()["reference"]
        order = PublicOrder.objects.get(reference=ref)
        claim_id = self._declare(ref, "1200")
        refused = self._confirm(order, claim_id)
        self.assertEqual(refused.status_code, 400, refused.data)
        self.assertEqual(refused.data["code"], "overpayment")
        self.assertEqual(refused.data["surplus"], "200.00")
        self.assertEqual(refused.data["due"], "1000.00")
        # Nothing happened: no invoice, the claim still waits.
        self.assertFalse(Invoice.objects.exists())
        self.assertEqual(
            PublicOrderPayment.objects.get(pk=claim_id).status, PublicOrderPayment.VERIFYING
        )

        accepted = self._confirm(order, claim_id, surplus_returned=True)
        self.assertEqual(accepted.status_code, 200, accepted.data)
        claim = PublicOrderPayment.objects.get(pk=claim_id)
        self.assertEqual(claim.payment.amount, Decimal("1000.00"))
        self.assertIn("200", claim.decision_note)
        self.assertEqual(claim.invoice.amount_due(), Decimal("0"))
        log = ActivityLog.objects.get(action="public_payment_confirmed")
        self.assertEqual(log.metadata["surplus_returned"], "200.00")
        page = self.visitor.get(f"/api/public/site/bakery/orders/{ref}/").data
        self.assertEqual(page["paid"], "1000.00")
        self.assertFalse(page["can_pay"])

    def test_second_transfer_above_the_balance_is_refused_too(self):
        ref = self._order()["reference"]
        order = PublicOrder.objects.get(reference=ref)
        first = self._declare(ref, "600", last4="1111")
        self.assertEqual(self._confirm(order, first).status_code, 200)
        second = self._declare(ref, "600", last4="2222")
        refused = self._confirm(order, second)
        self.assertEqual(refused.status_code, 400, refused.data)
        self.assertEqual(refused.data["code"], "overpayment")
        self.assertEqual(refused.data["due"], "400.00")
        accepted = self._confirm(order, second, surplus_returned=True)
        self.assertEqual(accepted.status_code, 200, accepted.data)
        order.refresh_from_db()
        amounts = sorted(
            Payment.objects.filter(invoice__source_order=order.sales_order)
            .values_list("amount", flat=True)
        )
        self.assertEqual(amounts, [Decimal("400.00"), Decimal("600.00")])
        # Paid in full: a further claim cannot be confirmed.
        third = self._declare(ref, "50", last4="3333")
        self.assertEqual(self._confirm(order, third).data["code"], "already_paid")
