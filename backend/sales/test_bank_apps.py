"""Bank-app transfers (Bankak, Fawri, O-Cash): channels, full references,
the duplicate-screenshot guard, and statement reconciliation."""
import io
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from sales.models import CompanyBankAccount, Payment
from sales.test_payment_verification import VerificationBase


class BankAppBase(VerificationBase):
    def setUp(self):
        super().setUp()
        self.bankak = CompanyBankAccount.objects.create(
            company=self.company, channel=CompanyBankAccount.CHANNEL_BANKAK,
            bank_name="Bank of Khartoum", account_name="Alpha Trading", account_number="1234",
        )
        self.branch_account = CompanyBankAccount.objects.create(
            company=self.company, bank_name="Faisal", account_name="Alpha",
        )

    def _transfer(self, client, amount, reference=None, last4=None, account=None):
        body = {
            "invoice": self.invoice.pk, "method": "bank_transfer", "amount": amount,
            "company_bank_account": (account or self.bankak).pk,
            "sender_bank_name": "Ahmed (Bankak)",
        }
        if reference is not None:
            body["transfer_reference"] = reference
        if last4 is not None:
            body["reference_last4"] = last4
        return client.post(reverse("payment-list"), body, format="json")


class TransferReferenceTests(BankAppBase):
    def test_full_reference_is_kept_and_last4_derived(self):
        r = self._transfer(self.client_for(self.cashier), "300.00", reference="BK-2026 0919 7788")
        self.assertEqual(r.status_code, 201, r.data)
        payment = Payment.objects.get(pk=r.data["id"])
        self.assertEqual(payment.transfer_reference, "BK202609197788")
        self.assertEqual(payment.reference_last4, "7788")
        self.assertEqual(r.data["bank_channel"], "bankak")

    def test_same_reference_on_same_account_is_refused(self):
        client = self.client_for(self.cashier)
        self.assertEqual(self._transfer(client, "300.00", reference="778899").status_code, 201)
        dup = self._transfer(client, "300.00", reference="778899")
        self.assertEqual(dup.status_code, 400, dup.data)
        self.assertIn("transfer_reference", dup.data)
        # A different receiving account may legitimately see the same id.
        other = self._transfer(client, "300.00", reference="778899", account=self.branch_account)
        self.assertEqual(other.status_code, 201, other.data)

    def test_last4_alone_still_works_and_nothing_at_all_is_refused(self):
        client = self.client_for(self.cashier)
        self.assertEqual(self._transfer(client, "100.00", last4="4321").status_code, 201)
        self.assertEqual(self._transfer(client, "100.00").status_code, 400)

    def test_pos_checkout_accepts_the_transfer_reference(self):
        from inventory.models import Product, StockMovement, Warehouse

        wh = Warehouse.objects.get(company=self.company)
        product = Product.objects.create(
            company=self.company, sku="P", name="P", sale_price=Decimal("50"),
        )
        StockMovement.objects.create(
            company=self.company, product=product, warehouse=wh,
            movement_type=StockMovement.PURCHASE_IN, quantity=Decimal("5"),
        )
        # The fixture invoice took number 1 by hand; move it out of the way
        # of the checkout's own numbering.
        type(self.invoice).objects.filter(pk=self.invoice.pk).update(number=900001)
        client = self.client_for(self.owner)
        r = client.post(reverse("pos-checkout"), {
            "warehouse": wh.pk, "lines": [{"product": product.pk, "quantity": "1"}],
            "payment": {
                "method": "bank_transfer", "amount": "50.00",
                "company_bank_account": self.bankak.pk, "sender_bank_name": "Sara",
                "transfer_reference": "TX 5555 6666",
            },
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        payment = Payment.objects.filter(invoice_id=r.data["id"]).get()
        self.assertEqual(payment.transfer_reference, "TX55556666")
        self.assertEqual(payment.reference_last4, "6666")


class ReconcileTests(BankAppBase):
    def _statement(self, rows, name="bankak.csv"):
        text = "التاريخ,رقم العملية,المبلغ,المرسل\n" + "\n".join(rows)
        return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")

    def _reconcile(self, user, rows, dry_run=False, account=None):
        client = self.client_for(user)
        return client.post(reverse("payment-reconcile"), {
            "account": (account or self.bankak).pk, "file": self._statement(rows),
            **({"dry_run": "1"} if dry_run else {}),
        }, format="multipart")

    def test_matches_by_reference_then_by_last4_and_marks_verified(self):
        cashier = self.client_for(self.cashier)
        a = Payment.objects.get(pk=self._transfer(cashier, "300.00", reference="AA1111").data["id"])
        b = Payment.objects.get(pk=self._transfer(cashier, "450.00", last4="2222").data["id"])
        c = Payment.objects.get(pk=self._transfer(cashier, "80.00", reference="CC3333").data["id"])
        r = self._reconcile(self.finance, [
            "2026-09-19 10:00,AA-1111,300.00,Ahmed",
            "2026-09-19 10:05,99992222,450,Sara",
            "2026-09-19 10:09,ZZ9999,120.00,Unknown",
        ])
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["rows"], 3)
        hows = {m["payment"]["id"]: m["how"] for m in r.data["matched"]}
        self.assertEqual(hows, {a.pk: "reference", b.pk: "last4_amount"})
        self.assertEqual([u["reason"] for u in r.data["unmatched_rows"]], ["not_recorded"])
        self.assertEqual([u["id"] for u in r.data["unmatched_payments"]], [c.pk])
        self.assertEqual(r.data["applied"], 2)
        for p in (a, b):
            p.refresh_from_db()
            self.assertEqual(p.verified_by, self.finance)
        c.refresh_from_db()
        self.assertIsNone(c.verified_at)

    def test_dry_run_previews_and_self_recorded_are_skipped(self):
        owner = self.client_for(self.owner)
        p = Payment.objects.get(pk=self._transfer(owner, "300.00", reference="AA1111").data["id"])
        preview = self._reconcile(self.finance, ["2026-09-19,AA1111,300,Ahmed"], dry_run=True)
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual((preview.data["applied"], len(preview.data["matched"])), (0, 1))
        p.refresh_from_db()
        self.assertIsNone(p.verified_at)
        # The owner recorded it, so the owner's own statement upload does not verify it.
        own = self._reconcile(self.owner, ["2026-09-19,AA1111,300,Ahmed"])
        self.assertEqual((own.data["applied"], own.data["skipped_self"]), (0, 1))
        self.assertEqual(own.data["matched"][0]["outcome"], "self_recorded")

    def test_amount_mismatch_is_reported_not_verified(self):
        cashier = self.client_for(self.cashier)
        self._transfer(cashier, "300.00", reference="AA1111")
        r = self._reconcile(self.finance, ["2026-09-19,AA1111,250,Ahmed"])
        self.assertTrue(r.data["matched"][0]["amount_differs"])
        self.assertEqual(r.data["matched"][0]["outcome"], "amount_differs")
        self.assertEqual(r.data["applied"], 0)

    def test_outsiders_cannot_reconcile_and_bad_files_are_refused(self):
        from accounts.models import Role, User

        stores = User.objects.create_user(
            email="stores@alpha.test", password="passw0rd123", company=self.company,
            role=Role.objects.create(name="Inventory Officer", scope_level=Role.SCOPE_BUSINESS),
        )
        r = self._reconcile(stores, ["2026-09-19,AA1111,300,Ahmed"])
        self.assertEqual(r.status_code, 403)
        client = self.client_for(self.finance)
        r = client.post(reverse("payment-reconcile"), {
            "account": self.bankak.pk,
            "file": SimpleUploadedFile("x.csv", b"date,name\n1,2", content_type="text/csv"),
        }, format="multipart")
        self.assertEqual(r.status_code, 400)
        self.assertIn("file", r.data)

    def test_xlsx_statement_is_accepted(self):
        from openpyxl import Workbook

        cashier = self.client_for(self.cashier)
        self._transfer(cashier, "300.00", reference="AA1111")
        wb = Workbook()
        ws = wb.active
        ws.append(["Date", "Transaction ID", "Amount"])
        ws.append(["2026-09-19", "AA1111", 300])
        buf = io.BytesIO()
        wb.save(buf)
        client = self.client_for(self.finance)
        r = client.post(reverse("payment-reconcile"), {
            "account": self.bankak.pk,
            "file": SimpleUploadedFile("bankak.xlsx", buf.getvalue()),
        }, format="multipart")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["applied"], 1)
