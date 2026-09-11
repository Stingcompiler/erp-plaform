from uuid import uuid4
from django.urls import reverse
from rest_framework.test import APITestCase
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
