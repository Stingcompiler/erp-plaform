"""Removing a user account: gone when it is unused, deactivated when its
name is on the company's records — and never the last owner or yourself."""
from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from core.models import ActivityLog
from inventory.models import Warehouse
from org.models import Branch, Company
from sales.models import Customer, Invoice, Payment


class AccountRemovalTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha Trading")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.owner_role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        self.sales_role = Role.objects.create(
            name="Sales Officer", scope_level=Role.SCOPE_BRANCH
        )
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=self.owner_role,
        )
        self.cashier = User.objects.create_user(
            email="cashier@alpha.test", password="passw0rd123",
            company=self.company, role=self.sales_role, branch=self.branch,
        )
        self.client.post(
            reverse("auth-login"),
            {"email": "owner@alpha.test", "password": "passw0rd123", "device_id": "TEST"},
        )

    def _remove(self, user):
        return self.client.post(f"/api/users/{user.pk}/remove/")

    def _invoice_paid_by(self, user):
        warehouse = Warehouse.objects.create(
            company=self.company, branch=self.branch, name="W",
        )
        customer = Customer.objects.create(company=self.company, name="C")
        invoice = Invoice.objects.create(
            company=self.company, customer=customer, warehouse=warehouse, number=1,
            subtotal=Decimal("100"), total=Decimal("100"),
        )
        Payment.objects.create(
            company=self.company, invoice=invoice, amount=Decimal("100"),
            method="cash", recorded_by=user,
        )

    def test_an_unused_account_is_deleted(self):
        response = self._remove(self.cashier)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["removed"])
        self.assertFalse(User.objects.filter(pk=self.cashier.pk).exists())
        entry = ActivityLog.objects.filter(action="delete", entity_type="User").first()
        self.assertEqual(entry.metadata["target_email"], "cashier@alpha.test")

    def test_an_account_with_records_is_deactivated_and_says_why(self):
        # The cashier's name is on a payment: deleting the row would strip it
        # off the document that proves who took the money.
        self._invoice_paid_by(self.cashier)
        response = self._remove(self.cashier)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["removed"])
        self.assertEqual(response.data["code"], "kept_for_audit")
        self.assertEqual(response.data["records"]["sales.Payment"], 1)
        self.cashier.refresh_from_db()
        self.assertFalse(self.cashier.is_active)
        self.assertEqual(Payment.objects.get().recorded_by, self.cashier)

    def test_signing_in_is_over_either_way(self):
        self._invoice_paid_by(self.cashier)
        self._remove(self.cashier)
        client = self.client_class()
        refused = client.post(
            reverse("auth-login"),
            {"email": "cashier@alpha.test", "password": "passw0rd123", "device_id": "X"},
        )
        self.assertEqual(refused.status_code, 400)

    def test_the_owner_cannot_remove_themselves_or_the_last_owner(self):
        response = self._remove(self.owner)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.owner.pk).exists())

        second = User.objects.create_user(
            email="owner2@alpha.test", password="passw0rd123",
            company=self.company, role=self.owner_role,
        )
        # With two owners the other one may go; with one left, nobody may.
        self.assertEqual(self._remove(second).status_code, 200)
        self.assertEqual(self._remove(self.owner).status_code, 400)

    def test_only_the_owner_may_remove_an_account(self):
        client = self.client_class()
        client.post(
            reverse("auth-login"),
            {"email": "cashier@alpha.test", "password": "passw0rd123", "device_id": "C"},
        )
        response = client.post(f"/api/users/{self.owner.pk}/remove/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.owner.pk).exists())

    def test_another_company_is_out_of_reach(self):
        other = Company.objects.create(name="Beta")
        stranger = User.objects.create_user(
            email="x@beta.test", password="passw0rd123", company=other, role=self.sales_role,
        )
        self.assertEqual(self._remove(stranger).status_code, 404)
        self.assertTrue(User.objects.filter(pk=stranger.pk).exists())
