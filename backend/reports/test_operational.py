"""The operational reports the build plan asked for (M5/M9): sales and
purchase returns, payment reconciliation (recorded vs verified) and CRM.
Each is checked for its figures, its CSV, and who may open it."""
import csv
import io
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Role, User
from crm.models import FollowUp, Lead
from inventory.models import Product, StockMovement, Warehouse
from org.models import Branch, Company
from purchasing.models import Supplier
from returns.models import (
    CreditNote, DebitNote, PurchaseReturn, PurchaseReturnLine, SalesReturn, SalesReturnLine,
)
from sales.models import CompanyBankAccount, Customer, Invoice, InvoiceLine, Payment, Refund


class OperationalReportTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.wh = Warehouse.objects.create(company=self.company, branch=self.branch, name="W")
        roles = {
            name: Role.objects.create(name=name, scope_level=scope)
            for name, scope in (
                ("Business Owner", Role.SCOPE_BUSINESS),
                ("Sales Officer", Role.SCOPE_BRANCH),
                ("HR Officer", Role.SCOPE_BUSINESS),
                ("Purchasing Officer", Role.SCOPE_BUSINESS),
            )
        }
        self.users = {
            name: User.objects.create_user(
                email=f"{name.split()[0].lower()}@alpha.test", password="passw0rd123",
                company=self.company, role=role, branch=self.branch,
            )
            for name, role in roles.items()
        }
        self.product = Product.objects.create(
            company=self.company, sku="SKU1", name="Rice", sale_price=Decimal("10"),
            cost_price=Decimal("6"),
        )
        customer = Customer.objects.create(company=self.company, name="Ahmed")
        self.invoice = Invoice.objects.create(
            company=self.company, customer=customer, warehouse=self.wh, branch=self.branch,
            number=1, subtotal=Decimal("100"), total=Decimal("100"),
        )
        line = InvoiceLine.objects.create(
            invoice=self.invoice, product=self.product, quantity=Decimal("10"),
            unit_price=Decimal("10"), line_subtotal=Decimal("100"), line_total=Decimal("100"),
        )
        # Sales return: 3 back, 2 restocked, 1 scrapped, a 30 credit note, 20 refunded.
        sr = SalesReturn.objects.create(
            company=self.company, invoice=self.invoice, reason="damaged",
        )
        SalesReturnLine.objects.create(
            sales_return=sr, invoice_line=line, product=self.product, quantity=Decimal("2"),
            disposition=SalesReturnLine.RESTOCKED,
        )
        SalesReturnLine.objects.create(
            sales_return=sr, invoice_line=line, product=self.product, quantity=Decimal("1"),
            disposition=SalesReturnLine.SCRAPPED, written_off_value=Decimal("6"),
        )
        note = CreditNote.objects.create(
            company=self.company, customer=customer, invoice=self.invoice, sales_return=sr,
            amount=Decimal("30"),
        )
        self.bank = CompanyBankAccount.objects.create(
            company=self.company, bank_name="Bankak", account_name="Alpha",
            account_number="0099887766",
        )
        Refund.objects.create(
            company=self.company, credit_note=note, method=Refund.BANK_TRANSFER,
            company_bank_account=self.bank, reference_last4="2222", amount=Decimal("20"),
        )
        # Purchase return: 4 back to the supplier, a 24 debit note.
        supplier = Supplier.objects.create(company=self.company, name="Nile Supply")
        pr = PurchaseReturn.objects.create(
            company=self.company, supplier=supplier, warehouse=self.wh,
        )
        out = StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.PURCHASE_RETURN_OUT, quantity=Decimal("-4"),
        )
        PurchaseReturnLine.objects.create(
            purchase_return=pr, product=self.product, quantity=Decimal("4"), movement=out,
        )
        DebitNote.objects.create(
            company=self.company, supplier=supplier, purchase_return=pr, amount=Decimal("24"),
        )
        # Payments: 70 by transfer verified, 30 cash not yet verified.
        Payment.objects.create(
            company=self.company, invoice=self.invoice, method=Payment.BANK_TRANSFER,
            company_bank_account=self.bank, sender_bank_name="BoK", reference_last4="1111",
            transfer_reference="TX-1", amount=Decimal("70"),
            verified_at=timezone.now(), verified_by=self.users["Business Owner"],
        )
        Payment.objects.create(
            company=self.company, invoice=self.invoice, method=Payment.CASH, amount=Decimal("30"),
        )
        # CRM: two open leads worth 500, one won, one lost; one overdue follow-up.
        for name, stage, value in (
            ("A", "new", "200"), ("B", "proposal", "300"), ("C", "won", "900"), ("D", "lost", "50"),
        ):
            lead = Lead.objects.create(
                company=self.company, branch=self.branch, name=name, stage=stage,
                estimated_value=Decimal(value), source="walk-in",
            )
        FollowUp.objects.create(
            company=self.company, lead=lead, due_date=timezone.localdate() - timedelta(days=2),
            summary="call back",
        )

    def _get(self, role, name, **params):
        self.client.force_authenticate(self.users[role])
        return self.client.get(reverse(name), params)

    def test_sales_returns_report(self):
        data = self._get("Business Owner", "report-sales-returns").data
        self.assertEqual(data["return_count"], 1)
        self.assertEqual(data["quantity"], "3")
        self.assertEqual(data["credit_total"], "30.00")
        self.assertEqual(data["refund_total"], "20.00")
        self.assertEqual(data["written_off_total"], "6.00")
        by = {row["disposition"]: row["quantity"] for row in data["by_disposition"]}
        self.assertEqual(by, {"restocked": "2", "scrapped": "1"})
        self.assertEqual(data["top_products"][0]["name"], "Rice")

    def test_purchase_returns_report(self):
        data = self._get("Business Owner", "report-purchase-returns").data
        self.assertEqual((data["return_count"], data["quantity"]), (1, "4"))
        self.assertEqual(data["debit_total"], "24.00")
        self.assertEqual(data["by_supplier"][0]["name"], "Nile Supply")

    def test_payment_reconciliation_report(self):
        data = self._get("Business Owner", "report-payment-reconciliation").data
        self.assertEqual(data["recorded"], {"count": 2, "amount": "100.00"})
        self.assertEqual(data["verified"], {"count": 1, "amount": "70.00"})
        self.assertEqual(data["unverified"], {"count": 1, "amount": "30.00"})
        self.assertEqual(data["verified_rate"], 50.0)
        self.assertEqual(data["oldest_unverified_days"], 0)
        by = {(row["method"], row["name"]): row for row in data["by_account"]}
        self.assertEqual(by[("bank_transfer", "Bankak · Alpha · 7766")]["unverified"], "0.00")
        self.assertEqual(by[("cash", "")]["unverified"], "30.00")

    def test_crm_report(self):
        data = self._get("Business Owner", "report-crm").data
        stages = {row["stage"]: row["count"] for row in data["stages"]}
        self.assertEqual(stages["new"], 1)
        self.assertEqual(stages["won"], 1)
        self.assertEqual(data["pipeline_value"], "500.00")
        self.assertEqual(data["conversion_rate"], 50.0)
        self.assertEqual(data["follow_ups"]["overdue"], 1)
        self.assertEqual(data["new_leads"], 4)

    def test_each_report_downloads_as_csv(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        for name, first_header in (
            ("report-sales-returns", "Return"),
            ("report-purchase-returns", "Return"),
            ("report-payment-reconciliation", "Payment"),
            ("report-crm", "Lead"),
        ):
            response = self._get("Business Owner", name, format="csv")
            self.assertEqual(response.status_code, 200, name)
            rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
            self.assertEqual(rows[0][0], first_header, name)
            self.assertGreater(len(rows), 1, name)

    def test_each_report_follows_the_role_areas(self):
        # Sales officer: returns and CRM, not payments or purchasing.
        self.assertEqual(self._get("Sales Officer", "report-sales-returns").status_code, 200)
        self.assertEqual(self._get("Sales Officer", "report-crm").status_code, 200)
        self.assertEqual(
            self._get("Sales Officer", "report-payment-reconciliation").status_code, 403
        )
        self.assertEqual(self._get("Sales Officer", "report-purchase-returns").status_code, 403)
        # Purchasing officer sees purchase returns only.
        self.assertEqual(
            self._get("Purchasing Officer", "report-purchase-returns").status_code, 200
        )
        self.assertEqual(self._get("Purchasing Officer", "report-sales-returns").status_code, 403)
        # HR sees none of them.
        for name in ("report-sales-returns", "report-purchase-returns",
                     "report-payment-reconciliation", "report-crm"):
            self.assertEqual(self._get("HR Officer", name).status_code, 403, name)

    def test_another_company_is_never_counted(self):
        other = Company.objects.create(name="Beta")
        wh = Warehouse.objects.create(company=other, name="W")
        cust = Customer.objects.create(company=other, name="X")
        inv = Invoice.objects.create(
            company=other, customer=cust, warehouse=wh, number=1,
            subtotal=Decimal("999"), total=Decimal("999"),
        )
        Payment.objects.create(
            company=other, invoice=inv, method=Payment.CASH, amount=Decimal("999"),
        )
        Lead.objects.create(company=other, name="Z", stage="new", estimated_value=Decimal("999"))
        reconciliation = self._get("Business Owner", "report-payment-reconciliation").data
        self.assertEqual(reconciliation["recorded"]["count"], 2)
        self.assertEqual(self._get("Business Owner", "report-crm").data["new_leads"], 4)

    def test_the_date_range_narrows_the_period(self):
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        data = self._get("Business Owner", "report-sales-returns", start=tomorrow).data
        self.assertEqual(data["return_count"], 0)
        data = self._get("Business Owner", "report-payment-reconciliation", start=tomorrow).data
        self.assertEqual(data["recorded"]["count"], 0)
        self.assertIsNone(data["verified_rate"])
