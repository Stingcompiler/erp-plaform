"""Validation messages reach the person in the language they are reading.

The frontend stores the UI language in the `erp_language` cookie;
LocaleMiddleware reads it, so the same refusal comes back in Arabic to an
Arabic screen and in English to an English one. Placeholders survive
translation, and the catalogue must cover every wrapped message.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import translation
from rest_framework.test import APIClient

from accounts.models import Role, User
from inventory.models import Warehouse
from org.models import Branch, Company
from sales.models import Invoice


class CatalogueTests(SimpleTestCase):
    def test_arabic_catalogue_is_complete_and_compiled(self):
        po = Path(settings.BASE_DIR) / "locale" / "ar" / "LC_MESSAGES" / "django.po"
        mo = po.with_suffix(".mo")
        self.assertTrue(mo.exists(), "run manage.py compilemessages -l ar")
        text = po.read_text(encoding="utf-8")
        empty = re.findall(r'msgid "([^"]+)"\nmsgstr ""', text)
        self.assertEqual(empty, [], f"untranslated: {empty[:5]}")

    def test_placeholders_survive_translation(self):
        with translation.override("ar"):
            template = translation.gettext("Amount exceeds the balance due (%(due)s).")
            msg = template % {"due": "250.00"}
        self.assertIn("250.00", msg)
        self.assertIn("المستحق", msg)


class LanguageNegotiationTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.user = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123", company=self.company, role=role,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        warehouse = Warehouse.objects.create(company=self.company, branch=self.branch, name="W")
        self.invoice = Invoice.objects.create(
            company=self.company, branch=self.branch, warehouse=warehouse, number=1,
            total="100.00", subtotal="100.00",
        )

    def _post_bad_payment(self, language=None):
        if language:
            self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
        # A negative amount is refused by our own serializer rule.
        return self.client.post(
            "/api/payments/",
            {"invoice": self.invoice.pk, "method": "cash", "amount": "-1",
             "client_uuid": "11111111-1111-4111-8111-111111111111"},
            format="json",
        )

    def test_arabic_cookie_gets_arabic_message(self):
        response = self._post_bad_payment("ar")
        self.assertEqual(response.status_code, 400)
        self.assertIn("المبلغ يجب أن يكون موجبًا", str(response.data))

    def test_english_cookie_gets_english_message(self):
        response = self._post_bad_payment("en")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Amount must be positive", str(response.data))

    @override_settings(LANGUAGE_CODE="ar")
    def test_no_cookie_falls_back_to_the_site_default(self):
        response = self._post_bad_payment()
        self.assertEqual(response.status_code, 400)
        self.assertIn("المبلغ يجب أن يكون موجبًا", str(response.data))


class MalformedClientUuidTests(TestCase):
    """A typo in the idempotency key is a 400, not a 500."""

    def test_bad_client_uuid_is_refused_cleanly(self):
        company = Company.objects.create(name="Beta")
        role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        user = User.objects.create_user(
            email="owner@beta.test", password="passw0rd123", company=company, role=role,
        )
        client = APIClient()
        client.force_authenticate(user)
        response = client.post(
            "/api/payments/",
            {"invoice": 1, "method": "cash", "amount": "1", "client_uuid": "not-a-uuid"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("client_uuid", response.data)
