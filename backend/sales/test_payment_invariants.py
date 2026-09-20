"""One payment service (sales/payments.py): capped at the balance due under
a lock, currency from the invoice, split receipts share a group. Closes
review findings F01 (public-order overpay), F04 (client-set currency) and
F17 (one transfer over several invoices)."""
import threading
import uuid
from decimal import Decimal

from django.db import connection, connections
from django.test import TransactionTestCase
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import Role, User
from inventory.models import Warehouse
from org.models import Branch, Company
from sales.models import CompanyBankAccount, Customer, Invoice, Payment
from sales.payments import record_payment
from sales.test_payment_verification import VerificationBase


class PaymentInvariantTests(VerificationBase):
    def setUp(self):
        super().setUp()
        Payment.objects.all().delete()  # the base fixture's two cash rows
        self.bank = CompanyBankAccount.objects.create(
            company=self.company, bank_name="BoK", account_name="Alpha",
        )

    def test_client_cannot_set_currency_or_rate(self):
        client = self.client_for(self.owner)
        r = client.post(reverse("payment-list"), {
            "invoice": self.invoice.pk, "method": "cash", "amount": "100",
            "currency": "USD", "exchange_rate": "0",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        payment = Payment.objects.get(pk=r.data["id"])
        self.assertEqual((payment.currency, payment.exchange_rate), ("SDG", Decimal("1")))

    def test_overpayment_is_refused_by_the_service(self):
        record_payment(self.invoice, amount=Decimal("4900"), method=Payment.CASH)
        with self.assertRaises(Exception) as ctx:
            record_payment(self.invoice, amount=Decimal("200"), method=Payment.CASH)
        self.assertIn("overpayment", str(ctx.exception.detail))
        self.assertEqual(self.invoice.amount_paid(), Decimal("4900"))

    def test_one_transfer_settles_several_invoices_under_one_receipt_group(self):
        second = Invoice.objects.create(
            company=self.company, customer=self.invoice.customer,
            warehouse=self.invoice.warehouse, number=2,
            total=Decimal("400"), subtotal=Decimal("400"),
        )
        client = self.client_for(self.owner)
        group = str(uuid.uuid4())
        body = {
            "method": "bank_transfer", "company_bank_account": self.bank.pk,
            "sender_bank_name": "Ahmed", "transfer_reference": "BK-1000", "receipt_group": group,
        }
        first = client.post(
            reverse("payment-list"), {**body, "invoice": self.invoice.pk, "amount": "600"},
            format="json",
        )
        self.assertEqual(first.status_code, 201, first.data)
        second_r = client.post(
            reverse("payment-list"), {**body, "invoice": second.pk, "amount": "400"},
            format="json",
        )
        self.assertEqual(second_r.status_code, 201, second_r.data)
        self.assertEqual(second.amount_due(), Decimal("0"))
        # The same reference outside the group is still a duplicate.
        again = client.post(reverse("payment-list"), {
            **body, "receipt_group": str(uuid.uuid4()), "invoice": self.invoice.pk,
            "amount": "10",
        }, format="json")
        self.assertEqual(again.status_code, 400)
        self.assertIn("transfer_reference", again.data)


class PublicOrderOverpayTests(TransactionTestCase):
    """F01 end to end: two 800 claims on a 1,000 order."""

    def setUp(self):
        from website.models import FeaturedProduct, Website
        from inventory.models import Product, StockMovement

        self.company = Company.objects.create(name="Bakery", slug="bakery", currency="SDG")
        branch = Branch.objects.create(company=self.company, name="Main")
        self.wh = Warehouse.objects.create(company=self.company, branch=branch, name="W")
        owner_role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.owner = User.objects.create_user(
            email="owner@bakery.test", password="Owner-passw0rd!x", company=self.company,
            role=owner_role, branch=branch,
        )
        Website.objects.create(
            company=self.company, business_name="Bakery", is_published=True, accept_orders=True,
        )
        bread = Product.objects.create(
            company=self.company, sku="BR", name="Bread", sale_price=Decimal("500"),
        )
        StockMovement.objects.create(
            company=self.company, product=bread, warehouse=self.wh, quantity=Decimal("10"),
            movement_type="adjustment",
        )
        FeaturedProduct.objects.create(
            company=self.company, website=self.company.website, product=bread,
        )
        self.bank = CompanyBankAccount.objects.create(
            company=self.company, bank_name="BoK", account_name="Bakery", show_to_customers=True,
        )
        self.visitor = APIClient()
        self.staff = APIClient()
        self.staff.force_authenticate(self.owner)
        order = self.visitor.post(
            "/api/public/site/bakery/orders/",
            {"contact_name": "Amal", "phone": "0912345678",
             "lines": [{"product": bread.pk, "quantity": 2}]},
            format="json",
        ).data
        self.ref = order["reference"]
        self.order_id = order["id"] if "id" in order else None

    def _claim(self, amount, last4):
        r = self.visitor.post(
            f"/api/public/site/bakery/orders/{self.ref}/",
            {"bank_account": self.bank.pk, "sender_bank_name": "Faisal",
             "reference_last4": last4, "amount": amount},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        return r.data["id"]

    def _confirm(self, claim_id):
        from website.models import PublicOrder

        order = PublicOrder.objects.get(reference=self.ref)
        return self.staff.post(
            f"/api/web-orders/{order.pk}/payments/{claim_id}/confirm/", {}, format="json"
        )

    def test_second_claim_cannot_push_paid_past_total(self):
        first, second = self._claim("800", "1111"), self._claim("800", "2222")
        self.assertEqual(self._confirm(first).status_code, 200)
        r = self._confirm(second)
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn("overpayment", str(r.data))
        invoice = Invoice.objects.get(company=self.company)
        self.assertEqual(invoice.amount_paid(), Decimal("800"))
        self.assertEqual(invoice.amount_due(), Decimal("200"))

    def test_a_second_claim_within_the_balance_is_accepted(self):
        first, second = self._claim("800", "1111"), self._claim("200", "2222")
        self.assertEqual(self._confirm(first).status_code, 200)
        self.assertEqual(self._confirm(second).status_code, 200)
        invoice = Invoice.objects.get(company=self.company)
        self.assertEqual(invoice.amount_due(), Decimal("0"))


class ConcurrentOverpayTests(TransactionTestCase):
    """Two writers racing on one invoice: the lock leaves paid <= total.
    Meaningful on PostgreSQL (row locks); SQLite serialises writers anyway."""

    def setUp(self):
        self.company = Company.objects.create(name="Race")
        branch = Branch.objects.create(company=self.company, name="Main")
        wh = Warehouse.objects.create(company=self.company, branch=branch, name="W")
        customer = Customer.objects.create(company=self.company, name="C")
        self.invoice = Invoice.objects.create(
            company=self.company, customer=customer, warehouse=wh, number=1,
            total=Decimal("1000"), subtotal=Decimal("1000"),
        )

    def test_parallel_payments_never_exceed_the_total(self):
        if connection.vendor == "sqlite":
            self.skipTest("row locks only exist on PostgreSQL")
        errors = []

        def worker():
            try:
                record_payment(self.invoice, amount=Decimal("800"), method=Payment.CASH)
            except Exception as exc:  # noqa: BLE001 - collected for the assertion
                errors.append(exc)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(Payment.objects.filter(invoice=self.invoice).count(), 1)
        self.assertEqual(len(errors), 3)
        self.assertLessEqual(self.invoice.amount_paid(), self.invoice.total)


class TransferIdentityTests(VerificationBase):
    """F10: a payment with a full reference is matched on it only; F13: the
    same reference on one invoice is refused even under a race."""

    def setUp(self):
        super().setUp()
        Payment.objects.all().delete()
        self.bank = CompanyBankAccount.objects.create(
            company=self.company, bank_name="BoK", account_name="Alpha",
        )

    def _pay(self, amount, **extra):
        return record_payment(
            self.invoice, amount=Decimal(amount), method=Payment.BANK_TRANSFER,
            company_bank_account=self.bank, sender_bank_name="Ahmed", **extra,
        )

    def _reconcile(self, rows):
        from django.core.files.uploadedfile import SimpleUploadedFile

        client = self.client_for(self.finance)
        text = "reference,amount\n" + "\n".join(rows)
        return client.post(reverse("payment-reconcile"), {
            "account": self.bank.pk,
            "file": SimpleUploadedFile("s.csv", text.encode(), content_type="text/csv"),
            "dry_run": "1",
        }, format="multipart").data

    def test_full_reference_conflict_never_matches_by_last4(self):
        self._pay("300", transfer_reference="AAA1234")
        data = self._reconcile(["BBB1234,300"])
        self.assertEqual(data["matched"], [])
        self.assertEqual([u["reason"] for u in data["unmatched_rows"]], ["not_recorded"])

    def test_last4_only_payment_still_matches_by_last4_and_amount(self):
        self._pay("300", reference_last4="1234")
        data = self._reconcile(["ZZ1234,300"])
        self.assertEqual(len(data["matched"]), 1)
        self.assertEqual(data["matched"][0]["how"], "last4_amount")

    def test_same_reference_on_the_same_invoice_is_refused_by_the_database(self):
        self._pay("100", transfer_reference="DUP1")
        # Bypass the application check to prove the constraint itself.
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError), transaction.atomic():
            Payment.objects.create(
                company=self.company, invoice=self.invoice, method=Payment.BANK_TRANSFER,
                company_bank_account=self.bank, sender_bank_name="x",
                transfer_reference="DUP1", reference_last4="DUP1", amount=Decimal("1"),
            )
        # And the service turns it into a clean 400 rather than a 500.
        with self.assertRaises(Exception) as ctx:
            self._pay("50", transfer_reference="DUP1")
        self.assertIn("transfer_reference", str(ctx.exception.detail))


class ConcurrentReferenceTests(TransactionTestCase):
    """Ten writers presenting one screenshot at once: one payment, nine refusals."""

    def setUp(self):
        self.company = Company.objects.create(name="Race")
        branch = Branch.objects.create(company=self.company, name="Main")
        wh = Warehouse.objects.create(company=self.company, branch=branch, name="W")
        customer = Customer.objects.create(company=self.company, name="C")
        self.bank = CompanyBankAccount.objects.create(
            company=self.company, bank_name="BoK", account_name="Race",
        )
        self.invoices = [
            Invoice.objects.create(
                company=self.company, customer=customer, warehouse=wh, number=n,
                total=Decimal("1000"), subtotal=Decimal("1000"),
            )
            for n in (1, 2)
        ]

    def test_ten_writers_one_reference_across_two_invoices(self):
        if connection.vendor == "sqlite":
            self.skipTest("row locks only exist on PostgreSQL")
        outcomes = []

        def worker(i):
            try:
                record_payment(
                    self.invoices[i % 2], amount=Decimal("100"), method=Payment.BANK_TRANSFER,
                    company_bank_account=self.bank, sender_bank_name="x",
                    transfer_reference="ONE-SCREENSHOT",
                )
                outcomes.append("ok")
            except Exception as exc:  # noqa: BLE001 - collected for the assertion
                outcomes.append(f"{type(exc).__name__}:{getattr(exc, 'detail', exc)}"[:160])
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(outcomes.count("ok"), 1, outcomes)
        self.assertEqual(
            Payment.objects.filter(transfer_reference="ONESCREENSHOT").count(), 1
        )
        self.assertNotIn("IntegrityError", outcomes)  # always a clean ValidationError
