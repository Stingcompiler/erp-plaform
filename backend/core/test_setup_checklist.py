"""The dashboard's "get your business ready" checklist.

Each step is worked out from the company's real data, so it ticks itself
off as the owner works. The team step counts people besides the owner
(the owner alone never meant "done"), and publishing the public page is a
step of its own.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Role, User
from org.models import Branch, Company
from website.models import Website


class SetupChecklistTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.owner_role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS,
        )
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=self.owner_role,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def steps(self):
        response = self.client.get("/api/dashboard/")
        self.assertEqual(response.status_code, 200, response.data)
        return {step["key"]: step for step in response.data["setup"]}

    def test_the_owner_alone_does_not_complete_the_team_step(self):
        self.assertFalse(self.steps()["userStep"]["done"])
        cashier = Role.objects.create(name="Cashier", scope_level=Role.SCOPE_BRANCH)
        User.objects.create_user(
            email="cashier@alpha.test", password="passw0rd123",
            company=self.company, role=cashier, branch=self.branch,
        )
        self.assertTrue(self.steps()["userStep"]["done"])

    def test_publishing_the_public_page_is_a_step(self):
        site = Website.objects.create(company=self.company)
        self.assertFalse(self.steps()["websiteStep"]["done"])
        site.is_published = True
        site.save()
        step = self.steps()["websiteStep"]
        self.assertTrue(step["done"])
        self.assertEqual(step["href"], "/website")

    def test_company_step_opens_the_company_tab(self):
        self.assertEqual(self.steps()["companyStep"]["href"], "/settings#company")

    def test_a_role_that_cannot_change_settings_gets_no_checklist(self):
        cashier = Role.objects.create(name="Cashier", scope_level=Role.SCOPE_BRANCH)
        user = User.objects.create_user(
            email="till@alpha.test", password="passw0rd123",
            company=self.company, role=cashier, branch=self.branch,
        )
        self.client.force_authenticate(user)
        response = self.client.get("/api/dashboard/")
        self.assertEqual(response.data["setup"], [])
