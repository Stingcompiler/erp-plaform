from uuid import uuid4
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from core.models import ActivityLog
from crm.models import Lead, Note
from org.models import Company


class DemoRequestTests(APITestCase):
    def setUp(self):
        self.owner = Company.objects.create(name="Platform owner")
        self.other = Company.objects.create(name="Other tenant")
        self.body = {
            "request_uuid": str(
                uuid4()),
            "name": "Demo visitor",
            "email": "visitor@example.test",
            "message": "Please show the inventory workflow."}

    def test_disabled_is_honest_not_fake_success(self):
        with override_settings(DEMO_REQUEST_COMPANY_SLUG=""):
            response = self.client.post(reverse("demo-request"), self.body, format="json")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(Lead.objects.exists())

    def test_saved_once_to_configured_tenant_and_audited(self):
        body = {**self.body, "company": self.other.pk}
        with override_settings(DEMO_REQUEST_COMPANY_SLUG=self.owner.slug):
            first = self.client.post(reverse("demo-request"), body, format="json")
            again = self.client.post(reverse("demo-request"), body, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(again.data, first.data)
        self.assertEqual(Lead.objects.count(), 1)
        self.assertEqual(Lead.objects.get().company_id, self.owner.pk)
        self.assertEqual(Note.objects.get().body, self.body["message"])
        self.assertEqual(ActivityLog.objects.filter(company=self.owner, action="create").count(), 2)
        self.assertEqual(set(first.data), {"status", "reference"})

    def test_validation_and_throttling(self):
        with override_settings(DEMO_REQUEST_COMPANY_SLUG=self.owner.slug):
            response = self.client.post(reverse("demo-request"),
                                        {**self.body, "email": "bad"}, format="json")
            self.assertEqual(response.status_code, 400)
            for _ in range(4):
                self.client.post(reverse("demo-request"), self.body, format="json")
            response = self.client.post(reverse("demo-request"), self.body, format="json")
            self.assertEqual(response.status_code, 429)
