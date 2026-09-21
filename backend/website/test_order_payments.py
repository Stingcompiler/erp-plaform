"""A visitor declares a bank transfer against their order; the company
confirms (invoice, stock, verified payment), rejects, or flags fraud
(phone and browser blocked)."""

from decimal import Decimal
from io import BytesIO

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import Role, User
from inventory.models import Product, StockMovement, Warehouse
from org.models import Branch, Company
from sales.models import CompanyBankAccount, Invoice, Payment
from website.models import (
    BlockedContact, FeaturedProduct, PublicOrder, PublicOrderPayment, Website,
)


def _png():
    return SimpleUploadedFile(
        "r.png", BytesIO(b"\x89PNG\r\n\x1a\n" + b"0" * 64).getvalue(), content_type="image/png"
    )


@override_settings(
    EMAIL_ENABLED=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    VEZANO_CANONICAL_HOST="vezano.app",
)
class OrderPaymentTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Bakery", slug="bakery", currency="SDG")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.warehouse = Warehouse.objects.create(
            company=self.company, branch=self.branch, name="Main WH"
        )
        owner_role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.owner = User.objects.create_user(
            email="owner@bakery.test", password="Owner-passw0rd!x", company=self.company,
            role=owner_role, branch=self.branch,
        )
        self.site = Website.objects.create(
            company=self.company, business_name="Bakery", is_published=True, accept_orders=True,
        )
        self.bread = Product.objects.create(
            company=self.company, sku="BR", name="Bread", sale_price=Decimal("500"),
            is_stock_tracked=True,
        )
        StockMovement.objects.create(
            company=self.company, product=self.bread, warehouse=self.warehouse,
            quantity=Decimal("10"), movement_type="adjustment",
        )
        FeaturedProduct.objects.create(company=self.company, website=self.site, product=self.bread)
        self.bank = CompanyBankAccount.objects.create(
            company=self.company, bank_name="Bank of Khartoum", account_name="Bakery Ltd",
            account_number="123456", show_to_customers=True,
        )
        CompanyBankAccount.objects.create(
            company=self.company, bank_name="Private", account_name="x", account_number="999",
        )
        self.visitor = APIClient()
        self.staff = APIClient()
        self.staff.force_authenticate(self.owner)

    def _order(self, email=""):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.visitor.post(
                "/api/public/site/bakery/orders/",
                {"contact_name": "Amal", "phone": "0912345678", "email": email,
                 "lines": [{"product": self.bread.pk, "quantity": 2}]},
                format="json",
            )
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_thank_you_carries_details_accounts_and_pay_link(self):
        data = self._order(email="amal@example.com")
        self.assertEqual(data["total"], "1000.00")
        self.assertTrue(data["priced"])
        self.assertEqual([a["bank_name"] for a in data["bank_accounts"]], ["Bank of Khartoum"])
        self.assertEqual(
            data["pay_url"], f"https://vezano.app/s/bakery/pay/?ref={data['reference']}"
        )
        self.assertNotIn("phone", data)
        customer_mail = next(m for m in mail.outbox if m.to == ["amal@example.com"])
        self.assertIn("1000.00 SDG", customer_mail.body)
        self.assertIn("123456", customer_mail.body)
        self.assertIn(data["pay_url"], customer_mail.body)

    def test_visitor_reads_order_and_declares_a_transfer(self):
        ref = self._order()["reference"]
        page = self.visitor.get(f"/api/public/site/bakery/orders/{ref}/")
        self.assertEqual(page.status_code, 200)
        self.assertTrue(page.data["can_pay"])
        missing = self.visitor.get("/api/public/site/bakery/orders/WNOPE00/")
        self.assertEqual(missing.status_code, 404)

        bad = self.visitor.post(
            f"/api/public/site/bakery/orders/{ref}/",
            {"bank_account": self.bank.pk, "sender_bank_name": "Faisal", "reference_last4": "12",
             "amount": "1000"},
        )
        self.assertEqual(bad.status_code, 400)
        self.assertIn("reference_last4", bad.data)
        with self.captureOnCommitCallbacks(execute=True):
            declared = self.visitor.post(
                f"/api/public/site/bakery/orders/{ref}/",
                {"bank_account": self.bank.pk, "sender_bank_name": "Faisal Islamic",
                 "reference_last4": "ab 4321", "amount": "1000", "proof": _png()},
                format="multipart",
            )
        self.assertEqual(declared.status_code, 201, declared.data)
        self.assertEqual(declared.data["status"], "verifying")
        self.assertEqual(declared.data["reference_last4"], "4321")
        again = self.visitor.post(
            f"/api/public/site/bakery/orders/{ref}/",
            {"bank_account": self.bank.pk, "sender_bank_name": "Faisal Islamic",
             "reference_last4": "4321", "amount": "1000"},
        )
        self.assertEqual(again.status_code, 400)
        page = self.visitor.get(f"/api/public/site/bakery/orders/{ref}/").data
        self.assertEqual(page["payments"][0]["status"], "verifying")

    def _declare(self, ref, last4="4321"):
        return self.visitor.post(
            f"/api/public/site/bakery/orders/{ref}/",
            {"bank_account": self.bank.pk, "sender_bank_name": "Faisal", "reference_last4": last4,
             "amount": "1000"},
        ).data["id"]

    def test_confirming_invoices_deducts_stock_and_records_verified_payment(self):
        ref = self._order()["reference"]
        claim_id = self._declare(ref)
        order = PublicOrder.objects.get(reference=ref)
        # Staff sees the claim on the order.
        detail = self.staff.get(f"/api/web-orders/{order.pk}/").data
        self.assertEqual(detail["payments"][0]["status"], "verifying")
        self.assertEqual(detail["payments"][0]["bank_name"], "Bank of Khartoum")

        confirmed = self.staff.post(
            f"/api/web-orders/{order.pk}/payments/{claim_id}/confirm/", {"note": "seen"},
            format="json",
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        claim = PublicOrderPayment.objects.get(pk=claim_id)
        self.assertEqual(claim.status, PublicOrderPayment.CONFIRMED)
        order.refresh_from_db()
        self.assertEqual(order.status, PublicOrder.CONFIRMED)   # order confirmed on the way
        invoice = Invoice.objects.get(pk=claim.invoice_id)
        self.assertEqual(invoice.source_order_id, order.sales_order_id)
        self.assertEqual(invoice.total, Decimal("1000.00"))
        self.assertEqual(self.bread.on_hand(), Decimal("8"))
        payment = Payment.objects.get(pk=claim.payment_id)
        self.assertEqual(payment.method, Payment.BANK_TRANSFER)
        self.assertEqual(payment.reference_last4, "4321")
        self.assertEqual(payment.company_bank_account, self.bank)
        self.assertEqual(payment.verified_by, self.owner)
        self.assertEqual(invoice.amount_due(), Decimal("0.00"))
        # Answering twice is refused.
        self.assertEqual(
            self.staff.post(f"/api/web-orders/{order.pk}/payments/{claim_id}/confirm/").status_code,
            400,
        )
        # The visitor sees it confirmed, and nothing more to pay.
        page = self.visitor.get(f"/api/public/site/bakery/orders/{ref}/").data
        self.assertEqual(page["payments"][0]["status"], "confirmed")
        self.assertFalse(page["can_pay"])

    def test_large_transfer_needs_an_approver(self):
        self.company.payment_approval_threshold = Decimal("500")
        self.company.save()
        sales_role = Role.objects.create(name="Sales Officer", scope_level=Role.SCOPE_BRANCH)
        clerk = User.objects.create_user(
            email="clerk@bakery.test", password="Clerk-passw0rd!x", company=self.company,
            role=sales_role, branch=self.branch,
        )
        ref = self._order()["reference"]
        claim_id = self._declare(ref)
        order = PublicOrder.objects.get(reference=ref)
        client = APIClient()
        client.force_authenticate(clerk)
        response = client.post(f"/api/web-orders/{order.pk}/payments/{claim_id}/confirm/")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "approval_required")
        self.assertEqual(
            self.staff.post(f"/api/web-orders/{order.pk}/payments/{claim_id}/confirm/").status_code,
            200,
        )

    def test_reject_keeps_the_order_open(self):
        ref = self._order()["reference"]
        claim_id = self._declare(ref)
        order = PublicOrder.objects.get(reference=ref)
        rejected = self.staff.post(
            f"/api/web-orders/{order.pk}/payments/{claim_id}/reject/", {"note": "لم يصل"},
            format="json",
        )
        self.assertEqual(rejected.data["payments"][0]["status"], "rejected")
        self.assertFalse(Invoice.objects.exists())
        page = self.visitor.get(f"/api/public/site/bakery/orders/{ref}/").data
        self.assertEqual(page["payments"][0]["decision_note"], "لم يصل")
        self.assertTrue(page["can_pay"])  # may declare the right transfer

    def test_fraud_blocks_the_phone_and_the_browser(self):
        ref = self._order()["reference"]
        claim_id = self._declare(ref)
        order = PublicOrder.objects.get(reference=ref)
        flagged = self.staff.post(
            f"/api/web-orders/{order.pk}/payments/{claim_id}/fraud/", {"note": "fake receipt"},
            format="json",
        )
        self.assertEqual(flagged.data["payments"][0]["status"], "fraud")
        self.assertEqual(flagged.data["status"], "rejected")
        blocked_rows = BlockedContact.objects.filter(company=self.company, phone="0912345678")
        self.assertEqual(blocked_rows.count(), 1)
        # The visitor sees "rejected", never "fraud".
        page = self.visitor.get(f"/api/public/site/bakery/orders/{ref}/").data
        self.assertEqual(page["payments"][0]["status"], "rejected")
        # And cannot order again from that phone.
        blocked = self.visitor.post(
            "/api/public/site/bakery/orders/",
            {"contact_name": "Amal", "phone": "0912345678",
             "lines": [{"product": self.bread.pk, "quantity": 1}]},
            format="json",
        )
        self.assertEqual(blocked.status_code, 400)


class ProofHardeningTests(OrderPaymentTests):
    def _claim_with_proof(self, proof):
        ref = self._order()["reference"]
        return self.visitor.post(
            f"/api/public/site/bakery/orders/{ref}/",
            {"bank_account": self.bank.pk, "sender_bank_name": "Faisal Islamic",
             "reference_last4": "4321", "amount": "1000", "proof": proof},
            format="multipart",
        )

    def test_svg_and_html_proofs_are_refused_even_labelled_as_images(self):
        svg = SimpleUploadedFile(
            "r.png", b'<svg xmlns="http://www.w3.org/2000/svg"><script>1</script></svg>',
            content_type="image/png",
        )
        self.assertEqual(self._claim_with_proof(svg).status_code, 400)
        html = SimpleUploadedFile("r.jpg", b"<html><script>1</script></html>",
                                  content_type="image/jpeg")
        r = self._claim_with_proof(html)
        self.assertEqual(r.status_code, 400)
        self.assertIn("proof", r.data)

    def test_a_real_image_is_stored_under_its_true_extension_and_downloads_as_attachment(self):
        from website.models import PublicOrder

        jpeg = SimpleUploadedFile("shot.svg", b"\xff\xd8\xff\xe0" + b"0" * 64,
                                  content_type="image/svg+xml")
        declared = self._claim_with_proof(jpeg)
        self.assertEqual(declared.status_code, 201, declared.data)
        order = PublicOrder.objects.latest("pk")
        claim = order.payments.get()
        self.assertTrue(claim.proof.name.endswith(".jpg"))
        with self.captureOnCommitCallbacks(execute=True):
            r = self.staff.get(f"/api/web-orders/{order.pk}/payments/{claim.pk}/proof/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/jpeg")
        self.assertTrue(r["Content-Disposition"].startswith("attachment"))
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
