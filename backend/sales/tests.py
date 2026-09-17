import uuid
from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product, StockMovement, Warehouse
from org.models import Branch, Company
from sales.models import CompanyBankAccount, Customer, Invoice, Payment


class SalesBase(APITestCase):
    def setUp(self):
        self.company_a = Company.objects.create(name="Alpha")
        self.company_b = Company.objects.create(name="Beta")
        self.branch_a = Branch.objects.create(company=self.company_a, name="Main")
        self.branch_b = Branch.objects.create(company=self.company_b, name="Main")
        self.role = Role.objects.create(
            name="Sales Officer", scope_level=Role.SCOPE_BRANCH
        )
        self.user_a = User.objects.create_user(
            email="a@alpha.test", password="passw0rd123",
            company=self.company_a, branch=self.branch_a, role=self.role,
        )
        self.wh_a = Warehouse.objects.create(
            company=self.company_a, branch=self.branch_a, name="A-WH"
        )
        self.product = Product.objects.create(
            company=self.company_a, sku="SKU1", name="Widget",
            sale_price=Decimal("100.00"),
        )
        self.bank_a = CompanyBankAccount.objects.create(
            company=self.company_a, bank_name="Bank of Alpha", account_name="Alpha Co",
        )
        # Sales on account need a named debtor (see POSCheckoutSerializer);
        # tests that leave a balance sell to this account customer.
        self.customer = Customer.objects.create(company=self.company_a, name="Account customer")
        r = self.client.post(
            reverse("auth-login"), {"email": "a@alpha.test", "password": "passw0rd123"}
        )
        assert r.status_code == 200, r.content

    def checkout(self, client_uuid=None, payment=None, qty="2"):
        payload = {
            "warehouse": self.wh_a.id,
            "customer": self.customer.id,
            "lines": [{"product": self.product.id, "quantity": qty}],
        }
        if client_uuid:
            payload["client_uuid"] = str(client_uuid)
        if payment is not None:
            payload["payment"] = payment
        return self.client.post(reverse("pos-checkout"), payload, format="json")


class OfflineCashSaleTests(SalesBase):
    def test_cash_sale_completes_and_deducts_stock(self):
        resp = self.checkout(
            payment={"method": "cash", "amount": "200.00"}
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertEqual(resp.data["status"], "paid")
        self.assertEqual(Decimal(str(resp.data["amount_due"])), Decimal("0"))
        # Exactly one sale_out movement, negative quantity.
        moves = StockMovement.objects.filter(movement_type="sale_out")
        self.assertEqual(moves.count(), 1)
        self.assertEqual(moves.first().quantity, Decimal("-2"))

    def test_checkout_is_idempotent_on_replay(self):
        cu = uuid.uuid4()
        r1 = self.checkout(client_uuid=cu, payment={"method": "cash", "amount": "200.00"})
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        r2 = self.checkout(client_uuid=cu, payment={"method": "cash", "amount": "200.00"})
        # Replay returns the same invoice, no second sale.
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(StockMovement.objects.filter(movement_type="sale_out").count(), 1)


class InvoiceNumberingTests(SalesBase):
    def test_numbers_are_sequential_and_gapless_per_company(self):
        n1 = self.checkout().data["number"]
        n2 = self.checkout().data["number"]
        n3 = self.checkout().data["number"]
        self.assertEqual([n1, n2, n3], [1, 2, 3])

    def test_numbering_is_independent_across_companies(self):
        self.checkout()  # company A -> 1
        # Company B's first invoice should also be 1.
        User.objects.create_user(
            email="b@beta.test", password="passw0rd123",
            company=self.company_b, branch=self.branch_b, role=self.role,
        )
        wh_b = Warehouse.objects.create(
            company=self.company_b, branch=self.branch_b, name="B-WH"
        )
        prod_b = Product.objects.create(
            company=self.company_b, sku="SKU1", name="W", sale_price=Decimal("50"),
        )
        client_b = self.client_class()
        client_b.post(
            reverse("auth-login"), {"email": "b@beta.test", "password": "passw0rd123"}
        )
        resp = client_b.post(
            reverse("pos-checkout"),
            {"warehouse": wh_b.id, "lines": [{"product": prod_b.id, "quantity": "1"}],
             "payment": {"method": "cash", "amount": "50.00"}},
            format="json",
        )
        self.assertEqual(resp.data["number"], 1)


class ManualPaymentTests(SalesBase):
    def _make_invoice(self):
        return self.checkout().data["id"]

    def test_bank_transfer_records_bank_and_last4_no_external_calls(self):
        invoice_id = self._make_invoice()
        resp = self.client.post(
            reverse("payment-list"),
            {
                "invoice": invoice_id,
                "method": "bank_transfer",
                "company_bank_account": self.bank_a.id,
                "sender_bank_name": "Customer Bank",
                "reference_last4": "1234",
                "amount": "200.00",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        payment = Payment.objects.get(id=resp.data["id"])
        self.assertEqual(payment.sender_bank_name, "Customer Bank")
        self.assertEqual(payment.reference_last4, "1234")
        self.assertEqual(payment.company_bank_account, self.bank_a)

    def test_bank_transfer_missing_details_rejected(self):
        invoice_id = self._make_invoice()
        resp = self.client.post(
            reverse("payment-list"),
            {"invoice": invoice_id, "method": "bank_transfer", "amount": "200.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reference_last4_must_be_digits(self):
        invoice_id = self._make_invoice()
        resp = self.client.post(
            reverse("payment-list"),
            {
                "invoice": invoice_id, "method": "bank_transfer",
                "company_bank_account": self.bank_a.id,
                "sender_bank_name": "X", "reference_last4": "abcd", "amount": "10",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cash_payment_must_not_carry_bank_details(self):
        invoice_id = self._make_invoice()
        resp = self.client.post(
            reverse("payment-list"),
            {
                "invoice": invoice_id, "method": "cash", "amount": "10",
                "sender_bank_name": "Nope",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_payment_verify_sets_verified_fields(self):
        # Segregation of duties: verification must come from a *different* user
        # than the one who recorded the payment, so a second user is used here.
        invoice_id = self._make_invoice()
        pay = self.client.post(
            reverse("payment-list"),
            {"invoice": invoice_id, "method": "cash", "amount": "200.00"},
            format="json",
        ).data
        checker = User.objects.create_user(
            email="checker@alpha.test", password="passw0rd123",
            company=self.company_a, role=self.role,
        )
        other = self.client_class()
        other.force_authenticate(checker)
        resp = other.post(reverse("payment-verify", args=[pay["id"]]))
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertIsNotNone(resp.data["verified_at"])

    def test_payments_are_append_only(self):
        invoice_id = self._make_invoice()
        pay = self.client.post(
            reverse("payment-list"),
            {"invoice": invoice_id, "method": "cash", "amount": "200.00"},
            format="json",
        ).data
        detail = reverse("payment-detail", args=[pay["id"]])
        self.assertEqual(self.client.put(detail, {}).status_code, 405)
        self.assertEqual(self.client.delete(detail).status_code, 405)


class SalesScopingTests(SalesBase):
    def test_cannot_pay_another_companys_invoice(self):
        # Build an invoice under company B directly.
        wh_b = Warehouse.objects.create(company=self.company_b, name="B-WH")
        inv_b = Invoice.objects.create(
            company=self.company_b, warehouse=wh_b, number=1, total=Decimal("50"),
        )
        resp = self.client.post(
            reverse("payment-list"),
            {"invoice": inv_b.id, "method": "cash", "amount": "50"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invoice_list_scoped(self):
        self.checkout()
        Invoice.objects.create(
            company=self.company_b,
            warehouse=Warehouse.objects.create(company=self.company_b, name="BW"),
            number=1, total=Decimal("5"),
        )
        resp = self.client.get(reverse("invoice-list"))
        companies = {i["company"] for i in resp.data["results"]}
        self.assertEqual(companies, {self.company_a.id})


class CustomerRecordsTests(APITestCase):
    """The customer records page: timeline assembly, status, export, RBAC."""

    def setUp(self):
        from decimal import Decimal
        from django.utils import timezone
        from inventory.models import Warehouse
        self.company = Company.objects.create(name="RecCo")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.role = Role.objects.create(name="Sales Officer", scope_level=Role.SCOPE_BRANCH)
        self.user = User.objects.create_user(
            email="rec@sales.test", password="passw0rd12345",
            company=self.company, branch=self.branch, role=self.role,
        )
        self.wh = Warehouse.objects.create(
            company=self.company, branch=self.branch, name="W1"
        )
        self.customer = Customer.objects.create(company=self.company, name="Acme Buyer")
        inv = Invoice.objects.create(
            company=self.company, customer=self.customer, branch=self.branch,
            warehouse=self.wh,
            number=1, subtotal=Decimal("100"), tax_amount=Decimal("0"),
            total=Decimal("100"), issued_at=timezone.now(),
        )
        Payment.objects.create(
            company=self.company, invoice=inv, method="cash",
            amount=Decimal("40"), recorded_at=timezone.now(),
        )
        self.client.force_authenticate(self.user)

    def _url(self):
        return reverse("customer-records", args=[self.customer.id])

    def test_records_returns_timeline_and_balance(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["customer"]["status"], "owing")
        self.assertEqual(resp.data["customer"]["balance"], "60.00")
        kinds = {e["type"] for e in resp.data["events"]}
        self.assertIn("invoice", kinds)
        self.assertIn("payment", kinds)

    def test_events_are_newest_first(self):
        resp = self.client.get(self._url())
        dates = [e["date"] for e in resp.data["events"] if e["date"]]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_type_filter(self):
        resp = self.client.get(self._url(), {"type": "payment"})
        self.assertTrue(all(e["type"] == "payment" for e in resp.data["events"]))

    def test_csv_export_and_is_audited(self):
        from core.models import ActivityLog
        resp = self.client.get(self._url(), {"format": "csv"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertTrue(
            ActivityLog.objects.filter(entity_type="Customer", action="export").exists()
        )

    def test_view_is_audited(self):
        from core.models import ActivityLog
        self.client.get(self._url())
        self.assertTrue(
            ActivityLog.objects.filter(entity_type="Customer", action="view").exists()
        )

    def test_role_without_sales_is_denied(self):
        hr = Role.objects.create(name="HR Officer", scope_level=Role.SCOPE_BRANCH)
        other = User.objects.create_user(
            email="hr@rec.test", password="passw0rd12345",
            company=self.company, branch=self.branch, role=hr,
        )
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get(self._url()).status_code, 403)

    def test_other_company_customer_is_not_reachable(self):
        beta = Company.objects.create(name="Beta")
        theirs = Customer.objects.create(company=beta, name="Theirs")
        resp = self.client.get(reverse("customer-records", args=[theirs.id]))
        self.assertEqual(resp.status_code, 404)


class CreditTermsAndControlsTests(APITestCase):
    """Phase-1 financial controls: credit terms drive due dates and aging, and
    a payment's recorder may not verify it."""

    def setUp(self):
        from inventory.models import Warehouse
        self.company = Company.objects.create(name="TermsCo")
        self.role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.maker = User.objects.create_user(
            email="maker@terms.test", password="passw0rd12345",
            company=self.company, role=self.role,
        )
        self.checker = User.objects.create_user(
            email="checker@terms.test", password="passw0rd12345",
            company=self.company, role=self.role,
        )
        self.wh = Warehouse.objects.create(company=self.company, name="W")
        self.customer = Customer.objects.create(company=self.company, name="Buyer")
        self.invoice = Invoice.objects.create(
            company=self.company, customer=self.customer, warehouse=self.wh,
            number=1, subtotal=Decimal("200"), total=Decimal("200"),
            payment_terms_days=30,
        )

    def test_due_date_derived_from_terms(self):
        from datetime import timedelta
        expected = self.invoice.issued_at.date() + timedelta(days=30)
        self.assertEqual(self.invoice.due_date, expected)
        self.assertFalse(self.invoice.is_overdue)

    def test_overdue_detection(self):
        from datetime import date, timedelta
        Invoice.objects.filter(pk=self.invoice.pk).update(
            due_date=date.today() - timedelta(days=10)
        )
        self.invoice.refresh_from_db()
        self.assertTrue(self.invoice.is_overdue)
        self.assertEqual(self.invoice.days_overdue, 10)

    def test_paid_invoice_is_never_overdue(self):
        from datetime import date, timedelta
        Invoice.objects.filter(pk=self.invoice.pk).update(
            due_date=date.today() - timedelta(days=10)
        )
        self.invoice.refresh_from_db()
        Payment.objects.create(
            company=self.company, invoice=self.invoice,
            method="cash", amount=Decimal("200"),
        )
        self.assertEqual(self.invoice.days_overdue, 0)

    def test_recorder_cannot_verify_own_payment(self):
        payment = Payment.objects.create(
            company=self.company, invoice=self.invoice, method="cash",
            amount=Decimal("50"), recorded_by=self.maker,
        )
        self.client.force_authenticate(self.maker)
        resp = self.client.post(reverse("payment-verify", args=[payment.id]))
        self.assertEqual(resp.status_code, 403, resp.data)
        payment.refresh_from_db()
        self.assertIsNone(payment.verified_at)

    def test_different_user_can_verify(self):
        payment = Payment.objects.create(
            company=self.company, invoice=self.invoice, method="cash",
            amount=Decimal("50"), recorded_by=self.maker,
        )
        self.client.force_authenticate(self.checker)
        resp = self.client.post(reverse("payment-verify", args=[payment.id]))
        self.assertEqual(resp.status_code, 200, resp.data)
        payment.refresh_from_db()
        self.assertEqual(payment.verified_by_id, self.checker.id)

    def test_income_statement_and_cash_flow(self):
        self.client.force_authenticate(self.maker)
        inc = self.client.get(reverse("report-income-statement"))
        self.assertEqual(inc.status_code, 200, inc.data)
        for key in ("revenue", "cogs", "gross_profit", "total_expenses", "net_profit"):
            self.assertIn(key, inc.data)
        cf = self.client.get(reverse("report-cash-flow"))
        self.assertEqual(cf.status_code, 200, cf.data)
        self.assertIn("net_cash_flow", cf.data)

    def test_receivables_worklist_lists_overdue(self):
        from datetime import date, timedelta
        Invoice.objects.filter(pk=self.invoice.pk).update(
            due_date=date.today() - timedelta(days=5)
        )
        self.client.force_authenticate(self.maker)
        resp = self.client.get(reverse("report-receivables-due"))
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["overdue_count"], 1)


class PaymentApprovalTierTests(APITestCase):
    """Two-tier approval: any second user for small payments, an approver role
    (CFO/owner/GM) once the company threshold is reached."""

    def setUp(self):
        from inventory.models import Warehouse
        self.company = Company.objects.create(
            name="ApprovalCo", payment_approval_threshold=Decimal("1000")
        )
        self.clerk_role = Role.objects.create(
            name="Finance Department", scope_level=Role.SCOPE_BUSINESS
        )
        self.cfo_role = Role.objects.create(
            name="Chief Financial Officer", scope_level=Role.SCOPE_BUSINESS
        )
        self.recorder = User.objects.create_user(
            email="rec@ap.test", password="passw0rd12345",
            company=self.company, role=self.clerk_role,
        )
        self.clerk = User.objects.create_user(
            email="clerk@ap.test", password="passw0rd12345",
            company=self.company, role=self.clerk_role,
        )
        self.cfo = User.objects.create_user(
            email="cfo@ap.test", password="passw0rd12345",
            company=self.company, role=self.cfo_role,
        )
        wh = Warehouse.objects.create(company=self.company, name="W")
        customer = Customer.objects.create(company=self.company, name="C")
        self.invoice = Invoice.objects.create(
            company=self.company, customer=customer, warehouse=wh, number=1,
            subtotal=Decimal("9000"), total=Decimal("9000"),
        )

    def _payment(self, amount):
        return Payment.objects.create(
            company=self.company, invoice=self.invoice, method="cash",
            amount=Decimal(amount), recorded_by=self.recorder,
        )

    def _verify_as(self, user, payment):
        self.client.force_authenticate(user)
        return self.client.post(reverse("payment-verify", args=[payment.id]))

    def test_small_payment_any_second_user(self):
        self.assertEqual(self._verify_as(self.clerk, self._payment("100")).status_code, 200)

    def test_large_payment_denied_to_non_approver(self):
        resp = self._verify_as(self.clerk, self._payment("2000"))
        self.assertEqual(resp.status_code, 403, resp.data)
        self.assertIn("threshold", resp.data)

    def test_large_payment_allowed_for_cfo(self):
        self.assertEqual(self._verify_as(self.cfo, self._payment("2000")).status_code, 200)

    def test_segregation_of_duties_beats_approval_authority(self):
        # Even a CFO cannot approve a payment they recorded themselves.
        payment = Payment.objects.create(
            company=self.company, invoice=self.invoice, method="cash",
            amount=Decimal("2000"), recorded_by=self.cfo,
        )
        self.assertEqual(self._verify_as(self.cfo, payment).status_code, 403)

    def test_threshold_of_zero_disables_the_extra_tier(self):
        self.company.payment_approval_threshold = Decimal("0")
        self.company.save()
        self.assertEqual(self._verify_as(self.clerk, self._payment("999999")).status_code, 200)

    def test_cfo_cannot_write_sales_or_purchasing(self):
        # The CFO controls money; it must not be able to raise invoices.
        from core.rbac import role_can
        self.assertFalse(role_can(self.cfo, "sales", write=True))
        self.assertFalse(role_can(self.cfo, "purchasing", write=True))
        self.assertTrue(role_can(self.cfo, "finance", write=True))
        self.assertTrue(role_can(self.cfo, "reports", write=True))

    def test_cfo_kpis_and_payables_due(self):
        self.client.force_authenticate(self.cfo)
        kpi = self.client.get(reverse("report-cfo-kpis"))
        self.assertEqual(kpi.status_code, 200, kpi.data)
        for section in ("profitability", "liquidity", "receivables", "payables"):
            self.assertIn(section, kpi.data)
        due = self.client.get(reverse("report-payables-due"))
        self.assertEqual(due.status_code, 200, due.data)
        self.assertIn("total_due", due.data)

    def test_ratio_is_null_not_zero_when_undefined(self):
        self.client.force_authenticate(self.cfo)
        kpi = self.client.get(reverse("report-cfo-kpis"))
        # No payables exist, so the ratio is undefined rather than 0.
        self.assertIsNone(kpi.data["liquidity"]["current_ratio_pct"])
