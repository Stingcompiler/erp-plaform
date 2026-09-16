"""Follow-ups on leads and registration requests: notes, next date, contact
clicks logged, due items counted by the attention badge."""
from datetime import timedelta
from uuid import uuid4

from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User
from core.attention import counts_for
from core.models import ActivityLog
from website.models import PlatformLead, RegistrationRequest


class FollowUpTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.root = User.objects.create_superuser("root@vezano.test", "secure-password")
        self.client.force_authenticate(self.root)
        self.lead = PlatformLead.objects.create(
            request_uuid=uuid4(), name="Shop", phone="0912345678"
        )
        self.registration = RegistrationRequest.objects.create(
            request_uuid=uuid4(), company_name="Co", contact_name="C", email="c@co.test",
            phone="+249912345678", country="SD", privacy_version="2026-09",
            delivery_mode="saas",
        )

    def test_note_and_next_follow_up_are_editable(self):
        soon = (timezone.now() + timedelta(days=2)).isoformat()
        lead = self.client.patch(
            reverse("platform-lead-detail", args=[self.lead.pk]),
            {"internal_note": "call after Eid", "next_follow_up_at": soon}, format="json",
        )
        self.assertEqual(lead.status_code, 200, lead.data)
        self.assertEqual(lead.data["internal_note"], "call after Eid")
        self.assertFalse(lead.data["follow_up_due"])
        registration = self.client.patch(
            reverse("platform-registration-request-detail", args=[self.registration.pk]),
            {"internal_note": "waiting for plan", "next_follow_up_at": soon}, format="json",
        )
        self.assertEqual(registration.status_code, 200, registration.data)
        self.assertEqual(registration.data["internal_note"], "waiting for plan")
        rows = ActivityLog.objects.filter(action="update").order_by("pk")
        self.assertEqual(
            [row.metadata["fields"] for row in rows],
            [["internal_note", "next_follow_up_at"], ["internal_note", "next_follow_up_at"]],
        )

    def test_contact_click_is_recorded_and_logged(self):
        url = reverse("platform-lead-contact", args=[self.lead.pk])
        self.assertEqual(self.client.post(url, {"channel": "fax"}, format="json").status_code, 400)
        response = self.client.post(url, {"channel": "whatsapp"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["last_contact_channel"], "whatsapp")
        self.assertIsNotNone(response.data["last_contacted_at"])
        row = ActivityLog.objects.get(action="contact", entity_type="PlatformLead")
        self.assertEqual(row.metadata, {"channel": "whatsapp", "label": "Shop"})
        # Registrations: open to whoever may see them (support agents included).
        invited = self.client.post(
            reverse("platform-team-list"),
            {"email": "support@vezano.test", "full_name": "S", "role": "Support Agent"},
            format="json",
        )
        agent = User.objects.get(pk=invited.data["id"])
        self.client.force_authenticate(agent)
        response = self.client.post(
            reverse("platform-registration-request-contact", args=[self.registration.pk]),
            {"channel": "call"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["last_contact_channel"], "call")
        self.assertEqual(
            ActivityLog.objects.get(action="contact", entity_type="RegistrationRequest").user,
            agent,
        )
        # …but editing the note stays a review right.
        forbidden = self.client.patch(
            reverse("platform-registration-request-detail", args=[self.registration.pk]),
            {"internal_note": "x"}, format="json",
        )
        self.assertEqual(forbidden.status_code, 403)

    def test_due_filter_and_attention_badge(self):
        past = timezone.now() - timedelta(hours=1)
        PlatformLead.objects.filter(pk=self.lead.pk).update(next_follow_up_at=past)
        RegistrationRequest.objects.filter(pk=self.registration.pk).update(
            next_follow_up_at=past
        )
        closed = PlatformLead.objects.create(
            request_uuid=uuid4(), name="Closed", email="x@y.test", status="closed",
            next_follow_up_at=past,
        )
        due = self.client.get(reverse("platform-lead-list"), {"due": "1"}).data["results"]
        self.assertEqual([row["id"] for row in due], [self.lead.pk])
        self.assertTrue(due[0]["follow_up_due"])
        due = self.client.get(
            reverse("platform-registration-request-list"), {"due": "1"}
        ).data["results"]
        self.assertEqual([row["id"] for row in due], [self.registration.pk])
        counts = counts_for(self.root, use_cache=False)["counts"]
        # One new lead + one due follow-up; the closed one does not count.
        self.assertEqual(counts["platform-leads"], 2)
        # One submitted registration + one due follow-up.
        self.assertEqual(counts["platform-registrations"], 2)
        self.assertEqual(PlatformLead.objects.get(pk=closed.pk).status, "closed")
