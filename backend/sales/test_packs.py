from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Product, ProductPack, StockMovement, Warehouse
from org.models import Branch, Company
from sales.models import Invoice


class PackSaleTests(APITestCase):
    """Selling by the carton writes pieces to the ledger, keeps the carton
    on the receipt, and a carton barcode scans straight to its product."""

    def setUp(self):
        self.company = Company.objects.create(name="Wholesale")
        branch = Branch.objects.create(company=self.company, name="Main")
        owner = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.user = User.objects.create_user(
            email="o@w.test", password="passw0rd123", company=self.company, role=owner
        )
        self.wh = Warehouse.objects.create(company=self.company, branch=branch, name="WH")
        self.water = Product.objects.create(
            company=self.company,
            sku="W",
            name="Water 500ml",
            barcode="111",
            sale_price=Decimal("1.00"),
            cost_price=Decimal("0.40"),
        )
        StockMovement.objects.create(
            company=self.company,
            product=self.water,
            warehouse=self.wh,
            movement_type=StockMovement.PURCHASE_IN,
            quantity=100,
        )
        self.carton = ProductPack.objects.create(
            company=self.company,
            product=self.water,
            name="Carton",
            quantity=Decimal("12"),
            barcode="222",
            sale_price=Decimal("10.00"),  # cheaper than 12 × 1.00
        )
        self.client.force_authenticate(self.user)

    def test_carton_sale_hits_ledger_in_pieces_and_receipt_in_cartons(self):
        response = self.client.post(
            reverse("pos-checkout"),
            {
                "warehouse": self.wh.id,
                "lines": [{"product": self.water.id, "pack": self.carton.id, "quantity": "2"}],
                "payment": {"method": "cash", "amount": "20.00"},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        inv = Invoice.objects.get(pk=response.data["id"])
        line = inv.lines.get()
        self.assertEqual(line.quantity, Decimal("24.000"))  # 2 cartons × 12
        self.assertEqual(line.packs_sold, Decimal("2.000"))
        self.assertEqual(line.pack_name, "Carton")
        self.assertEqual(line.line_subtotal, Decimal("20.00"))  # 2 × 10.00 pack price
        self.assertEqual(inv.status, "paid")
        self.assertEqual(self.water.on_hand(warehouse=self.wh), Decimal("76"))
        doc = self.client.get(reverse("invoice-document", args=[inv.id])).data
        self.assertEqual(
            doc["lines"][0]["pack"], {"name": "Carton", "contains": "12.000", "packs_sold": "2.000"}
        )

    def test_pack_barcode_resolves_to_product_with_scanned_pack(self):
        response = self.client.get(reverse("product-by-barcode"), {"code": "222"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["id"], self.water.id)
        self.assertEqual(response.data["scanned_pack"]["name"], "Carton")
        self.assertEqual(response.data["scanned_pack"]["effective_price"], "10.00")
        plain = self.client.get(reverse("product-by-barcode"), {"code": "111"})
        self.assertNotIn("scanned_pack", plain.data)

    def test_default_pack_price_is_base_price_times_quantity(self):
        strip = ProductPack.objects.create(
            company=self.company, product=self.water, name="Strip", quantity=Decimal("6")
        )
        self.assertEqual(strip.effective_price(), Decimal("6.00"))

    def test_pack_of_another_product_is_refused(self):
        other = Product.objects.create(company=self.company, sku="X", name="X", sale_price=1)
        response = self.client.post(
            reverse("pos-checkout"),
            {
                "warehouse": self.wh.id,
                "lines": [{"product": other.id, "pack": self.carton.id, "quantity": "1"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("pack", response.data)
