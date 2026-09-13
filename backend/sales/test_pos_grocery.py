"""
Till behaviour a grocery depends on: selling by weight, overriding the price at
the counter, and ringing up something that isn't stocked.

The backend already accepted decimal quantities and a unit_price override — the
till UI simply never sent them. These tests pin the server side so the new UI
has something to hold onto.
"""

from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product, StockMovement, Unit, Warehouse
from org.models import Branch, Company
from sales.models import Invoice, InvoiceLine


class GroceryTillTestCase(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Shop")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.warehouse = Warehouse.objects.create(
            company=self.company, branch=self.branch, name="Store"
        )
        self.kg = Unit.objects.create(company=self.company, name="kg", symbol="kg")
        self.tomatoes = Product.objects.create(
            company=self.company, sku="VEG1", name="Tomatoes",
            unit=self.kg, sale_price=Decimal("40"),
        )
        self.bag = Product.objects.create(
            company=self.company, sku="BAG", name="Carrier bag",
            sale_price=Decimal("2"), is_stock_tracked=False,
        )
        self.role = Role.objects.create(
            name="Sales Officer", scope_level=Role.SCOPE_BRANCH
        )
        self.user = User.objects.create_user(
            email="till@shop.test", password="passw0rd12345",
            company=self.company, branch=self.branch, role=self.role,
        )
        self.client.force_authenticate(self.user)

    def _checkout(self, lines, payment=None):
        body = {"warehouse": self.warehouse.id, "lines": lines}
        if payment:
            body["payment"] = payment
        return self.client.post(reverse("pos-checkout"), body, format="json")


class WeighedGoodsTests(GroceryTillTestCase):
    def test_a_weighed_line_sells_to_three_decimals(self):
        """A grocery sells 1.250 kg of tomatoes; whole-unit steppers alone can
        never express that."""
        resp = self._checkout(
            [{"product": self.tomatoes.id, "quantity": "1.250"}]
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        line = InvoiceLine.objects.get(invoice_id=resp.data["id"])
        self.assertEqual(line.quantity, Decimal("1.250"))
        # 1.25 kg x 40 = 50.00
        self.assertEqual(line.line_subtotal, Decimal("50.00"))

    def test_stock_leaves_by_the_same_fraction(self):
        self._checkout([{"product": self.tomatoes.id, "quantity": "0.750"}])
        movement = StockMovement.objects.get(product=self.tomatoes)
        self.assertEqual(movement.quantity, Decimal("-0.750"))

    def test_a_zero_quantity_is_refused(self):
        resp = self._checkout([{"product": self.tomatoes.id, "quantity": "0"}])
        self.assertEqual(resp.status_code, 400, resp.data)


class PriceOverrideTests(GroceryTillTestCase):
    def test_the_counter_price_wins_when_sent(self):
        resp = self._checkout(
            [{"product": self.tomatoes.id, "quantity": "1", "unit_price": "35"}]
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        line = InvoiceLine.objects.get(invoice_id=resp.data["id"])
        self.assertEqual(line.unit_price, Decimal("35"))
        self.assertEqual(line.line_subtotal, Decimal("35.00"))

    def test_omitting_it_follows_the_catalogue(self):
        resp = self._checkout([{"product": self.tomatoes.id, "quantity": "1"}])
        line = InvoiceLine.objects.get(invoice_id=resp.data["id"])
        self.assertEqual(line.unit_price, Decimal("40"))

    def test_the_override_does_not_change_the_catalogue(self):
        """Discounting one sale must not silently reprice the product for
        everyone."""
        self._checkout(
            [{"product": self.tomatoes.id, "quantity": "1", "unit_price": "10"}]
        )
        self.tomatoes.refresh_from_db()
        self.assertEqual(self.tomatoes.sale_price, Decimal("40"))


class NonStockProductTests(GroceryTillTestCase):
    def test_selling_a_non_stock_line_posts_no_movement(self):
        """There is no inventory behind a carrier bag; a movement would only
        invent a deficit that grows forever."""
        resp = self._checkout([{"product": self.bag.id, "quantity": "1"}])
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertFalse(StockMovement.objects.filter(product=self.bag).exists())

    def test_it_still_earns_revenue(self):
        resp = self._checkout([{"product": self.bag.id, "quantity": "3"}])
        invoice = Invoice.objects.get(pk=resp.data["id"])
        self.assertEqual(invoice.total, Decimal("6.00"))

    def test_a_mixed_basket_moves_only_the_stocked_line(self):
        resp = self._checkout([
            {"product": self.tomatoes.id, "quantity": "2"},
            {"product": self.bag.id, "quantity": "1"},
        ])
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertEqual(
            StockMovement.objects.get().product_id, self.tomatoes.id
        )

    def test_non_stock_products_stay_out_of_low_stock(self):
        """At zero on hand forever, they would otherwise bury the products that
        genuinely need reordering."""
        resp = self.client.get(reverse("product-low-stock"))
        self.assertEqual(resp.status_code, 200, resp.data)
        skus = [p["sku"] for p in resp.data["results"]]
        self.assertIn("VEG1", skus)
        self.assertNotIn("BAG", skus)

    def test_the_flag_round_trips_through_the_api(self):
        resp = self.client.get(reverse("product-detail", args=[self.bag.id]))
        self.assertFalse(resp.data["is_stock_tracked"])
        self.assertTrue(
            self.client.get(
                reverse("product-detail", args=[self.tomatoes.id])
            ).data["is_stock_tracked"]
        )

    def test_products_default_to_stocked(self):
        """The flag must be opt-out: a shop that never thinks about it keeps
        full stock tracking."""
        # Creating products is the inventory officer's job — a sales officer has
        # read-only inventory, so the till user cannot stand in here.
        stock_role = Role.objects.create(
            name="Inventory Officer", scope_level=Role.SCOPE_BRANCH
        )
        stock_user = User.objects.create_user(
            email="stock@shop.test", password="passw0rd12345",
            company=self.company, branch=self.branch, role=stock_role,
        )
        self.client.force_authenticate(stock_user)
        resp = self.client.post(
            reverse("product-list"),
            {"sku": "NEW1", "name": "Rice", "sale_price": "10", "barcode": ""},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertTrue(resp.data["is_stock_tracked"])

    def test_unit_name_is_exposed_for_the_till(self):
        resp = self.client.get(reverse("product-detail", args=[self.tomatoes.id]))
        self.assertEqual(resp.data["unit_name"], "kg")


class PartialPaymentTests(GroceryTillTestCase):
    def test_paying_less_leaves_a_balance(self):
        """The till caps the payment at what is owed, but a genuinely partial
        payment must still be recordable."""
        resp = self._checkout(
            [{"product": self.tomatoes.id, "quantity": "1"}],
            payment={"method": "cash", "amount": "30"},
        )
        invoice = Invoice.objects.get(pk=resp.data["id"])
        self.assertEqual(invoice.amount_paid(), Decimal("30"))
        self.assertEqual(invoice.amount_due(), Decimal("10"))
        self.assertEqual(invoice.status, "partially_paid")

    def test_paying_in_full_settles_it(self):
        resp = self._checkout(
            [{"product": self.tomatoes.id, "quantity": "1"}],
            payment={"method": "cash", "amount": "40"},
        )
        invoice = Invoice.objects.get(pk=resp.data["id"])
        self.assertEqual(invoice.amount_due(), Decimal("0"))
        self.assertEqual(invoice.status, "paid")
