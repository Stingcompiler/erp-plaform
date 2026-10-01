"""core.otp on its own: the purpose-scoped email-code mechanism behind the
trial form and request tracking (and password reset next)."""

from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, override_settings

from core import otp

MAIL = dict(EMAIL_ENABLED=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")


class OtpTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.clock = 1_900_000_000.0
        patcher = mock.patch("core.otp.now", side_effect=lambda: self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.sent = []

    def deliver(self, code):
        self.sent.append(code)
        return True

    def request(self, ip="10.5.0.1"):
        return RequestFactory().post("/", REMOTE_ADDR=ip)

    def issue(self, subject="a@example.test", purpose="test", **kwargs):
        kwargs.setdefault("deliver", self.deliver)
        return otp.issue(purpose, subject, {"who": subject}, **kwargs)

    def test_issue_then_verify_returns_the_payload_once(self):
        challenge = self.issue()
        code = self.sent[-1]
        self.assertRegex(code, r"^\d{6}$")
        self.assertEqual(otp.verify(challenge, code, purpose="test"), {"who": "a@example.test"})
        with self.assertRaises(otp.Expired):
            otp.verify(challenge, code, purpose="test")

    def test_consume_false_keeps_the_challenge(self):
        challenge = self.issue()
        code = self.sent[-1]
        otp.verify(challenge, code, purpose="test", consume=False)
        self.assertEqual(otp.verify(challenge, code, purpose="test"), {"who": "a@example.test"})

    def test_the_code_is_kept_only_as_an_hmac(self):
        challenge = self.issue()
        entry = otp.stored(challenge)
        self.assertNotIn(self.sent[-1], repr(entry))
        self.assertNotIn("a@example.test", repr({k: v for k, v in entry.items() if k != "payload"}))
        self.assertEqual(entry["code_hash"], otp.code_hash("test", self.sent[-1]))
        self.assertNotEqual(otp.code_hash("test", "123456"), otp.code_hash("other", "123456"))

    def test_a_challenge_belongs_to_its_purpose(self):
        challenge = self.issue(purpose="trial")
        with self.assertRaises(otp.Expired):
            otp.verify(challenge, self.sent[-1], purpose="password_reset")
        self.assertTrue(otp.verify(challenge, self.sent[-1], purpose="trial"))

    def test_wrong_codes_then_too_many_attempts(self):
        challenge = self.issue()
        wrong = "000000" if self.sent[-1] != "000000" else "111111"
        left = []
        for _try in range(4):
            with self.assertRaises(otp.WrongCode) as caught:
                otp.verify(challenge, wrong, purpose="test")
            left.append(caught.exception.attempts_left)
        self.assertEqual(left, [4, 3, 2, 1])
        with self.assertRaises(otp.TooManyAttempts):
            otp.verify(challenge, wrong, purpose="test")
        with self.assertRaises(otp.Expired):
            otp.verify(challenge, self.sent[-1], purpose="test")

    def test_a_malformed_code_costs_no_attempt(self):
        challenge = self.issue()
        for _try in range(7):
            with self.assertRaises(otp.WrongCode) as caught:
                otp.verify(challenge, "12", purpose="test")
            self.assertEqual(caught.exception.attempts_left, 5)
        self.assertTrue(otp.verify(challenge, self.sent[-1], purpose="test"))

    def test_arabic_digits_are_read(self):
        challenge = self.issue()
        arabic = self.sent[-1].translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))
        self.assertTrue(otp.verify(challenge, arabic, purpose="test"))

    def test_ten_minutes_then_expired(self):
        challenge = self.issue()
        self.clock += otp.CODE_TTL + 1
        with self.assertRaises(otp.Expired):
            otp.verify(challenge, self.sent[-1], purpose="test")

    def test_resend_cooldown_new_code_and_fresh_tries(self):
        challenge = self.issue()
        first = self.sent[-1]
        with self.assertRaises(otp.Cooldown) as caught:
            otp.resend(challenge, purpose="test", deliver=self.deliver)
        self.assertEqual(caught.exception.retry_after, 60)
        self.clock += 61
        with mock.patch("core.otp.new_code", return_value="424242" if first != "424242"
                        else "434343"):
            self.assertEqual(otp.resend(challenge, purpose="test", deliver=self.deliver),
                             {"who": "a@example.test"})
        second = self.sent[-1]
        with self.assertRaises(otp.WrongCode):
            otp.verify(challenge, first, purpose="test")
        self.assertTrue(otp.verify(challenge, second, purpose="test"))

    def test_three_sends_an_hour_per_subject(self):
        challenge = self.issue()
        for _send in range(2):
            self.clock += 61
            otp.resend(challenge, purpose="test", deliver=self.deliver)
        self.clock += 61
        with self.assertRaises(otp.TooManySends) as caught:
            otp.resend(challenge, purpose="test", deliver=self.deliver)
        self.assertGreater(caught.exception.retry_after, 3000)
        with self.assertRaises(otp.TooManySends):
            self.issue()
        self.issue(purpose="other")  # budgets are per purpose
        self.issue(subject="b@example.test")
        self.clock += 3600
        self.issue()

    def test_three_sends_an_hour_per_client_address(self):
        for index in range(3):
            self.issue(subject=f"s{index}@example.test", request=self.request())
        with self.assertRaises(otp.TooManySends):
            self.issue(subject="s9@example.test", request=self.request())
        self.issue(subject="s9@example.test", request=self.request("10.5.0.2"))
        # Without a request the caller counts addresses itself.
        self.issue(subject="s8@example.test")

    def test_a_failed_delivery_keeps_nothing(self):
        with self.assertRaises(otp.DeliveryFailed):
            otp.issue("test", "a@example.test", deliver=lambda code: False)
        with self.assertRaises(otp.DeliveryFailed):
            otp.issue("test", "a@example.test", deliver=mock.Mock(side_effect=OSError("down")))
        self.assertEqual(
            [key for key in cache._cache if ":otp:" in key and "otp-sends" not in key], []
        )

    def test_mask_and_normalise(self):
        self.assertEqual(otp.mask_email("Musab@Gmail.com"), "M•••@gmail.com")
        self.assertEqual(otp.mask_email("nope"), "")
        self.assertEqual(otp.normalise_code(" 12 34 56 "), "123456")
        self.assertEqual(otp.normalise_code("1234567"), "")

    @override_settings(**MAIL)
    def test_the_code_email_shows_the_code_large_but_not_in_the_subject(self):
        with self.assertLogs("core.otp", "INFO") as logs:
            self.issue(deliver=lambda code: otp.send_code_email(
                "a@example.test", code, subject_ar="رمز", subject_en="Your code",
                ar=["رمزك:"], en=["Your code is above."],
            ))
        message = mail.outbox[0]
        code = otp.normalise_code(message.body.split("\n\n")[1])
        self.assertTrue(code)
        self.assertNotIn(code, message.subject)
        html = message.alternatives[0][0]
        self.assertIn("font-size:34px", html)
        self.assertIn(f">{code}</td>", html)
        self.assertNotIn(code, "\n".join(logs.output))
