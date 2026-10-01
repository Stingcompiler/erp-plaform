"""Trial and demo requests on vezano.app/track/, behind an email code.

POST /api/public/track/requests/ answers the same 202 for every search; a
code goes to the email stored on each matching request; …/verify/ shows
that email's requests with their stages and a 30-minute view token;
…/view/ shows them again while the token lasts."""

import re
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from core import otp
from website import request_tracking
from website.models import PlatformLead, RegistrationRequest

MAIL = dict(
    EMAIL_ENABLED=True,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    TEAM_NOTIFY_BACKGROUND=False,
    VEZANO_CANONICAL_HOST="vezano.app",
)
CODE_LINE = re.compile(r"^\d{6}$", re.M)


@override_settings(**MAIL)
class RequestTrackingBase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.clock = 1_900_000_000.0
        patcher = mock.patch("core.otp.now", side_effect=lambda: self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)

    def registration(self, **fields):
        data = {
            "company_name": "Northwind Trading", "contact_name": "Amina Owner",
            "email": "amina@northwind.test", "phone": "+249 912 345 678", "country": "SD",
            "privacy_version": "2026-09",
        }
        data.update(fields)
        return RegistrationRequest.objects.create(**data)

    def search(self, query, ip="10.3.0.1", language="en"):
        return self.client.post(reverse("track-request-start"),
                                {"q": query, "language": language},
                                format="json", REMOTE_ADDR=ip)

    def verify(self, challenge_id, code, language="en"):
        return self.client.post(reverse("track-request-verify"),
                                {"challenge_id": challenge_id, "code": code,
                                 "language": language}, format="json")

    def codes_by_address(self):
        """{address: the last code mailed to it}."""
        out = {}
        for message in mail.outbox:
            found = CODE_LINE.search(message.body)
            if found:
                out[message.to[0]] = found.group(0)
        return out


class GenericAnswerTests(RequestTrackingBase):
    def test_a_match_and_a_miss_answer_identically(self):
        self.registration()
        shapes = []
        for query, ip in (("0912345678", "10.3.0.1"), ("0999999999", "10.3.0.2"),
                          ("Amina Owner", "10.3.0.3"), ("Nobody Here", "10.3.0.4"),
                          ("RZZZZZZ", "10.3.0.5")):
            response = self.search(query, ip=ip)
            self.assertEqual(response.status_code, 202, query)
            self.assertEqual(response["Cache-Control"], "no-store")
            data = dict(response.json())
            self.assertRegex(data.pop("challenge_id"), r"^[\w-]{20,}$")
            shapes.append(data)
        self.assertEqual(shapes, [{"sent_hint": "", "resend_after": 60}] * 5)
        # Only the real match got mail, and at the stored address.
        self.assertEqual([m.to for m in mail.outbox], [["amina@northwind.test"]] * 2)

    def test_an_email_search_shows_the_typed_address_masked_match_or_not(self):
        self.registration()
        hit = self.search("Amina@Northwind.test", ip="10.3.1.1").json()
        miss = self.search("nobody@northwind.test", ip="10.3.1.2").json()
        self.assertEqual(hit["sent_hint"], "A•••@northwind.test")
        self.assertEqual(miss["sent_hint"], "n•••@northwind.test")
        self.assertEqual(set(hit), set(miss))

    def test_the_hourly_cap_reads_the_same_with_or_without_a_match(self):
        self.registration()
        for _search in range(3):
            self.assertEqual(self.search("0999999999").status_code, 202)
        limited = self.search("0912345678")
        self.assertEqual((limited.status_code, limited.json()["code"]), (429, "too_many_codes"))
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(self.search("0912345678", ip="10.3.9.9").status_code, 202)

    def test_a_demo_request_without_email_gets_no_code_and_no_tell(self):
        lead = PlatformLead.objects.create(name="Sara Musa", phone="0912 000 111")
        with_nothing = self.search("0955555555", ip="10.3.2.1").json()
        demo = self.search(lead.public_reference, ip="10.3.2.2").json()
        by_phone = self.search("0912000111", ip="10.3.2.3").json()
        for data in (with_nothing, demo, by_phone):
            data.pop("challenge_id")
        self.assertEqual(with_nothing, demo)
        self.assertEqual(with_nothing, by_phone)
        self.assertEqual(mail.outbox, [])

    def test_an_empty_search_is_refused(self):
        self.assertEqual(self.search("   ").status_code, 400)
        response = self.client.post(reverse("track-request-start"), [1], format="json")
        self.assertEqual(response.status_code, 400)

    def test_codes_and_queries_are_never_logged(self):
        self.registration()
        with self.assertLogs("website.request_tracking", "INFO") as logs:
            self.search("amina@northwind.test")
        text = "\n".join(logs.output)
        self.assertIn("matches=1 sent=1", text)
        self.assertNotIn("amina", text)
        code = self.codes_by_address()["amina@northwind.test"]
        self.assertNotIn(code, text)


class CodeTests(RequestTrackingBase):
    def test_the_code_goes_to_the_stored_email_for_any_search_key(self):
        row = self.registration()
        for query in (row.public_reference.lower(), "+249912345678", "amina owner",
                      "northwind  trading"):
            cache.clear()
            mail.outbox.clear()
            challenge = self.search(query).json()["challenge_id"]
            self.assertEqual([m.to for m in mail.outbox], [["amina@northwind.test"]], query)
            message = mail.outbox[0]
            code = self.codes_by_address()["amina@northwind.test"]
            self.assertNotIn(code, message.subject)
            response = self.verify(challenge, code)
            self.assertEqual(response.status_code, 200, query)
            self.assertEqual([item["reference"] for item in response.json()["results"]],
                             [row.public_reference])

    def test_one_code_per_address_and_each_shows_only_its_own(self):
        mine = self.registration()
        also_mine = PlatformLead.objects.create(
            name="Amina Owner", email="AMINA@northwind.test", phone="0912345678",
        )
        theirs = self.registration(email="other@shop.test", company_name="Other Shop",
                                   contact_name="Other Person")
        challenge = self.search("0912345678").json()["challenge_id"]
        codes = self.codes_by_address()
        self.assertEqual(sorted(codes), ["amina@northwind.test", "other@shop.test"])
        self.assertEqual(len(mail.outbox), 2)
        response = self.verify(challenge, codes["other@shop.test"])
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([item["reference"] for item in data["results"]],
                         [theirs.public_reference])
        self.assertEqual(data["email_masked"], "o•••@shop.test")
        body = response.content.decode()
        for other in (mine.public_reference, also_mine.public_reference):
            self.assertNotIn(other, body)
        # The challenge is spent once used.
        self.assertEqual(self.verify(challenge, codes["amina@northwind.test"]).json()["code"],
                         "code_expired")

    def test_wrong_codes_count_down_then_the_challenge_is_gone(self):
        self.registration()
        challenge = self.search("0912345678").json()["challenge_id"]
        code = self.codes_by_address()["amina@northwind.test"]
        wrong = "000000" if code != "000000" else "111111"
        answers = [self.verify(challenge, wrong).json() for _try in range(5)]
        self.assertEqual([a["code"] for a in answers], ["wrong_code"] * 4 + ["too_many_attempts"])
        self.assertEqual(answers[0]["attempts_left"], 4)
        self.assertEqual(self.verify(challenge, code).json()["code"], "code_expired")

    def test_a_miss_fails_verification_like_a_wrong_code(self):
        challenge = self.search("0999999999").json()["challenge_id"]
        response = self.verify(challenge, "123456")
        self.assertEqual((response.status_code, response.json()["code"]), (400, "wrong_code"))

    def test_the_code_expires_after_ten_minutes(self):
        self.registration()
        challenge = self.search("0912345678").json()["challenge_id"]
        code = self.codes_by_address()["amina@northwind.test"]
        self.clock += 601
        self.assertEqual(self.verify(challenge, code).json()["code"], "code_expired")

    def test_resend_waits_a_minute_and_sends_a_new_code(self):
        self.registration()
        challenge = self.search("0912345678").json()["challenge_id"]
        first = self.codes_by_address()["amina@northwind.test"]
        url = reverse("track-request-resend")
        early = self.client.post(url, {"challenge_id": challenge}, format="json")
        self.assertEqual((early.status_code, early.json()["code"]), (429, "resend_cooldown"))
        self.clock += 61
        with mock.patch("core.otp.new_code", return_value="777777" if first != "777777"
                        else "888888"):
            again = self.client.post(url, {"challenge_id": challenge}, format="json")
        self.assertEqual(again.status_code, 202)
        self.assertEqual(set(again.json()), {"challenge_id", "sent_hint", "resend_after"})
        second = self.codes_by_address()["amina@northwind.test"]
        self.assertNotEqual(first, second)
        self.assertEqual(self.verify(challenge, first).json()["code"], "wrong_code")
        self.assertEqual(self.verify(challenge, second).status_code, 200)

    def test_an_address_gets_at_most_three_codes_an_hour(self):
        self.registration()
        for index in range(4):
            self.assertEqual(self.search("0912345678", ip=f"10.4.0.{index}").status_code, 202)
        self.assertEqual(len(mail.outbox), 3)


class ResultTests(RequestTrackingBase):
    def open(self, query="amina@northwind.test", language="en"):
        challenge = self.search(query, language=language).json()["challenge_id"]
        code = self.codes_by_address()["amina@northwind.test"]
        response = self.verify(challenge, code, language=language)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_status_stages_note_and_next_step_nothing_private(self):
        row = self.registration(internal_note="call them twice, spammy")
        admin = User.objects.create_superuser(email="root@vezano.test", password="x" * 12)
        staff = APIClient()
        staff.force_authenticate(admin)
        staff.post(f"/api/platform/registration-requests/{row.pk}/review/",
                   {"status": "under_review"}, format="json")
        staff.post(f"/api/platform/registration-requests/{row.pk}/review/",
                   {"status": "needs_information", "public_note": "Send the trade licence"},
                   format="json")
        data = self.open()
        item = data["results"][0]
        self.assertEqual(item["kind"], "registration")
        self.assertEqual(item["reference"], row.public_reference)
        self.assertEqual(item["status"], "needs_information")
        self.assertEqual(item["status_label"], "We need more information")
        self.assertEqual(item["note"], "Send the trade licence")
        self.assertTrue(item["note_updated_at"])
        self.assertTrue(item["next"])
        self.assertEqual(item["customer"], "Northwind Trading")
        steps = [(step["key"], step["done"], step["current"], bool(step["at"]))
                 for step in item["timeline"]]
        self.assertEqual(steps, [
            ("submitted", True, False, True),
            ("under_review", True, False, True),
            ("needs_information", True, True, True),
            ("approved", False, False, False),
            ("provisioned", False, False, False),
        ])
        body = str(data)
        for secret in ("spammy", "912", "amina@northwind.test", "Amina Owner"):
            self.assertNotIn(secret, body)
        self.assertEqual(data["expires_in"], 1800)

    def test_a_rejected_request_closes_its_timeline(self):
        row = self.registration(status=RegistrationRequest.REJECTED, public_note="Duplicate")
        item = self.open(language="ar")["results"][0]
        self.assertEqual(item["reference"], row.public_reference)
        self.assertEqual(item["status_label"], "مرفوض")
        self.assertEqual([step["key"] for step in item["timeline"]], ["submitted", "rejected"])
        self.assertTrue(item["timeline"][-1]["closed"])
        self.assertEqual(item["note"], "Duplicate")

    def test_demo_requests_with_that_email_are_listed_too(self):
        self.registration()
        lead = PlatformLead.objects.create(name="Amina", email="amina@northwind.test",
                                           phone="0912345678", status="contacted")
        kinds = {item["kind"]: item for item in self.open()["results"]}
        self.assertEqual(set(kinds), {"registration", "demo"})
        self.assertEqual(kinds["demo"]["reference"], lead.public_reference)
        self.assertEqual(kinds["demo"]["timeline"][1]["key"], "contacted")
        self.assertTrue(kinds["demo"]["timeline"][1]["current"])

    def test_the_view_token_lasts_thirty_minutes(self):
        self.registration()
        data = self.open()
        url = reverse("track-request-view")
        again = self.client.post(url, {"token": data["token"], "language": "ar"}, format="json")
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["results"][0]["status_label"],
                         "استلمنا طلبك — قيد المراجعة")
        self.assertEqual(again["Cache-Control"], "no-store")
        self.clock += request_tracking.VIEW_TTL + 1
        expired = self.client.post(url, {"token": data["token"]}, format="json")
        self.assertEqual((expired.status_code, expired.json()["code"]), (403, "view_expired"))
        forged = self.client.post(url, {"token": data["token"] + "x"}, format="json")
        self.assertEqual(forged.status_code, 403)

    def test_the_token_names_no_one_else(self):
        token = request_tracking.view_token("someone@else.test")
        self.registration()
        response = self.client.post(reverse("track-request-view"), {"token": token},
                                    format="json")
        self.assertEqual(response.json()["results"], [])

    def test_codes_live_only_as_hashes(self):
        self.registration()
        challenge = self.search("0912345678").json()["challenge_id"]
        code = self.codes_by_address()["amina@northwind.test"]
        bundle = request_tracking._load(challenge)
        self.assertEqual(len(bundle["challenges"]), 1)
        entry = otp.stored(bundle["challenges"][0])
        self.assertNotIn(code, repr(bundle) + repr(entry))
        self.assertEqual(entry["code_hash"], otp.code_hash(request_tracking.PURPOSE, code))
