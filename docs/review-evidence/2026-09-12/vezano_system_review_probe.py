from decimal import Decimal
from rest_framework.test import APITestCase
from accounts.models import Role, User
from org.models import Company
from inventory.models import Product, Warehouse, Category
from sales.models import Customer, Invoice, InvoiceLine
from purchasing.models import Supplier
from returns.models import CreditNote, DebitNote
from finance.models import Budget

class ReviewProbes(APITestCase):
    def setUp(self):
        self.co = Company.objects.create(name='Review A')
        self.other = Company.objects.create(name='Review B')
        role = Role.objects.create(name='Business Owner', scope_level='business')
        self.user = User.objects.create_user(email='review@example.test', company=self.co, role=role)
        self.client.force_authenticate(self.user)
        self.p = Product.objects.create(company=self.co, name='Review product', sku='R1', sale_price=100)
        self.wh = Warehouse.objects.create(company=self.co, name='Review WH')
        self.customer = Customer.objects.create(company=self.co, name='Review customer')

    def test_owner_can_promote_to_platform(self):
        platform = Role.objects.create(name='Review platform', scope_level='platform')
        foreign = Customer.objects.create(company=self.other, name='Foreign test customer')
        r = self.client.patch(f'/api/users/{self.user.pk}/', {'role': platform.pk}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.user.refresh_from_db()
        self.client.force_authenticate(self.user)
        r = self.client.get(f'/api/customers/{foreign.pk}/')
        self.assertEqual(r.status_code, 200, r.data)
        print('REPRO: tenant owner became platform admin and read another tenant customer')

    def test_cross_tenant_product_category(self):
        cat = Category.objects.create(company=self.other, name='Foreign category')
        r = self.client.patch(f'/api/products/{self.p.pk}/', {'category':cat.pk}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.p.refresh_from_db()
        self.assertEqual(self.p.category_id, cat.pk)
        print('REPRO: product accepts another tenant category')

    def test_purchase_return_without_receipt_or_note(self):
        supplier = Supplier.objects.create(company=self.co, name='Review supplier')
        r = self.client.post('/api/purchase-returns/', {'supplier':supplier.pk, 'warehouse':self.wh.pk, 'lines':[{'product':self.p.pk, 'quantity':'100'}]}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(self.p.on_hand(), Decimal('-100'))
        self.assertEqual(DebitNote.objects.count(), 0)
        print('REPRO: returned 100 units without receipt, available stock or debit note')

    def invoice(self):
        inv = Invoice.objects.create(company=self.co, customer=self.customer, warehouse=self.wh, number=1, subtotal=100, tax_amount=15, total=115)
        line = InvoiceLine.objects.create(invoice=inv, product=self.p, quantity=1, unit_price=100, line_subtotal=100, line_tax=15, line_total=115)
        return inv,line

    def test_return_tax_not_credited(self):
        inv,line = self.invoice()
        r = self.client.post('/api/sales-returns/', {'invoice':inv.pk, 'lines':[{'invoice_line':line.pk,'product':self.p.pk,'quantity':'1'}]}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(CreditNote.objects.get().amount, Decimal('100'))
        print('REPRO: full return of 115 invoice issues credit 100')
        from finance.metrics import operating_summary
        self.assertEqual(operating_summary(self.co.pk)['revenue'], '100.00')
        print('REPRO: fully returned invoice still contributes 100 revenue')

    def test_duplicate_quote_conversion(self):
        from sales.models import Quotation
        quote = Quotation.objects.create(company=self.co, customer=self.customer)
        first = self.client.post(f'/api/quotations/{quote.pk}/convert_to_order/')
        second = self.client.post(f'/api/quotations/{quote.pk}/convert_to_order/')
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 201, second.data)
        self.assertNotEqual(first.data['id'], second.data['id'])
        print('REPRO: repeat quotation conversion creates a second order')

    def test_inconsistent_bill_total(self):
        supplier = Supplier.objects.create(company=self.co, name='Review supplier')
        r = self.client.post('/api/bills/', {'supplier':supplier.pk,'subtotal':'100','tax_amount':'15','total':'1'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        print('REPRO: bill accepts subtotal 100 plus tax 15 with total 1')

    def test_wrong_customer_credit(self):
        inv,line = self.invoice()
        wrong = Customer.objects.create(company=self.co, name='Unrelated customer')
        r = self.client.post('/api/credit-notes/', {'customer':wrong.pk,'invoice':inv.pk,'amount':'50'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        print('REPRO: credit note customer differs from linked invoice customer')

    def test_sync_loses_overflow(self):
        Customer.objects.bulk_create([Customer(company=self.co, name=f'Bulk {i}') for i in range(500)])
        r = self.client.get('/api/sync/pull/')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(len(r.data['changes']['customers']), 500)
        second = self.client.get('/api/sync/pull/', {'since':r.data['cursor']})
        self.assertEqual(len(second.data['changes']['customers']), 0)
        print('REPRO: of 501 customers, sync returns 500 then zero; one omitted')

    def test_approved_budget_edit(self):
        budget = Budget.objects.create(company=self.co, name='Review budget', period_start='2026-01-01', period_end='2026-12-31', status=Budget.APPROVED)
        role = Role.objects.create(name='Finance Department', scope_level='business')
        self.user.role = role
        self.user.save()
        r = self.client.patch(f'/api/budgets/{budget.pk}/', {'lines':[{'kind':'expense','category':'Changed','planned_amount':'99999'}]}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        budget.refresh_from_db()
        self.assertEqual(budget.status, Budget.APPROVED)
        self.assertEqual(budget.lines.get().planned_amount, Decimal('99999'))
        print('REPRO: finance employee replaces approved budget lines without reapproval')
