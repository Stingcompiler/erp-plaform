"""Customer refunds leave the bank and the cash flow (review F02/F03).

Fixture from the review: opening 1,000 + payment 300 − refund 200 − supplier
payment 100 = 1,000 on the account, and the cash-flow report shows the same
movements to the cent."""
from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Warehouse
from org.models import Branch, Company
from purchasing.models import Bill, Supplier, SupplierPayment
from returns.models import CreditNote
from sales.models import CompanyBankAccount, Customer, Invoice, Payment, Refund


class RefundLedgerTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        branch = Branch.objects.create(company=self.company, name="Main")
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123", company=self.company,
            role=Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS),
        )
        wh = Warehouse.objects.create(company=self.company, branch=branch, name="W")
        customer = Customer.objects.create(company=self.company, name="C")
        self.bank = CompanyBankAccount.objects.create(
            company=self.company, bank_name="BoK", account_name="Alpha",
            opening_balance=Decimal("1000"),
        )
        invoice = Invoice.objects.create(
            company=self.company, customer=customer, warehouse=wh, number=1,
            subtotal=Decimal("300"), total=Decimal("300"),
        )
        Payment.objects.create(
            company=self.company, invoice=invoice, method=Payment.BANK_TRANSFER,
            company_bank_account=self.bank, sender_bank_name="x", reference_last4="1111",
            amount=Decimal("300"),
        )
        note = CreditNote.objects.create(
            company=self.company, customer=customer, invoice=invoice, amount=Decimal("200"),
            reason="goodwill",
        )
        Refund.objects.create(
            company=self.company, credit_note=note, method=Refund.BANK_TRANSFER,
            company_bank_account=self.bank, reference_last4="2222", amount=Decimal("200"),
        )
        supplier = Supplier.objects.create(company=self.company, name="S")
        bill = Bill.objects.create(
            company=self.company, supplier=supplier, subtotal=Decimal("100"), total=Decimal("100"),
        )
        SupplierPayment.objects.create(
            company=self.company, supplier=supplier, bill=bill, method="bank_transfer",
            from_bank_account=self.bank, amount=Decimal("100"),
        )
        self.client.force_authenticate(self.owner)

    def test_bank_balance_subtracts_refunds(self):
        self.assertEqual(self.bank.balance(), Decimal("1000"))
        row = next(
            r for r in self.client.get(reverse("bankaccount-list")).data["results"]
            if r["id"] == self.bank.pk
        )
        self.assertEqual(
            [Decimal(row[k]) for k in
             ("balance", "received_total", "paid_total", "refunded_total")],
            [Decimal("1000"), Decimal("300"), Decimal("100"), Decimal("200")],
        )

    def test_cash_flow_report_counts_refunds_as_outflow(self):
        r = self.client.get(reverse("report-cash-flow"))
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(Decimal(r.data["inflows"]), Decimal("300"))
        self.assertEqual(Decimal(r.data["supplier_payments"]), Decimal("100"))
        self.assertEqual(Decimal(r.data["customer_refunds"]), Decimal("200"))
        self.assertEqual(Decimal(r.data["outflows"]), Decimal("300"))
        self.assertEqual(Decimal(r.data["net_cash_flow"]), Decimal("0"))
        by_method = r.data["refunds_by_method"]
        self.assertEqual((by_method[0]["method"], Decimal(by_method[0]["amount"])),
                         ("bank_transfer", Decimal("200")))
        csv = self.client.get(reverse("report-cash-flow"), {"format": "csv"}).content.decode()
        self.assertIn("customer refunds,200", csv)

    def test_cfo_cash_out_includes_refunds(self):
        r = self.client.get(reverse("report-cfo-kpis"))
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(Decimal(r.data["liquidity"]["cash_out"]), Decimal("300"))
        self.assertEqual(Decimal(r.data["liquidity"]["net_cash_flow"]), Decimal("0"))

    def test_zakat_bank_figure_uses_the_corrected_balance(self):
        r = self.client.get(reverse("report-zakat"))
        self.assertEqual(Decimal(r.data["bank"]), Decimal("1000"))
