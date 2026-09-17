from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product, Warehouse
from org.models import Branch, Company
from sales.models import Customer, Invoice


class DiscountTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Shop")
        branch = Branch.objects.create(company=self.company, name="Main")
        owner = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.user = User.objects.create_user(
            email="o@shop.test", password="passw0rd123", company=self.company, role=owner
        )
        self.wh = Warehouse.objects.create(company=self.company, branch=branch, name="WH")
        self.a = Product.objects.create(
            company=self.company, sku="A", name="A", sale_price=Decimal("100")
        )
        self.b = Product.objects.create(
            company=self.company, sku="B", name="B", sale_price=Decimal("50")
        )
        profile = self.company.tax_profile
        profile.flat_tax_rate = Decimal("10")
        profile.save(update_fields=["flat_tax_rate"])
        # Sales on account need a named debtor (see POSCheckoutSerializer);
        # tests that leave a balance sell to this account customer.
        self.customer = Customer.objects.create(company=self.company, name="Account customer")
        self.client.force_authenticate(self.user)

    def _checkout(self, lines, **extra):
        return self.client.post(
            reverse("pos-checkout"),
            {"warehouse": self.wh.id, "customer": self.customer.id, "lines": lines, **extra},
            format="json",
        )

    def test_line_percent_discount_is_taken_before_tax(self):
        r = self._checkout([{"product": self.a.id, "quantity": "2", "discount_percent": "10"}])
        self.assertEqual(r.status_code, 201, r.data)
        inv = Invoice.objects.get(pk=r.data["id"])
        line = inv.lines.get()
        self.assertEqual(line.unit_price, Decimal("100.00"))  # gross list price kept
        self.assertEqual(line.discount_amount, Decimal("20.00"))
        self.assertEqual(line.line_subtotal, Decimal("180.00"))
        self.assertEqual(line.line_tax, Decimal("18.00"))
        self.assertEqual(inv.discount_total, Decimal("20.00"))
        self.assertEqual(inv.total, Decimal("198.00"))

    def test_ticket_discount_is_allocated_proportionally_and_sums_exactly(self):
        # Lines net 100 and 50 -> a 10.00 ticket discount splits 6.67 / 3.33.
        r = self._checkout(
            [{"product": self.a.id, "quantity": "1"}, {"product": self.b.id, "quantity": "1"}],
            discount_amount="10.00",
        )
        self.assertEqual(r.status_code, 201, r.data)
        inv = Invoice.objects.get(pk=r.data["id"])
        parts = sorted(inv.lines.values_list("discount_amount", flat=True))
        self.assertEqual(parts, [Decimal("3.33"), Decimal("6.67")])
        self.assertEqual(inv.discount_total, Decimal("10.00"))
        self.assertEqual(inv.subtotal, Decimal("140.00"))
        self.assertEqual(inv.tax_amount, Decimal("14.00"))
        self.assertEqual(inv.total, Decimal("154.00"))

    def test_discount_cannot_exceed_value(self):
        r = self._checkout([{"product": self.a.id, "quantity": "1", "discount_amount": "150"}])
        self.assertEqual(r.status_code, 400)
        r = self._checkout([{"product": self.a.id, "quantity": "1"}], discount_amount="101")
        self.assertEqual(r.status_code, 400)
        r = self._checkout(
            [
                {
                    "product": self.a.id,
                    "quantity": "1",
                    "discount_amount": "5",
                    "discount_percent": "5",
                }
            ]
        )
        self.assertEqual(r.status_code, 400)

    def test_printed_invoice_shows_discounts(self):
        r = self._checkout([{"product": self.a.id, "quantity": "1", "discount_percent": "50"}])
        doc = self.client.get(reverse("invoice-document", args=[r.data["id"]]))
        self.assertEqual(doc.status_code, 200, doc.data)
        self.assertEqual(doc.data["discount"], "50.00")
        self.assertEqual(doc.data["lines"][0]["discount"], "50.00")
