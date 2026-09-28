"""Money and inventory review, round 2 (2026-09-28): regression tests.

Each case reproduced a defect on main; the assertions state the correct
behaviour."""
from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest import mock
from zoneinfo import ZoneInfo

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.costing import compute
from inventory.models import Product, StockMovement, Warehouse
from org.models import Branch, Company
from returns.models import SalesReturnLine
from sales.models import Customer, Invoice


class Base(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Shop", timezone="Africa/Khartoum")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.wh = Warehouse.objects.create(company=self.company, branch=self.branch, name="WH")
        self.product = Product.objects.create(
            company=self.company, sku="P1", name="Widget",
            cost_price=Decimal("80"), sale_price=Decimal("100"),
        )
        self.cashier = User.objects.create_user(
            email="till@shop.test", password="passw0rd12345", company=self.company,
            branch=self.branch,
            role=Role.objects.create(name="Sales Officer", scope_level=Role.SCOPE_BRANCH),
        )
        self.owner = User.objects.create_user(
            email="owner@shop.test", password="passw0rd12345", company=self.company,
            role=Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS),
        )
        self.customer = Customer.objects.create(company=self.company, name="Ali")

    def _in(self, qty, cost, when):
        return StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh,
            movement_type=StockMovement.PURCHASE_IN, quantity=Decimal(str(qty)),
            unit_cost=Decimal(str(cost)), created_at=when,
        )

    def sell(self, user, lines, **extra):
        self.client.force_authenticate(user)
        return self.client.post(
            reverse("pos-checkout"),
            {"warehouse": self.wh.pk, "lines": lines, **extra}, format="json",
        )

    def two_layers_and_one_sale(self, **payment):
        now = timezone.now()
        self._in(10, 50, now - timedelta(hours=3))
        self._in(10, 80, now - timedelta(hours=2))  # cost_price is 80 (last landed)
        r = self.sell(self.owner, [{"product": self.product.pk, "quantity": "1"}],
                      customer=self.customer.pk, **payment)
        self.assertEqual(r.status_code, 201, r.data)
        return Invoice.objects.get(pk=r.data["id"])

    def return_and_restock(self, inv, quantity="1"):
        ret = self.client.post(reverse("salesreturn-list"), {
            "invoice": inv.pk,
            "lines": [{"invoice_line": inv.lines.get().pk, "product": self.product.pk,
                       "quantity": quantity}],
        }, format="json")
        self.assertEqual(ret.status_code, 201, ret.data)
        line = SalesReturnLine.objects.get(sales_return_id=ret.data["id"])
        url = reverse("salesreturn-list") + f"{ret.data['id']}/disposition/"
        body = {"decisions": [{"line_id": line.pk, "action": "restock"}]}
        return url, body, self.client.post(url, body, format="json")


class ReturnsPutBackWhatTheSaleTook(Base):
    """FIFO/average: a return or a void re-enters at what the method charged
    for the sale, not the sale's standard snapshot (the last price paid)."""

    def assert_nothing_sold(self):
        for method in ("fifo", "average"):
            result = compute(self.product, method)
            self.assertEqual(result["cogs"], Decimal("0"), method)
            self.assertEqual(result["on_hand"], Decimal("20"), method)
            self.assertEqual(result["valuation"], Decimal("1300"), method)

    def test_sale_then_full_return(self):
        inv = self.two_layers_and_one_sale(payment={"method": "cash", "amount": "100.00"})
        self.assertEqual(compute(self.product, "fifo")["cogs"], Decimal("50"))
        self.assertEqual(compute(self.product, "average")["cogs"], Decimal("65"))
        _url, _body, d = self.return_and_restock(inv)
        self.assertEqual(d.status_code, 200, d.data)
        self.assert_nothing_sold()
        # The standard method still reverses at the sale's snapshot.
        self.assertEqual(compute(self.product, "standard")["cogs"], Decimal("0"))

    def test_void_reversal(self):
        inv = self.two_layers_and_one_sale()  # on account: nothing to refund
        r = self.client.post(reverse("invoice-void", args=[inv.pk]), {"reason": "typo"},
                             format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assert_nothing_sold()

    def test_restock_twice_is_refused_and_moves_stock_once(self):
        inv = self.two_layers_and_one_sale(payment={"method": "cash", "amount": "100.00"})
        url, body, first = self.return_and_restock(inv)
        self.assertEqual(first.status_code, 200, first.data)
        again = self.client.post(url, body, format="json")
        self.assertEqual(again.status_code, 400)
        self.assertEqual(
            StockMovement.objects.filter(
                movement_type=StockMovement.SALES_RETURN_IN, reference_type="SalesReturn",
            ).count(), 1,
        )


class PurchaseReturnLeavesAtItsCost(Base):
    def test_returning_the_dear_receipt_leaves_the_cheap_stock(self):
        from purchasing.models import GoodsReceipt, Supplier
        from returns.models import DebitNote

        supplier = Supplier.objects.create(company=self.company, name="Acme")
        self.client.force_authenticate(self.owner)
        ids = []
        for cost in ("50.00", "80.00"):
            r = self.client.post(reverse("receiving-create"), {
                "supplier": supplier.pk, "warehouse": self.wh.pk,
                "lines": [{"product": self.product.pk, "quantity": "10", "unit_cost": cost}],
            }, format="json")
            self.assertEqual(r.status_code, 201, r.data)
            ids.append(r.data["id"])
        dear = GoodsReceipt.objects.get(pk=ids[1])
        r = self.client.post(reverse("purchasereturn-list"), {
            "supplier": supplier.pk, "warehouse": self.wh.pk, "goods_receipt": dear.pk,
            "lines": [{"goods_receipt_line": dear.lines.get().pk, "quantity": "10"}],
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(DebitNote.objects.get().amount, Decimal("800.00"))
        # Paid 500 + 800, got 800 back: the 10 left cost 500.
        for method in ("fifo", "average"):
            self.assertEqual(compute(self.product, method)["valuation"], Decimal("500"), method)


class PriceFloorAfterDiscounts(Base):
    def setUp(self):
        super().setUp()
        self.product.cost_price = Decimal("95")
        self.product.save(update_fields=["cost_price"])

    def test_cashier_discount_under_cost_is_refused(self):
        r = self.sell(self.cashier, [{"product": self.product.pk, "quantity": "1",
                                      "discount_percent": "10"}],
                      payment={"method": "cash", "amount": "90.00"})
        self.assertEqual(r.status_code, 400, r.data)
        self.assertEqual(r.data.get("code"), "price_rule")
        self.assertFalse(Invoice.objects.exists())

    def test_discount_above_cost_still_passes(self):
        r = self.sell(self.cashier, [{"product": self.product.pk, "quantity": "1",
                                      "discount_amount": "5.00"}],
                      payment={"method": "cash", "amount": "95.00"})
        self.assertEqual(r.status_code, 201, r.data)

    def test_approver_overrides_and_is_audited(self):
        from core.models import ActivityLog

        r = self.sell(self.owner, [{"product": self.product.pk, "quantity": "1",
                                    "discount_percent": "10"}],
                      payment={"method": "cash", "amount": "90.00"})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(ActivityLog.objects.filter(action="pos_price_override").exists())

    def test_rule_reads_the_net_price(self):
        from sales.price_rules import price_breaches

        row = {
            "sku": "P1", "cost": Decimal("95"), "units": Decimal("1"),
            "unit_value": Decimal("100"), "floor": Decimal("95"), "listed": Decimal("100"),
            "reference": Decimal("100"), "gross": Decimal("100"), "discount": Decimal("10"),
        }
        rules = [b["rule"] for b in price_breaches([row], Decimal("10"))]
        self.assertEqual(rules, ["below_cost"])
        self.assertEqual(price_breaches([{**row, "discount": Decimal("0")}], Decimal("10")), [])


class LateCompletedRenewalStartsNow(APITestCase):
    def test_completed_partial_renewal_grants_a_current_period(self):
        from subscriptions.models import (
            Plan, PlanVersion, Subscription, SubscriptionEvent, SubscriptionInvoice,
            SubscriptionPayment,
        )
        from subscriptions.renewals import renew_with_payment

        company = Company.objects.create(name="Late", timezone="Africa/Khartoum")
        owner = User.objects.create_user(
            email="o@late.test", password="long-password", company=company,
            role=Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS),
        )
        admin = User.objects.create_superuser(email="p@late.test", password="long-password")
        version = PlanVersion.objects.create(
            plan=Plan.objects.create(code="b", name="b"), version=1, currency="SDG",
            price=Decimal("500000.00"), billing_cycle=PlanVersion.MONTHLY, modules=["*"],
            limits={}, published_at=timezone.now(),
        )
        now = timezone.now()
        sub = Subscription.objects.create(
            company=company, plan_version=version, status=Subscription.READ_ONLY,
            starts_at=now - timedelta(days=120), period_ends_at=now - timedelta(days=50),
        )
        first = SubscriptionPayment.objects.create(
            company=company, amount=Decimal("200000.00"), currency="SDG", method="cash",
            recorded_by=owner,
        )
        renew_with_payment(first.pk, admin, now=now - timedelta(days=40))
        invoice = SubscriptionInvoice.objects.get(company=company)
        length = invoice.period_end - invoice.period_start
        second = SubscriptionPayment.objects.create(
            company=company, amount=Decimal("300000.00"), currency="SDG", method="cash",
            recorded_by=owner,
        )
        renew_with_payment(second.pk, admin, now=now)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, SubscriptionInvoice.PAID)
        self.assertEqual(invoice.amount, Decimal("500000.00"))
        today = timezone.localtime(now, ZoneInfo("Africa/Khartoum")).date()
        self.assertEqual(invoice.period_start, today)
        self.assertEqual(invoice.period_end - invoice.period_start, length)
        sub.refresh_from_db()
        self.assertGreater(sub.period_ends_at, now)
        self.assertEqual(sub.status, Subscription.ACTIVE)
        event = SubscriptionEvent.objects.get(event_type="payment_renewed",
                                              metadata__payment_id=second.pk)
        self.assertEqual(len(event.metadata["periods_shifted"]), 1)


class SupplierPaymentRateFromTheBill(Base):
    def setUp(self):
        super().setUp()
        from purchasing.models import Supplier
        from sales.models import CompanyBankAccount

        self.supplier = Supplier.objects.create(company=self.company, name="Acme")
        self.bank = CompanyBankAccount.objects.create(
            company=self.company, bank_name="BoK", account_name="Shop",
            opening_balance=Decimal("10000"),
        )
        self.client.force_authenticate(self.owner)

    def pay(self, bill, **extra):
        return self.client.post("/api/supplier-payments/", {
            "supplier": self.supplier.pk, "bill": bill.pk, "method": "bank_transfer",
            "from_bank_account": self.bank.pk, "reference_last4": "1234",
            "amount": "1000.00", **extra,
        }, format="json")

    def test_client_rate_is_ignored(self):
        from purchasing.models import Bill, SupplierPayment

        bill = Bill.objects.create(
            company=self.company, supplier=self.supplier, currency=self.company.currency,
            subtotal=Decimal("1000"), total=Decimal("1000"),
        )
        r = self.pay(bill, currency="USD", exchange_rate="3")
        self.assertEqual(r.status_code, 201, r.data)
        payment = SupplierPayment.objects.get()
        self.assertEqual(payment.exchange_rate, Decimal("1"))
        self.assertEqual(payment.currency, self.company.currency)
        bill.refresh_from_db()
        self.assertEqual(bill.amount_due(), Decimal("0"))
        self.assertEqual(self.bank.balance(), Decimal("9000"))
        report = self.client.get("/api/reports/cash-flow/")
        self.assertEqual(report.status_code, 200)
        self.assertEqual(Decimal(report.data["supplier_payments"]), Decimal("1000"))

    def test_company_currency_bill_with_a_rate_is_refused(self):
        from purchasing.models import Bill

        bill = Bill.objects.create(
            company=self.company, supplier=self.supplier, currency=self.company.currency,
            exchange_rate=Decimal("3"), subtotal=Decimal("1000"), total=Decimal("1000"),
        )
        r = self.pay(bill)
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn("exchange_rate", r.data)


class ExpenseCorrectionRestoresTheBank(Base):
    def test_correction_follows_the_original(self):
        from finance.models import Expense
        from sales.models import CompanyBankAccount

        bank = CompanyBankAccount.objects.create(
            company=self.company, bank_name="BoK", account_name="Shop",
            opening_balance=Decimal("5000"),
        )
        self.client.force_authenticate(self.owner)
        today = timezone.localdate()
        first = self.client.post(reverse("expense-list"), {
            "category": "Rent", "amount": "1000.00", "method": "bank_transfer",
            "company_bank_account": bank.pk, "date": str(today - timedelta(days=2)),
        }, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(bank.balance(), Decimal("4000"))
        fix = self.client.post(reverse("expense-list"), {
            "category": "Rent", "amount": "-1000.00", "reverses": first.data["id"],
            "date": str(today - timedelta(days=1)),
        }, format="json")
        self.assertEqual(fix.status_code, 201, fix.data)
        correction = Expense.objects.get(pk=fix.data["id"])
        self.assertEqual(correction.method, Expense.BANK_TRANSFER)
        self.assertEqual(correction.company_bank_account_id, bank.pk)
        self.assertEqual(bank.balance(), Decimal("5000"))


class PartialReturnsCreditTheWholeLine(Base):
    def test_three_single_returns_credit_the_line(self):
        from returns.models import CreditNote

        self.product.cost_price = Decimal("1")
        self.product.save(update_fields=["cost_price"])
        r = self.sell(self.owner, [{"product": self.product.pk, "quantity": "3",
                                    "unit_price": "3.34", "discount_amount": "0.02"}],
                      customer=self.customer.pk, payment={"method": "cash", "amount": "10.00"})
        self.assertEqual(r.status_code, 201, r.data)
        inv = Invoice.objects.get(pk=r.data["id"])
        self.assertEqual(inv.total, Decimal("10.00"))
        line = inv.lines.get()
        for _i in range(3):
            ret = self.client.post(reverse("salesreturn-list"), {
                "invoice": inv.pk,
                "lines": [{"invoice_line": line.pk, "product": self.product.pk,
                           "quantity": "1"}],
            }, format="json")
            self.assertEqual(ret.status_code, 201, ret.data)
        amounts = [n.amount for n in CreditNote.objects.filter(invoice=inv).order_by("pk")]
        self.assertEqual(amounts, [Decimal("3.33"), Decimal("3.34"), Decimal("3.33")])
        self.assertEqual(sum(amounts), Decimal("10.00"))

    def test_return_after_void_is_refused(self):
        r = self.sell(self.owner, [{"product": self.product.pk, "quantity": "1"}],
                      customer=self.customer.pk)
        self.assertEqual(r.status_code, 201, r.data)
        inv = Invoice.objects.get(pk=r.data["id"])
        v = self.client.post(reverse("invoice-void", args=[inv.pk]), {"reason": "typo"},
                             format="json")
        self.assertEqual(v.status_code, 200, v.data)
        ret = self.client.post(reverse("salesreturn-list"), {
            "invoice": inv.pk,
            "lines": [{"invoice_line": inv.lines.get().pk, "product": self.product.pk,
                       "quantity": "1"}],
        }, format="json")
        self.assertEqual(ret.status_code, 400)


class BillDueDateOnTheCompanyCalendar(Base):
    def test_bill_entered_after_local_midnight_is_due_that_local_day(self):
        from purchasing.models import Bill, Supplier

        supplier = Supplier.objects.create(company=self.company, name="Acme")
        zone = ZoneInfo("Africa/Khartoum")
        local_day = timezone.localtime(timezone.now(), zone).date()
        # 00:30 local: still the previous day in UTC (Khartoum is UTC+2).
        moment = datetime.combine(local_day, time(0, 30), tzinfo=zone)
        self.assertNotEqual(moment.astimezone(ZoneInfo("UTC")).date(), local_day)
        with mock.patch("django.utils.timezone.now", return_value=moment):
            bill = Bill.objects.create(
                company=self.company, supplier=supplier, subtotal=Decimal("10"),
                total=Decimal("10"),
            )
        self.assertEqual(bill.due_date, local_day)


class CountAdjustmentCarriesItsCost(Base):
    def test_approved_count_movement_is_valued(self):
        from inventory.counts import approve_count
        from inventory.models import StockCount, StockCountLine

        self._in(10, 80, timezone.now() - timedelta(hours=1))
        count = StockCount.objects.create(
            company=self.company, warehouse=self.wh, status=StockCount.SUBMITTED,
            counted_by=self.cashier,
        )
        StockCountLine.objects.create(
            count=count, product=self.product, counted_quantity=Decimal("8"),
            expected_quantity=Decimal("10"),
        )
        approve_count(count.pk, self.owner)
        movement = StockMovement.objects.get(reference_type="StockCount")
        self.assertEqual(movement.unit_cost, Decimal("80"))
        self.assertEqual(compute(self.product, "standard")["adjustments"], Decimal("160"))


class AuditCommand(Base):
    def test_audit_is_read_only_and_reports(self):
        from io import StringIO

        from django.core.management import call_command

        self._in(5, 10, timezone.now())
        before = StockMovement.objects.count()
        out = StringIO()
        call_command("audit_money_review", stdout=out)
        self.assertIn("bills whose due date", out.getvalue())
        self.assertEqual(StockMovement.objects.count(), before)
