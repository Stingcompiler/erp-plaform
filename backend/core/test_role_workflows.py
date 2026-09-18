"""What a role must be able to SEE to do its own job, found by signing in as
every staff role and walking its screens (2026-09-18)."""

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Role, User
from inventory.models import Product, Warehouse
from org.models import Branch, Company
from purchasing.models import Bill, Supplier, SupplierPayment
from sales.models import CompanyBankAccount, Customer


class RoleReadGrantTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha", business_type="enterprise")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.wh = Warehouse.objects.create(company=self.company, branch=self.branch, name="W")
        self.product = Product.objects.create(
            company=self.company, sku="P1", name="Widget", sale_price=Decimal("10"),
        )
        CompanyBankAccount.objects.create(
            company=self.company, bank_name="Bank", account_name="Main", opening_balance=0,
        )
        supplier = Supplier.objects.create(company=self.company, name="Acme")
        bill = Bill.objects.create(
            company=self.company, supplier=supplier, subtotal=Decimal("5"), total=Decimal("5"),
        )
        SupplierPayment.objects.create(
            company=self.company, supplier=supplier, bill=bill, method="cash",
            amount=Decimal("5"),
        )
        Customer.objects.create(company=self.company, name="Buyer")

    def as_role(self, name):
        role = Role.objects.create(name=name, scope_level=Role.SCOPE_BUSINESS)
        user = User.objects.create_user(
            email=f"{name.lower().replace(' ', '-')}@alpha.test", password="passw0rd123",
            company=self.company, role=role, branch=self.branch,
        )
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_purchasing_officer_can_pick_a_paying_account(self):
        client = self.as_role("Purchasing Officer")
        self.assertEqual(client.get("/api/bank-accounts/").status_code, 200)
        self.assertEqual(client.post("/api/bank-accounts/", {"bank_name": "X"}).status_code, 403)

    def test_finance_department_reads_the_whole_money_ledger(self):
        client = self.as_role("Finance Department")
        self.assertEqual(client.get("/api/supplier-payments/").status_code, 200)
        self.assertEqual(client.get("/api/refunds/").status_code, 200)
        self.assertEqual(client.get("/api/bank-accounts/").status_code, 200)
        self.assertEqual(client.post("/api/supplier-payments/", {}).status_code, 403)

    def test_cfo_sees_warehouses_and_landing_manager_sees_products(self):
        cfo = self.as_role("Chief Financial Officer")
        self.assertEqual(cfo.get("/api/warehouses/").status_code, 200)
        self.assertEqual(cfo.post("/api/warehouses/", {"name": "N"}).status_code, 403)
        lpm = self.as_role("Landing Page Manager")
        self.assertEqual(lpm.get("/api/products/").status_code, 200)
        self.assertEqual(lpm.post("/api/products/", {"name": "N", "sku": "N"}).status_code, 403)

    def test_hr_officer_still_cannot_read_bank_accounts(self):
        client = self.as_role("HR Officer")
        self.assertEqual(client.get("/api/bank-accounts/").status_code, 403)
