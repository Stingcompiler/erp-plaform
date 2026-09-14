import os
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from accounts.models import Role, User
from licensing.models import Installation
from org.models import Branch, Company

STRONG = "correct-horse-battery-staple-9"


@override_settings(VEZANO_DEPLOYMENT_MODE="standalone", SUBSCRIPTION_POLICY="enforce")
class CreateOwnerTests(TestCase):
    def run_command(self, *args, password=STRONG):
        with mock.patch.dict(os.environ, {"VEZANO_OWNER_PASSWORD": password}):
            call_command("create_owner", *args, "--password-env", verbosity=0)

    def test_creates_company_branch_roles_and_owner_from_installation(self):
        Installation.objects.create(organisation_name="Acme Trading LLC")
        self.run_command("--email", "owner@acme.example", "--full-name", "Amal")

        company = Company.objects.get()
        self.assertEqual(company.name, "Acme Trading LLC")
        self.assertTrue(company.business_type_chosen)
        branch = Branch.objects.get(company=company)
        self.assertEqual(branch.code, "MAIN")
        owner = User.objects.get(email="owner@acme.example")
        self.assertEqual(owner.company, company)
        self.assertEqual(owner.branch, branch)
        self.assertEqual(owner.role.name, "Business Owner")
        self.assertTrue(owner.check_password(STRONG))
        self.assertTrue(Role.objects.filter(name="Sales Officer").exists())

    def test_second_owner_joins_the_existing_company(self):
        Installation.objects.create(organisation_name="Acme")
        self.run_command("--email", "one@acme.example")
        self.run_command("--email", "two@acme.example")
        self.assertEqual(Company.objects.count(), 1)
        self.assertEqual(User.objects.filter(role__name="Business Owner").count(), 2)

    def test_needs_a_company_name_from_somewhere(self):
        with self.assertRaisesMessage(CommandError, "No company name"):
            self.run_command("--email", "x@acme.example")

    def test_rejects_a_weak_password(self):
        Installation.objects.create(organisation_name="Acme")
        with self.assertRaises(CommandError):
            self.run_command("--email", "x@acme.example", password="password")
        self.assertFalse(User.objects.exists())
        self.assertFalse(Company.objects.exists())

    def test_rejects_duplicate_email(self):
        Installation.objects.create(organisation_name="Acme")
        self.run_command("--email", "x@acme.example")
        with self.assertRaisesMessage(CommandError, "already belongs"):
            self.run_command("--email", "X@acme.example")

    @override_settings(VEZANO_DEPLOYMENT_MODE="saas")
    def test_refused_on_the_hosted_platform(self):
        with self.assertRaisesMessage(CommandError, "standalone"):
            self.run_command("--email", "x@acme.example", "--company-name", "Acme")
