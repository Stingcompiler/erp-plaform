"""The verification worklist and the control it finally makes real.

The API always required a second person to confirm a payment, and an
approver role above the company threshold — but nothing listed what was
waiting, so the control never ran. This pins the list and the gate.
"""

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Role, User
from inventory.models import Warehouse
from org.models import Branch, Company
from sales.models import Customer, Invoice, Payment


class VerificationBase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name="Alpha", payment_approval_threshold=Decimal("1000")
        )
        self.branch = Branch.objects.create(company=self.company, name="Main")
        business = Role.SCOPE_BUSINESS
        sales_role = Role.objects.create(name="Sales Officer", scope_level=business)
        finance_role = Role.objects.create(name="Finance Department", scope_level=business)
        owner_role = Role.objects.create(name="Business Owner", scope_level=business)
        self.cashier = User.objects.create_user(
            email="cashier@alpha.test", password="passw0rd123",
            company=self.company, role=sales_role,
        )
        self.finance = User.objects.create_user(
            email="finance@alpha.test", password="passw0rd123",
            company=self.company, role=finance_role,
        )
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=owner_role,
        )
        wh = Warehouse.objects.create(company=self.company, branch=self.branch, name="W")
        customer = Customer.objects.create(company=self.company, name="Buyer")
        self.invoice = Invoice.objects.create(
            company=self.company, customer=customer, warehouse=wh, number=1,
            total=Decimal("5000"), subtotal=Decimal("5000"),
        )
        self.small = Payment.objects.create(
            company=self.company, invoice=self.invoice, method=Payment.CASH,
            amount=Decimal("200"), recorded_by=self.cashier,
        )
        self.large = Payment.objects.create(
            company=self.company, invoice=self.invoice, method=Payment.CASH,
            amount=Decimal("1500"), recorded_by=self.cashier,
        )

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client


class WorklistTests(VerificationBase):
    def test_unverified_filter_lists_oldest_first_with_display_fields(self):
        response = self.client_for(self.finance).get("/api/payments/", {"unverified": 1})
        self.assertEqual(response.status_code, 200, response.data)
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual([r["id"] for r in rows], [self.small.pk, self.large.pk])
        self.assertEqual(rows[0]["invoice_number"], "INV-000001")
        self.assertEqual(rows[0]["customer_name"], "Buyer")
        self.assertEqual(rows[0]["recorded_by_name"], self.cashier.full_name)

    def test_verified_rows_leave_the_worklist(self):
        self.client_for(self.finance).post(f"/api/payments/{self.small.pk}/verify/")
        response = self.client_for(self.finance).get("/api/payments/", {"unverified": 1})
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual([r["id"] for r in rows], [self.large.pk])


class GateTests(VerificationBase):
    def test_recorder_cannot_verify_own_payment(self):
        response = self.client_for(self.cashier).post(f"/api/payments/{self.small.pk}/verify/")
        self.assertEqual(response.status_code, 403, response.data)

    def test_finance_confirms_below_threshold(self):
        response = self.client_for(self.finance).post(f"/api/payments/{self.small.pk}/verify/")
        self.assertEqual(response.status_code, 200, response.data)
        self.small.refresh_from_db()
        self.assertEqual(self.small.verified_by, self.finance)

    def test_threshold_needs_an_approver_role(self):
        denied = self.client_for(self.finance).post(f"/api/payments/{self.large.pk}/verify/")
        self.assertEqual(denied.status_code, 403, denied.data)
        self.assertIn("threshold", denied.data)
        allowed = self.client_for(self.owner).post(f"/api/payments/{self.large.pk}/verify/")
        self.assertEqual(allowed.status_code, 200, allowed.data)
