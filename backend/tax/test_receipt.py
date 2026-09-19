"""Receipt printing: the paper/footer settings reach the document, and the
invoice document says how it was paid."""
from decimal import Decimal

from django.urls import reverse

from sales.models import CompanyBankAccount, Payment
from tax.tests import TaxBase


class ReceiptDocumentTests(TaxBase):
    def test_issuer_carries_paper_and_footer_from_settings(self):
        r = self.client.patch(
            reverse("company-profile"),
            {"receipt_paper": "80mm", "receipt_footer": "  البضاعة المباعة لا تُرد بعد 3 أيام  "},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["receipt_paper"], "80mm")
        self.assertEqual(r.data["receipt_footer"], "البضاعة المباعة لا تُرد بعد 3 أيام")
        doc = self.client.get(reverse("invoice-document", args=[self.invoice.id])).data
        self.assertEqual(doc["issuer"]["receipt_paper"], "80mm")
        self.assertEqual(doc["issuer"]["receipt_footer"], "البضاعة المباعة لا تُرد بعد 3 أيام")
        bad = self.client.patch(
            reverse("company-profile"), {"receipt_paper": "letter"}, format="json"
        )
        self.assertEqual(bad.status_code, 400)

    def test_invoice_document_lists_payments_with_channel_and_reference(self):
        bankak = CompanyBankAccount.objects.create(
            company=self.company, channel=CompanyBankAccount.CHANNEL_BANKAK,
            bank_name="BoK", account_name="Alpha",
        )
        Payment.objects.create(
            company=self.company, invoice=self.invoice, method=Payment.CASH,
            amount=Decimal("100"),
        )
        Payment.objects.create(
            company=self.company, invoice=self.invoice, method=Payment.BANK_TRANSFER,
            amount=Decimal("15"), company_bank_account=bankak, sender_bank_name="Ali",
            transfer_reference="BK7788", reference_last4="7788",
        )
        doc = self.client.get(reverse("invoice-document", args=[self.invoice.id])).data
        self.assertEqual(
            [(p["method"], p["amount"], p["channel"], p["reference"]) for p in doc["payments"]],
            [("cash", "100.00", "", ""), ("bank_transfer", "15.00", "bankak", "BK7788")],
        )
        self.assertEqual(doc["amount_due"], "0.00")
