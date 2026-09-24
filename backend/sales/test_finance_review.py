"""Finance fixes from the 2026-09-24 review: bank accounts, statement
reconciliation, expenses, budgets."""

import uuid
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from finance.models import Budget, BudgetLine
from sales.models import Payment
from sales import test_bank_apps
from sales.test_bank_apps import BankAppBase


class BankAccountGuardTests(BankAppBase):
    def test_a_sales_officer_cannot_repoint_the_public_account(self):
        response = self.client_for(self.cashier).patch(
            reverse("bankaccount-detail", args=[self.bankak.pk]),
            {"account_number": "999-MINE", "show_to_customers": True}, format="json",
        )
        self.assertIn(response.status_code, (400, 403))
        self.bankak.refresh_from_db()
        self.assertEqual(self.bankak.account_number, "1234")

    def test_finance_manages_accounts_but_a_manager_sets_the_sensitive_details(self):
        finance = self.client_for(self.finance)
        renamed = finance.patch(
            reverse("bankaccount-detail", args=[self.bankak.pk]),
            {"account_name": "Alpha Trading Co."}, format="json",
        )
        self.assertEqual(renamed.status_code, 200, renamed.data)
        refused = finance.patch(
            reverse("bankaccount-detail", args=[self.bankak.pk]),
            {"opening_balance": "1000000"}, format="json",
        )
        self.assertEqual(refused.status_code, 400)

    def test_the_opening_balance_is_fixed_once_money_moved(self):
        self._transfer(self.client_for(self.cashier), "300.00", reference="OB1")
        response = self.client_for(self.owner).patch(
            reverse("bankaccount-detail", args=[self.bankak.pk]),
            {"opening_balance": "50"}, format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_a_bank_transfer_expense_lowers_the_account_balance(self):
        before = self.bankak.balance()
        created = self.client_for(self.owner).post(reverse("expense-list"), {
            "category": "Rent", "amount": "999.99", "method": "bank_transfer",
            "date": str(timezone.localdate()), "company_bank_account": self.bankak.pk,
        }, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(self.bankak.balance(), before - Decimal("999.99"))
        missing = self.client_for(self.owner).post(reverse("expense-list"), {
            "category": "Rent", "amount": "10", "method": "bank_transfer",
            "date": str(timezone.localdate()),
        }, format="json")
        self.assertEqual(missing.status_code, 400)
        self.assertIn("company_bank_account", missing.data)


class ReconcileGuardTests(BankAppBase):
    _statement = test_bank_apps.ReconcileTests._statement
    _reconcile = test_bank_apps.ReconcileTests._reconcile

    def _statement_rows(self, *rows):
        return [f"{timezone.localdate():%Y-%m-%d},{ref},{amount},Ahmed" for ref, amount in rows]

    def test_a_transfer_above_the_threshold_waits_for_a_manager(self):
        self._transfer(self.client_for(self.cashier), "2000.00", reference="BIG1")
        r = self._reconcile(self.finance, self._statement_rows(("BIG1", "2000.00")))
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["applied"], 0)
        self.assertEqual(r.data["matched"][0]["outcome"], "needs_approver")
        self.assertIsNone(Payment.objects.get(transfer_reference="BIG1").verified_at)

    def test_one_transfer_split_over_invoices_is_matched_as_one(self):
        group = uuid.uuid4()
        second = type(self.invoice).objects.create(
            company=self.company, customer=self.invoice.customer, warehouse=self.invoice.warehouse,
            number=2, total=Decimal("200"), subtotal=Decimal("200"),
        )
        for invoice, amount in ((self.invoice, "100.00"), (second, "200.00")):
            Payment.objects.create(
                company=self.company, invoice=invoice, method=Payment.BANK_TRANSFER,
                amount=Decimal(amount), company_bank_account=self.bankak,
                transfer_reference="TX777", reference_last4="0777", sender_bank_name="Ahmed",
                receipt_group=group, recorded_by=self.cashier,
            )
        r = self._reconcile(self.finance, self._statement_rows(("TX777", "300.00")))
        self.assertEqual(r.data["applied"], 1, r.data)
        self.assertEqual(
            Payment.objects.filter(receipt_group=group, verified_at__isnull=False).count(), 2,
        )


class ExpenseRuleTests(BankAppBase):
    def _post(self, **body):
        body.setdefault("category", "Rent")
        body.setdefault("date", str(timezone.localdate()))
        return self.client_for(self.finance).post(reverse("expense-list"), body, format="json")

    def test_zero_and_unanchored_negative_expenses_are_refused(self):
        self.assertEqual(self._post(amount="0").status_code, 400)
        self.assertEqual(self._post(amount="-50").status_code, 400)
        # -50,000 used to raise profit with no approval at all.
        self.assertEqual(self._post(amount="-50000").status_code, 400)

    def test_a_correction_names_its_expense_and_cannot_exceed_it(self):
        rent = self._post(amount="300").data
        too_much = self._post(amount="-400", reverses=rent["id"])
        self.assertEqual(too_much.status_code, 400)
        ok = self._post(amount="-100", reverses=rent["id"])
        self.assertEqual(ok.status_code, 201, ok.data)
        self.assertEqual(self._post(amount="-250", reverses=rent["id"]).status_code, 400)


class BudgetRevenueTests(BankAppBase):
    def test_budget_revenue_is_the_income_statement_revenue_and_counted_once(self):
        from returns.models import CreditNote

        from sales.models import InvoiceLine
        from inventory.models import Product

        product = Product.objects.create(company=self.company, sku="B1", name="B")
        InvoiceLine.objects.create(
            invoice=self.invoice, product=product, quantity=1, unit_price=Decimal("1000"),
            line_subtotal=Decimal("1000"), line_total=Decimal("1000"),
        )
        CreditNote.objects.create(
            company=self.company, customer=self.invoice.customer, invoice=self.invoice,
            amount=Decimal("100"), created_by=self.owner,
        )
        today = timezone.localdate()
        budget = Budget.objects.create(
            company=self.company, name="Q", period_start=today.replace(day=1), period_end=today,
        )
        BudgetLine.objects.create(budget=budget, kind=BudgetLine.REVENUE, category="Sales",
                                  planned_amount=Decimal("1000"))
        BudgetLine.objects.create(budget=budget, kind=BudgetLine.REVENUE, category="Other",
                                  planned_amount=Decimal("500"))
        rows = self.client_for(self.owner).get(
            reverse("budget-variance", args=[budget.pk])
        ).data["rows"]
        actuals = [Decimal(row["actual"]) for row in rows if row["kind"] == BudgetLine.REVENUE]
        self.assertEqual(actuals, [Decimal("900.00"), Decimal("0.00")])
