"""Regression tests for the September 2026 functional review fixes."""
from decimal import Decimal

from rest_framework.test import APITestCase

from accounts.models import Role, User
from finance.metrics import operating_summary
from finance.models import Budget
from inventory.models import Category, Product, StockMovement, Warehouse
from org.models import Company
from purchasing.models import GoodsReceipt, GoodsReceiptLine, Supplier
from returns.models import CreditNote, DebitNote
from sales.models import Customer, Invoice, InvoiceLine, Quotation, SalesOrder


class FunctionalReviewRegressionTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Review A")
        self.other = Company.objects.create(name="Review B")
        self.role = Role.objects.create(name="Business Owner", scope_level="business")
        self.user = User.objects.create_user(
            email="review-owner@example.test", company=self.company, role=self.role
        )
        self.client.force_authenticate(self.user)
        self.product = Product.objects.create(
            company=self.company, name="Product", sku="REVIEW-1",
            cost_price=40, sale_price=100,
        )
        self.warehouse = Warehouse.objects.create(company=self.company, name="WH")
        self.customer = Customer.objects.create(company=self.company, name="Customer")

    def invoice(self):
        invoice = Invoice.objects.create(
            company=self.company, customer=self.customer, warehouse=self.warehouse,
            number=1, subtotal=100, tax_amount=15, total=115,
        )
        line = InvoiceLine.objects.create(
            invoice=invoice, product=self.product, quantity=1, unit_price=100,
            line_subtotal=100, line_tax=15, line_total=115,
        )
        return invoice, line

    def receipt(self):
        supplier = Supplier.objects.create(company=self.company, name="Supplier")
        receipt = GoodsReceipt.objects.create(
            company=self.company, supplier=supplier, warehouse=self.warehouse
        )
        movement = StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.warehouse,
            movement_type="purchase_in", quantity=10, unit_cost=40,
        )
        line = GoodsReceiptLine.objects.create(
            receipt=receipt, product=self.product, quantity=10,
            unit_cost=40, movement=movement,
        )
        return supplier, receipt, line

    def test_tenant_owner_cannot_promote_account_to_platform(self):
        platform = Role.objects.create(name="Platform", scope_level="platform")
        response = self.client.patch(
            f"/api/users/{self.user.pk}/", {"role": platform.pk}, format="json"
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role_id, self.role.pk)
        roles = self.client.get("/api/roles/")
        self.assertNotIn(platform.pk, {row["id"] for row in roles.data["results"]})

    def test_tenant_owner_cannot_deactivate_self_by_patch(self):
        response = self.client.patch(
            f"/api/users/{self.user.pk}/", {"is_active": False}, format="json"
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_product_rejects_foreign_category(self):
        category = Category.objects.create(company=self.other, name="Foreign")
        response = self.client.patch(
            f"/api/products/{self.product.pk}/", {"category": category.pk}, format="json"
        )
        self.assertEqual(response.status_code, 400, response.data)

    def test_purchase_return_uses_original_line_caps_quantity_and_creates_note(self):
        supplier, receipt, line = self.receipt()
        payload = {
            "supplier": supplier.pk, "warehouse": self.warehouse.pk,
            "goods_receipt": receipt.pk,
            "lines": [{"goods_receipt_line": line.pk, "quantity": "3"}],
        }
        response = self.client.post("/api/purchase-returns/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(DebitNote.objects.get().amount, Decimal("120"))
        payload["lines"][0]["quantity"] = "8"
        self.assertEqual(
            self.client.post("/api/purchase-returns/", payload, format="json").status_code,
            400,
        )

    def test_sales_return_credits_tax_and_reduces_revenue(self):
        invoice, line = self.invoice()
        response = self.client.post("/api/sales-returns/", {
            "invoice": invoice.pk,
            "lines": [{
                "invoice_line": line.pk, "product": self.product.pk, "quantity": "1"
            }],
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(CreditNote.objects.get().amount, Decimal("115"))
        summary = operating_summary(self.company.pk)
        self.assertEqual(summary["gross_sales"], "100.00")
        self.assertEqual(summary["sales_returns"], "100.00")
        self.assertEqual(summary["revenue"], "0.00")

    def test_credit_note_customer_must_match_invoice(self):
        invoice, _ = self.invoice()
        wrong = Customer.objects.create(company=self.company, name="Wrong")
        response = self.client.post("/api/credit-notes/", {
            "customer": wrong.pk, "invoice": invoice.pk, "amount": "50"
        }, format="json")
        self.assertEqual(response.status_code, 400, response.data)

    def test_sync_paginates_all_records(self):
        Customer.objects.bulk_create([
            Customer(company=self.company, name=f"Bulk {index}") for index in range(500)
        ])
        first = self.client.get("/api/sync/pull/")
        self.assertTrue(first.data["has_more"])
        ids = {row["id"] for row in first.data["changes"]["customers"]}
        second = self.client.get(
            "/api/sync/pull/", {"page_cursor": first.data["next_page_cursor"]}
        )
        ids.update(row["id"] for row in second.data["changes"]["customers"])
        self.assertFalse(second.data["has_more"])
        self.assertEqual(len(ids), 501)

    def test_approved_budget_is_locked(self):
        budget = Budget.objects.create(
            company=self.company, name="Approved", period_start="2026-01-01",
            period_end="2026-12-31", status="approved",
        )
        response = self.client.patch(f"/api/budgets/{budget.pk}/", {
            "lines": [{
                "kind": "expense", "category": "Changed", "planned_amount": "99999"
            }]
        }, format="json")
        self.assertEqual(response.status_code, 400, response.data)

    def test_bill_rejects_inconsistent_total(self):
        supplier = Supplier.objects.create(company=self.company, name="Bill supplier")
        response = self.client.post("/api/bills/", {
            "supplier": supplier.pk, "subtotal": "100", "tax_amount": "15", "total": "1"
        }, format="json")
        self.assertEqual(response.status_code, 400, response.data)

    def test_quotation_conversion_is_idempotent(self):
        quote = Quotation.objects.create(company=self.company, customer=self.customer)
        first = self.client.post(f"/api/quotations/{quote.pk}/convert_to_order/")
        second = self.client.post(f"/api/quotations/{quote.pk}/convert_to_order/")
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(SalesOrder.objects.count(), 1)
