from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import PlatformInvitation, Role, User
from org.models import Company


class PlatformTeamTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("root@vezano.test", "secure-password")
        self.client.force_authenticate(self.admin)

    def _invite(self, email="ops@vezano.test", name="Ops Person", role="Super Administrator"):
        response = self.client.post(
            reverse("platform-team-list"),
            {"email": email, "full_name": name, "role": role}, format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_invite_creates_companyless_platform_member_with_one_time_link(self):
        data = self._invite()
        member = User.objects.get(email="ops@vezano.test")
        self.assertIsNone(member.company_id)
        self.assertEqual(member.role.scope_level, Role.SCOPE_PLATFORM)
        self.assertTrue(member.is_platform_admin)
        self.assertFalse(member.has_usable_password())
        self.assertFalse(data["activated"])
        self.assertIsNotNone(data["invitation_expires_at"])
        token = data["invitation_token"]

        self.client.force_authenticate(None)
        accept_url = reverse("platform-invitation-accept")
        accepted = self.client.post(
            accept_url, {"token": token, "password": "a-sufficiently-secure-password"},
            format="json",
        )
        self.assertEqual(accepted.status_code, 200, accepted.data)
        member.refresh_from_db()
        self.assertTrue(member.check_password("a-sufficiently-secure-password"))
        # Single use.
        again = self.client.post(
            accept_url, {"token": token, "password": "another-secure-password"}, format="json"
        )
        self.assertEqual(again.status_code, 400)
        # The new member can now use platform endpoints.
        self.client.force_authenticate(member)
        self.assertEqual(self.client.get(reverse("platform-team-list")).status_code, 200)

    def test_duplicate_email_is_refused(self):
        Company.objects.create(name="Tenant")
        User.objects.create_user("taken@vezano.test", "secure-password")
        response = self.client.post(
            reverse("platform-team-list"),
            {"email": "Taken@vezano.test", "full_name": "Dup", "role": "Support Agent"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_expired_link_can_be_reissued_and_old_one_dies(self):
        data = self._invite()
        member = User.objects.get(email="ops@vezano.test")
        PlatformInvitation.objects.filter(user=member).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        reissued = self.client.post(
            reverse("platform-team-reissue-invitation", args=[member.pk]), {}, format="json"
        )
        self.assertEqual(reissued.status_code, 201, reissued.data)
        self.assertNotEqual(reissued.data["invitation_token"], data["invitation_token"])
        self.client.force_authenticate(None)
        accept_url = reverse("platform-invitation-accept")
        old = self.client.post(
            accept_url,
            {"token": data["invitation_token"], "password": "a-sufficiently-secure-password"},
            format="json",
        )
        self.assertEqual(old.status_code, 400)
        new = self.client.post(
            accept_url,
            {
                "token": reissued.data["invitation_token"],
                "password": "a-sufficiently-secure-password",
            },
            format="json",
        )
        self.assertEqual(new.status_code, 200, new.data)

    def test_cannot_deactivate_self_or_last_active_admin(self):
        me = self.client.post(
            reverse("platform-team-deactivate", args=[self.admin.pk]), {}, format="json"
        )
        self.assertEqual(me.status_code, 400)
        self._invite()
        member = User.objects.get(email="ops@vezano.test")
        # Deactivate the newcomer: fine, root remains.
        off = self.client.post(
            reverse("platform-team-deactivate", args=[member.pk]), {}, format="json"
        )
        self.assertEqual(off.status_code, 200, off.data)
        self.assertFalse(off.data["is_active"])
        self.assertFalse(
            PlatformInvitation.objects.filter(user=member, revoked_at__isnull=True).exists()
        )
        # Now act as the newcomer after reactivation and try to remove root.
        on = self.client.post(
            reverse("platform-team-activate", args=[member.pk]), {}, format="json"
        )
        self.assertEqual(on.status_code, 200)
        self.client.force_authenticate(member)
        self.admin.refresh_from_db()
        root_off = self.client.post(
            reverse("platform-team-deactivate", args=[self.admin.pk]), {}, format="json"
        )
        self.assertEqual(root_off.status_code, 200, root_off.data)
        # And then the newcomer is the last one standing.
        self.client.force_authenticate(member)
        last = self.client.post(
            reverse("platform-team-deactivate", args=[member.pk]), {}, format="json"
        )
        self.assertEqual(last.status_code, 400)

    def test_tenant_owner_cannot_see_or_invite_platform_team(self):
        company = Company.objects.create(name="Tenant")
        owner_role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        owner = User.objects.create_user(
            "owner@tenant.test", "secure-password", company=company, role=owner_role
        )
        self.client.force_authenticate(owner)
        self.assertEqual(self.client.get(reverse("platform-team-list")).status_code, 403)
        response = self.client.post(
            reverse("platform-team-list"),
            {"email": "sneak@vezano.test", "full_name": "Sneak", "role": "Support Agent"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(email="sneak@vezano.test").exists())


class PlatformRoleCapabilityTests(APITestCase):
    """Reads are open to every platform member; writes follow the role map."""

    def setUp(self):
        self.root = User.objects.create_superuser("root@vezano.test", "secure-password")
        self.client.force_authenticate(self.root)
        self.members = {}
        roles = ("Subscription Manager", "Billing Reviewer", "Marketing Manager", "Support Agent")
        for role in roles:
            slug = role.lower().replace(" ", "-")
            response = self.client.post(
                reverse("platform-team-list"),
                {"email": f"{slug}@vezano.test", "full_name": role, "role": role},
                format="json",
            )
            self.assertEqual(response.status_code, 201, response.data)
            self.members[role] = User.objects.get(email=f"{slug}@vezano.test")

    def _as(self, role):
        self.client.force_authenticate(self.members[role])

    def test_me_exposes_platform_capabilities(self):
        self._as("Billing Reviewer")
        caps = self.client.get(reverse("auth-me")).data["capabilities"]
        self.assertTrue(caps["platform.billing.review"])
        self.assertNotIn("platform.team.manage", caps)
        self.assertNotIn("platform.registrations.provision", caps)

    # Which console areas each role may open. Money (subscriptions, payments)
    # is for the commercial and collections roles; the team list is the
    # Super Administrator's; marketing sees the funnel, the price list and
    # the public site's search settings (which support may read).
    VISIBLE = {
        "Subscription Manager": {
            "registrations", "leads", "subscriptions", "payments", "plans", "seo",
        },
        "Billing Reviewer": {"subscriptions", "payments"},
        "Marketing Manager": {"registrations", "leads", "plans", "seo"},
        "Support Agent": {"registrations", "leads", "subscriptions", "seo"},
    }
    SCREENS = {
        "team": "platform-team-list",
        "registrations": "platform-registration-request-list",
        "leads": "platform-lead-list",
        "subscriptions": "platform-subscription-list",
        "payments": "platform-subscription-payment-list",
        "plans": "platform-plan-list",
        "seo": "platform-seo-override-list",
    }
    # Who may change the search settings: marketing and the commercial lead.
    SEO_WRITERS = {"Subscription Manager", "Marketing Manager"}

    def test_each_role_reads_only_its_areas(self):
        for role, visible in self.VISIBLE.items():
            self._as(role)
            self.assertEqual(self.client.get(reverse("platform-overview")).status_code, 200, role)
            for area, name in self.SCREENS.items():
                expected = 200 if area in visible else 403
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, expected, (role, area, response.data))

    def test_badges_follow_the_same_visibility(self):
        from core.attention import visible_sources

        for role, visible in self.VISIBLE.items():
            keys = {source.key for source in visible_sources(self.members[role])}
            self.assertEqual("platform-registrations" in keys, "registrations" in visible, role)
            self.assertEqual("platform-leads" in keys, "leads" in visible, role)
            self.assertEqual("platform-subscriptions" in keys, "subscriptions" in visible, role)

    def test_seo_settings_follow_the_seo_capabilities(self):
        settings_url = reverse("platform-seo-settings")
        for role, visible in self.VISIBLE.items():
            self._as(role)
            read = self.client.get(settings_url)
            self.assertEqual(read.status_code, 200 if "seo" in visible else 403, role)
            write = self.client.patch(settings_url, {"analytics_id": "G-TEST1"}, format="json")
            self.assertEqual(
                write.status_code, 200 if role in self.SEO_WRITERS else 403, (role, write.data)
            )
            override = self.client.post(
                reverse("platform-seo-override-list"),
                {"path": f"/{role.split()[0].lower()}", "title": "T"}, format="json",
            )
            expected = 201 if role in self.SEO_WRITERS else 403
            self.assertEqual(override.status_code, expected, (role, override.data))

    def test_only_super_admin_manages_team_and_plans(self):
        for role in self.members:
            self._as(role)
            invite = self.client.post(
                reverse("platform-team-list"),
                {"email": "x@vezano.test", "full_name": "X", "role": "Support Agent"},
                format="json",
            )
            self.assertEqual(invite.status_code, 403, role)
            plan = self.client.post(
                reverse("platform-plan-list"), {"code": "p", "name": "P"}, format="json"
            )
            self.assertEqual(plan.status_code, 403, role)

    def test_support_agent_cannot_review_billing_but_billing_reviewer_can(self):
        from org.models import Company
        from subscriptions.models import SubscriptionPayment

        company = Company.objects.create(name="Tenant")
        payment = SubscriptionPayment.objects.create(
            company=company, amount="10.00", currency="USD", method="cash",
            recorded_by=self.root,
        )
        url = reverse("platform-subscription-payment-reject", args=[payment.pk])
        self._as("Support Agent")
        self.assertEqual(self.client.post(url, {"reason": "no"}, format="json").status_code, 403)
        self._as("Billing Reviewer")
        self.assertEqual(self.client.post(url, {"reason": "no"}, format="json").status_code, 200)

    def test_billing_reviewer_cannot_provision_but_subscription_manager_can_review(self):
        from uuid import uuid4

        from website.models import RegistrationRequest

        registration = RegistrationRequest.objects.create(
            request_uuid=uuid4(), company_name="Co", contact_name="C", email="c@co.test",
            phone="+1", country="SD", privacy_version="2026-09", delivery_mode="standalone",
        )
        review = reverse("platform-registration-request-review", args=[registration.pk])
        self._as("Billing Reviewer")
        self.assertEqual(
            self.client.post(review, {"status": "under_review"}, format="json").status_code, 403
        )
        self._as("Subscription Manager")
        self.assertEqual(
            self.client.post(review, {"status": "under_review"}, format="json").status_code, 200
        )

    def test_role_change_is_guarded(self):
        agent = self.members["Support Agent"]
        promote = self.client.post(
            reverse("platform-team-set-role", args=[agent.pk]),
            {"role": "Subscription Manager"}, format="json",
        )
        self.assertEqual(promote.status_code, 200, promote.data)
        self.assertEqual(promote.data["role_name"], "Subscription Manager")
        # A superuser has no platform role to change.
        me = self.client.post(
            reverse("platform-team-set-role", args=[self.root.pk]),
            {"role": "Support Agent"}, format="json",
        )
        self.assertEqual(me.status_code, 400)

    def test_marketing_manager_works_leads_and_nothing_else(self):
        from website.models import PlatformLead

        lead = PlatformLead.objects.create(name="Shop", email="shop@example.com")
        url = reverse("platform-lead-detail", args=[lead.pk])
        self._as("Marketing Manager")
        moved = self.client.patch(url, {"status": "contacted"}, format="json")
        self.assertEqual(moved.status_code, 200, moved.data)
        caps = self.client.get(reverse("auth-me")).data["capabilities"]
        for capability in (
            "platform.leads.manage", "platform.leads.view",
            "platform.registrations.view", "platform.plans.view",
        ):
            self.assertTrue(caps.get(capability), capability)
        for capability in (
            "platform.team.manage", "platform.team.view", "platform.plans.manage",
            "platform.billing.review", "platform.billing.view",
            "platform.subscriptions.view", "platform.registrations.provision",
            "platform.invitations.reissue",
        ):
            self.assertNotIn(capability, caps, capability)
        self._as("Billing Reviewer")
        refused = self.client.patch(url, {"status": "closed"}, format="json")
        self.assertEqual(refused.status_code, 403)


class SuperAdministratorRoleTests(APITestCase):
    """A member holding the Super Administrator *role* (not a Django superuser)
    has the same full control of the team as the platform owner."""

    def setUp(self):
        root = User.objects.create_superuser("root@vezano.test", "secure-password")
        self.client.force_authenticate(root)
        response = self.client.post(
            reverse("platform-team-list"),
            {"email": "gm@vezano.test", "full_name": "General Manager",
             "role": "Super Administrator"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.gm = User.objects.get(email="gm@vezano.test")
        self.assertFalse(self.gm.is_superuser)
        self.client.force_authenticate(self.gm)

    def test_super_administrator_role_runs_the_whole_team(self):
        caps = self.client.get(reverse("auth-me")).data["capabilities"]
        self.assertTrue(caps["platform.team.manage"])
        invited = self.client.post(
            reverse("platform-team-list"),
            {"email": "mkt@vezano.test", "full_name": "Marketing", "role": "Marketing Manager"},
            format="json",
        )
        self.assertEqual(invited.status_code, 201, invited.data)
        member_id = invited.data["id"]
        for name, body in (
            ("platform-team-set-role", {"role": "Support Agent"}),
            ("platform-team-reissue-invitation", {}),
            ("platform-team-deactivate", {}),
            ("platform-team-activate", {}),
        ):
            response = self.client.post(reverse(name, args=[member_id]), body, format="json")
            self.assertIn(response.status_code, (200, 201), (name, response.data))
        plan = self.client.post(
            reverse("platform-plan-list"), {"code": "p", "name": "P"}, format="json"
        )
        self.assertEqual(plan.status_code, 201, plan.data)

    def test_member_detail_carries_capabilities_provenance_and_history(self):
        invited = self.client.post(
            reverse("platform-team-list"),
            {"email": "mkt@vezano.test", "full_name": "Marketing", "role": "Marketing Manager"},
            format="json",
        )
        member_id = invited.data["id"]
        self.client.post(
            reverse("platform-team-set-role", args=[member_id]), {"role": "Support Agent"},
            format="json",
        )
        detail = self.client.get(reverse("platform-team-detail", args=[member_id])).data
        self.assertEqual(detail["role_name"], "Support Agent")
        self.assertEqual(
            detail["capabilities"],
            [
                "platform.invitations.reissue",
                "platform.leads.manage",
                "platform.leads.view",
                "platform.registrations.view",
                "platform.seo.view",
                "platform.subscriptions.view",
            ],
        )
        self.assertEqual(detail["invited_by"]["email"], "gm@vezano.test")
        self.assertEqual(len(detail["invitations"]), 1)
        self.assertIsNone(detail["invitations"][0]["accepted_at"])
        actions = [(row["action"], row["metadata"].get("role_to")) for row in detail["history"]]
        self.assertIn(("update", "Support Agent"), actions)
        self.assertIn(("create", None), actions)
        self.assertTrue(all(row["user"]["email"] == "gm@vezano.test" for row in detail["history"]))
        # A member who has never signed in has no activity of their own yet.
        self.assertEqual(detail["activity"], [])
        # The list endpoint stays lean.
        listed = self.client.get(reverse("platform-team-list")).data
        rows = listed["results"] if isinstance(listed, dict) else listed
        self.assertNotIn("activity", rows[0])


class PlatformActivityTests(APITestCase):
    """The team's audit trail: what is recorded, who may read it, and that
    tenant business rows never leak into it."""

    def setUp(self):
        self.root = User.objects.create_superuser("root@vezano.test", "secure-password")
        self.client.force_authenticate(self.root)
        invited = self.client.post(
            reverse("platform-team-list"),
            {"email": "mkt@vezano.test", "full_name": "Marketing", "role": "Marketing Manager"},
            format="json",
        )
        self.member = User.objects.get(pk=invited.data["id"])

    def _rows(self, **params):
        response = self.client.get(reverse("platform-activity-list"), params)
        self.assertEqual(response.status_code, 200, response.data)
        data = response.data
        return data["results"] if isinstance(data, dict) else data

    def test_platform_writes_are_recorded_with_actor_and_time(self):
        plan = self.client.post(
            reverse("platform-plan-list"), {"code": "basic", "name": "Basic"}, format="json"
        )
        self.assertEqual(plan.status_code, 201, plan.data)
        self.client.patch(
            reverse("platform-plan-detail", args=[plan.data["id"]]), {"name": "Basic+"},
            format="json",
        )
        from website.models import PlatformLead

        lead = PlatformLead.objects.create(name="Shop", email="shop@example.com")
        self.client.patch(
            reverse("platform-lead-detail", args=[lead.pk]), {"status": "contacted"},
            format="json",
        )
        rows = self._rows()
        kinds = [(r["action"], r["entity_type"]) for r in rows]
        self.assertIn(("create", "PlatformMember"), kinds)
        self.assertIn(("create", "Plan"), kinds)
        self.assertIn(("update", "Plan"), kinds)
        self.assertIn(("update", "PlatformLead"), kinds)
        plan_update = next(
            r for r in rows if r["entity_type"] == "Plan" and r["action"] == "update"
        )
        self.assertEqual(plan_update["metadata"]["fields"], ["name"])
        self.assertEqual(plan_update["user"]["email"], "root@vezano.test")
        self.assertEqual(plan_update["user"]["role_name"], "Django superuser")
        self.assertTrue(plan_update["created_at"])
        lead_update = next(r for r in rows if r["entity_type"] == "PlatformLead")
        self.assertEqual(lead_update["metadata"]["status_to"], "contacted")
        # Newest first.
        self.assertGreaterEqual(rows[0]["created_at"], rows[-1]["created_at"])

    def test_platform_sign_ins_appear_but_tenant_sign_ins_do_not(self):
        self.member.set_password("a-sufficiently-secure-password")
        self.member.save()
        anon = self.client_class()
        signed = anon.post(
            reverse("auth-login"),
            {"email": "mkt@vezano.test", "password": "a-sufficiently-secure-password",
                "device_id": "TEST"},
        )
        self.assertEqual(signed.status_code, 200, signed.data)
        from org.models import Branch, Company

        company = Company.objects.create(name="Tenant")
        owner_role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        User.objects.create_user(
            "owner@tenant.test", "a-sufficiently-secure-password", company=company,
            role=owner_role, branch=Branch.objects.create(company=company, name="Main"),
        )
        tenant = anon.post(
            reverse("auth-login"),
            {"email": "owner@tenant.test", "password": "a-sufficiently-secure-password",
                "device_id": "TEST"},
        )
        self.assertEqual(tenant.status_code, 200, tenant.data)
        logins = [r for r in self._rows(action="login")]
        self.assertEqual([r["user"]["email"] for r in logins], ["mkt@vezano.test"])

    def test_tenant_activity_never_appears_and_filters_work(self):
        from core.activity import log_activity
        from org.models import Company

        company = Company.objects.create(name="Tenant")
        tenant_user = User.objects.create_user("clerk@tenant.test", "x", company=company)
        log_activity(action="create", user=tenant_user, company=company,
                     entity_type="Invoice", entity_id=7)
        rows = self._rows()
        self.assertFalse(any(r["entity_type"] == "Invoice" for r in rows))
        only_member = self._rows(user=self.member.pk)
        self.assertTrue(all(r["user"]["id"] == self.member.pk for r in only_member))
        facets = self.client.get(reverse("platform-activity-facets")).data
        self.assertIn("PlatformMember", facets["entity_types"])
        self.assertNotIn("Invoice", facets["entity_types"])
        self.assertIn("create", facets["actions"])

    def test_only_members_who_see_the_team_read_the_trail(self):
        self.client.force_authenticate(self.member)  # Marketing Manager: no team view
        self.assertEqual(self.client.get(reverse("platform-activity-list")).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(reverse("platform-activity-list")).status_code, 401)


class PlatformMemberProfileTests(APITestCase):
    """Editing a member's details and deleting a mistaken invitation."""

    def setUp(self):
        self.root = User.objects.create_superuser("root@vezano.test", "secure-password")
        self.client.force_authenticate(self.root)
        invited = self.client.post(
            reverse("platform-team-list"),
            {"email": "mkt@vezano.test", "full_name": "Marketing", "role": "Marketing Manager"},
            format="json",
        )
        self.member = User.objects.get(pk=invited.data["id"])

    def test_profile_edit_is_validated_and_audited(self):
        url = reverse("platform-team-detail", args=[self.member.pk])
        edited = self.client.patch(
            url, {"full_name": "Hassan", "email": "hassan@vezano.test"}, format="json"
        )
        self.assertEqual(edited.status_code, 200, edited.data)
        self.assertEqual(edited.data["full_name"], "Hassan")
        self.assertEqual(edited.data["email"], "hassan@vezano.test")
        clash = self.client.patch(url, {"email": "ROOT@vezano.test"}, format="json")
        self.assertEqual(clash.status_code, 400)
        detail = self.client.get(url).data
        edits = [r for r in detail["history"] if r["metadata"].get("profile")]
        self.assertEqual(edits[0]["metadata"]["profile"]["email"],
                         ["mkt@vezano.test", "hassan@vezano.test"])

    def test_never_activated_member_can_be_deleted_but_a_signed_in_one_cannot(self):
        url = reverse("platform-team-detail", args=[self.member.pk])
        # A member who signed in keeps an account.
        self.member.set_password("a-sufficiently-secure-password")
        self.member.save()
        refused = self.client.delete(url)
        self.assertEqual(refused.status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.member.pk).exists())
        # A pending invitation is simply removed, and the removal is recorded.
        pending = self.client.post(
            reverse("platform-team-list"),
            {"email": "typo@vezano.test", "full_name": "Typo", "role": "Support Agent"},
            format="json",
        ).data["id"]
        gone = self.client.delete(reverse("platform-team-detail", args=[pending]))
        self.assertEqual(gone.status_code, 204)
        self.assertFalse(User.objects.filter(pk=pending).exists())
        trail = self.client.get(reverse("platform-activity-list"), {"action": "delete"}).data
        rows = trail["results"] if isinstance(trail, dict) else trail
        self.assertEqual(rows[0]["metadata"]["email"], "typo@vezano.test")
        # Never yourself, never a superuser.
        me = self.client.delete(reverse("platform-team-detail", args=[self.root.pk]))
        self.assertEqual(me.status_code, 400)

    def test_only_team_managers_edit_or_delete(self):
        self.client.force_authenticate(self.member)
        url = reverse("platform-team-detail", args=[self.member.pk])
        self.assertEqual(self.client.patch(url, {"full_name": "x"}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(url).status_code, 403)
