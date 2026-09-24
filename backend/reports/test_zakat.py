"""Zakat on trade goods: the base, the toggles, and the Hijri conversion."""
from datetime import date, timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Role, User
from core.hijri import format_hijri, next_occurrence, to_gregorian, to_hijri
from inventory.models import Product, StockMovement, Warehouse
from org.models import Branch, Company
from purchasing.models import Bill, Supplier
from sales.models import CashShift, CompanyBankAccount, Customer, Invoice


class HijriTests(APITestCase):
    def test_known_dates_round_trip(self):
        # 1 Muharram 1447 fell on 26 June 2025 in the tabular calendar.
        self.assertEqual(to_hijri(date(2025, 6, 26)), (1447, 1, 1))
        self.assertEqual(to_gregorian(1447, 1, 1), date(2025, 6, 26))
        # Umm al-Qura had 1 Ramadan 1446 on 1 March 2025 and 1 Ramadan 1445
        # on 11 March 2024; the tabular calendar is within a day of both.
        known = (((1446, 9, 1), date(2025, 3, 1)), ((1445, 9, 1), date(2024, 3, 11)))
        for hijri, umm_al_qura in known:
            self.assertLessEqual(abs((to_gregorian(*hijri) - umm_al_qura).days), 1)
        for offset in range(0, 4000, 37):
            g = date(2020, 1, 1) + timedelta(days=offset)
            self.assertEqual(to_gregorian(*to_hijri(g)), g)

    def test_format_and_next_occurrence(self):
        self.assertEqual(format_hijri(date(2025, 6, 26), "ar"), "1 محرم 1447 هـ")
        self.assertEqual(format_hijri(date(2025, 6, 26), "en"), "1 Muharram 1447 AH")
        nxt = next_occurrence(date(2025, 7, 1), 1, 1)
        self.assertEqual(to_hijri(nxt)[:2], (1448, 1))
        self.assertGreater(nxt, date(2025, 7, 1))
        # Day 30 of a 29-day month clamps rather than rolling over.
        self.assertEqual(to_hijri(next_occurrence(date(2025, 6, 26), 2, 30))[1], 2)


class ZakatReportTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        branch = Branch.objects.create(company=self.company, name="Main")
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123", company=self.company,
            role=Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS),
        )
        wh = Warehouse.objects.create(company=self.company, branch=branch, name="W")
        sugar = Product.objects.create(
            company=self.company, sku="S", name="Sugar",
            sale_price=Decimal("420000"), cost_price=Decimal("300000"),
        )
        StockMovement.objects.create(
            company=self.company, product=sugar, warehouse=wh,
            movement_type=StockMovement.PURCHASE_IN, quantity=Decimal("10"),
        )
        # Sold out product and a service line must not count.
        empty = Product.objects.create(
            company=self.company, sku="E", name="Empty", sale_price=Decimal("999"),
        )
        StockMovement.objects.create(
            company=self.company, product=empty, warehouse=wh,
            movement_type=StockMovement.PURCHASE_IN, quantity=Decimal("0"),
        )
        Product.objects.create(
            company=self.company, sku="D", name="Delivery", sale_price=Decimal("500"),
            is_stock_tracked=False,
        )
        CompanyBankAccount.objects.create(
            company=self.company, bank_name="BoK", account_name="A",
            opening_balance=Decimal("1000000"),
        )
        CashShift.objects.create(
            company=self.company, branch=branch, opened_by=self.owner,
            opening_float=Decimal("50000"), status=CashShift.OPEN,
        )
        customer = Customer.objects.create(company=self.company, name="C")
        today = timezone.localdate()
        Invoice.objects.create(
            company=self.company, customer=customer, warehouse=wh, number=1,
            subtotal=Decimal("200000"), total=Decimal("200000"),
            due_date=today + timedelta(days=10),
        )
        Invoice.objects.create(
            company=self.company, customer=customer, warehouse=wh, number=2,
            subtotal=Decimal("80000"), total=Decimal("80000"),
            due_date=today - timedelta(days=120),
        )
        supplier = Supplier.objects.create(company=self.company, name="S")
        Bill.objects.create(
            company=self.company, supplier=supplier,
            subtotal=Decimal("150000"), total=Decimal("150000"),
        )
        self.client.force_authenticate(self.owner)

    def test_base_counts_stock_cash_bank_receivables_less_payables(self):
        r = self.client.get(reverse("report-zakat"))
        self.assertEqual(r.status_code, 200, r.data)
        d = r.data
        self.assertEqual(d["stock_at_sale"], "4200000.00")
        self.assertEqual(d["stock_at_cost"], "3000000.00")
        self.assertEqual(d["stock"], "4200000.00")
        self.assertEqual(d["stock_items"], 1)
        self.assertEqual(d["cash_in_tills"], "50000.00")
        self.assertEqual(d["bank"], "1000000.00")
        self.assertEqual(d["receivables"], "280000.00")
        self.assertEqual(d["doubtful_receivables"], "80000.00")
        self.assertEqual(d["payables"], "150000.00")
        # 4,200,000 + 50,000 + 1,000,000 + 280,000 − 150,000
        self.assertEqual(d["base"], "5380000.00")
        self.assertEqual(d["zakat"], "134500.00")
        self.assertIn("هـ", d["hijri_ar"])
        self.assertEqual(d["as_of"], timezone.localdate().isoformat())

    def test_cost_valuation_and_doubtful_exclusion_and_hawl(self):
        r = self.client.get(
            reverse("report-zakat"),
            {"valuation": "cost", "exclude_doubtful": "1", "hawl_month": 9, "hawl_day": 1},
        )
        d = r.data
        self.assertEqual(d["stock"], "3000000.00")
        self.assertEqual(d["counted_receivables"], "200000.00")
        # 3,000,000 + 50,000 + 1,000,000 + 200,000 − 150,000
        self.assertEqual(d["base"], "4100000.00")
        self.assertEqual(d["zakat"], "102500.00")
        self.assertEqual(to_hijri(date.fromisoformat(d["next_hawl"]))[1:], (9, 1))

    def test_csv_and_role_gate(self):
        r = self.client.get(reverse("report-zakat"), {"format": "csv"})
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"zakat,134500.00", r.content)
        clerk = User.objects.create_user(
            email="clerk@alpha.test", password="passw0rd123", company=self.company,
            role=Role.objects.create(name="Inventory Officer", scope_level=Role.SCOPE_BUSINESS),
        )
        self.client.force_authenticate(clerk)
        self.assertEqual(self.client.get(reverse("report-zakat")).status_code, 403)


class ZakatCashTests(APITestCase):
    """Cash = the last known cash in each cashier's hands, or the owner's
    own figure. Closed drawers used to drop out entirely; summing every
    closed shift would count each day's cash again every day."""

    def setUp(self):
        self.company = Company.objects.create(name="Cash")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.owner = User.objects.create_user(
            email="owner@cash.test", password="passw0rd123", company=self.company, role=role,
        )
        self.cashier = User.objects.create_user(
            email="cashier@cash.test", password="passw0rd123", company=self.company, role=role,
        )
        self.client.force_authenticate(self.owner)

    def shift(self, user, days_ago, **fields):
        shift = CashShift.objects.create(
            company=self.company, branch=self.branch, opened_by=user, **fields,
        )
        CashShift.objects.filter(pk=shift.pk).update(
            opened_at=timezone.now() - timedelta(days=days_ago)
        )
        return shift

    def test_estimate_takes_each_cashiers_latest_shift(self):
        # Owner: two closed days — only the latest count (700) is cash today.
        self.shift(self.owner, 1, status=CashShift.CLOSED, counted_cash=Decimal("700"))
        self.shift(self.owner, 2, status=CashShift.CLOSED, counted_cash=Decimal("500"))
        # Cashier: closed yesterday, open today — the live drawer (300).
        self.shift(self.cashier, 1, status=CashShift.CLOSED, counted_cash=Decimal("900"))
        self.shift(self.cashier, 0, opening_float=Decimal("300"))
        d = self.client.get(reverse("report-zakat")).data
        self.assertEqual(d["cash_in_tills"], "1000.00")
        self.assertEqual(d["cash_source"], "estimate")
        self.assertEqual(d["base"], "1000.00")

    def test_the_owner_can_enter_the_cash_instead(self):
        self.shift(self.owner, 1, status=CashShift.CLOSED, counted_cash=Decimal("700"))
        d = self.client.get(reverse("report-zakat"), {"cash_on_hand": "2500.50"}).data
        self.assertEqual(d["cash_in_tills"], "2500.50")
        self.assertEqual(d["cash_source"], "entered")
        self.assertEqual(d["base"], "2500.50")
        zero = self.client.get(reverse("report-zakat"), {"cash_on_hand": "0"}).data
        self.assertEqual(zero["cash_in_tills"], "0.00")
        for bad in ("-1", "abc", "NaN"):
            response = self.client.get(reverse("report-zakat"), {"cash_on_hand": bad})
            self.assertEqual(response.status_code, 400, bad)
