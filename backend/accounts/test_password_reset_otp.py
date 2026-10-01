"""Password reset by email code (owner decision 2026-10-01: no links).

email -> 6-digit code -> 10-minute single-use reset token -> new password.
The request answers identically for known and unknown addresses; an
administrator's reset sends the person a code too, and no API answer ever
carries a code."""

import logging
from io import StringIO
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts import password_reset
from accounts.models import Role, User
from core import otp
from core.models import ActivityLog
from org.models import Company

MAIL = {
    "EMAIL_ENABLED": True,
    "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    "PUBLIC_APP_ORIGIN": "https://vezano.test",
    "PASSWORD_RESET_EMAIL_BACKGROUND": False,
}
CODE = "246810"
OLD = "Old-passw0rd!x"
NEW = "Brand-new-passw0rd"


@override_settings(**MAIL)
class ResetBase(TestCase):
    def setUp(self):
        cache.clear()
        self.company = Company.objects.create(name="Alpha", business_type="enterprise")
        self.owner_role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.clerk_role = Role.objects.create(
            name="Sales Officer", scope_level=Role.SCOPE_BUSINESS)
        self.user = User.objects.create_user(
            email="owner@alpha.test", password=OLD, company=self.company,
            role=self.owner_role, full_name="Owner One",
        )
        self.client = APIClient()
        self.clock = 1_900_000_000.0
        patcher = mock.patch("core.otp.now", side_effect=lambda: self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)

    def request_code(self, email="owner@alpha.test", code=CODE, client=None):
        with mock.patch("core.otp.new_code", return_value=code):
            return (client or self.client).post(
                "/api/auth/password-reset/", {"email": email}, format="json")

    def verify(self, challenge_id, code=CODE):
        return self.client.post("/api/auth/password-reset/verify/",
                                {"challenge_id": challenge_id, "code": code}, format="json")

    def resend(self, challenge_id, code=CODE):
        with mock.patch("core.otp.new_code", return_value=code):
            return self.client.post("/api/auth/password-reset/resend/",
                                    {"challenge_id": challenge_id}, format="json")

    def confirm(self, token, password=NEW):
        return self.client.post("/api/auth/password-reset/confirm/",
                                {"reset_token": token, "password": password}, format="json")

    def token(self):
        challenge = self.request_code().data["challenge_id"]
        response = self.verify(challenge)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data["reset_token"]


class RequestTests(ResetBase):
    def test_known_and_unknown_addresses_get_the_same_answer(self):
        known = self.request_code("Owner@Alpha.test")
        unknown = self.request_code("nobody@alpha.test")
        self.assertEqual(known.status_code, 202)
        self.assertEqual(unknown.status_code, 202)
        self.assertEqual(set(known.data), set(unknown.data))
        self.assertEqual(set(known.data), {"challenge_id", "resend_after", "expires_in",
                                           "email_enabled"})
        for key in ("resend_after", "expires_in", "email_enabled"):
            self.assertEqual(known.data[key], unknown.data[key])
        self.assertEqual(len(known.data["challenge_id"]), len(unknown.data["challenge_id"]))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["owner@alpha.test"])

    def test_the_email_carries_the_code_and_no_link(self):
        self.request_code()
        message = mail.outbox[0]
        self.assertIn(CODE, message.body)
        self.assertNotIn(CODE, message.subject)
        self.assertNotIn("reset-password", message.body)
        self.assertNotIn("http", message.body.split("—")[0].replace("https://vezano", ""))
        html = message.alternatives[0][0]
        self.assertIn(CODE, html)
        self.assertNotIn("/reset-password", html)
        self.assertNotIn("/forgot-password", html)
        self.assertIn("password reset code", message.subject)
        self.assertIn("valid for 10 minutes", html)  # the preheader

    def test_an_inactive_account_gets_nothing_but_the_same_answer(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.request_code()
        self.assertEqual(response.status_code, 202)
        self.assertIn("challenge_id", response.data)
        self.assertEqual(len(mail.outbox), 0)

    def test_an_unknown_address_challenge_never_verifies(self):
        challenge = self.request_code("nobody@alpha.test").data["challenge_id"]
        for left in (4, 3, 2, 1):
            response = self.verify(challenge)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data["code"], "wrong_code")
            self.assertEqual(response.data["attempts_left"], left)
        self.assertEqual(self.verify(challenge).data["code"], "too_many_attempts")

    def test_resend_and_budget_behave_alike_for_unknown_addresses(self):
        for email in ("owner@alpha.test", "nobody@alpha.test"):
            cache.clear()
            challenge = self.request_code(email).data["challenge_id"]
            self.assertEqual(self.resend(challenge).data["code"], "resend_cooldown")
            self.clock += 61
            self.assertEqual(self.resend(challenge).status_code, 202)
            self.clock += 61
            self.assertEqual(self.resend(challenge).status_code, 202)
            self.clock += 61
            capped = self.resend(challenge)
            self.assertEqual(capped.status_code, 429, email)
            self.assertEqual(capped.data["code"], "too_many_codes")
            self.assertGreater(capped.data["retry_after"], 0)

    @override_settings(EMAIL_ENABLED=False)
    def test_reports_when_this_server_cannot_email(self):
        response = self.request_code()
        self.assertEqual(response.status_code, 202)
        self.assertFalse(response.data["email_enabled"])
        self.assertEqual(len(mail.outbox), 0)
        # Nothing to verify: every challenge is a decoy here.
        self.assertEqual(self.verify(response.data["challenge_id"]).data["code"], "wrong_code")

    def test_the_request_is_logged_without_the_code(self):
        self.request_code()
        row = ActivityLog.objects.get(action="password_reset_requested")
        self.assertEqual(row.entity_id, str(self.user.pk))
        self.assertNotIn(CODE, str(row.metadata))

    def test_a_bad_email_is_refused(self):
        response = self.client.post("/api/auth/password-reset/", {"email": "nope"},
                                    format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)

    def test_codes_are_never_logged(self):
        with self.assertLogs(level=logging.DEBUG) as captured:
            logging.getLogger("accounts").debug("start")
            challenge = self.request_code().data["challenge_id"]
            self.verify(challenge, "000000")
            self.clock += 61
            self.resend(challenge, code="975310")
            self.verify(challenge, "975310")
            self.request_code("nobody@alpha.test", code="864200")
        text = "\n".join(record.getMessage() for record in captured.records)
        for code in (CODE, "975310", "864200"):
            self.assertNotIn(code, text)
        self.assertIn("otp issued", text)


class CodeTests(ResetBase):
    def test_happy_path_sets_the_password_and_ends_sessions(self):
        login = self.client.post(
            "/api/auth/login/", {"email": "owner@alpha.test", "password": OLD,
                                 "device_id": "TEST"}, format="json")
        self.assertEqual(login.status_code, 200)
        challenge = self.request_code().data["challenge_id"]
        verified = self.verify(challenge)
        self.assertEqual(verified.status_code, 200, verified.data)
        self.assertEqual(set(verified.data), {"reset_token", "expires_in"})
        self.assertEqual(verified.data["expires_in"], 600)
        done = self.confirm(verified.data["reset_token"])
        self.assertEqual(done.status_code, 200, done.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW))
        self.assertFalse(self.user.must_change_password)
        # The refresh token from before the reset is dead.
        self.assertEqual(self.client.post("/api/auth/refresh/", {}, format="json").status_code,
                         401)
        self.assertTrue(ActivityLog.objects.filter(action="password_reset",
                                                   entity_id=str(self.user.pk)).exists())

    def test_a_code_works_once(self):
        challenge = self.request_code().data["challenge_id"]
        self.assertEqual(self.verify(challenge).status_code, 200)
        self.assertEqual(self.verify(challenge).data["code"], "code_expired")

    def test_wrong_code_then_too_many_attempts(self):
        challenge = self.request_code().data["challenge_id"]
        response = self.verify(challenge, "111111")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "wrong_code")
        self.assertEqual(response.data["attempts_left"], 4)
        for _try in range(3):
            self.verify(challenge, "111111")
        self.assertEqual(self.verify(challenge, "111111").data["code"], "too_many_attempts")
        # Even the right code is no use now.
        self.assertEqual(self.verify(challenge).data["code"], "code_expired")

    def test_a_code_expires_after_ten_minutes(self):
        challenge = self.request_code().data["challenge_id"]
        self.clock += otp.CODE_TTL + 1
        response = self.verify(challenge)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "code_expired")

    def test_resend_cooldown_new_code_and_cap(self):
        challenge = self.request_code().data["challenge_id"]
        early = self.resend(challenge, code="999999")
        self.assertEqual(early.status_code, 429)
        self.assertEqual(early.data["code"], "resend_cooldown")
        self.clock += 61
        again = self.resend(challenge, code="999999")
        self.assertEqual(again.status_code, 202)
        self.assertEqual(set(again.data), {"challenge_id", "resend_after", "expires_in"})
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("999999", mail.outbox[-1].body)
        # The first code stopped working.
        self.assertEqual(self.verify(challenge, CODE).data["code"], "wrong_code")
        self.clock += 61
        self.assertEqual(self.resend(challenge).status_code, 202)
        self.clock += 61
        self.assertEqual(self.resend(challenge).data["code"], "too_many_codes")
        # And a fresh request for the same account is over the hour too.
        self.assertEqual(self.request_code().status_code, 429)

    def test_a_deactivated_account_cannot_finish(self):
        challenge = self.request_code().data["challenge_id"]
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.verify(challenge).data["code"], "code_expired")


class TokenTests(ResetBase):
    def test_a_token_is_single_use(self):
        token = self.token()
        self.assertEqual(self.confirm(token).status_code, 200)
        again = self.confirm(token, "Another-passw0rd!")
        self.assertEqual(again.status_code, 400)
        self.assertEqual(again.data["code"], "reset_expired")

    def test_a_weak_password_keeps_the_token(self):
        token = self.token()
        weak = self.confirm(token, "short")
        self.assertEqual(weak.status_code, 400)
        self.assertIn("password", weak.data)
        common = self.confirm(token, "password123")
        self.assertEqual(common.status_code, 400)
        self.assertIn("password", common.data)
        self.assertEqual(self.confirm(token).status_code, 200)

    def test_a_token_dies_when_the_password_changes(self):
        token = self.token()
        self.user.set_password("Changed-elsewhere-1!")
        self.user.save(update_fields=["password"])
        self.assertEqual(self.confirm(token).data["code"], "reset_expired")

    def test_a_token_dies_on_a_sign_in(self):
        token = self.token()
        User.objects.filter(pk=self.user.pk).update(last_login=timezone.now())
        self.assertEqual(self.confirm(token).data["code"], "reset_expired")

    def test_a_token_expires_after_ten_minutes(self):
        token = self.token()
        self.clock += password_reset.TOKEN_TTL + 1
        self.assertEqual(self.confirm(token).data["code"], "reset_expired")

    def test_a_forged_token_is_refused(self):
        self.assertEqual(self.confirm("not-a-token").data["code"], "reset_expired")
        self.assertEqual(self.client.post("/api/auth/password-reset/confirm/",
                                          {"password": NEW}, format="json").status_code, 400)

    def test_the_old_link_shape_is_retired(self):
        response = self.client.post(
            "/api/auth/password-reset/confirm/",
            {"uid": "MQ", "token": "abc-123", "password": NEW}, format="json")
        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.data["code"], "link_flow_retired")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD))


class AdminResetTests(ResetBase):
    def setUp(self):
        super().setUp()
        self.clerk = User.objects.create_user(
            email="clerk@alpha.test", password="Clerk-passw0rd!x", company=self.company,
            role=self.clerk_role, full_name="Clerk Two",
        )
        self.admin = APIClient()
        self.admin.force_authenticate(self.user)

    def send(self, target=None, client=None):
        with mock.patch("core.otp.new_code", return_value=CODE):
            return (client or self.admin).post(
                f"/api/users/{(target or self.clerk).pk}/send-reset-code/", {}, format="json")

    def test_sends_a_code_with_a_link_to_the_code_step(self):
        response = self.send()
        self.assertEqual(response.status_code, 202, response.data)
        self.assertEqual(set(response.data), {"sent", "email_masked", "expires_in"})
        self.assertNotIn(CODE, str(response.data))
        self.assertEqual(response.data["email_masked"], "c•••@alpha.test")
        message = mail.outbox[-1]
        self.assertEqual(message.to, ["clerk@alpha.test"])
        self.assertIn(CODE, message.body)
        self.assertIn("Owner One", message.body)
        self.assertIn("https://vezano.test/forgot-password/?email=clerk%40alpha.test&challenge=",
                      message.body)
        challenge = message.body.split("challenge=", 1)[1].split()[0]
        # The person finishes on the same page with that challenge.
        token = self.verify(challenge).data["reset_token"]
        self.assertEqual(self.confirm(token).status_code, 200)
        self.clerk.refresh_from_db()
        self.assertTrue(self.clerk.check_password(NEW))
        row = ActivityLog.objects.get(action="password_reset_code_by_admin")
        self.assertEqual(row.user_id, self.user.pk)
        self.assertEqual(row.entity_id, str(self.clerk.pk))
        self.assertNotIn(CODE, str(row.metadata))

    def test_the_password_is_untouched_until_the_person_acts(self):
        self.send()
        self.clerk.refresh_from_db()
        self.assertTrue(self.clerk.check_password("Clerk-passw0rd!x"))

    def test_a_peer_or_senior_is_refused(self):
        clerk_client = APIClient()
        clerk_client.force_authenticate(self.clerk)
        response = self.send(self.user, clerk_client)
        self.assertIn(response.status_code, (403, 404))
        self.assertEqual(len(mail.outbox), 0)

    def test_not_for_yourself(self):
        self.assertEqual(self.send(self.user).status_code, 400)

    @override_settings(EMAIL_ENABLED=False)
    def test_says_when_email_cannot_go_out(self):
        response = self.send()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "email_unavailable")
        self.assertNotIn(CODE, str(response.data))

    def test_platform_team_member_gets_a_code(self):
        root = User.objects.create_superuser("root@vezano.test", "secure-password")
        support = Role.objects.create(name="Support Agent", scope_level=Role.SCOPE_PLATFORM)
        member = User.objects.create_user(email="ops@vezano.test", password="Ops-passw0rd!x",
                                          full_name="Ops", role=support)
        client = APIClient()
        client.force_authenticate(root)
        with mock.patch("core.otp.new_code", return_value=CODE):
            response = client.post(f"/api/platform/team/{member.pk}/send-reset-code/", {},
                                   format="json")
        self.assertEqual(response.status_code, 202, response.data)
        self.assertNotIn(CODE, str(response.data))
        self.assertEqual(mail.outbox[-1].to, ["ops@vezano.test"])
        self.assertIn("/forgot-password/?email=ops%40vezano.test", mail.outbox[-1].body)


class NoMigrationTests(TestCase):
    def test_no_model_changes(self):
        out = StringIO()
        try:
            call_command("makemigrations", "--check", "--dry-run", stdout=out, stderr=out)
        except SystemExit:
            self.fail(f"makemigrations found model changes:\n{out.getvalue()}")
