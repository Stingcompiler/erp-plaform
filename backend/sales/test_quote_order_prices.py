"""The till's price rule on quotations and sales orders: no line below cost,
no discount (a typed-down price counts) above Company.max_discount_percent
unless an approver prices it — recorded on the document so converting the
quote and invoicing the order do not refuse it again. Orders from before the
rule, and web orders, keep their price."""
from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from core.models import ActivityLog
from inventory.models import Product, Warehouse
from org.models import Branch, Company
from sales.models import Customer, Invoice, Quotation, SalesOrder, SalesOrderLine


class QuoteOrderPriceTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Shop")  # limit 10% by default
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.warehouse = Warehouse.objects.create(
            company=self.company, branch=self.branch, name="Store"
        )
        self.rice = Product.objects.create(
            company=self.company, sku="RICE", name="أرز",
            cost_price=Decimal("80"), sale_price=Decimal("100"),
        )
        self.seller = User.objects.create_user(
            email="seller@shop.test", password="passw0rd12345", company=self.company,
            branch=self.branch,
            role=Role.objects.create(name="Sales Officer", scope_level=Role.SCOPE_BRANCH),
        )
        self.owner = User.objects.create_user(
            email="owner@shop.test", password="passw0rd12345", company=self.company,
            role=Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS),
        )
        self.customer = Customer.objects.create(company=self.company, name="Ali")
        self.client.force_authenticate(self.seller)

    def body(self, price, qty="2"):
        return {"customer": self.customer.pk, "branch": self.branch.pk,
                "lines": [{"product": self.rice.pk, "quantity": qty, "unit_price": price}]}

    def quote(self, price, **kw):
        return self.client.post("/api/quotations/", self.body(price, **kw), format="json")

    def order(self, price, **kw):
        return self.client.post("/api/sales-orders/", self.body(price, **kw), format="json")

    def convert(self, quote_id):
        return self.client.post(f"/api/quotations/{quote_id}/convert_to_order/")

    def confirm(self, order_id):
        return SalesOrder.objects.filter(pk=order_id).update(status=SalesOrder.CONFIRMED)

    def invoice(self, order_id, price, **extra):
        return self.client.post(reverse("pos-checkout"), {
            "warehouse": self.warehouse.pk, "customer": self.customer.pk,
            "source_order": order_id,
            "lines": [{"product": self.rice.pk, "quantity": "2", "unit_price": price, **extra}],
        }, format="json")

    # --- creating ---

    def test_seller_cannot_quote_beyond_the_limit(self):
        r = self.quote("85.00")
        self.assertEqual(r.status_code, 400, r.data)
        self.assertEqual(r.data["code"], "price_rule")
        self.assertIn("15.00", str(r.data["lines"]))
        self.assertFalse(Quotation.objects.exists())

    def test_seller_cannot_order_below_cost(self):
        r = self.order("50.00")
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn("RICE", str(r.data["lines"]))
        self.assertFalse(SalesOrder.objects.exists())

    def test_a_free_line_counts_as_a_full_discount(self):
        Product.objects.filter(pk=self.rice.pk).update(cost_price=Decimal("0"))
        r = self.quote("0.00")
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn("100.00", str(r.data["lines"]))

    def test_seller_within_the_limit_is_checked_not_approved(self):
        r = self.quote("90.00")
        self.assertEqual(r.status_code, 201, r.data)
        quote = Quotation.objects.get()
        self.assertTrue(quote.price_checked)
        self.assertIsNone(quote.price_approved_at)
        self.assertIsNone(r.data["price_approved_by"])

    def test_approver_override_is_recorded_and_audited(self):
        self.client.force_authenticate(self.owner)
        r = self.order("60.00")
        self.assertEqual(r.status_code, 201, r.data)
        order = SalesOrder.objects.get()
        self.assertEqual(order.price_approved_by, self.owner)
        self.assertIsNotNone(order.price_approved_at)
        self.assertTrue(r.data["prices_trusted"])
        row = ActivityLog.objects.get(action="order_price_override")
        self.assertEqual(row.entity_type, "SalesOrder")
        self.assertEqual(row.entity_id, str(order.pk))
        self.assertEqual({b["rule"] for b in row.metadata["breaches"]},
                         {"below_cost", "discount"})
        q = self.quote("60.00")
        self.assertEqual(q.status_code, 201, q.data)
        self.assertTrue(ActivityLog.objects.filter(action="quote_price_override").exists())

    # --- converting ---

    def test_an_approved_quote_converts_for_a_seller(self):
        self.client.force_authenticate(self.owner)
        quote_id = self.quote("70.00").data["id"]
        self.client.force_authenticate(self.seller)
        r = self.convert(quote_id)
        self.assertEqual(r.status_code, 201, r.data)
        order = SalesOrder.objects.get()
        self.assertEqual(order.price_approved_by, self.owner)
        self.assertTrue(order.prices_trusted)

    def test_a_legacy_quote_beyond_the_limit_is_measured_on_conversion(self):
        self.client.force_authenticate(self.owner)
        quote_id = self.quote("70.00").data["id"]
        # As a quote written before the rule: nothing recorded on it.
        Quotation.objects.filter(pk=quote_id).update(
            price_checked=False, price_approved_by=None, price_approved_at=None
        )
        self.client.force_authenticate(self.seller)
        r = self.convert(quote_id)
        self.assertEqual(r.status_code, 400, r.data)
        self.assertEqual(r.data["code"], "price_rule")
        self.assertFalse(SalesOrder.objects.exists())
        self.assertEqual(Quotation.objects.get().status, Quotation.DRAFT)
        self.client.force_authenticate(self.owner)
        ok = self.convert(quote_id)
        self.assertEqual(ok.status_code, 201, ok.data)
        self.assertEqual(SalesOrder.objects.get().price_approved_by, self.owner)
        self.assertTrue(ActivityLog.objects.filter(action="order_price_override").exists())

    # --- invoicing ---

    def test_approved_order_invoices_at_its_price_for_a_cashier(self):
        self.client.force_authenticate(self.owner)
        order_id = self.order("85.00").data["id"]
        self.confirm(order_id)
        self.client.force_authenticate(self.seller)
        r = self.invoice(order_id, "85.00")
        self.assertEqual(r.status_code, 201, r.data)

    def test_a_discount_cannot_stack_on_a_checked_order(self):
        order_id = self.order("92.00").data["id"]  # 8% off: within the limit
        self.confirm(order_id)
        r = self.invoice(order_id, "92.00", discount_percent="5")  # 12.6% in all
        self.assertEqual(r.status_code, 400, r.data)
        self.assertFalse(Invoice.objects.exists())
        ok = self.invoice(order_id, "92.00")
        self.assertEqual(ok.status_code, 201, ok.data)

    def test_a_legacy_order_keeps_its_agreed_price(self):
        order = SalesOrder.objects.create(
            company=self.company, customer=self.customer, branch=self.branch,
            status=SalesOrder.CONFIRMED, subtotal=Decimal("170"), total=Decimal("170"),
        )
        SalesOrderLine.objects.create(
            sales_order=order, product=self.rice, quantity=Decimal("2"),
            unit_price=Decimal("85"), line_total=Decimal("170"),
        )
        self.assertFalse(order.price_checked)
        r = self.invoice(order.pk, "85.00")
        self.assertEqual(r.status_code, 201, r.data)

    def test_a_web_order_is_not_measured_by_the_rule(self):
        from website.models import PublicOrder, PublicOrderLine, Website
        from website.orders import confirm

        Customer.objects.filter(pk=self.customer.pk).update(phone="0912345678")
        site = Website.objects.create(company=self.company, business_name="Shop")
        public = PublicOrder.objects.create(
            company=self.company, website=site, branch=self.branch, reference="W1",
            contact_name="Amal", phone="0912345678",
        )
        # The page showed 70; the list price is 100 now.
        PublicOrderLine.objects.create(
            order=public, product=self.rice, name="Rice", quantity=Decimal("2"),
            unit_price=Decimal("70"),
        )
        confirm(public, self.seller)
        order = SalesOrder.objects.get()
        self.assertFalse(order.price_checked)
        self.assertTrue(order.prices_trusted)
        Product.objects.filter(pk=self.rice.pk).update(cost_price=Decimal("60"))
        r = self.invoice(order.pk, "70.00")
        self.assertEqual(r.status_code, 201, r.data)
