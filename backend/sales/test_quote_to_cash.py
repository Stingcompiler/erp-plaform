"""Quotation → sales order → invoice, end to end through the API the new
screens drive. The order is fulfilled only by invoicing it.
"""

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Role, User
from inventory.models import Product, Warehouse
from org.models import Branch, Company
from sales.models import Customer, Invoice, SalesOrder


class QuoteToCashTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.user = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123", company=self.company, role=role,
        )
        self.wh = Warehouse.objects.create(company=self.company, branch=self.branch, name="W")
        self.product = Product.objects.create(
            company=self.company, sku="P1", name="Thing", sale_price=Decimal("10"),
        )
        self.customer = Customer.objects.create(company=self.company, name="Buyer")
        self.other = Customer.objects.create(company=self.company, name="Other")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _quotation(self):
        r = self.client.post(
            "/api/quotations/",
            {"customer": self.customer.pk,
             "lines": [{"product": self.product.pk, "quantity": "2", "unit_price": "10"}]},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        return r.data

    def _checkout(self, order_id, customer_id=None, uuid="11111111-1111-4111-8111-111111111111"):
        return self.client.post(
            "/api/pos/checkout/",
            {"warehouse": self.wh.pk, "customer": customer_id or self.customer.pk,
             "source_order": order_id,
             "lines": [{"product": self.product.pk, "quantity": "2", "unit_price": "10"}],
             "client_uuid": uuid},
            format="json",
        )

    def test_quotation_converts_confirms_and_invoices(self):
        q = self._quotation()
        self.assertEqual(q["customer_name"], "Buyer")
        self.assertEqual(q["lines"][0]["product_sku"], "P1")
        converted = self.client.post(f"/api/quotations/{q['id']}/convert_to_order/")
        self.assertEqual(converted.status_code, 201, converted.data)
        order_id = converted.data["id"]
        self.assertEqual(converted.data["status"], SalesOrder.DRAFT)

        confirmed = self.client.post(
            f"/api/sales-orders/{order_id}/set_status/", {"status": "confirmed"}, format="json"
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.data)

        sold = self._checkout(order_id)
        self.assertEqual(sold.status_code, 201, sold.data)
        invoice = Invoice.objects.get(pk=sold.data["id"])
        self.assertEqual(invoice.source_order_id, order_id)
        order = SalesOrder.objects.get(pk=order_id)
        self.assertEqual(order.status, SalesOrder.FULFILLED)
        detail = self.client.get(f"/api/sales-orders/{order_id}/").data
        self.assertEqual(detail["invoice_id"], invoice.pk)

    def test_only_confirmed_orders_can_be_invoiced(self):
        q = self._quotation()
        order_id = self.client.post(f"/api/quotations/{q['id']}/convert_to_order/").data["id"]
        refused = self._checkout(order_id)  # still draft
        self.assertEqual(refused.status_code, 400)
        self.assertIn("source_order", refused.data)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_customer_must_match_the_order(self):
        q = self._quotation()
        order_id = self.client.post(f"/api/quotations/{q['id']}/convert_to_order/").data["id"]
        self.client.post(
            f"/api/sales-orders/{order_id}/set_status/", {"status": "confirmed"}, format="json"
        )
        refused = self._checkout(order_id, customer_id=self.other.pk)
        self.assertEqual(refused.status_code, 400)
        self.assertIn("source_order", refused.data)

    def test_order_transitions_are_enforced(self):
        q = self._quotation()
        order_id = self.client.post(f"/api/quotations/{q['id']}/convert_to_order/").data["id"]
        url = f"/api/sales-orders/{order_id}/set_status/"

        def move(target):
            return self.client.post(url, {"status": target}, format="json").status_code

        self.assertEqual(move("fulfilled"), 400)   # only invoicing fulfils
        self.assertEqual(move("cancelled"), 200)
        self.assertEqual(move("confirmed"), 400)   # cancelled is terminal
