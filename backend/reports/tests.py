from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product, StockMovement, Warehouse
from org.models import Branch, Company
from purchasing.models import Bill, Supplier
from sales.models import Customer, Invoice, InvoiceLine


class ReportsBase(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.owner = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        self.lpm = Role.objects.create(
            name="Landing Page Manager", scope_level=Role.SCOPE_BRANCH
        )
        self.user = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=self.owner,
        )
        self.wh = Warehouse.objects.create(
            company=self.company, branch=self.branch, name="Main"
        )
        self.product = Product.objects.create(
            company=self.company, sku="SKU1", name="Widget",
            cost_price=Decimal("6.00"), sale_price=Decimal("10.00"),
        )
        # Stock in 20 units.
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.PURCHASE_IN, quantity=Decimal("20"),
        )
        # An invoice with one line: 5 units @ 10 = 50 subtotal.
        self.customer = Customer.objects.create(company=self.company, name="C1")
        self.invoice = Invoice.objects.create(
            company=self.company, customer=self.customer, warehouse=self.wh,
            branch=self.branch,
            number=1, subtotal=Decimal("50"), total=Decimal("50"),
        )
        InvoiceLine.objects.create(
            invoice=self.invoice, product=self.product, quantity=Decimal("5"),
            unit_price=Decimal("10"), line_subtotal=Decimal("50"),
            line_total=Decimal("50"),
        )
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.SALE_OUT, quantity=Decimal("-5"),
        )
        self.client.force_authenticate(self.user)


class SalesReportTests(ReportsBase):
    def test_sales_summary_matches_invoices(self):
        resp = self.client.get(reverse("report-sales-summary"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["totals"]["invoice_count"], 1)
        self.assertEqual(Decimal(resp.data["totals"]["total"]), Decimal("50"))

    def test_sales_by_product(self):
        resp = self.client.get(reverse("report-sales-by-product"))
        row = resp.data[0]
        self.assertEqual(row["sku"], "SKU1")
        self.assertEqual(Decimal(row["units"]), Decimal("5"))
        self.assertEqual(Decimal(row["revenue"]), Decimal("50"))

    def test_sales_by_product_csv(self):
        resp = self.client.get(reverse("report-sales-by-product"), {"format": "csv"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("SKU1", resp.content.decode())

    def test_payroll_report_returns_company_payroll_entries(self):
        from hr.models import Employee, PayrollEntry, PayrollRun, Position

        position = Position.objects.create(company=self.company, title="Cashier", base_salary="1000.00")
        employee = Employee.objects.create(company=self.company, full_name="Amina Ali", position=position)
        run = PayrollRun.objects.create(company=self.company, period="2026-09-01")
        PayrollEntry.objects.create(
            payroll_run=run, employee=employee, employee_name=employee.full_name,
            position_title="Cashier", base_salary="1000.00", deductions_total="50.00",
            advances_total="100.00", net_salary="850.00",
        )
        response = self.client.get(reverse("report-payroll"))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data[0]["net_total"], "850.00")
        self.assertEqual(response.data[0]["entries"][0]["employee_name"], "Amina Ali")


class ValuationAndProfitTests(ReportsBase):
    def test_inventory_valuation(self):
        resp = self.client.get(reverse("report-inventory-valuation"))
        # on_hand = 20 - 5 = 15; value = 15 * 6 = 90.
        self.assertEqual(Decimal(resp.data["total_value"]), Decimal("90"))
        item = resp.data["items"][0]
        self.assertEqual(Decimal(item["on_hand"]), Decimal("15"))
        self.assertEqual(Decimal(item["value"]), Decimal("90"))

    def test_profit_summary(self):
        resp = self.client.get(reverse("report-profit-summary"))
        # revenue 50; cogs = 5 units * 6 = 30; gross = 20.
        self.assertEqual(Decimal(resp.data["revenue"]), Decimal("50"))
        self.assertEqual(Decimal(resp.data["cogs_standard_cost"]), Decimal("30"))
        self.assertEqual(Decimal(resp.data["gross_profit"]), Decimal("20"))


class AgingTests(ReportsBase):
    def test_ar_aging_reflects_outstanding(self):
        resp = self.client.get(reverse("report-ar-aging"))
        self.assertEqual(len(resp.data), 1)
        row = resp.data[0]
        self.assertEqual(Decimal(row["total"]), Decimal("50"))

    def test_ap_aging_reflects_outstanding(self):
        supplier = Supplier.objects.create(company=self.company, name="Acme")
        Bill.objects.create(company=self.company, supplier=supplier, total=Decimal("120"))
        resp = self.client.get(reverse("report-ap-aging"))
        self.assertEqual(Decimal(resp.data[0]["total"]), Decimal("120"))


class ReportsRBACTests(ReportsBase):
    def test_branch_manager_sales_report_excludes_other_branches(self):
        other_branch = Branch.objects.create(company=self.company, name="Other")
        other_warehouse = Warehouse.objects.create(
            company=self.company, branch=other_branch, name="Other warehouse"
        )
        Invoice.objects.create(
            company=self.company,
            branch=other_branch,
            warehouse=other_warehouse,
            number=2,
            subtotal=Decimal("999"),
            total=Decimal("999"),
        )
        response = self.client_for_role("Branch Manager").get(
            reverse("report-sales-summary")
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Decimal(response.data["totals"]["total"]), Decimal("50"))

    def test_landing_page_manager_denied_reports(self):
        lpm_user = User.objects.create_user(
            email="lpm@alpha.test", password="passw0rd123",
            company=self.company, branch=self.branch, role=self.lpm,
        )
        c = self.client_class()
        c.force_authenticate(lpm_user)
        resp = c.get(reverse("report-sales-summary"))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_reports_are_company_scoped(self):
        # A second company's invoice must not appear in this company's report.
        other = Company.objects.create(name="Beta")
        Invoice.objects.create(
            company=other,
            warehouse=Warehouse.objects.create(company=other, name="BW"),
            number=1, subtotal=Decimal("999"), total=Decimal("999"),
        )
        resp = self.client.get(reverse("report-sales-summary"))
        self.assertEqual(Decimal(resp.data["totals"]["total"]), Decimal("50"))

    def client_for_role(self, role_name):
        role = Role.objects.create(name=role_name, scope_level=Role.SCOPE_BRANCH)
        user = User.objects.create_user(
            email=f"{role_name.lower().replace(' ', '-')}@alpha.test",
            password="passw0rd123", company=self.company,
            branch=self.branch, role=role,
        )
        client = self.client_class()
        client.force_authenticate(user)
        return client

    def test_hr_cannot_read_company_financial_reports(self):
        client = self.client_for_role("HR Officer")
        for name in (
            "report-sales-summary", "report-inventory-valuation",
            "report-purchases-summary", "report-income-statement",
            "report-cash-flow", "report-cfo-kpis",
        ):
            with self.subTest(report=name):
                self.assertEqual(client.get(reverse(name)).status_code, 403)

    def test_hr_reads_only_hr_summary(self):
        from hr.models import Attendance, Employee, LeaveRequest

        employee = Employee.objects.create(
            company=self.company, branch=self.branch, full_name="HR Person"
        )
        Attendance.objects.create(
            company=self.company, employee=employee, date="2026-09-11", status="present"
        )
        LeaveRequest.objects.create(
            company=self.company, employee=employee,
            start_date="2026-09-12", end_date="2026-09-13",
        )
        client = self.client_for_role("HR Officer")
        response = client.get(reverse("report-hr-summary"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["employee_total"], 1)
        self.assertEqual(response.data["attendance"]["present"], 1)
        self.assertEqual(response.data["leave"]["pending"], 1)

    def test_cfo_can_read_payroll_without_access_to_hr_summary(self):
        cfo_role = Role.objects.create(
            name="Chief Financial Officer", scope_level=Role.SCOPE_BUSINESS
        )
        cfo = User.objects.create_user(
            email="cfo@alpha.test", password="passw0rd123",
            company=self.company, role=cfo_role,
        )
        client = self.client_class()
        client.force_authenticate(cfo)
        self.assertEqual(client.get(reverse("report-payroll")).status_code, 200)
        self.assertEqual(client.get(reverse("report-hr-summary")).status_code, 403)

    def test_operational_roles_only_read_their_report_family(self):
        cases = {
            "Sales Officer": ("report-sales-summary", "report-inventory-valuation"),
            "Inventory Officer": ("report-inventory-valuation", "report-sales-summary"),
            "Purchasing Officer": ("report-purchases-summary", "report-income-statement"),
        }
        for role_name, (allowed, denied) in cases.items():
            with self.subTest(role=role_name):
                client = self.client_for_role(role_name)
                self.assertEqual(client.get(reverse(allowed)).status_code, 200)
                self.assertEqual(client.get(reverse(denied)).status_code, 403)
