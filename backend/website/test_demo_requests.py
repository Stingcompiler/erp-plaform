from uuid import uuid4
from django.urls import reverse
from rest_framework.test import APITestCase
from accounts.models import User
from org.models import Company
from website.models import PlatformLead


class DemoRequestTests(APITestCase):
    def setUp(self):
        self.body = {
            "request_uuid": str(
                uuid4()),
            "name": "Demo visitor",
            "email": "visitor@example.test",
            "message": "Please show the inventory workflow."}

    def test_request_is_saved_to_platform_inbox(self):
        response = self.client.post(reverse("demo-request"), self.body, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(PlatformLead.objects.get().email, self.body["email"])

    def test_retries_are_idempotent(self):
        first = self.client.post(reverse("demo-request"), self.body, format="json")
        again = self.client.post(reverse("demo-request"), self.body, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(again.data, first.data)
        self.assertEqual(PlatformLead.objects.count(), 1)
        self.assertEqual(set(first.data), {"status", "reference"})

    def test_validation_and_throttling(self):
        response = self.client.post(reverse("demo-request"),
                                    {**self.body, "email": "bad"}, format="json")
        self.assertEqual(response.status_code, 400)
        for _ in range(4):
            self.client.post(reverse("demo-request"), self.body, format="json")
        response = self.client.post(reverse("demo-request"), self.body, format="json")
        self.assertEqual(response.status_code, 429)

    def test_platform_admin_can_manage_inbox_but_tenant_user_cannot(self):
        lead = PlatformLead.objects.create(
            request_uuid=uuid4(), name="Prospect", email="prospect@example.test"
        )
        tenant = Company.objects.create(name="Tenant")
        member = User.objects.create_user("member@example.test", "pass", company=tenant)
        self.client.force_authenticate(member)
        self.assertEqual(self.client.get("/api/platform/leads/").status_code, 403)

        admin = User.objects.create_superuser("admin@example.test", "pass")
        self.client.force_authenticate(admin)
        response = self.client.get("/api/platform/leads/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["email"], lead.email)
        response = self.client.patch(
            f"/api/platform/leads/{lead.pk}/", {"status": "contacted"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        lead.refresh_from_db()
        self.assertEqual(lead.status, "contacted")
