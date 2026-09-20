"""sync/pull must show a branch-scoped user exactly what the normal endpoint
shows — no more. The 2026-09-20 review found employees (with salaries),
warehouses, purchase orders and bills of other branches leaking into the
offline mirror while the screens hid them.

The matrix below builds, for every pull entity, a row in the user's branch,
a row in another branch and (where the model allows) an unassigned row,
then compares the ids pull returns with the ids the entity's own list
endpoint returns for the same user. Company-wide master data is expected
to match in full; branch documents must match the branch rule including
the unassigned-rows policy.
"""
from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from hr.models import Employee
from inventory.models import Product, StockMovement, Warehouse
from org.models import Branch, Company
from purchasing.models import Bill, PurchaseOrder, Supplier
from sales.models import Customer, Invoice
from sync.views import _pull_specs

LIST_ROUTE = {
    "products": "product-list", "warehouses": "warehouse-list",
    "stock_movements": "stockmovement-list", "customers": "customer-list",
    "invoices": "invoice-list", "suppliers": "supplier-list",
    "purchase_orders": "purchaseorder-list", "bills": "bill-list",
    "employees": "employee-list",
}


class PullBranchScopeTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha", business_type="enterprise")
        self.mine = Branch.objects.create(company=self.company, name="Omdurman")
        self.other = Branch.objects.create(company=self.company, name="Port Sudan")
        role = Role.objects.create(name="Branch Manager", scope_level=Role.SCOPE_BRANCH)
        self.manager = User.objects.create_user(
            email="bm@alpha.test", password="passw0rd123", company=self.company,
            branch=self.mine, role=role,
        )
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123", company=self.company,
            role=Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS),
        )
        supplier = Supplier.objects.create(company=self.company, name="S")
        customer = Customer.objects.create(company=self.company, name="C")
        product = Product.objects.create(company=self.company, sku="P", name="P")
        self.rows = {}
        for label, branch in (("mine", self.mine), ("other", self.other), ("none", None)):
            wh = Warehouse.objects.create(
                company=self.company, branch=branch, name=f"WH-{label}"
            ) if branch else None
            self.rows[label] = {
                "warehouses": wh,
                "stock_movements": StockMovement.objects.create(
                    company=self.company, product=product, warehouse=wh,
                    movement_type=StockMovement.PURCHASE_IN, quantity=Decimal("1"),
                ) if wh else None,
                "invoices": Invoice.objects.create(
                    company=self.company, branch=branch, customer=customer,
                    warehouse=wh or Warehouse.objects.filter(company=self.company).first(),
                    number={"mine": 1, "other": 2, "none": 3}[label],
                    subtotal=1, total=1,
                ),
                "purchase_orders": PurchaseOrder.objects.create(
                    company=self.company, supplier=supplier, branch=branch,
                ),
                "employees": Employee.objects.create(
                    company=self.company, branch=branch, full_name=f"Emp {label}",
                    status="active",
                    base_salary_override=Decimal("999") if label == "other" else None,
                ),
            }
        # Company-wide master data: one of each is enough.
        self.shared = {
            "products": product.pk, "customers": customer.pk, "suppliers": supplier.pk,
            "bills": Bill.objects.create(
                company=self.company, supplier=supplier, subtotal=1, total=1,
            ).pk,
        }

    def _pull_ids(self, user):
        self.client.force_authenticate(user)
        ids = {}
        page_cursor = None
        while True:
            params = {"page_cursor": page_cursor} if page_cursor else {}
            r = self.client.get(reverse("sync-pull"), params)
            self.assertEqual(r.status_code, 200, r.data)
            for key, rows in r.data["changes"].items():
                ids.setdefault(key, set()).update(row["id"] for row in rows)
            page_cursor = r.data.get("page_cursor")
            if not page_cursor:
                return ids

    def _endpoint_ids(self, user, key):
        self.client.force_authenticate(user)
        ids = set()
        url = reverse(LIST_ROUTE[key])
        params = {"page_size": 500}
        while url:
            r = self.client.get(url, params)
            self.assertEqual(r.status_code, 200, (key, r.data))
            body = r.data
            rows = body["results"] if isinstance(body, dict) and "results" in body else body
            ids.update(row["id"] for row in rows)
            url = body.get("next") if isinstance(body, dict) else None
            params = {}
        return ids

    def test_every_pull_entity_matches_its_endpoint_for_a_branch_manager(self):
        pulled = self._pull_ids(self.manager)
        for key, *_ in _pull_specs():
            with self.subTest(entity=key):
                if key not in pulled:
                    # The role cannot read this module at all; the endpoint
                    # must agree by refusing (403), not by listing.
                    self.client.force_authenticate(self.manager)
                    self.assertEqual(self.client.get(reverse(LIST_ROUTE[key])).status_code, 403)
                    continue
                self.assertEqual(pulled[key], self._endpoint_ids(self.manager, key))

    def test_branch_documents_of_another_branch_never_reach_the_mirror(self):
        pulled = self._pull_ids(self.manager)
        for key in ("warehouses", "stock_movements", "invoices", "employees"):
            with self.subTest(entity=key):
                self.assertIn(self.rows["mine"][key].pk, pulled[key])
                self.assertNotIn(self.rows["other"][key].pk, pulled[key])
        # Rows with no branch follow the endpoint policy (hidden for these
        # viewsets, which set include_unassigned_branch_rows = False).
        for key in ("invoices", "employees"):
            with self.subTest(entity=f"{key}:unassigned"):
                self.assertNotIn(self.rows["none"][key].pk, pulled[key])

    def test_purchase_orders_follow_the_branch_rule_when_the_role_can_read_them(self):
        # Branch Manager has purchasing write in the capability matrix.
        pulled = self._pull_ids(self.manager)
        self.assertIn(self.rows["mine"]["purchase_orders"].pk, pulled["purchase_orders"])
        self.assertNotIn(self.rows["other"]["purchase_orders"].pk, pulled["purchase_orders"])
        self.assertNotIn(self.rows["none"]["purchase_orders"].pk, pulled["purchase_orders"])

    def test_another_branchs_salary_is_never_in_the_pull_payload(self):
        self.client.force_authenticate(self.manager)
        r = self.client.get(reverse("sync-pull"))
        employees = r.data["changes"]["employees"]
        self.assertEqual([e["full_name"] for e in employees], ["Emp mine"])
        self.assertNotIn(
            "999.00", [str(e.get("base_salary_override")) for e in employees]
        )
        self.assertNotIn("Emp other", str(r.data))

    def test_company_wide_master_data_and_bills_stay_complete(self):
        pulled = self._pull_ids(self.manager)
        for key, pk in self.shared.items():
            with self.subTest(entity=key):
                self.assertIn(pk, pulled[key])

    def test_the_owner_still_sees_every_branch(self):
        pulled = self._pull_ids(self.owner)
        for key in ("warehouses", "stock_movements", "invoices", "employees", "purchase_orders"):
            with self.subTest(entity=key):
                self.assertIn(self.rows["mine"][key].pk, pulled[key])
                self.assertIn(self.rows["other"][key].pk, pulled[key])
