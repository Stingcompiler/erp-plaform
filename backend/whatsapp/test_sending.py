"""Sending: the Graph client (mocked HTTP), purpose notifications after a
sale and a payment, the 24-hour window, templates, opt-in, and the
company settings endpoints (token write-only)."""
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role, User
from inventory.models import Product, StockMovement, Warehouse
from org.models import Branch, Company
from sales.models import Customer, Invoice, Payment
from whatsapp import client
from whatsapp.models import WhatsAppAccount, WhatsAppMessage, WhatsAppTemplate
from whatsapp.notify import notify_invoice, notify_payment

ACCEPTED = (200, {"messaging_product": "whatsapp", "messages": [{"id": "wamid.SENT1"}]})
REJECTED = (400, {"error": {"code": 131047, "message": "Re-engagement message",
                            "error_user_msg": "Outside the 24h window"}})


class SendingBase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha", business_type="enterprise")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123", company=self.company,
            role=Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS),
        )
        self.cashier = User.objects.create_user(
            email="till@alpha.test", password="passw0rd123", company=self.company,
            branch=self.branch,
            role=Role.objects.create(name="Sales Officer", scope_level=Role.SCOPE_BRANCH),
        )
        self.account = WhatsAppAccount.objects.create(
            company=self.company, phone_number_id="PN1", display_phone="249912345678",
            access_token="EAAB-token",
        )
        self.customer = Customer.objects.create(
            company=self.company, name="أحمد", phone="+249 12 345 6789", whatsapp_opt_in=True,
        )
        self.wh = Warehouse.objects.create(company=self.company, branch=self.branch, name="W")
        self.product = Product.objects.create(
            company=self.company, sku="S", name="Sugar", sale_price=Decimal("1000"),
        )
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.PURCHASE_IN, quantity=Decimal("10"),
        )

    def client_for(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def sell(self, paid=None, user=None):
        body = {
            "warehouse": self.wh.pk, "customer": self.customer.pk,
            "lines": [{"product": self.product.pk, "quantity": "2"}],
        }
        if paid is not None:
            body["payment"] = {"method": "cash", "amount": paid}
        return self.client_for(user or self.cashier).post(
            reverse("pos-checkout"), body, format="json"
        )


class ClientTests(SendingBase):
    def test_accepted_send_keeps_metas_id_and_stays_queued_until_the_webhook(self):
        with mock.patch.object(client, "_post_json", return_value=ACCEPTED) as post:
            row = client.send(
                self.account, "+249 12 345 6789", client.text_payload("249123456789", "hi"),
                purpose="test", text="hi",
            )
        url, token, payload = post.call_args[0]
        self.assertTrue(url.endswith("/v21.0/PN1/messages"))
        self.assertEqual(token, "EAAB-token")
        self.assertEqual(payload["to"], "249123456789")
        self.assertEqual((row.wa_message_id, row.status), ("wamid.SENT1", WhatsAppMessage.QUEUED))
        self.assertEqual(row.raw["purpose"], "test")

    def test_rejected_send_records_metas_error(self):
        with mock.patch.object(client, "_post_json", return_value=REJECTED):
            row = client.send(
                self.account, "249123456789", client.text_payload("249123456789", "x")
            )
        self.assertEqual((row.status, row.error_code), (WhatsAppMessage.FAILED, "131047"))
        self.assertIn("24h", row.error_title)
        self.assertTrue(row.wa_message_id.startswith("local:"))

    def test_network_failure_is_a_failed_row_not_an_exception(self):
        with mock.patch.object(client, "_post_json", side_effect=OSError("timed out")):
            row = client.send(
                self.account, "249123456789", client.text_payload("249123456789", "x")
            )
        self.assertEqual((row.status, row.error_code), ("failed", "network"))

    def test_no_token_or_inactive_or_bad_phone_sends_nothing(self):
        self.assertIsNone(client.send(self.account, "12", client.text_payload("12", "x")))
        self.account.access_token = ""
        self.account.save()
        with mock.patch.object(client, "_post_json") as post:
            self.assertIsNone(client.send(self.account, "249123456789", {}))
            post.assert_not_called()

    def test_template_payload_shape(self):
        payload = client.template_payload("2491", "invoice_ar", "ar", ["أحمد", "INV-000001"])
        self.assertEqual(payload["template"]["name"], "invoice_ar")
        self.assertEqual(payload["template"]["language"], {"code": "ar"})
        params = payload["template"]["components"][0]["parameters"]
        self.assertEqual([p["text"] for p in params], ["أحمد", "INV-000001"])

    def test_a_repeated_meta_id_keeps_the_local_id_instead_of_losing_the_send(self):
        WhatsAppMessage.objects.create(
            account=self.account, direction=WhatsAppMessage.OUTBOUND,
            wa_message_id="wamid.SENT1", phone="1",
        )
        with mock.patch.object(client, "_post_json", return_value=ACCEPTED):
            row = client.send(
                self.account, "249123456789", client.text_payload("249123456789", "x")
            )
        self.assertTrue(row.wa_message_id.startswith("local:"))
        self.assertEqual(row.raw["duplicate_meta_id"], "wamid.SENT1")
        self.assertEqual(row.status, WhatsAppMessage.QUEUED)


class NotificationTests(SendingBase):
    def test_sale_sends_the_invoice_template_with_its_parameters(self):
        WhatsAppTemplate.objects.create(
            company=self.company, purpose=WhatsAppTemplate.INVOICE_SENT,
            template_name="vezano_invoice", language="ar",
        )
        with mock.patch.object(client, "_post_json", return_value=ACCEPTED) as post:
            r = self.sell(paid="1500")
        self.assertEqual(r.status_code, 201, r.data)
        payload = post.call_args[0][2]
        self.assertEqual(payload["type"], "template")
        texts = [p["text"] for p in payload["template"]["components"][0]["parameters"]]
        self.assertEqual(texts[0], "أحمد")
        self.assertEqual(texts[1], Invoice.objects.get().number_display)
        self.assertEqual(texts[2], "2,000.00 SDG")
        self.assertEqual(texts[3], "500.00 SDG")
        row = WhatsAppMessage.objects.get()
        self.assertEqual((row.customer, row.raw["purpose"]), (self.customer, "invoice_sent"))

    def test_without_a_template_free_text_goes_only_inside_the_window(self):
        with mock.patch.object(client, "_post_json", return_value=ACCEPTED) as post:
            self.assertEqual(self.sell().status_code, 201)
            post.assert_not_called()  # outside the window, no template: skipped
        WhatsAppMessage.objects.create(
            account=self.account, company=self.company, direction=WhatsAppMessage.INBOUND,
            wa_message_id="in1", phone="249123456789",
        )
        with mock.patch.object(client, "_post_json", return_value=ACCEPTED) as post:
            self.assertEqual(self.sell().status_code, 201)
            payload = post.call_args[0][2]
        self.assertEqual(payload["type"], "text")
        self.assertIn("INV-", payload["text"]["body"])
        self.assertIn("المتبقي", payload["text"]["body"])

    def test_window_is_exactly_24_hours(self):
        old = WhatsAppMessage.objects.create(
            account=self.account, company=self.company, direction=WhatsAppMessage.INBOUND,
            wa_message_id="in-old", phone="249123456789",
        )
        WhatsAppMessage.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(hours=25)
        )
        with mock.patch.object(client, "_post_json", return_value=ACCEPTED) as post:
            self.sell()
            post.assert_not_called()

    def test_no_opt_in_or_no_phone_or_no_account_means_no_message(self):
        WhatsAppTemplate.objects.create(
            company=self.company, purpose=WhatsAppTemplate.INVOICE_SENT, template_name="t",
        )
        self.customer.whatsapp_opt_in = False
        self.customer.save()
        with mock.patch.object(client, "_post_json", return_value=ACCEPTED) as post:
            self.sell()
            post.assert_not_called()
        self.customer.whatsapp_opt_in = True
        self.customer.phone = "12"
        self.customer.save()
        with mock.patch.object(client, "_post_json", return_value=ACCEPTED) as post:
            self.sell()
            post.assert_not_called()
        self.customer.phone = "249123456789"
        self.customer.save()
        self.account.access_token = ""
        self.account.save()
        with mock.patch.object(client, "_post_json", return_value=ACCEPTED) as post:
            self.sell()
            post.assert_not_called()

    def test_a_send_failure_never_fails_the_sale(self):
        WhatsAppTemplate.objects.create(
            company=self.company, purpose=WhatsAppTemplate.INVOICE_SENT, template_name="t",
        )
        with mock.patch.object(client, "_post_json", side_effect=RuntimeError("boom")):
            r = self.sell()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(Invoice.objects.count(), 1)

    def test_recording_a_payment_sends_the_receipt_template(self):
        WhatsAppTemplate.objects.create(
            company=self.company, purpose=WhatsAppTemplate.PAYMENT_RECEIVED,
            template_name="vezano_receipt",
        )
        with mock.patch.object(client, "_post_json", return_value=ACCEPTED):
            invoice = Invoice.objects.get(pk=self.sell().data["id"])
        with mock.patch.object(client, "_post_json", return_value=ACCEPTED) as post:
            r = self.client_for(self.owner).post(
                reverse("payment-list"),
                {"invoice": invoice.pk, "method": "cash", "amount": "700"}, format="json",
            )
        self.assertEqual(r.status_code, 201, r.data)
        texts = [p["text"] for p in post.call_args[0][2]["template"]["components"][0]["parameters"]]
        self.assertEqual(texts, ["أحمد", "700.00 SDG", invoice.number_display, "1,300.00 SDG"])
        self.assertEqual(Payment.objects.count(), 1)

    def test_direct_calls_report_why_nothing_went(self):
        invoice = Invoice.objects.create(
            company=self.company, warehouse=self.wh, number=1, total=Decimal("1"),
        )
        self.assertEqual(notify_invoice(invoice), (None, "no_customer"))
        invoice.customer = self.customer
        invoice.save()
        self.assertEqual(notify_invoice(invoice)[1], "outside_window")
        payment = Payment.objects.create(
            company=self.company, invoice=invoice, method=Payment.CASH, amount=Decimal("1"),
        )
        self.assertEqual(notify_payment(payment)[1], "outside_window")


class SettingsEndpointTests(SendingBase):
    def test_get_shows_connection_without_the_token_and_put_needs_a_manager(self):
        r = self.client_for(self.owner).get(reverse("whatsapp-settings"))
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["account"]["phone_number_id"], "PN1")
        self.assertTrue(r.data["account"]["has_token"])
        self.assertNotIn("access_token", r.data["account"])
        self.assertEqual([t["purpose"] for t in r.data["templates"]][:2],
                         ["invoice_sent", "payment_received"])
        self.assertEqual(r.data["opted_in_customers"], 1)
        denied = self.client_for(self.cashier).put(
            reverse("whatsapp-settings"), {"templates": []}, format="json"
        )
        self.assertEqual(denied.status_code, 403)

    def test_put_updates_account_keeps_token_when_blank_and_saves_templates(self):
        c = self.client_for(self.owner)
        r = c.put(reverse("whatsapp-settings"), {
            "account": {"phone_number_id": "PN1", "waba_id": "W1", "display_phone": "+249 91 234",
                        "display_name": "Alpha Shop", "access_token": ""},
            "templates": [
                {"purpose": "invoice_sent", "template_name": "inv_ar", "language": "ar"},
                {"purpose": "bogus", "template_name": "x"},
            ],
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.account.refresh_from_db()
        self.assertEqual((self.account.waba_id, self.account.display_phone), ("W1", "24991234"))
        self.assertEqual(self.account.access_token, "EAAB-token")
        self.assertEqual(
            list(WhatsAppTemplate.objects.values_list("purpose", "template_name")),
            [("invoice_sent", "inv_ar")],
        )
        r = c.put(reverse("whatsapp-settings"), {
            "account": {"phone_number_id": "PN1", "access_token": "NEW"},
        }, format="json")
        self.account.refresh_from_db()
        self.assertEqual(self.account.access_token, "NEW")

    def test_a_number_connected_elsewhere_is_refused(self):
        other = Company.objects.create(name="Beta")
        WhatsAppAccount.objects.create(company=other, phone_number_id="PN-BETA")
        r = self.client_for(self.owner).put(
            reverse("whatsapp-settings"),
            {"account": {"phone_number_id": "PN-BETA"}}, format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_test_send_uses_the_client(self):
        with mock.patch.object(client, "_post_json", return_value=ACCEPTED):
            r = self.client_for(self.owner).post(
                reverse("whatsapp-test-send"),
                {"phone": "+249 12 345 6789", "text": "تجربة"}, format="json",
            )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((r.data["status"], r.data["purpose"]), ("queued", "test"))
        bad = self.client_for(self.owner).post(
            reverse("whatsapp-test-send"), {"phone": "1", "text": ""}, format="json"
        )
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(
            self.client_for(self.cashier).post(
                reverse("whatsapp-test-send"), {"phone": "249123456789", "text": "x"},
                format="json",
            ).status_code, 403,
        )
