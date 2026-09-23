"""
Sales returns and purchase returns carry separate authority.

Dispositioning a return is what puts goods back into sellable stock, so the
decision belongs to whoever owns the original transaction: a sales officer for
what customers bring back, a purchasing officer for what we send to suppliers.
Before the split both sat under one `returns` module and either role could act
on the other's returns.
"""

from decimal import Decimal

from django.conf import settings
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from core.rbac import APP_MODULE, MODULES, ROLE_MODULE_MATRIX, level_for
from inventory.models import Product, Warehouse
from org.models import Branch, Company
from purchasing.models import Bill, Supplier
from returns.models import CreditNote, DebitNote, SalesReturn, SalesReturnLine
from sales.models import Customer, Invoice


class ModuleWiringTests(APITestCase):
    def test_returns_app_is_not_mapped_by_app_label(self):
        """One app, two authorities — an app-label mapping cannot tell them
        apart, so it must be absent."""
        self.assertNotIn("returns", APP_MODULE)

    def test_split_modules_are_registered(self):
        self.assertIn("sales_returns", MODULES)
        self.assertIn("purchase_returns", MODULES)
        self.assertNotIn("returns", MODULES)

    def test_every_returns_viewset_declares_its_module(self):
        """`RoleModuleAccess` treats an unresolvable module as 'not module
        scoped' and waves the request through. With the app-label mapping gone,
        a viewset that forgets `rbac_module` would be completely ungated."""
        import returns.views as views
        from rest_framework.viewsets import GenericViewSet

        missing = [
            name
            for name in dir(views)
            if isinstance(getattr(views, name), type)
            and issubclass(getattr(views, name), GenericViewSet)
            and name.endswith("ViewSet")
            # Only classes defined here — imported base classes carry no module.
            and getattr(views, name).__module__ == views.__name__
            and not getattr(getattr(views, name), "rbac_module", None)
        ]
        self.assertEqual(missing, [], f"viewsets without rbac_module: {missing}")

    def test_no_role_matrix_entry_still_mentions_the_old_module(self):
        stale = [
            role for role, perms in ROLE_MODULE_MATRIX.items() if "returns" in perms
        ]
        self.assertEqual(stale, [])

    def test_officers_hold_opposite_sides(self):
        sales = Role(name="Sales Officer", scope_level=Role.SCOPE_BRANCH)
        purch = Role(name="Purchasing Officer", scope_level=Role.SCOPE_BRANCH)
        self.assertEqual(level_for(sales, "sales_returns"), "write")
        self.assertEqual(level_for(sales, "purchase_returns"), "none")
        self.assertEqual(level_for(purch, "purchase_returns"), "write")
        self.assertEqual(level_for(purch, "sales_returns"), "none")

    def test_managers_keep_both_sides(self):
        for name in ("Branch Manager", "General Manager", "Business Owner"):
            role = Role(name=name, scope_level=Role.SCOPE_BUSINESS)
            self.assertEqual(level_for(role, "sales_returns"), "write", name)
            self.assertEqual(level_for(role, "purchase_returns"), "write", name)


class ReturnsAccessTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.warehouse = Warehouse.objects.create(
            company=self.company, branch=self.branch, name="W"
        )
        self.product = Product.objects.create(
            company=self.company, sku="P1", name="Widget"
        )
        self.customer = Customer.objects.create(company=self.company, name="C")
        self.supplier = Supplier.objects.create(company=self.company, name="S")
        self.invoice = Invoice.objects.create(
            company=self.company, customer=self.customer, warehouse=self.warehouse,
            branch=self.branch,
            number=1, subtotal=Decimal("100"), total=Decimal("100"),
        )
        self.sales_return = SalesReturn.objects.create(
            company=self.company, invoice=self.invoice, customer=self.customer
        )
        self.line = SalesReturnLine.objects.create(
            sales_return=self.sales_return, product=self.product,
            quantity=Decimal("1"), disposition=SalesReturnLine.QUARANTINE,
        )

    def _user(self, role_name):
        role, _ = Role.objects.get_or_create(
            name=role_name, defaults={"scope_level": Role.SCOPE_BRANCH}
        )
        return User.objects.create_user(
            email=f"{role_name.replace(' ', '').lower()}@alpha.test",
            password="passw0rd12345", company=self.company,
            branch=self.branch, role=role,
        )

    def test_purchasing_officer_cannot_disposition_a_sales_return(self):
        """The reported problem: a purchasing officer was restocking customer
        returns, a decision that belongs to whoever sold the goods."""
        self.client.force_authenticate(self._user("Purchasing Officer"))
        resp = self.client.post(
            reverse("salesreturn-disposition", args=[self.sales_return.id]),
            {"decisions": [
                {"line_id": self.line.id, "action": "restock",
                 "warehouse": self.warehouse.id}
            ]},
            format="json",
        )
        self.assertEqual(resp.status_code, 403, resp.data)
        self.line.refresh_from_db()
        self.assertEqual(self.line.disposition, SalesReturnLine.QUARANTINE)

    def test_purchasing_officer_cannot_even_list_sales_returns(self):
        self.client.force_authenticate(self._user("Purchasing Officer"))
        resp = self.client.get(reverse("salesreturn-list"))
        self.assertEqual(resp.status_code, 403, resp.data)

    def test_sales_officer_can_disposition_a_sales_return(self):
        self.client.force_authenticate(self._user("Sales Officer"))
        resp = self.client.post(
            reverse("salesreturn-disposition", args=[self.sales_return.id]),
            {"decisions": [
                {"line_id": self.line.id, "action": "restock",
                 "warehouse": self.warehouse.id}
            ]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)

    def test_sales_officer_cannot_create_a_purchase_return(self):
        self.client.force_authenticate(self._user("Sales Officer"))
        resp = self.client.get(reverse("purchasereturn-list"))
        self.assertEqual(resp.status_code, 403, resp.data)

    def test_purchasing_officer_can_reach_purchase_returns(self):
        self.client.force_authenticate(self._user("Purchasing Officer"))
        resp = self.client.get(reverse("purchasereturn-list"))
        self.assertEqual(resp.status_code, 200, resp.data)

    def test_credit_notes_follow_the_sales_side(self):
        CreditNote.objects.create(
            company=self.company, customer=self.customer, amount=Decimal("10")
        )
        self.client.force_authenticate(self._user("Sales Officer"))
        self.assertEqual(self.client.get(reverse("creditnote-list")).status_code, 200)
        self.client.force_authenticate(self._user("Purchasing Officer"))
        self.assertEqual(self.client.get(reverse("creditnote-list")).status_code, 403)

    def test_debit_notes_follow_the_purchasing_side(self):
        bill = Bill.objects.create(
            company=self.company, supplier=self.supplier, total=Decimal("50")
        )
        DebitNote.objects.create(
            company=self.company, supplier=self.supplier, bill=bill,
            amount=Decimal("10"),
        )
        self.client.force_authenticate(self._user("Purchasing Officer"))
        self.assertEqual(self.client.get(reverse("debitnote-list")).status_code, 200)
        self.client.force_authenticate(self._user("Sales Officer"))
        self.assertEqual(self.client.get(reverse("debitnote-list")).status_code, 403)

    def test_sync_cannot_be_used_to_bypass_the_split(self):
        """The offline queue applies ops through the same role check; if it
        didn't, queueing a sales return would route around the module gate."""
        self.client.force_authenticate(self._user("Purchasing Officer"))
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        resp = self.client.post(
            reverse("sync-push"),
            {
                "batch_uuid": "22222222-2222-2222-2222-222222222222",
                "operations": [{
                    "op_type": "sales_return",
                    "client_uuid": "11111111-1111-1111-1111-111111111111",
                    "payload": {
                        "invoice": self.invoice.id,
                        "lines": [
                            {"product": self.product.id, "quantity": "1"},
                        ],
                    },
                }],
            },
            format="json",
        )

        # The batch is accepted (201) but the individual op is refused — that is
        # how the queue reports a per-operation failure without failing the
        # whole batch.
        self.assertEqual(resp.status_code, 201, resp.data)
        result = resp.data["results"][0]
        self.assertEqual(result["status"], "error", result)
        self.assertIn("does not permit", result["error"])
        self.assertEqual(SalesReturn.objects.count(), 1)  # only the fixture

    def test_dashboard_disposition_tile_is_sales_side(self):
        self.client.force_authenticate(self._user("Purchasing Officer"))
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("returns", resp.data["sections"])

        self.client.force_authenticate(self._user("Sales Officer"))
        resp = self.client.get(reverse("dashboard"))
        self.assertIn("returns", resp.data["sections"])
        self.assertEqual(
            resp.data["sections"]["returns"]["pending_disposition_count"], 1
        )
