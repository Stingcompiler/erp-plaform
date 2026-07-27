from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from inventory.models import Warehouse
from org.models import Branch, Company


class BranchVisibilityBase(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.branch_a = Branch.objects.create(company=self.company, name="Branch A")
        self.branch_b = Branch.objects.create(company=self.company, name="Branch B")
        self.branch_role = Role.objects.create(
            name="Branch Manager", scope_level=Role.SCOPE_BRANCH
        )
        self.biz_role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        # Warehouses in each branch, plus one shared (no branch).
        self.wh_a = Warehouse.objects.create(
            company=self.company, name="WH A", branch=self.branch_a
        )
        self.wh_b = Warehouse.objects.create(
            company=self.company, name="WH B", branch=self.branch_b
        )
        self.wh_shared = Warehouse.objects.create(
            company=self.company, name="WH Shared", branch=None
        )

    def login(self, email, company=None, role=None, branch=None):
        User.objects.create_user(
            email=email, password="passw0rd123",
            company=company or self.company, role=role, branch=branch,
        )
        c = self.client_class()
        r = c.post(reverse("auth-login"), {"email": email, "password": "passw0rd123"})
        assert r.status_code == 200, r.content
        return c


class BranchScopingTests(BranchVisibilityBase):
    def test_branch_user_sees_only_own_branch_plus_shared(self):
        c = self.login(
            "a@alpha.test", role=self.branch_role, branch=self.branch_a
        )
        resp = c.get(reverse("warehouse-list"))
        names = {w["name"] for w in resp.data["results"]}
        self.assertIn("WH A", names)
        self.assertIn("WH Shared", names)  # unassigned rows stay visible
        self.assertNotIn("WH B", names)    # other branch hidden

    def test_business_user_sees_all_branches(self):
        c = self.login("owner@alpha.test", role=self.biz_role)
        resp = c.get(reverse("warehouse-list"))
        names = {w["name"] for w in resp.data["results"]}
        self.assertEqual(names, {"WH A", "WH B", "WH Shared"})

    def test_branch_user_without_branch_sees_all(self):
        # A branch-scoped role but no branch assigned -> no row filtering.
        c = self.login("nobranch@alpha.test", role=self.branch_role, branch=None)
        resp = c.get(reverse("warehouse-list"))
        names = {w["name"] for w in resp.data["results"]}
        self.assertEqual(names, {"WH A", "WH B", "WH Shared"})

    def test_created_rows_are_tagged_with_user_branch(self):
        c = self.login("a2@alpha.test", role=self.branch_role, branch=self.branch_a)
        resp = c.post(reverse("warehouse-list"), {"name": "New WH"}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        created = Warehouse.objects.get(company=self.company, name="New WH")
        self.assertEqual(created.branch_id, self.branch_a.id)

    def test_branch_user_cannot_see_other_branch_detail(self):
        c = self.login("a3@alpha.test", role=self.branch_role, branch=self.branch_a)
        # Directly requesting Branch B's warehouse -> 404 (filtered out).
        resp = c.get(reverse("warehouse-detail", args=[self.wh_b.id]))
        self.assertEqual(resp.status_code, 404)
