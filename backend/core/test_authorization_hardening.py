from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import Role, User
from core.models import ActivityLog
from inventory.models import Product
from org.models import Branch, Company


class AuthorizationHardeningTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Alpha")
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.other_branch = Branch.objects.create(company=self.company, name="Other")
        Product.objects.create(
            company=self.company, sku="PRIVATE", name="Tenant product"
        )

    def test_roleless_company_user_cannot_login(self):
        User.objects.create_user(
            email="roleless@alpha.test",
            password="passw0rd123",
            company=self.company,
        )
        response = self.client.post(
            reverse("auth-login"),
            {"email": "roleless@alpha.test", "password": "passw0rd123"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "role_assignment_required")

    def test_unknown_business_role_has_no_implicit_access(self):
        role = Role.objects.create(name="Custom Executive", scope_level="business")
        user = User.objects.create_user(
            email="custom@alpha.test", password="passw0rd123",
            company=self.company, role=role,
        )
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get(reverse("product-list")).status_code, 403)

    def test_platform_admin_cannot_read_tenant_products_or_activity(self):
        admin = User.objects.create_superuser(
            email="platform@test.local", password="passw0rd123"
        )
        ActivityLog.objects.create(
            company=self.company, action="create", entity_type="Product"
        )
        self.client.force_authenticate(admin)
        self.assertEqual(self.client.get(reverse("product-list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("activitylog-list")).status_code, 403)

    def test_platform_admin_keeps_dedicated_platform_access(self):
        admin = User.objects.create_superuser(
            email="operator@test.local", password="passw0rd123"
        )
        self.client.force_authenticate(admin)
        self.assertEqual(
            self.client.get(reverse("platform-subscription-list")).status_code,
            200,
        )

    def test_branch_role_requires_branch_on_user_creation(self):
        owner_role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        branch_role = Role.objects.create(
            name="Branch Manager", scope_level=Role.SCOPE_BRANCH
        )
        owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=owner_role,
        )
        self.client.force_authenticate(owner)
        response = self.client.post(
            reverse("user-list"),
            {
                "email": "manager@alpha.test",
                "password": "Str0ngPass!99",
                "role": branch_role.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("branch", response.data)

    def test_general_manager_has_company_wide_module_authority(self):
        role = Role.objects.create(
            name="General Manager", scope_level=Role.SCOPE_BUSINESS
        )
        manager = User.objects.create_user(
            email="gm@alpha.test", password="passw0rd123",
            company=self.company, role=role,
        )
        self.client.force_authenticate(manager)
        response = self.client.get(reverse("rbac-access"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(level == "write" for level in response.data.values()))

    def test_owner_can_create_second_owner_and_last_owner_is_protected(self):
        owner_role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=owner_role,
        )
        self.client.force_authenticate(owner)
        created = self.client.post(reverse("user-list"), {
            "email": "second-owner@alpha.test", "password": "Str0ngPass!99",
            "role": owner_role.pk,
        }, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(User.objects.filter(role=owner_role).count(), 2)
        self.assertEqual(
            self.client.delete(reverse("user-detail", args=[created.data["id"]])).status_code,
            204,
        )
        self.assertEqual(
            self.client.delete(reverse("user-detail", args=[owner.pk])).status_code,
            400,
        )

    def test_general_manager_cannot_assign_or_modify_an_owner(self):
        owner_role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        manager_role = Role.objects.create(
            name="General Manager", scope_level=Role.SCOPE_BUSINESS
        )
        owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=owner_role,
        )
        manager = User.objects.create_user(
            email="gm2@alpha.test", password="passw0rd123",
            company=self.company, role=manager_role,
        )
        self.client.force_authenticate(manager)
        created = self.client.post(reverse("user-list"), {
            "email": "third-owner@alpha.test", "password": "Str0ngPass!99",
            "role": owner_role.pk,
        }, format="json")
        self.assertEqual(created.status_code, 400)
        changed = self.client.patch(
            reverse("user-detail", args=[owner.pk]),
            {"full_name": "Changed"}, format="json",
        )
        self.assertEqual(changed.status_code, 400)

    def test_branch_manager_controls_only_lower_users_in_own_branch(self):
        manager_role = Role.objects.create(
            name="Branch Manager", scope_level=Role.SCOPE_BRANCH
        )
        sales_role = Role.objects.create(
            name="Sales Officer", scope_level=Role.SCOPE_BRANCH
        )
        manager = User.objects.create_user(
            email="manager@alpha.test", password="passw0rd123",
            company=self.company, branch=self.branch, role=manager_role,
        )
        hidden = User.objects.create_user(
            email="hidden@alpha.test", password="passw0rd123",
            company=self.company, branch=self.other_branch, role=sales_role,
        )
        self.client.force_authenticate(manager)
        listed = self.client.get(reverse("user-list"))
        self.assertNotIn(hidden.pk, {row["id"] for row in listed.data["results"]})
        created = self.client.post(reverse("user-list"), {
            "email": "sales@alpha.test", "password": "Str0ngPass!99",
            "role": sales_role.pk, "branch": self.branch.pk,
        }, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        forbidden = self.client.post(reverse("user-list"), {
            "email": "manager2@alpha.test", "password": "Str0ngPass!99",
            "role": manager_role.pk, "branch": self.branch.pk,
        }, format="json")
        self.assertEqual(forbidden.status_code, 400)

    def test_company_must_keep_one_active_owner(self):
        owner_role = Role.objects.create(
            name="Business Owner", scope_level=Role.SCOPE_BUSINESS
        )
        manager_role = Role.objects.create(
            name="General Manager", scope_level=Role.SCOPE_BUSINESS
        )
        owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123",
            company=self.company, role=owner_role,
        )
        second = User.objects.create_user(
            email="second@alpha.test", password="passw0rd123",
            company=self.company, role=owner_role,
        )
        self.client.force_authenticate(owner)
        response = self.client.patch(
            reverse("user-detail", args=[second.pk]),
            {"role": manager_role.pk}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            self.client.delete(reverse("user-detail", args=[owner.pk])).status_code,
            400,
        )

    def test_branch_manager_sees_only_own_branch_and_cannot_create_one(self):
        role = Role.objects.create(
            name="Branch Manager", scope_level=Role.SCOPE_BRANCH
        )
        manager = User.objects.create_user(
            email="branch-manager@alpha.test", password="passw0rd123",
            company=self.company, branch=self.branch, role=role,
        )
        self.client.force_authenticate(manager)
        listed = self.client.get(reverse("branch-list"))
        self.assertEqual({row["id"] for row in listed.data["results"]}, {self.branch.pk})
        created = self.client.post(reverse("branch-list"), {"name": "New"})
        self.assertEqual(created.status_code, 403)
