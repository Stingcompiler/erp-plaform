"""A plan's ``devices`` limit is a limit on browsers, enforced at sign-in;
revoking a device ends its sessions; the platform sees every company's
usage against its plan."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role, User
from core.models import ActivityLog
from org.models import Branch, Company, Device
from subscriptions.models import Plan, PlanVersion, Subscription


@override_settings(SUBSCRIPTION_POLICY="enforce")
class DeviceLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        owner_role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        sales_role = Role.objects.create(name="Sales Officer", scope_level=Role.SCOPE_BRANCH)
        self.company = Company.objects.create(name="Two Tills", business_type="enterprise")
        branch = Branch.objects.create(company=self.company, name="Main")
        self.owner = User.objects.create_user(
            email="owner@tills.test", password="Owner-passw0rd!x", company=self.company,
            role=owner_role, full_name="Owner",
        )
        self.sales = User.objects.create_user(
            email="sales@tills.test", password="Sales-passw0rd!x", company=self.company,
            role=sales_role, full_name="Sales", branch=branch,
        )
        plan = Plan.objects.create(code="shop", name="Shop")
        version = PlanVersion.objects.create(
            plan=plan, version=1, modules=["*"], limits={"devices": 2},
            published_at=timezone.now(),
        )
        Subscription.objects.create(
            company=self.company, plan_version=version, status=Subscription.ACTIVE,
            starts_at=timezone.now(), period_ends_at=timezone.now() + timedelta(days=30),
        )

    def _login(self, email, password, device_id, agent="Mozilla/5.0 (Till)"):
        client = APIClient(HTTP_USER_AGENT=agent)
        response = client.post(
            "/api/auth/login/",
            {"email": email, "password": password, "device_id": device_id}, format="json",
        )
        return client, response

    def test_third_device_is_refused_at_sign_in_and_named_in_the_log(self):
        _, first = self._login("owner@tills.test", "Owner-passw0rd!x", "AAAA")
        _, second = self._login("sales@tills.test", "Sales-passw0rd!x", "BBBB")
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        # The same browser again is not a new device.
        _, again = self._login("sales@tills.test", "Sales-passw0rd!x", "AAAA")
        self.assertEqual(again.status_code, 200)
        self.assertEqual(Device.objects.filter(company=self.company, is_active=True).count(), 2)

        _, third = self._login("sales@tills.test", "Sales-passw0rd!x", "CCCC")
        self.assertEqual(third.status_code, 403)
        self.assertEqual(third.data["code"], "device_limit_reached")
        self.assertEqual(third.data["limit"], 2)
        self.assertEqual(third.data["owner_contact"], "owner@tills.test")
        self.assertFalse(Device.objects.filter(device_id="CCCC").exists())
        blocked = ActivityLog.objects.get(action="login_blocked")
        self.assertEqual(blocked.metadata["reason"], "device_limit_reached")

    def test_company_login_without_a_device_id_is_refused(self):
        """Review F06: omitting the id used to sign in uncounted."""
        _, response = self._login("owner@tills.test", "Owner-passw0rd!x", "")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data["code"], "device_required")
        self.assertEqual(Device.objects.count(), 0)
        # Two tills fill the plan; a third with a made-up id and a third
        # without any id are both refused.
        for device in ("TILL1", "TILL2"):
            self.assertEqual(self._login("sales@tills.test", "Sales-passw0rd!x", device)[1]
                             .status_code, 200)
        self.assertEqual(self._login("sales@tills.test", "Sales-passw0rd!x", "TILL3")[1]
                         .status_code, 403)
        self.assertEqual(self._login("sales@tills.test", "Sales-passw0rd!x", "")[1]
                         .status_code, 400)

    def test_platform_accounts_need_no_device(self):
        """The documented exception: console logins belong to no company."""
        User.objects.create_superuser(email="root@vezano.test", password="Root-passw0rd!")
        _, response = self._login("root@vezano.test", "Root-passw0rd!", "")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Device.objects.count(), 0)

    def test_revocation_survives_a_cache_loss(self):
        """Review F05: the flag lived in cache only."""
        till, _ = self._login("sales@tills.test", "Sales-passw0rd!x", "TILL1")
        device = Device.objects.get(device_id="TILL1")
        owner, _ = self._login("owner@tills.test", "Owner-passw0rd!x", "OWNER")
        self.assertEqual(
            owner.post(f"/api/subscription/devices/{device.pk}/revoke/", {}, format="json")
            .status_code, 200,
        )
        cache.clear()  # eviction, restart, or a rebuilt cache table
        self.assertEqual(till.get("/api/auth/me/").status_code, 401)
        self.assertEqual(till.post("/api/auth/refresh/", {}, format="json").status_code, 401)
        # A new sign-in from the removed device is refused too.
        self.assertEqual(self._login("sales@tills.test", "Sales-passw0rd!x", "TILL1")[1]
                         .status_code, 403)
        # Reactivating clears it, also without the cache.
        owner.post(f"/api/subscription/devices/{device.pk}/reactivate/", {}, format="json")
        cache.clear()
        self.assertEqual(self._login("sales@tills.test", "Sales-passw0rd!x", "TILL1")[1]
                         .status_code, 200)

    def test_sessions_minted_without_a_device_cannot_refresh(self):
        """Tokens from before device identity was mandatory end at refresh."""
        from rest_framework_simplejwt.tokens import RefreshToken

        legacy = RefreshToken.for_user(self.sales)  # no "device" claim
        client = APIClient()
        client.cookies["refresh_token"] = str(legacy)
        response = client.post("/api/auth/refresh/", {}, format="json")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["code"], "device_required")

    def test_sync_after_an_outage_keeps_working_and_stops_once_revoked(self):
        till, _ = self._login("sales@tills.test", "Sales-passw0rd!x", "TILL1")
        # The till comes back online and replays its queue with its session.
        self.assertEqual(till.get("/api/sync/pull/").status_code, 200)
        # Signing in again from the same device counts no new device.
        self.assertEqual(self._login("sales@tills.test", "Sales-passw0rd!x", "TILL1")[1]
                         .status_code, 200)
        self.assertEqual(Device.objects.filter(is_active=True).count(), 1)
        device = Device.objects.get(device_id="TILL1")
        owner, _ = self._login("owner@tills.test", "Owner-passw0rd!x", "OWNER")
        owner.post(f"/api/subscription/devices/{device.pk}/revoke/", {}, format="json")
        cache.clear()
        self.assertEqual(till.get("/api/sync/pull/").status_code, 401)

    def test_owner_sees_usage_and_devices_and_revoking_ends_the_session(self):
        till, _ = self._login("sales@tills.test", "Sales-passw0rd!x", "TILL1")
        owner, _ = self._login("owner@tills.test", "Owner-passw0rd!x", "DESK1")
        self.assertEqual(till.get("/api/customers/").status_code, 200)

        listing = owner.get("/api/subscription/devices/")
        self.assertEqual(listing.status_code, 200, listing.data)
        self.assertEqual(listing.data["usage"]["devices"], {"used": 2, "limit": 2})
        ids = {d["device_id"]: d for d in listing.data["devices"]}
        self.assertEqual(ids["TILL1"]["last_user_name"], "Sales")
        self.assertIn("Till", ids["TILL1"]["user_agent"])

        labelled = owner.patch(
            f"/api/subscription/devices/{ids['TILL1']['id']}/", {"label": "كاشير 1"},
            format="json",
        )
        self.assertEqual(labelled.status_code, 200)
        self.assertEqual(labelled.data["label"], "كاشير 1")

        revoked = owner.post(f"/api/subscription/devices/{ids['TILL1']['id']}/revoke/")
        self.assertEqual(revoked.status_code, 200)
        self.assertFalse(revoked.data["is_active"])
        # The till's existing session is dead, and it cannot sign in again.
        dead = till.get("/api/customers/")
        self.assertEqual(dead.status_code, 401)
        _, back = self._login("sales@tills.test", "Sales-passw0rd!x", "TILL1")
        self.assertEqual(back.status_code, 403)
        self.assertEqual(back.data["code"], "device_revoked")
        # Room for a new one now.
        _, fresh = self._login("sales@tills.test", "Sales-passw0rd!x", "TILL2")
        self.assertEqual(fresh.status_code, 200)
        # Allowing the old one again would be a third device.
        third = owner.post(f"/api/subscription/devices/{ids['TILL1']['id']}/reactivate/")
        self.assertEqual(third.status_code, 400)
        self.assertEqual(third.data["code"], "plan_limit_reached")
        self.assertEqual(
            set(ActivityLog.objects.filter(entity_type="Device").values_list("action", flat=True)),
            {"device_registered", "device_revoked", "update"},
        )

    def test_owner_removes_a_device_and_its_sessions_stop_at_once(self):
        """The owner asked for removal, not just revocation: the row goes, and
        a session from that device is refused immediately rather than being
        trusted again because the id is now unknown."""
        till, _ = self._login("sales@tills.test", "Sales-passw0rd!x", "TILL1")
        owner, _ = self._login("owner@tills.test", "Owner-passw0rd!x", "ADMIN")
        device = Device.objects.get(device_id="TILL1")
        self.assertEqual(till.get("/api/products/").status_code, 200)

        removed = owner.delete(f"/api/subscription/devices/{device.pk}/")
        self.assertEqual(removed.status_code, 204, removed.content)
        self.assertFalse(Device.objects.filter(pk=device.pk).exists())
        self.assertEqual(till.get("/api/products/").status_code, 401)
        # The slot is free again, and the log keeps where the data was handled.
        self.assertEqual(
            owner.get("/api/subscription/devices/").data["usage"]["devices"]["used"], 1
        )
        entry = ActivityLog.objects.get(action="device_deleted")
        self.assertEqual(entry.metadata["device_id"], "TILL1")

    def test_removing_a_device_is_the_owners_alone(self):
        till, _ = self._login("sales@tills.test", "Sales-passw0rd!x", "TILL1")
        device = Device.objects.get(device_id="TILL1")
        self.assertEqual(till.delete(f"/api/subscription/devices/{device.pk}/").status_code, 403)
        self.assertTrue(Device.objects.filter(pk=device.pk).exists())

    def test_a_non_owner_cannot_manage_devices(self):
        till, _ = self._login("sales@tills.test", "Sales-passw0rd!x", "TILL1")
        self.assertEqual(till.get("/api/subscription/devices/").status_code, 403)

    def test_owner_subscription_page_reports_usage(self):
        owner, _ = self._login("owner@tills.test", "Owner-passw0rd!x", "DESK1")
        page = owner.get("/api/subscription/")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.data["usage"]["devices"], {"used": 1, "limit": 2})
        self.assertEqual(page.data["usage"]["users"], {"used": 2, "limit": None})


@override_settings(SUBSCRIPTION_POLICY="enforce")
class PlatformCompaniesTests(TestCase):
    def setUp(self):
        cache.clear()
        owner_role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        self.company = Company.objects.create(name="Alpha", phone="+249900000000")
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="Owner-passw0rd!x", company=self.company,
            role=owner_role, full_name="Alpha Owner",
        )
        plan = Plan.objects.create(code="shop", name="Shop")
        version = PlanVersion.objects.create(
            plan=plan, version=1, modules=["*"], limits={"devices": 1, "branches": 1},
            published_at=timezone.now(),
        )
        Subscription.objects.create(
            company=self.company, plan_version=version, status=Subscription.ACTIVE,
            starts_at=timezone.now(), period_ends_at=timezone.now() + timedelta(days=30),
        )
        Device.objects.create(company=self.company, device_id="D1", last_user=self.owner)
        Device.objects.create(company=self.company, device_id="D2", last_user=self.owner)
        self.admin = User.objects.create_superuser(
            email="root@vezano.test", password="Root-passw0rd!"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_lists_every_company_with_usage_plan_owner_and_over_limit(self):
        response = self.client.get("/api/platform/companies/")
        self.assertEqual(response.status_code, 200, response.data)
        row = next(r for r in response.data["companies"] if r["id"] == self.company.pk)
        self.assertEqual(row["owner"]["email"], "owner@alpha.test")
        self.assertEqual(row["owner"]["phone"], "+249900000000")
        self.assertEqual(row["plan"]["name"], "Shop")
        self.assertEqual(row["plan"]["status"], "active")
        self.assertEqual(row["usage"]["devices"], {"used": 2, "limit": 1})
        self.assertEqual(row["usage"]["branches"]["limit"], 1)
        self.assertEqual(row["over_limit"], ["devices"])
        self.assertEqual(row["invoices_30d"], 0)
        self.assertEqual(response.data["policy"], "enforce")

    def test_platform_can_revoke_a_device(self):
        device = Device.objects.get(device_id="D2")
        response = self.client.post(
            f"/api/platform/companies/{self.company.pk}/devices/{device.pk}/revoke/"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["is_active"])
        listing = self.client.get(f"/api/platform/companies/{self.company.pk}/devices/")
        self.assertEqual(len(listing.data["devices"]), 2)
        row = self.client.get("/api/platform/companies/").data["companies"][0]
        self.assertEqual(row["over_limit"], [])

    def test_tenant_users_cannot_see_the_platform_list(self):
        client = APIClient()
        client.force_authenticate(self.owner)
        self.assertEqual(client.get("/api/platform/companies/").status_code, 403)
