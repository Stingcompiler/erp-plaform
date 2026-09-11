from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product, Warehouse
from org.models import Company
from purchasing.models import Supplier


class RBACBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Alpha")
        cls.roles = {}
        for name, scope in [
            ("Sales Officer", Role.SCOPE_BRANCH),
            ("Inventory Officer", Role.SCOPE_BRANCH),
            ("HR Officer", Role.SCOPE_BRANCH),
            ("Viewer", Role.SCOPE_BRANCH),
            ("Business Owner", Role.SCOPE_BUSINESS),
        ]:
            cls.roles[name] = Role.objects.create(name=name, scope_level=scope)
        cls.wh = Warehouse.objects.create(company=cls.company, name="Main")
        cls.product = Product.objects.create(
            company=cls.company, sku="SKU1", name="Widget", sale_price=Decimal("10"),
        )
        cls.supplier = Supplier.objects.create(company=cls.company, name="Acme")

    def as_role(self, role_name, email=None):
        email = email or f"{role_name.replace(' ', '').lower()}@alpha.test"
        User.objects.create_user(
            email=email, password="passw0rd123",
            company=self.company, role=self.roles[role_name],
        )
        client = self.client_class()
        r = client.post(
            reverse("auth-login"), {"email": email, "password": "passw0rd123"}
        )
        assert r.status_code == 200, r.content
        return client


class ModuleAccessTests(RBACBase):
    def test_hr_officer_cannot_touch_sales(self):
        client = self.as_role("HR Officer")
        # Read denied.
        self.assertEqual(
            client.get(reverse("invoice-list")).status_code, status.HTTP_403_FORBIDDEN
        )
        # Write denied.
        self.assertEqual(
            client.post(reverse("pos-checkout"), {}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_sales_officer_allowed_sales_denied_purchasing(self):
        client = self.as_role("Sales Officer")
        self.assertEqual(client.get(reverse("invoice-list")).status_code, 200)
        # Purchasing is off-limits for a sales officer.
        self.assertEqual(
            client.get(reverse("supplier-list")).status_code, status.HTTP_403_FORBIDDEN
        )

    def test_inventory_officer_denied_sales_checkout(self):
        client = self.as_role("Inventory Officer")
        self.assertEqual(client.get(reverse("product-list")).status_code, 200)
        self.assertEqual(
            client.post(reverse("pos-checkout"), {}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_viewer_can_read_but_not_write(self):
        client = self.as_role("Viewer")
        self.assertEqual(client.get(reverse("product-list")).status_code, 200)
        resp = client.post(
            reverse("stockmovement-list"),
            {
                "product": self.product.id, "warehouse": self.wh.id,
                "movement_type": "purchase_in", "quantity": "1",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_business_owner_has_broad_access(self):
        client = self.as_role("Business Owner")
        self.assertEqual(client.get(reverse("invoice-list")).status_code, 200)
        self.assertEqual(client.get(reverse("supplier-list")).status_code, 200)
        self.assertEqual(client.get(reverse("product-list")).status_code, 200)


class AccessMapTests(RBACBase):
    def test_access_map_reflects_role(self):
        client = self.as_role("HR Officer")
        resp = client.get(reverse("rbac-access"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["hr"], "write")
        self.assertEqual(resp.data["sales"], "none")
        self.assertEqual(resp.data["reports"], "read")


class DashboardTests(RBACBase):
    def test_dashboard_scoped_to_role_modules(self):
        client = self.as_role("Inventory Officer")
        resp = client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        sections = resp.data["sections"]
        # Inventory Officer sees inventory + read-only purchasing, not sales.
        self.assertIn("inventory", sections)
        self.assertNotIn("sales", sections)

    def test_sales_officer_dashboard_has_sales(self):
        client = self.as_role("Sales Officer")
        resp = client.get(reverse("dashboard"))
        self.assertIn("sales", resp.data["sections"])
        self.assertIn("inventory", resp.data["sections"])  # read access
        self.assertNotIn("purchasing", resp.data["sections"])

    def test_pending_salary_advance_alert_is_limited_to_financial_approvers(self):
        from hr.models import Employee, SalaryAdvance

        employee = Employee.objects.create(company=self.company, full_name="Amina Ali")
        SalaryAdvance.objects.create(
            company=self.company, employee=employee, amount="800.00",
            status=SalaryAdvance.PENDING,
        )
        hr_client = self.as_role("HR Officer", email="hr-alert@alpha.test")
        self.assertNotIn("salary_advances", hr_client.get(reverse("dashboard")).data["sections"])

        cfo_role = Role.objects.create(
            name="Chief Financial Officer", scope_level=Role.SCOPE_BUSINESS
        )
        cfo = User.objects.create_user(
            email="cfo-alert@alpha.test", password="passw0rd123",
            company=self.company, role=cfo_role,
        )
        cfo_client = self.client_class()
        cfo_client.force_authenticate(cfo)
        alert = cfo_client.get(reverse("dashboard")).data["sections"]["salary_advances"]
        self.assertEqual(alert, {"pending_count": 1, "pending_total": "800"})

    def test_hr_receives_salary_advance_status_summary_without_financial_alert(self):
        from hr.models import Employee, SalaryAdvance

        employee = Employee.objects.create(company=self.company, full_name="Amina Ali")
        for state in (SalaryAdvance.PENDING, SalaryAdvance.APPROVED, SalaryAdvance.REJECTED):
            SalaryAdvance.objects.create(
                company=self.company, employee=employee, amount="100", status=state
            )
        hr_client = self.as_role("HR Officer", email="hr-status@alpha.test")
        sections = hr_client.get(reverse("dashboard")).data["sections"]
        self.assertEqual(
            sections["advance_requests"],
            {"pending_count": 1, "approved_count": 1, "rejected_count": 1},
        )
        self.assertNotIn("salary_advances", sections)
