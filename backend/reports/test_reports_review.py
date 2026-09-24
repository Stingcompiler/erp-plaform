"""Reports review (2026-09-24): CSV safety, CRM leak to finance roles, one
receivables rule across screens, `?days=` overflow, the dashboard's
low-stock and period figures, company-clock CSV dates, branch scoping,
HR headcount and the English strings that reached Arabic screens."""
import csv
import io
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Role, User
from core.csvexport import safe_cell
from core.records import rows_csv
from crm.models import Lead
from inventory.models import Product, Warehouse
from org.models import Branch, Company, Department
from sales.models import Customer, Invoice, InvoiceLine, Payment


def csv_rows(response):
    body = response.content.decode("utf-8")
    assert body.startswith("﻿"), "CSV must start with a BOM"
    return list(csv.reader(io.StringIO(body[1:])))


class ReportsReviewTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha", timezone="Africa/Khartoum")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.other_branch = Branch.objects.create(company=self.company, name="South")
        self.owner = self.user("Business Owner", "owner")
        self.wh = Warehouse.objects.create(company=self.company, branch=self.branch, name="W")
        self.client.force_authenticate(self.owner)
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"

    def user(self, role_name, handle, scope=Role.SCOPE_BUSINESS, branch=None):
        role = Role.objects.filter(name=role_name).first() or Role.objects.create(
            name=role_name, scope_level=scope
        )
        return User.objects.create_user(
            email=f"{handle}@alpha.test", password="passw0rd123", company=self.company,
            role=role, branch=branch,
        )

    def invoice(self, total, customer=None, number=1, branch=None, **extra):
        return Invoice.objects.create(
            company=self.company, warehouse=self.wh, branch=branch or self.branch,
            customer=customer, number=number, subtotal=Decimal(total), total=Decimal(total),
            **extra,
        )

    # 1 — CSV formula injection and BOM ---------------------------------
    def test_report_csv_has_bom_and_neutralises_formulas(self):
        customer = Customer.objects.create(
            company=self.company, name='=HYPERLINK("http://x","a")'
        )
        self.invoice("100", customer, due_date=timezone.localdate() - timedelta(days=3))
        response = self.client.get(reverse("report-receivables-due"), {"format": "csv"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        rows = csv_rows(response)
        self.assertEqual(rows[0][0], "Invoice")
        self.assertEqual(rows[1][1], '\'=HYPERLINK("http://x","a")')
        self.assertEqual(Decimal(rows[1][4]), Decimal("100"))

    def test_safe_cell_leaves_numbers_alone(self):
        self.assertEqual(safe_cell("-12.50"), "-12.50")
        self.assertEqual(safe_cell("+249912345678"), "+249912345678")
        self.assertEqual(safe_cell(Decimal("-3")), Decimal("-3"))
        self.assertEqual(safe_cell(-3), -3)
        self.assertEqual(safe_cell("-2+3+cmd|' /C calc'!A0"), "'-2+3+cmd|' /C calc'!A0")
        self.assertEqual(safe_cell("@SUM(A1)"), "'@SUM(A1)")
        self.assertEqual(safe_cell("\tx"), "'\tx")
        self.assertEqual(safe_cell("Ahmed"), "Ahmed")

    def test_records_rows_csv_is_neutralised_too(self):
        rows = csv_rows(rows_csv("x.csv", ["name"], [["+SUM(1,2)"]]))
        self.assertEqual(rows[1][0], "'+SUM(1,2)")

    # 2 — CRM report needs the CRM module -------------------------------
    def test_crm_report_is_closed_to_finance_roles(self):
        Lead.objects.create(company=self.company, name="Lead A", phone="0912345678")
        for role_name, handle in (
            ("Chief Financial Officer", "cfo"), ("Finance Department", "fin"),
        ):
            self.client.force_authenticate(self.user(role_name, handle))
            self.assertEqual(self.client.get(reverse("report-crm")).status_code, 403)
            response = self.client.get(reverse("report-crm"), {"format": "csv"})
            self.assertEqual(response.status_code, 403)
            self.assertNotIn(b"0912345678", response.content)
            # The rest of the sales area stays open to them.
            self.assertEqual(self.client.get(reverse("report-ar-aging")).status_code, 200)
        self.client.force_authenticate(self.user("CRM Officer", "crm"))
        self.assertEqual(self.client.get(reverse("report-crm")).status_code, 200)

    # 3 — one receivables figure ------------------------------------------
    def test_dashboard_ledger_aging_and_cfo_agree(self):
        archived = Customer.objects.create(company=self.company, name="Gone", is_active=False)
        live = Customer.objects.create(company=self.company, name="Here")
        past = timezone.localdate() - timedelta(days=5)
        self.invoice("100", archived, number=1, due_date=past)
        self.invoice("40", live, number=2)
        self.invoice("25", None, number=3, due_date=past)  # walk-in left on account

        aging = self.client.get(reverse("report-ar-aging")).data
        aging_total = sum(Decimal(row["total"]) for row in aging)
        cfo = self.client.get(reverse("report-cfo-kpis")).data["receivables"]
        dashboard = self.client.get(reverse("dashboard")).data["sections"]["debts"]
        summary = self.client.get(reverse("debt-summary")).data

        self.assertEqual(aging_total, Decimal("165.00"))
        self.assertEqual(Decimal(cfo["outstanding"]), aging_total)
        self.assertEqual(Decimal(dashboard["outstanding"]), aging_total)
        self.assertEqual(Decimal(summary["outstanding"]), aging_total)
        self.assertEqual(Decimal(summary["overdue"]), Decimal(cfo["overdue"]))
        self.assertEqual(summary["walk_in_outstanding"], "25.00")
        self.assertEqual(summary["debtor_count"], 2)

        listed = self.client.get(reverse("debt-customer-list")).data
        by_name = {row["name"]: row for row in listed["results"]}
        self.assertFalse(by_name["Gone"]["is_active"])
        self.assertEqual(by_name["Gone"]["outstanding"], "100.00")
        self.assertTrue(by_name["Here"]["is_active"])
        self.assertEqual(listed["walk_in"], {"outstanding": "25.00", "overdue": "25.00"})
        listed_total = sum(Decimal(r["outstanding"]) for r in listed["results"])
        self.assertEqual(listed_total + Decimal(listed["walk_in"]["outstanding"]), aging_total)

    def test_settled_archived_customer_stays_off_the_ledger(self):
        Customer.objects.create(company=self.company, name="Old and settled", is_active=False)
        settled = self.client.get(reverse("debt-customer-list"), {"status": "settled"}).data
        self.assertEqual(settled["count"], 0)

    # 4 — ?days= overflow -------------------------------------------------
    def test_days_is_clamped(self):
        self.client.raise_request_exception = False
        response = self.client.get(reverse("report-receivables-due"), {"days": "99999999"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["horizon_days"], 365)
        response = self.client.get(reverse("report-payables-due"), {"days": "-99999999"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["horizon_days"], 0)
        response = self.client.get(reverse("report-payables-due"), {"days": "soon"})
        self.assertEqual(response.data["horizon_days"], 7)

    # 5 — low stock on the dashboard --------------------------------------
    def test_dashboard_low_stock_counts_active_tracked_products_only(self):
        Product.objects.create(company=self.company, name="Rice", sku="RICE")
        Product.objects.create(
            company=self.company, name="Bag", sku="BAG", is_stock_tracked=False
        )
        Product.objects.create(company=self.company, name="Old", sku="OLD", is_active=False)
        inventory = self.client.get(reverse("dashboard")).data["sections"]["inventory"]
        self.assertEqual(inventory["low_stock_count"], 1)
        self.assertEqual(inventory["product_count"], 2)

    # 6 — CSV dates on the company's clock --------------------------------
    def test_operational_csv_dates_are_company_local(self):
        customer = Customer.objects.create(company=self.company, name="Ahmed")
        invoice = self.invoice("100", customer)
        payment = Payment.objects.create(
            company=self.company, invoice=invoice, method=Payment.CASH,
            amount=Decimal("100"), recorded_by=self.owner,
        )
        # 22:30 UTC on the 1st is 00:30 on the 2nd in Khartoum (UTC+2).
        moment = datetime(2026, 9, 1, 22, 30, tzinfo=ZoneInfo("UTC"))
        Payment.objects.filter(pk=payment.pk).update(recorded_at=moment)
        lead = Lead.objects.create(company=self.company, name="L")
        Lead.objects.filter(pk=lead.pk).update(created_at=moment)

        rows = csv_rows(self.client.get(
            reverse("report-payment-reconciliation"), {"format": "csv"}
        ))
        self.assertEqual(rows[1][1], "2026-09-02 00:30")
        self.assertEqual(rows[1][4], "Cash")
        self.assertEqual(rows[1][9], "Unverified")
        rows = csv_rows(self.client.get(reverse("report-crm"), {"format": "csv"}))
        self.assertEqual(rows[1][1], "2026-09-02")
        self.assertEqual(rows[1][6], "New")

    def test_operational_csv_is_arabic_for_an_arabic_screen(self):
        Lead.objects.create(company=self.company, name="L")
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "ar"
        rows = csv_rows(self.client.get(reverse("report-crm"), {"format": "csv"}))
        self.assertNotEqual(rows[0][0], "Lead")
        self.assertNotEqual(rows[1][6], "New")

    # 7 — dashboard period ------------------------------------------------
    def test_dashboard_revenue_is_month_to_date(self):
        product = Product.objects.create(company=self.company, name="Rice", sku="RICE")
        month_start = timezone.localdate().replace(day=1)
        last_month = datetime.combine(month_start - timedelta(days=1), datetime.min.time())
        old = self.invoice("500", number=1, issued_at=timezone.make_aware(last_month))
        new = self.invoice("70", number=2)
        for inv, amount in ((old, "500"), (new, "70")):
            InvoiceLine.objects.create(
                invoice=inv, product=product, quantity=1, unit_price=Decimal(amount),
                line_subtotal=Decimal(amount), line_total=Decimal(amount),
            )
        sales = self.client.get(reverse("dashboard")).data["sections"]["sales"]
        self.assertEqual(Decimal(sales["revenue_total"]), Decimal("70"))
        self.assertEqual(sales["period_start"], month_start.isoformat())
        finance = self.client.get(reverse("dashboard")).data["sections"]["finance"]
        self.assertEqual(Decimal(finance["revenue"]), Decimal("70"))
        month = self.client.get(reverse("report-income-statement"), {
            "start": month_start.isoformat(), "end": timezone.localdate().isoformat(),
        }).data
        self.assertEqual(Decimal(finance["net_profit"]), Decimal(month["net_profit"]))

    def test_dashboard_top_products_group_by_product_not_name(self):
        first = Product.objects.create(company=self.company, name="Tea", sku="T1")
        second = Product.objects.create(company=self.company, name="Tea", sku="T2")
        inv = self.invoice("30")
        for product, amount in ((first, "10"), (second, "20")):
            InvoiceLine.objects.create(
                invoice=inv, product=product, quantity=1, unit_price=Decimal(amount),
                line_subtotal=Decimal(amount), line_total=Decimal(amount),
            )
        top = self.client.get(reverse("dashboard")).data["sections"]["sales"]["top_products"]
        self.assertEqual(
            [(row["product"], row["value"]) for row in top],
            [(second.id, "20"), (first.id, "10")],
        )

    # 8 — branch scoping --------------------------------------------------
    def test_dashboard_crm_and_purchases_receipts_follow_the_branch(self):
        from purchasing.models import GoodsReceipt, Supplier

        Lead.objects.create(company=self.company, name="Mine", branch=self.branch,
                            estimated_value=Decimal("10"))
        Lead.objects.create(company=self.company, name="Theirs", branch=self.other_branch,
                            estimated_value=Decimal("90"))
        manager = self.user("Branch Manager", "bm", Role.SCOPE_BRANCH, self.branch)
        self.client.force_authenticate(manager)
        crm = self.client.get(reverse("dashboard")).data["sections"]["crm"]
        self.assertEqual(crm["open_lead_count"], 1)
        self.assertEqual(Decimal(crm["pipeline_value"]), Decimal("10"))

        supplier = Supplier.objects.create(company=self.company, name="S")
        other_wh = Warehouse.objects.create(
            company=self.company, branch=self.other_branch, name="W2"
        )
        GoodsReceipt.objects.create(company=self.company, supplier=supplier, warehouse=self.wh)
        GoodsReceipt.objects.create(company=self.company, supplier=supplier, warehouse=other_wh)
        officer = self.user("Purchasing Officer", "po", Role.SCOPE_BRANCH, self.branch)
        self.client.force_authenticate(officer)
        summary = self.client.get(reverse("report-purchases-summary")).data
        self.assertEqual(summary["receipt_count"], 1)
        self.client.force_authenticate(self.owner)
        summary = self.client.get(reverse("report-purchases-summary")).data
        self.assertEqual(summary["receipt_count"], 2)

    # 9 — HR headcount ----------------------------------------------------
    def test_hr_headcount_leaves_out_terminated(self):
        from hr.models import Employee

        dept = Department.objects.create(company=self.company, name="Shop")
        Employee.objects.create(company=self.company, full_name="A", department=dept)
        Employee.objects.create(
            company=self.company, full_name="B", department=dept,
            status=Employee.STATUS_TERMINATED,
        )
        data = self.client.get(reverse("report-hr-summary")).data
        self.assertEqual(data["employee_total"], 1)
        self.assertEqual(data["departments"], [{"name": "Shop", "count": 1}])
        self.assertEqual(data["employees"]["terminated"], 1)

    # 10 — English that reached Arabic screens ----------------------------
    def test_walk_in_and_cogs_note_are_translated(self):
        self.invoice("50", None)
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "ar"
        names = [row["name"] for row in self.client.get(reverse("report-ar-aging")).data]
        self.assertNotIn("(walk-in)", names)
        profit = self.client.get(reverse("report-profit-summary")).data
        self.assertEqual(profit["note_code"], "cogs_method")
        self.assertNotIn("COGS uses", profit["note"])
