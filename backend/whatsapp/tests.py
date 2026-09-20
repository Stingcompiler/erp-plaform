"""The Meta webhook: verification handshake, HMAC signature, routing by
phone_number_id, idempotent messages, monotonic statuses, retention."""
import hashlib
import hmac
import json

from django.test import TestCase, override_settings
from django.urls import reverse

from org.models import Company
from ops.preflight import check_whatsapp
from whatsapp.models import WhatsAppAccount, WhatsAppMessage, WhatsAppWebhookEvent

SECRET = "app-secret-for-tests"
VERIFY = "vezano-verify-2026"


def body_for(phone_number_id, messages=None, statuses=None, contacts=None):
    value = {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "249912345678", "phone_number_id": phone_number_id},
    }
    if contacts is not None:
        value["contacts"] = contacts
    if messages is not None:
        value["messages"] = messages
    if statuses is not None:
        value["statuses"] = statuses
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "WABA1", "changes": [{"value": value, "field": "messages"}]}],
    }


def text_message(wa_id="wamid.ABC1", sender="249123456789", text="مرحبا", ts="1758326400"):
    return {"from": sender, "id": wa_id, "timestamp": ts, "type": "text", "text": {"body": text}}


@override_settings(WHATSAPP_VERIFY_TOKEN=VERIFY, WHATSAPP_APP_SECRET=SECRET)
class WebhookTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.account = WhatsAppAccount.objects.create(
            company=self.company, phone_number_id="PN1", display_phone="249912345678",
        )
        self.url = reverse("whatsapp-webhook")

    def _post(self, payload, sign=True, secret=SECRET):
        raw = json.dumps(payload).encode("utf-8")
        headers = {}
        if sign:
            digest = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
            headers["HTTP_X_HUB_SIGNATURE_256"] = f"sha256={digest}"
        return self.client.generic(
            "POST", self.url, data=raw, content_type="application/json", **headers
        )

    # --- handshake ---------------------------------------------------------
    def test_verification_echoes_the_challenge_only_with_the_right_token(self):
        ok = self.client.get(self.url, {
            "hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "1234567",
        })
        self.assertEqual((ok.status_code, ok.content), (200, b"1234567"))
        bad = self.client.get(self.url, {
            "hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "1",
        })
        self.assertEqual(bad.status_code, 403)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    @override_settings(WHATSAPP_VERIFY_TOKEN="")
    def test_unconfigured_verify_token_never_matches(self):
        r = self.client.get(
            self.url, {"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "x"}
        )
        self.assertEqual(r.status_code, 403)

    # --- signature ---------------------------------------------------------
    def test_unsigned_or_missigned_bodies_are_refused(self):
        payload = body_for("PN1", messages=[text_message()])
        self.assertEqual(self._post(payload, sign=False).status_code, 403)
        self.assertEqual(self._post(payload, secret="other").status_code, 403)
        self.assertEqual(WhatsAppMessage.objects.count(), 0)

    # --- inbound messages --------------------------------------------------
    def test_inbound_message_is_stored_once_and_routed_to_the_company(self):
        payload = body_for(
            "PN1", messages=[text_message()],
            contacts=[{"profile": {"name": "أحمد"}, "wa_id": "249123456789"}],
        )
        first = self._post(payload)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json()["messages"], 1)
        again = self._post(payload)
        self.assertEqual(again.json()["messages"], 0)
        row = WhatsAppMessage.objects.get()
        self.assertEqual(row.company, self.company)
        self.assertEqual(row.direction, WhatsAppMessage.INBOUND)
        self.assertEqual((row.phone, row.contact_name, row.text), ("249123456789", "أحمد", "مرحبا"))
        self.assertEqual(row.status, WhatsAppMessage.RECEIVED)
        self.assertEqual(row.wa_timestamp.isoformat(), "2025-09-20T00:00:00+00:00")
        self.account.refresh_from_db()
        self.assertIsNotNone(self.account.last_event_at)
        event = WhatsAppWebhookEvent.objects.latest("received_at")
        self.assertEqual((event.messages, event.statuses), (0, 0))  # the redelivery

    def test_button_and_image_messages_keep_their_text(self):
        payload = body_for("PN1", messages=[
            {"from": "1", "id": "m1", "timestamp": "1", "type": "button",
             "button": {"payload": "YES", "text": "نعم"}},
            {"from": "1", "id": "m2", "timestamp": "1", "type": "image",
             "image": {"id": "img", "caption": "الفاتورة"}},
            {"from": "1", "id": "m3", "timestamp": "1", "type": "interactive",
             "interactive": {"type": "list_reply", "list_reply": {"id": "a", "title": "الطلب"}}},
        ])
        self.assertEqual(self._post(payload).json()["messages"], 3)
        texts = dict(WhatsAppMessage.objects.values_list("wa_message_id", "text"))
        self.assertEqual(texts, {"m1": "نعم", "m2": "الفاتورة", "m3": "الطلب"})

    def test_unknown_number_is_counted_but_nothing_is_stored(self):
        r = self._post(body_for("PN-OTHER", messages=[text_message()]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["unknown_numbers"], 1)
        self.assertEqual(WhatsAppMessage.objects.count(), 0)
        self.assertEqual(WhatsAppWebhookEvent.objects.get().unknown_numbers, 1)

    def test_inactive_account_is_treated_as_unknown(self):
        self.account.is_active = False
        self.account.save()
        r = self._post(body_for("PN1", messages=[text_message()]))
        self.assertEqual(r.json()["unknown_numbers"], 1)

    # --- statuses ----------------------------------------------------------
    def test_statuses_advance_an_outbound_message_and_never_go_backwards(self):
        sent = WhatsAppMessage.objects.create(
            account=self.account, company=self.company, direction=WhatsAppMessage.OUTBOUND,
            wa_message_id="wamid.OUT1", phone="249123456789", status=WhatsAppMessage.QUEUED,
        )

        def status(name, ts):
            return {"id": "wamid.OUT1", "status": name, "timestamp": ts,
                    "recipient_id": "249123456789"}
        self._post(body_for("PN1", statuses=[status("sent", "10"), status("delivered", "11")]))
        sent.refresh_from_db()
        self.assertEqual(sent.status, WhatsAppMessage.DELIVERED)
        # A late "sent" must not roll back.
        r = self._post(body_for("PN1", statuses=[status("sent", "12")]))
        self.assertEqual(r.json()["statuses"], 0)
        sent.refresh_from_db()
        self.assertEqual(sent.status, WhatsAppMessage.DELIVERED)
        self._post(body_for("PN1", statuses=[status("read", "13")]))
        sent.refresh_from_db()
        self.assertEqual(sent.status, WhatsAppMessage.READ)

    def test_failed_status_records_the_error(self):
        WhatsAppMessage.objects.create(
            account=self.account, direction=WhatsAppMessage.OUTBOUND,
            wa_message_id="wamid.OUT2", phone="2491", status=WhatsAppMessage.SENT,
        )
        self._post(body_for("PN1", statuses=[{
            "id": "wamid.OUT2", "status": "failed", "timestamp": "1", "recipient_id": "2491",
            "errors": [{"code": 131047, "title": "Re-engagement message"}],
        }]))
        row = WhatsAppMessage.objects.get(wa_message_id="wamid.OUT2")
        self.assertEqual((row.status, row.error_code), ("failed", "131047"))
        self.assertIn("Re-engagement", row.error_title)

    def test_status_for_a_message_we_never_sent_is_kept_as_a_bare_row(self):
        self._post(body_for("PN1", statuses=[{
            "id": "wamid.EXT", "status": "delivered", "timestamp": "1", "recipient_id": "2499",
        }]))
        row = WhatsAppMessage.objects.get(wa_message_id="wamid.EXT")
        self.assertEqual((row.direction, row.status, row.phone), ("out", "delivered", "2499"))

    # --- robustness --------------------------------------------------------
    def test_malformed_json_and_wrong_object_are_400_and_a_parse_bug_is_still_200(self):
        raw = b"{not json"
        digest = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
        r = self.client.generic(
            "POST", self.url, data=raw, content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=f"sha256={digest}",
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self._post({"object": "page", "entry": []}).status_code, 400)
        # A body with entries of the wrong shape must not make Meta retry forever.
        r = self._post({"object": "whatsapp_business_account", "entry": [{"changes": "oops"}]})
        self.assertEqual(r.status_code, 200)

    def test_preflight_reports_configuration(self):
        self.assertEqual(check_whatsapp().level, "ok")
        with override_settings(WHATSAPP_APP_SECRET=""):
            self.assertEqual(check_whatsapp().level, "warn")
        with override_settings(WHATSAPP_APP_SECRET="", WHATSAPP_VERIFY_TOKEN=""):
            self.assertEqual(check_whatsapp().level, "ok")


class RetentionTests(TestCase):
    def test_old_webhook_bodies_are_pruned_and_messages_kept(self):
        from datetime import timedelta

        from django.utils import timezone

        from whatsapp.tasks import prune_webhook_events

        account = WhatsAppAccount.objects.create(phone_number_id="PN9")
        old = WhatsAppWebhookEvent.objects.create(account=account, payload={})
        WhatsAppWebhookEvent.objects.filter(pk=old.pk).update(
            received_at=timezone.now() - timedelta(days=20)
        )
        WhatsAppWebhookEvent.objects.create(account=account, payload={})
        WhatsAppMessage.objects.create(
            account=account, direction=WhatsAppMessage.INBOUND, wa_message_id="keep", phone="1",
        )
        self.assertEqual(prune_webhook_events.run()["deleted"], 1)
        self.assertEqual(WhatsAppWebhookEvent.objects.count(), 1)
        self.assertEqual(WhatsAppMessage.objects.count(), 1)


class ConnectCommandTests(TestCase):
    def test_connects_updates_and_reads_the_token_from_the_environment(self):
        import os
        from io import StringIO
        from unittest import mock

        from django.core.management import call_command

        company = Company.objects.create(name="Alpha")
        out = StringIO()
        with mock.patch.dict(os.environ, {"WA_TOKEN": "EAAB-secret"}):
            call_command(
                "whatsapp_connect", "--phone-number-id", " PN77 ", "--display-phone", "+249 91 234",
                "--company", "Alpha", "--token-env", "WA_TOKEN", stdout=out,
            )
        account = WhatsAppAccount.objects.get(phone_number_id="PN77")
        self.assertEqual((account.company, account.display_phone), (company, "24991234"))
        self.assertEqual(account.access_token, "EAAB-secret")
        self.assertIn("Connected", out.getvalue())
        self.assertNotIn("EAAB-secret", out.getvalue())
        call_command("whatsapp_connect", "--phone-number-id", "PN77", "--deactivate", stdout=out)
        account.refresh_from_db()
        self.assertFalse(account.is_active)
        self.assertEqual(account.access_token, "EAAB-secret")  # kept when not re-supplied
        with self.assertRaises(Exception):
            call_command("whatsapp_connect", "--phone-number-id", "PN78", "--company", "Nope")
