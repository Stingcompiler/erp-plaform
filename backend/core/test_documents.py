"""
Printable-document tests.

Documents are the only artefact a customer physically holds, so these check the
things that would be visible on paper: that the issuer identity is present,
that money is formatted consistently, that settlement figures agree with the
payment ledger, and that blank optional fields are omitted rather than printed
as empty labels.
"""

from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product, Warehouse
from org.models import Branch, Company
from purchasing.models import Bill, Supplier, SupplierPayment
from returns.models import CreditNote, DebitNote
from sales.models import CompanyBankAccount, Customer, Invoice, InvoiceLine, Payment


class DocumentTestCase(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name="Docs Co",
            legal_name="Docs Trading LLC",
            currency="SDG",
            address="12 Market St, Khartoum",
            phone="+249100000000",
            tax_number="TAX-99887",
            registration_number="CR-12345",
        )
        self.role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        self.user = User.objects.create_user(
            email="owner@docs.test", password="passw0rd12345",
            full_name="Amal Yousif", company=self.company, role=self.role,
        )
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.warehouse = Warehouse.objects.create(company=self.company, name="W")
        self.customer = Customer.objects.create(
            company=self.company, name="Nile Retail", phone="+249111111111",
        )
        self.client.force_authenticate(self.user)

    def _invoice(self, total="1000", number=1):
        inv = Invoice.objects.create(
            company=self.company, customer=self.customer, branch=self.branch,
            warehouse=self.warehouse, number=number,
            subtotal=Decimal(total), total=Decimal(total),
            created_by=self.user,
        )
        product = Product.objects.create(
            company=self.company, sku=f"SKU{number}", name="Widget"
        )
        InvoiceLine.objects.create(
            invoice=inv, product=product, description="Widget",
            quantity=Decimal("2"), unit_price=Decimal("500"),
            line_subtotal=Decimal(total), line_total=Decimal(total),
        )
        return inv


class InvoiceDocumentTests(DocumentTestCase):
    def test_issuer_identity_is_present(self):
        """Without the seller's name, address and tax number a printout is a
        receipt, not a tax invoice."""
        inv = self._invoice()
        resp = self.client.get(reverse("invoice-document", args=[inv.id]))
        self.assertEqual(resp.status_code, 200, resp.data)
        issuer = resp.data["issuer"]
        self.assertEqual(issuer["name"], "Docs Co")
        self.assertEqual(issuer["legal_name"], "Docs Trading LLC")
        self.assertEqual(issuer["tax_number"], "TAX-99887")
        self.assertEqual(issuer["registration_number"], "CR-12345")
        self.assertEqual(issuer["address"], "12 Market St, Khartoum")

    def test_blank_issuer_fields_are_omitted_not_empty(self):
        """An unregistered company must not print a dangling 'Tax No:' label."""
        bare = Company.objects.create(name="Bare Co")
        user = User.objects.create_user(
            email="b@bare.test", password="passw0rd12345",
            company=bare, role=self.role,
        )
        wh = Warehouse.objects.create(company=bare, name="W")
        inv = Invoice.objects.create(
            company=bare, warehouse=wh, number=1,
            subtotal=Decimal("10"), total=Decimal("10"),
        )
        self.client.force_authenticate(user)
        resp = self.client.get(reverse("invoice-document", args=[inv.id]))
        self.assertEqual(resp.data["issuer"], {"name": "Bare Co"})

    def test_dates_and_terms_are_present(self):
        inv = self._invoice()
        resp = self.client.get(reverse("invoice-document", args=[inv.id]))
        self.assertIsNotNone(resp.data["issued_at"])
        self.assertIsNotNone(resp.data["due_date"])
        self.assertIn("payment_terms_days", resp.data)

    def test_settlement_matches_the_payment_ledger(self):
        inv = self._invoice(total="1000")
        Payment.objects.create(
            company=self.company, invoice=inv, method="cash",
            amount=Decimal("400"), recorded_by=self.user,
        )
        resp = self.client.get(reverse("invoice-document", args=[inv.id]))
        self.assertEqual(resp.data["amount_paid"], "400.00")
        self.assertEqual(resp.data["amount_due"], "600.00")
        self.assertEqual(resp.data["status"], "partially_paid")

    def test_money_is_uniformly_two_decimals(self):
        """Mixing '0' with '0.00' on one page reads as a bug to whoever is
        holding the paper."""
        inv = self._invoice(total="1000")
        resp = self.client.get(reverse("invoice-document", args=[inv.id]))
        amounts = [
            resp.data["subtotal"], resp.data["tax"], resp.data["total"],
            resp.data["amount_paid"], resp.data["amount_due"],
            resp.data["lines"][0]["unit_price"],
            resp.data["lines"][0]["line_total"],
        ]
        for value in amounts:
            self.assertRegex(value, r"^-?\d+\.\d{2}$", value)

    def test_line_detail_survives(self):
        inv = self._invoice()
        resp = self.client.get(reverse("invoice-document", args=[inv.id]))
        line = resp.data["lines"][0]
        self.assertEqual(line["description"], "Widget")
        self.assertEqual(line["unit_price"], "500.00")

    def test_document_is_company_scoped(self):
        other = Company.objects.create(name="Other Co")
        wh = Warehouse.objects.create(company=other, name="W")
        foreign = Invoice.objects.create(
            company=other, warehouse=wh, number=1,
            subtotal=Decimal("5"), total=Decimal("5"),
        )
        resp = self.client.get(reverse("invoice-document", args=[foreign.id]))
        self.assertEqual(resp.status_code, 404)


class CompanyProfileTests(DocumentTestCase):
    """A business must be able to fix its own printed identity without needing
    a platform administrator."""

    def test_owner_can_read_own_issuer_details(self):
        resp = self.client.get(reverse("company-profile"))
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["tax_number"], "TAX-99887")

    def test_owner_can_update_issuer_details(self):
        resp = self.client.patch(
            reverse("company-profile"),
            {"address": "New Street 5", "tax_number": "TAX-00001"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.company.refresh_from_db()
        self.assertEqual(self.company.address, "New Street 5")
        self.assertEqual(self.company.tax_number, "TAX-00001")

    def test_update_flows_through_to_the_printed_document(self):
        inv = self._invoice()
        self.client.patch(
            reverse("company-profile"), {"phone": "+249999"}, format="json"
        )
        resp = self.client.get(reverse("invoice-document", args=[inv.id]))
        self.assertEqual(resp.data["issuer"]["phone"], "+249999")

    def test_company_name_cannot_be_blanked(self):
        """Every document's issuer block is anchored on the name."""
        resp = self.client.patch(
            reverse("company-profile"), {"name": "   "}, format="json"
        )
        self.assertEqual(resp.status_code, 400, resp.data)

    def test_structural_fields_are_not_editable_here(self):
        resp = self.client.patch(
            reverse("company-profile"),
            {"is_active": False, "slug": "hijacked"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.company.refresh_from_db()
        self.assertTrue(self.company.is_active)
        self.assertNotEqual(self.company.slug, "hijacked")

    def test_role_without_settings_access_is_denied(self):
        clerk_role = Role.objects.create(
            name="Sales Officer", scope_level=Role.SCOPE_BRANCH
        )
        clerk = User.objects.create_user(
            email="clerk@docs.test", password="passw0rd12345",
            company=self.company, role=clerk_role,
        )
        self.client.force_authenticate(clerk)
        resp = self.client.patch(
            reverse("company-profile"), {"phone": "x"}, format="json"
        )
        self.assertEqual(resp.status_code, 403, resp.data)


class CreditNoteDocumentTests(DocumentTestCase):
    def test_credit_note_document_renders(self):
        """Rule #6 requires a note for every return; before this it existed in
        the database but nobody could hand it to the customer."""
        inv = self._invoice()
        note = CreditNote.objects.create(
            company=self.company, customer=self.customer, invoice=inv,
            amount=Decimal("250"), reason="Damaged goods", created_by=self.user,
        )
        resp = self.client.get(reverse("creditnote-document", args=[note.id]))
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["doc_type"], "credit_note")
        self.assertEqual(resp.data["number"], f"CN-{note.id:06d}")
        self.assertEqual(resp.data["amount"], "250.00")
        self.assertEqual(resp.data["against_invoice"], inv.number_display)
        self.assertEqual(resp.data["party"]["name"], "Nile Retail")
        self.assertEqual(resp.data["issuer"]["tax_number"], "TAX-99887")
        self.assertEqual(resp.data["issued_by"], "Amal Yousif")

    def test_debit_note_document_renders(self):
        supplier = Supplier.objects.create(company=self.company, name="Delta Supply")
        bill = Bill.objects.create(
            company=self.company, supplier=supplier,
            supplier_invoice_number="SUP-77", total=Decimal("900"),
        )
        note = DebitNote.objects.create(
            company=self.company, supplier=supplier, bill=bill,
            amount=Decimal("100"), reason="Short delivery",
        )
        resp = self.client.get(reverse("debitnote-document", args=[note.id]))
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["doc_type"], "debit_note")
        self.assertEqual(resp.data["party"]["name"], "Delta Supply")
        self.assertEqual(resp.data["against_bill"], "SUP-77")

    def test_credit_note_document_is_company_scoped(self):
        other = Company.objects.create(name="Other Co")
        cust = Customer.objects.create(company=other, name="Foreign")
        note = CreditNote.objects.create(
            company=other, customer=cust, amount=Decimal("1"),
        )
        resp = self.client.get(reverse("creditnote-document", args=[note.id]))
        self.assertEqual(resp.status_code, 404)


class PaymentDocumentTests(DocumentTestCase):
    def test_receipt_shows_invoice_position_after_the_payment(self):
        inv = self._invoice(total="1000")
        payment = Payment.objects.create(
            company=self.company, invoice=inv, method="cash",
            amount=Decimal("300"), recorded_by=self.user,
        )
        resp = self.client.get(reverse("payment-document", args=[payment.id]))
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["doc_type"], "payment_receipt")
        self.assertEqual(resp.data["amount"], "300.00")
        self.assertEqual(resp.data["invoice_total"], "1000.00")
        self.assertEqual(resp.data["invoice_due"], "700.00")
        self.assertEqual(resp.data["received_by"], "Amal Yousif")

    def test_receipt_never_exposes_a_full_bank_reference(self):
        inv = self._invoice(total="500")
        account = CompanyBankAccount.objects.create(
            company=self.company, bank_name="Bank X", account_name="Main",
            account_number="1234567890123",
        )
        payment = Payment.objects.create(
            company=self.company, invoice=inv, method="bank_transfer",
            company_bank_account=account, amount=Decimal("500"),
            sender_bank_name="Bank Y", reference_last4="4321",
        )
        resp = self.client.get(reverse("payment-document", args=[payment.id]))
        self.assertEqual(resp.data["bank"]["reference_last4"], "4321")
        self.assertNotIn("1234567890123", str(resp.data))

    def test_supplier_payment_voucher_renders(self):
        supplier = Supplier.objects.create(company=self.company, name="Delta Supply")
        bill = Bill.objects.create(
            company=self.company, supplier=supplier,
            supplier_invoice_number="SUP-88", total=Decimal("700"),
        )
        payment = SupplierPayment.objects.create(
            company=self.company, supplier=supplier, bill=bill,
            method="cash", amount=Decimal("700"), recorded_by=self.user,
        )
        resp = self.client.get(reverse("supplierpayment-document", args=[payment.id]))
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["doc_type"], "payment_voucher")
        self.assertEqual(resp.data["against_bill"], "SUP-88")
        self.assertEqual(resp.data["amount"], "700.00")
