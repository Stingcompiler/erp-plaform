"""
Cross-milestone integration tests.

Unlike the per-app unit tests, these drive whole workflows through the real API
across several milestones at once — proving the modules cooperate and the
PROJECT_RULES hold end to end. Master data (company/warehouse/product) is set up
via the ORM; the interesting steps (receive, sell, return, disposition, sync,
report, backup) go through HTTP.
"""

from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from accounts.models import Role, User
from inventory.models import Product, Warehouse
from org.models import Company
from purchasing.models import Supplier


class IntegrationBase(APITestCase):
    def make_company(self, name, tax_rate="0"):
        company = Company.objects.create(name=name)
        # Company auto-creates a TaxProfile; pin the rate for clean arithmetic.
        profile = company.tax_profile
        profile.flat_tax_rate = Decimal(tax_rate)
        profile.save()
        return company

    def make_role(self, name, scope):
        return Role.objects.get_or_create(name=name, defaults={"scope_level": scope})[0]

    def make_user(self, company, role, email, password="passw0rd123"):
        return User.objects.create_user(
            email=email, password=password, company=company, role=role
        )

    def client_for(self, email, password="passw0rd123"):
        client = APIClient()
        resp = client.post(reverse("auth-login"), {"email": email, "password": password})
        assert resp.status_code == 200, resp.content
        return client

    def owner_client(self, company, email):
        """An authenticated Business Owner (business-wide write) for a company."""
        role = self.make_role("Business Owner", Role.SCOPE_BUSINESS)
        self.make_user(company, role, email)
        return self.client_for(email)

    def warehouse(self, company, name="Main"):
        return Warehouse.objects.create(company=company, name=name)

    def product(self, company, sku="SKU1", cost="6", price="10", reorder="0"):
        return Product.objects.create(
            company=company, sku=sku, name=f"Product {sku}",
            cost_price=Decimal(cost), sale_price=Decimal(price),
            reorder_level=Decimal(reorder),
        )

    def supplier(self, company, name="Acme"):
        return Supplier.objects.create(company=company, name=name)

    def on_hand(self, client, product_id):
        resp = client.get(reverse("product-stock", args=[product_id]))
        assert resp.status_code == 200, resp.content
        return Decimal(str(resp.data["on_hand"]))
