"""SQL balances agree with the model methods, and the reports scale.

The aging reports, the debt ledger, the cash-flow forecast and the CFO tile
used to call Invoice.amount_due() per row (three queries each). They now read
balances annotated in SQL. These tests pin that the two paths agree on
every combination that matters — payments, credit notes, refunds, voids — and
that the query count no longer grows with the number of invoices.
"""
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product, Warehouse
from org.models import Branch, Company
from purchasing.models import Bill, Supplier, SupplierPayment
from purchasing.querysets import open_bills, payable_total
from returns.models import CreditNote, DebitNote
from sales.models import Customer, Invoice, Payment, Refund
from sales.querysets import open_invoices, receivable_total, with_outstanding


class BalanceBase(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        owner = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=owner,
        )
        self.wh = Warehouse.objects.create(company=self.company, branch=self.branch, name="WH")
        Product.objects.create(company=self.company, sku="S", name="P")
        self.customers = [
            Customer.objects.create(company=self.company, name=f"C{i}") for i in range(6)
        ]
        self.client.force_authenticate(self.owner)

    def _invoice(self, customer, total, number, days=-5):
        from datetime import timedelta

        from django.utils import timezone

        return Invoice.objects.create(
            company=self.company, customer=customer, warehouse=self.wh, number=number,
            branch=self.branch, total=Decimal(total), subtotal=Decimal(total),
            due_date=timezone.localdate() + timedelta(days=days),
        )


class ReceivableParityTests(BalanceBase):
    def test_sql_outstanding_matches_amount_due_in_every_case(self):
        c = self.customers[0]
        plain = self._invoice(c, "100", 1)
        part_paid = self._invoice(c, "100", 2)
        Payment.objects.create(company=self.company, invoice=part_paid, method="cash",
                               amount=Decimal("40"))
        credited = self._invoice(c, "100", 3)
        note = CreditNote.objects.create(company=self.company, customer=c, invoice=credited,
                                         amount=Decimal("30"))
        void_note = CreditNote.objects.create(company=self.company, customer=c,
                                              invoice=credited, amount=Decimal("99"),
                                              is_void=True)
        self.assertTrue(void_note.is_void)
        refunded = self._invoice(c, "100", 4)
        Payment.objects.create(company=self.company, invoice=refunded, method="cash",
                               amount=Decimal("100"))
        big_note = CreditNote.objects.create(company=self.company, customer=c,
                                             invoice=refunded, amount=Decimal("100"))
        Refund.objects.create(company=self.company, credit_note=big_note, method="cash",
                              amount=Decimal("60"))
        voided = self._invoice(c, "100", 5)
        voided.is_void = True
        voided.save(update_fields=["is_void"])
        self.assertIsNotNone(note)

        annotated = {
            row.pk: row.outstanding
            for row in with_outstanding(Invoice.objects.filter(company=self.company))
        }
        for invoice in (plain, part_paid, credited, refunded):
            self.assertEqual(annotated[invoice.pk], invoice.amount_due(), invoice.number)
        self.assertNotIn(voided.pk, annotated)
        self.assertEqual(annotated[refunded.pk], Decimal("-40"))
        # Only positive balances count as receivables.
        self.assertEqual(
            receivable_total(Invoice.objects.filter(company=self.company)),
            Decimal("100") + Decimal("60") + Decimal("70"),
        )
        self.assertEqual(
            {i.pk for i in open_invoices(Invoice.objects.filter(company=self.company))},
            {plain.pk, part_paid.pk, credited.pk},
        )

    def test_payable_parity(self):
        supplier = Supplier.objects.create(company=self.company, name="Imp")
        bill = Bill.objects.create(company=self.company, supplier=supplier,
                                   subtotal=Decimal("1000"), total=Decimal("1000"))
        SupplierPayment.objects.create(company=self.company, supplier=supplier, bill=bill,
                                       method="cash", amount=Decimal("200"))
        DebitNote.objects.create(company=self.company, supplier=supplier, bill=bill,
                                 amount=Decimal("300"))
        DebitNote.objects.create(company=self.company, supplier=supplier, bill=bill,
                                 amount=Decimal("5"), is_void=True)
        row = open_bills(Bill.objects.filter(company=self.company)).get()
        self.assertEqual(row.outstanding, bill.amount_due())
        self.assertEqual(row.outstanding, Decimal("500"))
        self.assertEqual(payable_total(Bill.objects.filter(company=self.company)),
                         Decimal("500"))


class QueryCountTests(BalanceBase):
    def _seed(self, count):
        start = (Invoice.objects.filter(company=self.company).count() or 0) + 100
        for i in range(count):
            inv = self._invoice(self.customers[i % 6], "50", start + i, days=-(i % 40))
            if i % 3 == 0:
                Payment.objects.create(company=self.company, invoice=inv, method="cash",
                                       amount=Decimal("20"))

    def _queries(self, url, params=None):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url, params or {})
        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        return len(ctx.captured_queries), response

    def test_report_query_counts_do_not_grow_with_invoices(self):
        self._seed(12)
        small = {
            name: self._queries(reverse(name))[0]
            for name in ("report-ar-aging", "debt-customer-list", "debt-summary")
        }
        self._seed(60)
        for name, before in small.items():
            after = self._queries(reverse(name))[0]
            # A handful of fixed queries either way; never proportional to rows.
            self.assertLessEqual(after, before + 2, name)
            self.assertLess(after, 15, name)

    def test_debt_list_and_aging_agree_on_totals(self):
        self._seed(30)
        _, aging = self._queries(reverse("report-ar-aging"))
        _, debts = self._queries(reverse("debt-customer-list"), {"page_size": "200"})
        _, summary = self._queries(reverse("debt-summary"))
        aging_total = sum(Decimal(row["total"]) for row in aging.data)
        debt_total = sum(Decimal(row["outstanding"]) for row in debts.data["results"])
        self.assertEqual(aging_total, debt_total)
        self.assertEqual(Decimal(summary.data["outstanding"]), debt_total)
        # Every seeded invoice is due within the last 40 days.
        overdue = sum(Decimal(row["overdue"]) for row in debts.data["results"])
        self.assertEqual(Decimal(summary.data["overdue"]), overdue)

    def test_page_size_is_honoured_and_capped(self):
        response = self.client.get(reverse("customer-list"), {"page_size": "2"})
        self.assertEqual(len(response.data["results"]), 2)
        response = self.client.get(reverse("customer-list"), {"page_size": "9999"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 6)
