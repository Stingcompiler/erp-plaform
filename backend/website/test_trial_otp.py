"""The public trial form behind an email code (owner decisions 2026-10-01).

POST /api/public/registration-requests/ validates and checks duplicates,
then emails a 6-digit code (202, nothing in the database yet);
…/verify/ creates the request; …/resend/ sends a new code. Limits: 10
minutes, 5 tries, 60 s between codes, 3 codes an hour per email and per
client address. The code is kept only as an HMAC, in the cache."""

from io import StringIO
from unittest import mock
from uuid import uuid4

from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from subscriptions.models import Plan, PlanVersion
from core import otp
from website import trial_requests
from website.models import RegistrationRequest, SeoSettings

MAIL = dict(
    EMAIL_ENABLED=True,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    TEAM_NOTIFY_BACKGROUND=False,
)
CODE = "135790"


@override_settings(**MAIL)
class TrialOtpBase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        plan = Plan.objects.create(code="business", name="Business")
        self.version = PlanVersion.objects.create(
            plan=plan, version=1, currency="SDG", price=20, modules=["sales"],
            published_at=timezone.now(),
        )
        self.clock = 1_900_000_000.0
        patcher = mock.patch("core.otp.now", side_effect=lambda: self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)

    def body(self, **fields):
        data = {
            "request_uuid": str(uuid4()),
            "company_name": "Northwind Trading",
            "contact_name": "Amina Owner",
            "email": "amina@northwind.test",
            "phone": "+249 912 345 678",
            "country": "SD",
            "delivery_mode": "saas",
            "plan_version": self.version.pk,
            "privacy_version": "2026-09",
        }
        data.update(fields)
        return data

    def start(self, ip="10.1.0.1", code=CODE, **fields):
        with mock.patch("core.otp.new_code", return_value=code):
            return self.client.post(
                reverse("registration-request"), self.body(**fields), format="json",
                REMOTE_ADDR=ip,
            )

    def verify(self, pending_id, code=CODE, ip="10.1.0.1"):
        return self.client.post(
            reverse("registration-request-verify"), {"pending_id": pending_id, "code": code},
            format="json", REMOTE_ADDR=ip,
        )

    def resend(self, pending_id, code="864200", ip="10.1.0.1"):
        with mock.patch("core.otp.new_code", return_value=code):
            return self.client.post(
                reverse("registration-request-resend"), {"pending_id": pending_id},
                format="json", REMOTE_ADDR=ip,
            )

    def existing(self, **fields):
        data = {
            "company_name": "Old Company", "contact_name": "Somebody Else",
            "email": "old@example.test", "phone": "0111000000", "country": "SD",
            "privacy_version": "2026-09", "plan_version": self.version,
        }
        data.update(fields)
        return RegistrationRequest.objects.create(**data)


class CodeFlowTests(TrialOtpBase):
    def test_the_request_exists_only_after_the_code(self):
        started = self.start()
        self.assertEqual(started.status_code, 202, started.data)
        self.assertEqual(set(started.data),
                         {"pending_id", "email_masked", "resend_after", "expires_in"})
        self.assertEqual(started.data["email_masked"], "a•••@northwind.test")
        self.assertEqual(started.data["resend_after"], 60)
        self.assertEqual(started.data["expires_in"], 600)
        self.assertFalse(RegistrationRequest.objects.exists())
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["amina@northwind.test"])
        self.assertIn(CODE, message.body)
        self.assertIn(CODE, message.alternatives[0][0])
        self.assertNotIn(CODE, message.subject)

        verified = self.verify(started.data["pending_id"])
        self.assertEqual(verified.status_code, 201, verified.data)
        row = RegistrationRequest.objects.get()
        self.assertEqual(verified.data["public_reference"], row.public_reference)
        self.assertEqual(set(verified.data),
                         {"reference", "public_reference", "track_url", "status"})
        self.assertEqual(row.email, "amina@northwind.test")
        self.assertEqual(row.plan_version, self.version)
        # The acknowledgement follows the code.
        self.assertIn(row.public_reference, mail.outbox[-1].body)

    def test_the_code_is_stored_only_as_a_hash_and_never_logged(self):
        with self.assertLogs(level="INFO") as logs:
            started = self.start()
            self.verify(started.data["pending_id"], code="000000")
        entry = otp.stored(started.data["pending_id"])
        self.assertNotIn(CODE, repr(entry))
        self.assertEqual(entry["code_hash"], otp.code_hash("trial", CODE))
        self.assertNotIn(CODE, "\n".join(logs.output))

    def test_arabic_digits_and_spaces_in_the_code_are_accepted(self):
        started = self.start()
        self.assertEqual(self.verify(started.data["pending_id"], "١٣٥ ٧٩٠").status_code, 201)

    def test_a_wrong_code_counts_down(self):
        started = self.start()
        wrong = self.verify(started.data["pending_id"], "111111")
        self.assertEqual(wrong.status_code, 400)
        self.assertEqual((wrong.data["code"], wrong.data["attempts_left"]), ("wrong_code", 4))
        self.assertFalse(RegistrationRequest.objects.exists())
        self.assertEqual(self.verify(started.data["pending_id"]).status_code, 201)

    def test_five_wrong_codes_throw_the_form_away(self):
        pending = self.start().data["pending_id"]
        answers = [self.verify(pending, "111111").data["code"] for _try in range(5)]
        self.assertEqual(answers, ["wrong_code"] * 4 + ["too_many_attempts"])
        late = self.verify(pending)
        self.assertEqual((late.status_code, late.data["code"]), (400, "code_expired"))
        self.assertFalse(RegistrationRequest.objects.exists())

    def test_the_code_expires_after_ten_minutes(self):
        pending = self.start().data["pending_id"]
        self.clock += 601
        expired = self.verify(pending)
        self.assertEqual((expired.status_code, expired.data["code"]), (400, "code_expired"))
        self.assertFalse(RegistrationRequest.objects.exists())

    def test_resend_waits_60_seconds_and_replaces_the_code(self):
        pending = self.start().data["pending_id"]
        early = self.resend(pending)
        self.assertEqual((early.status_code, early.data["code"]), (429, "resend_cooldown"))
        self.assertEqual(early.data["retry_after"], 60)
        self.assertEqual(early["Retry-After"], "60")
        self.clock += 61
        again = self.resend(pending, code="864200")
        self.assertEqual(again.status_code, 202, again.data)
        self.assertEqual(again.data["pending_id"], pending)
        self.assertIn("864200", mail.outbox[-1].body)
        self.assertEqual(self.verify(pending, CODE).data["code"], "wrong_code")
        self.assertEqual(self.verify(pending, "864200").status_code, 201)

    def test_three_codes_an_hour_per_email(self):
        pending = self.start().data["pending_id"]
        for _send in range(2):
            self.clock += 61
            self.assertEqual(self.resend(pending).status_code, 202)
        self.clock += 61
        capped = self.resend(pending)
        self.assertEqual((capped.status_code, capped.data["code"]), (429, "too_many_codes"))
        self.assertGreater(capped.data["retry_after"], 3000)
        # The same address from another network is still capped …
        other = self.start(ip="10.9.9.9")
        self.assertEqual((other.status_code, other.data["code"]), (429, "too_many_codes"))
        # … until the hour has passed.
        self.clock += 3600
        self.assertEqual(self.start(ip="10.9.9.9").status_code, 202)

    def test_three_codes_an_hour_per_client_address(self):
        for index in range(3):
            response = self.start(
                email=f"p{index}@example.test", phone=f"09{index}0000000",
                company_name=f"Shop {index}", contact_name=f"Person {index}",
            )
            self.assertEqual(response.status_code, 202, response.data)
        capped = self.start(email="p9@example.test", phone="0990000000",
                            company_name="Shop 9", contact_name="Person 9")
        self.assertEqual((capped.status_code, capped.data["code"]), (429, "too_many_codes"))

    def test_the_endpoints_are_throttled_per_address(self):
        for _try in range(10):
            self.client.post(reverse("registration-request"), {}, format="json",
                             REMOTE_ADDR="10.2.0.1")
        response = self.client.post(reverse("registration-request"), {}, format="json",
                                    REMOTE_ADDR="10.2.0.1")
        self.assertEqual(response.status_code, 429)

    @override_settings(EMAIL_ENABLED=False)
    def test_without_email_the_form_says_so_and_keeps_nothing(self):
        SeoSettings.objects.create(support_whatsapp="+249 91 234 5678")
        response = self.start()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "email_unavailable")
        self.assertEqual(response.data["whatsapp"], "+249 91 234 5678")
        self.assertFalse(RegistrationRequest.objects.exists())

    def test_a_replayed_verify_returns_the_same_request(self):
        pending = self.start().data["pending_id"]
        first = self.verify(pending)
        again = self.verify(pending)
        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.assertEqual(again.data["public_reference"], first.data["public_reference"])
        self.assertEqual(RegistrationRequest.objects.count(), 1)

    def test_a_replayed_form_after_verify_answers_without_a_new_code(self):
        body = self.body()
        with mock.patch("core.otp.new_code", return_value=CODE):
            pending = self.client.post(reverse("registration-request"), body,
                                       format="json").data["pending_id"]
        created = self.verify(pending)
        sent = len(mail.outbox)
        replay = self.client.post(reverse("registration-request"), body, format="json")
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.data["public_reference"], created.data["public_reference"])
        self.assertEqual(len(mail.outbox), sent)

    def test_the_team_hears_only_after_the_code(self):
        with mock.patch("core.team_notify.registration_submitted") as notice:
            pending = self.start().data["pending_id"]
            self.verify(pending, "111111")
            notice.assert_not_called()
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(self.verify(pending).status_code, 201)
            notice.assert_called_once()
            self.verify(pending)
            notice.assert_called_once()

    def test_no_pending_migrations(self):
        """The whole feature lives in the cache: production refuses migrations."""
        out = StringIO()
        try:
            call_command("makemigrations", "--check", "--dry-run", stdout=out, stderr=out)
        except SystemExit:
            self.fail(f"makemigrations found model changes:\n{out.getvalue()}")


class DuplicateTests(TrialOtpBase):
    def assertDuplicate(self, response):
        self.assertEqual(response.status_code, 409, getattr(response, "data", None))
        self.assertEqual(response.data["code"], "duplicate_request")
        self.assertNotIn("pending_id", response.data)
        self.assertEqual(set(response.data), {"code", "detail", "message", "whatsapp"})
        body = response.content.decode()
        for leak in ("email", "phone", "company_name", "contact_name", "Old Company"):
            self.assertNotIn(leak, body)

    def unrelated(self, **fields):
        """A form sharing nothing with ``existing()`` except ``fields``."""
        data = {"email": "new@example.test", "phone": "0922222222",
                "company_name": "Fresh Shop", "contact_name": "New Person"}
        data.update(fields)
        return self.start(**data)

    def test_email_matches_whatever_the_case(self):
        self.existing(email="Old@Example.test")
        self.assertDuplicate(self.unrelated(email="OLD@example.TEST"))

    def test_phone_matches_in_every_format(self):
        self.existing(phone="0912345678")
        for phone in ("+249912345678", "00249 91 234 5678", "0912 345 678", "٠٩١٢٣٤٥٦٧٨"):
            cache.clear()
            self.assertDuplicate(self.unrelated(phone=phone))

    def test_company_name_matches_after_arabic_folding(self):
        self.existing(company_name="مؤسسة الإخاء التجارية")
        self.assertDuplicate(self.unrelated(company_name="  مؤسسه  الاخاء التجاريه "))

    def test_contact_name_matches_after_folding(self):
        self.existing(contact_name="أحمد عليّ")
        self.assertDuplicate(self.unrelated(contact_name="احمد   علي"))
        cache.clear()
        self.existing(contact_name="Sara Musa", email="s@x.test", phone="0933333333",
                      company_name="S Co")
        self.assertDuplicate(self.unrelated(contact_name="SARA musa"))

    def test_every_open_or_provisioned_state_blocks(self):
        row = self.existing()
        for state in (RegistrationRequest.SUBMITTED, RegistrationRequest.UNDER_REVIEW,
                      RegistrationRequest.NEEDS_INFORMATION, RegistrationRequest.APPROVED,
                      RegistrationRequest.PROVISIONED):
            RegistrationRequest.objects.filter(pk=row.pk).update(status=state)
            cache.clear()
            self.assertDuplicate(self.unrelated(email="old@example.test"))

    def test_rejected_and_withdrawn_requests_do_not_block(self):
        row = self.existing()
        for state in (RegistrationRequest.REJECTED, RegistrationRequest.WITHDRAWN):
            RegistrationRequest.objects.filter(pk=row.pk).update(status=state)
            cache.clear()
            response = self.start(email="old@example.test", phone="0111000000",
                                  company_name="Old Company", contact_name="Somebody Else")
            self.assertEqual(response.status_code, 202, response.data)

    def test_the_whatsapp_link_comes_from_the_seo_settings(self):
        SeoSettings.objects.create(support_whatsapp="+249 91 000 0000")
        self.existing()
        response = self.unrelated(email="old@example.test")
        self.assertEqual(response.data["whatsapp"], "+249 91 000 0000")
        self.assertIn("ar", response.data["message"])
        self.assertIn("en", response.data["message"])

    def test_the_existing_address_gets_its_reference_once_an_hour(self):
        row = self.existing()
        self.assertDuplicate(self.unrelated(phone="0111000000"))
        self.assertDuplicate(self.unrelated(phone="0111000000"))
        self.assertEqual(len(mail.outbox), 1)
        notice = mail.outbox[0]
        # The address on file, never the one just typed.
        self.assertEqual(notice.to, ["old@example.test"])
        self.assertIn(row.public_reference, notice.body)
        self.assertIn("/track/", notice.body)
        self.assertNotIn(row.public_reference, self.unrelated(phone="0111000000")
                         .content.decode())

    def test_duplicates_are_checked_again_at_verify(self):
        pending = self.start().data["pending_id"]
        # Another tab finished first.
        self.existing(email="amina@northwind.test")
        response = self.verify(pending)
        self.assertDuplicate(response)
        self.assertEqual(RegistrationRequest.objects.count(), 1)
        self.assertEqual(self.verify(pending).data["code"], "code_expired")

    def test_the_duplicate_check_is_one_query(self):
        self.existing()
        with self.assertNumQueries(1):
            trial_requests.find_duplicate(self.body())
