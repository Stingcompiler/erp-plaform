from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role, User
from crm.models import CustomerGroup, FollowUp, Lead, Note
from org.models import Branch, Company


class CrmBase(APITestCase):
    def setUp(self):
        self.company_a = Company.objects.create(name="Alpha")
        self.company_b = Company.objects.create(name="Beta")
        self.branch_a = Branch.objects.create(company=self.company_a, name="Main")
        self.branch_b = Branch.objects.create(company=self.company_b, name="Main")
        self.role = Role.objects.create(
            name="CRM Officer", scope_level=Role.SCOPE_BRANCH
        )
        self.user_a = User.objects.create_user(
            email="a@alpha.test", password="passw0rd123",
            company=self.company_a, branch=self.branch_a, role=self.role,
        )
        self.group_a = CustomerGroup.objects.create(
            company=self.company_a, name="Wholesale"
        )
        self.group_b = CustomerGroup.objects.create(
            company=self.company_b, name="Beta Group"
        )
        r = self.client.post(
            reverse("auth-login"),
            {"email": "a@alpha.test", "password": "passw0rd123", "device_id": "TEST"},
        )
        assert r.status_code == 200, r.content

    def make_lead(self, **kw):
        payload = {"name": "Prospect Co", "stage": "new", **kw}
        return self.client.post(reverse("lead-list"), payload, format="json")


class LeadTests(CrmBase):
    def test_create_lead_forces_company_and_created_by(self):
        resp = self.make_lead(estimated_value="5000.00")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        lead = Lead.objects.get(pk=resp.data["id"])
        self.assertEqual(lead.company_id, self.company_a.id)
        self.assertEqual(lead.created_by_id, self.user_a.id)

    def test_cannot_attach_other_company_group(self):
        resp = self.make_lead(customer_group=self.group_b.id)
        # The group is scoped out of the field queryset -> invalid pk.
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)

    def test_list_is_company_scoped(self):
        self.make_lead()
        Lead.objects.create(
            company=self.company_b, branch=self.branch_b, name="Beta Lead"
        )
        resp = self.client.get(reverse("lead-list"))
        self.assertEqual(resp.status_code, 200)
        names = [row["name"] for row in resp.data["results"]]
        self.assertIn("Prospect Co", names)
        self.assertNotIn("Beta Lead", names)

    def test_pipeline_summary(self):
        self.make_lead(stage="new", estimated_value="1000.00")
        self.make_lead(stage="won", estimated_value="2000.00")
        resp = self.client.get(reverse("lead-pipeline"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["new"]["count"], 1)
        self.assertEqual(resp.data["won"]["count"], 1)

    def test_open_filter_excludes_closed(self):
        self.make_lead(stage="new")
        self.make_lead(stage="won")
        resp = self.client.get(reverse("lead-list"), {"open": "1"})
        stages = [row["stage"] for row in resp.data["results"]]
        self.assertIn("new", stages)
        self.assertNotIn("won", stages)


class FollowUpNoteTests(CrmBase):
    def setUp(self):
        super().setUp()
        self.lead = Lead.objects.create(
            company=self.company_a, branch=self.branch_a, name="Lead One"
        )

    def test_followup_marks_done_stamps_time(self):
        resp = self.client.post(
            reverse("followup-list"),
            {"lead": self.lead.id, "due_date": "2026-08-01", "summary": "Call back"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        fu_id = resp.data["id"]
        patch = self.client.patch(
            reverse("followup-detail", args=[fu_id]), {"done": True}, format="json"
        )
        self.assertEqual(patch.status_code, 200, patch.content)
        self.assertIsNotNone(FollowUp.objects.get(pk=fu_id).done_at)

    def test_note_records_author(self):
        resp = self.client.post(
            reverse("crmnote-list"),
            {"lead": self.lead.id, "body": "Spoke to buyer."},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Note.objects.get(pk=resp.data["id"]).created_by_id, self.user_a.id)

    def test_notes_filtered_by_lead(self):
        Note.objects.create(company=self.company_a, lead=self.lead, body="A")
        other = Lead.objects.create(
            company=self.company_a, branch=self.branch_a, name="Lead Two"
        )
        Note.objects.create(company=self.company_a, lead=other, body="B")
        resp = self.client.get(reverse("crmnote-list"), {"lead": self.lead.id})
        bodies = [row["body"] for row in resp.data["results"]]
        self.assertEqual(bodies, ["A"])
