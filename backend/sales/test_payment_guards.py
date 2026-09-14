from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Warehouse
from org.models import Branch, Company
from sales.models import Payment


class PaymentAndShiftGuardTests(APITestCase):
    """The three money guards added in the pre-production review:
    a cash shift cannot borrow another company's branch, a payment can never
    exceed the balance due, and a POS payment is capped at the tax-inclusive
    total the server computes."""

    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.other = Company.objects.create(name="Beta")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.foreign_branch = Branch.objects.create(company=self.other, name="B-Main")
        owner = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.user = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=owner,
        )
        self.warehouse = Warehouse.objects.create(
            company=self.company, branch=self.branch, name="WH"
        )
        self.client.force_authenticate(self.user)
        # 10% flat tax so the POS totals actually diverge from the subtotal.
        profile = self.company.tax_profile
        profile.flat_tax_rate = Decimal("10.00")
        profile.save(update_fields=["flat_tax_rate"])

    _sku = 0

    def _product(self):
        from inventory.models import Product

        PaymentAndShiftGuardTests._sku += 1
        return Product.objects.create(
            company=self.company, sku=f"P{self._sku}", name="Widget",
            sale_price=Decimal("100.00"),
        )

    def _checkout(self, payment_amount):
        return self.client.post(
            reverse("pos-checkout"),
            {
                "warehouse": self.warehouse.id,
                "lines": [{"product": self._product().id, "quantity": "1"}],
                "payment": {"method": "cash", "amount": payment_amount},
            },
            format="json",
        )

    def test_me_exposes_the_tax_rate(self):
        response = self.client.get(reverse("auth-me"))
        self.assertEqual(response.data["tax_rate"], "10.00")

    def test_cash_shift_rejects_foreign_branch(self):
        response = self.client.post(
            reverse("cashshift-list"),
            {"branch": self.foreign_branch.id, "opening_float": "0"},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        response = self.client.post(
            reverse("cashshift-list"),
            {"branch": self.branch.id, "opening_float": "0"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_pos_payment_capped_at_tax_inclusive_total(self):
        # 100 + 10% tax = 110. Paying 110 settles the invoice in full.
        settled = self._checkout("110.00")
        self.assertEqual(settled.status_code, 201, settled.data)
        self.assertEqual(settled.data["status"], "paid")
        # Anything above the total is refused, not silently absorbed.
        over = self._checkout("120.00")
        self.assertEqual(over.status_code, 400, over.data)

    def test_direct_payment_cannot_exceed_balance_due(self):
        invoice_id = self._checkout("50.00").data["id"]
        # Balance due is 60.00; 70.00 must be refused, 60.00 accepted.
        refused = self.client.post(
            reverse("payment-list"),
            {"invoice": invoice_id, "method": "cash", "amount": "70.00"},
            format="json",
        )
        self.assertEqual(refused.status_code, 400, refused.data)
        accepted = self.client.post(
            reverse("payment-list"),
            {"invoice": invoice_id, "method": "cash", "amount": "60.00"},
            format="json",
        )
        self.assertEqual(accepted.status_code, 201, accepted.data)
        self.assertEqual(
            Payment.objects.filter(invoice_id=invoice_id).count(), 2
        )


class CostSnapshotAndCurrencyTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha", currency="SDG")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        owner = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.user = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=owner,
        )
        self.warehouse = Warehouse.objects.create(
            company=self.company, branch=self.branch, name="WH"
        )
        self.client.force_authenticate(self.user)
        from inventory.models import Product

        self.product = Product.objects.create(
            company=self.company, sku="C1", name="Widget",
            sale_price=Decimal("100.00"), cost_price=Decimal("60.00"),
        )

    def _sell(self, **extra):
        return self.client.post(
            reverse("pos-checkout"),
            {
                "warehouse": self.warehouse.id,
                "lines": [{"product": self.product.id, "quantity": "2"}],
                **extra,
            },
            format="json",
        )

    def test_foreign_currency_sale_is_refused(self):
        response = self._sell(currency="USD")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("currency", response.data)
        self.assertEqual(self._sell(currency="SDG").status_code, 201)

    def test_standard_cogs_uses_cost_at_time_of_sale(self):
        from finance.metrics import operating_summary
        from inventory.models import StockMovement

        self.assertEqual(self._sell().status_code, 201)
        movement = StockMovement.objects.get(movement_type=StockMovement.SALE_OUT)
        self.assertEqual(movement.unit_cost, Decimal("60.00"))
        before = Decimal(operating_summary(self.company.id)["cogs"])
        # Re-pricing the product later must not rewrite the past.
        self.product.cost_price = Decimal("90.00")
        self.product.save(update_fields=["cost_price"])
        after = Decimal(operating_summary(self.company.id)["cogs"])
        self.assertEqual(before, Decimal("120.00"))
        self.assertEqual(after, before)
