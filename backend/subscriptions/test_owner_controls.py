"""The platform owner's controls over a tenant: suspend until payment, and
delete a company (deferred 30 days, with backup, restore and purge)."""

import io
import json
import tempfile
import uuid
import zipfile
from datetime import timedelta
from decimal import Decimal

from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Role, User
from core.models import ActivityLog
from core.platform_roles import ensure_platform_roles
from org.models import Branch, Company
from subscriptions.models import (
    CompanyDeletion,
    Plan,
    PlanVersion,
    Subscription,
    SubscriptionEvent,
    SubscriptionPayment,
)

PASSWORD = "secure-password-1"


class OwnerControlsBase(APITestCase):
    def setUp(self):
        self.owner_role, _created = Role.objects.get_or_create(
            name="Business Owner", defaults={"scope_level": Role.SCOPE_BUSINESS}
        )
        self.staff_role, _created = Role.objects.get_or_create(
            name="General Manager", defaults={"scope_level": Role.SCOPE_BUSINESS}
        )
        self.company = Company.objects.create(name="Nile Traders", timezone="Africa/Khartoum")
        self.branch = Branch.objects.create(company=self.company, name="Main", code="MAIN")
        self.owner = User.objects.create_user(
            email="owner@nile.test", password=PASSWORD, company=self.company,
            role=self.owner_role, branch=self.branch,
        )
        self.staff = User.objects.create_user(
            email="gm@nile.test", password=PASSWORD, company=self.company,
            role=self.staff_role, branch=self.branch,
        )
        self.root = User.objects.create_superuser("root@vezano.test", PASSWORD)
        roles = ensure_platform_roles()
        self.manager = User.objects.create_user(
            email="subs@vezano.test", password=PASSWORD,
            role=roles["Subscription Manager"],
        )
        self.billing = User.objects.create_user(
            email="billing@vezano.test", password=PASSWORD, role=roles["Billing Reviewer"],
        )
        plan = Plan.objects.create(code="business", name="Business")
        self.version = PlanVersion.objects.create(
            plan=plan, version=1, currency="SDG", price=Decimal("500000.00"),
            billing_cycle=PlanVersion.MONTHLY, modules=["*"], published_at=timezone.now(),
        )
        now = timezone.now()
        self.subscription = Subscription.objects.create(
            company=self.company, plan_version=self.version, status=Subscription.ACTIVE,
            starts_at=now - timedelta(days=40), period_ends_at=now - timedelta(days=2),
            grace_ends_at=now + timedelta(days=5),
        )

    def as_platform(self, user):
        self.client.logout()
        self.client.force_authenticate(user)

    def login(self, user):
        self.client.force_authenticate(None)
        self.client.logout()
        return self.client.post(
            reverse("auth-login"),
            {"email": user.email, "password": PASSWORD, "device_id": f"DEV-{user.pk}"},
        )

    def suspend(self, reason="Invoice VSUB-000001 is two months overdue"):
        """Suspend through the service, leaving the test client's session
        (cookies) alone; the endpoint itself is tested separately."""
        from subscriptions.tenant_controls import suspend_until_payment

        return suspend_until_payment(self.company, self.root, reason)


class SuspendUntilPaymentTests(OwnerControlsBase):
    def test_reason_and_capability_are_required(self):
        url = reverse("platform-company-suspend", args=[self.company.pk])
        self.as_platform(self.billing)
        self.assertEqual(
            self.client.post(url, {"reason": "late"}, format="json").status_code, 403
        )
        self.as_platform(self.manager)
        self.assertEqual(self.client.post(url, {"reason": " "}, format="json").status_code, 400)
        response = self.client.post(url, {"reason": "late"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.subscription.refresh_from_db()
        self.assertTrue(self.subscription.is_suspended_unpaid)
        self.assertEqual(self.subscription.suspended_reason, "late")
        self.assertEqual(self.subscription.status_before_suspension, Subscription.ACTIVE)
        log = ActivityLog.objects.get(action="company_suspended_unpaid")
        self.assertEqual(log.user, self.manager)
        self.assertEqual(log.metadata["reason"], "late")
        # The companies console shows it.
        row = next(
            r for r in self.client.get(reverse("platform-company-list")).data["companies"]
            if r["id"] == self.company.pk
        )
        self.assertEqual(row["suspension"]["kind"], "unpaid")

    def test_owner_signs_in_and_reaches_only_what_paying_needs(self):
        self.suspend()
        self.assertEqual(self.login(self.owner).status_code, 200)
        me = self.client.get(reverse("auth-me"))
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["company_access"]["state"], "suspended_unpaid")
        self.assertTrue(me.data["company_access"]["is_owner"])
        self.assertIn("two months", me.data["company_access"]["reason"])
        self.assertEqual(self.client.get(reverse("company-subscription")).status_code, 200)
        self.assertEqual(self.client.get("/api/rbac/access/").status_code, 200)
        paid = self.client.post(
            reverse("subscription-payment-list"),
            {"amount": "500000.00", "currency": "SDG", "method": "bank_transfer",
             "reference_last4": "4321", "transfer_reference": "TRX99887766"},
        )
        self.assertEqual(paid.status_code, 201, paid.data)
        refused = self.client.get(reverse("user-list"))
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(refused.data["code"], "suspended_unpaid")
        self.assertIn("two months", refused.data["reason"])
        self.assertEqual(self.client.post(reverse("auth-logout")).status_code, 200)

    def test_staff_are_refused_at_sign_in_and_mid_session(self):
        self.assertEqual(self.login(self.staff).status_code, 200)  # signed in before
        self.suspend()
        mid_session = self.client.get(reverse("user-list"))
        self.assertEqual(mid_session.status_code, 403)
        self.assertEqual(mid_session.data["code"], "suspended_unpaid")
        me = self.client.get(reverse("auth-me"))
        self.assertFalse(me.data["company_access"]["is_owner"])
        # Staff never reach the subscription area.
        self.assertEqual(self.client.get(reverse("company-subscription")).status_code, 403)
        refused = self.login(self.staff)
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(refused.data["code"], "company_suspended")
        self.assertTrue(
            ActivityLog.objects.filter(
                action="login_blocked", user=self.staff, metadata__reason="company_suspended"
            ).exists()
        )

    def test_staff_refusal_reads_in_arabic(self):
        self.suspend()
        self.client.cookies["erp_language"] = "ar"
        refused = self.client.post(
            reverse("auth-login"),
            {"email": self.staff.email, "password": PASSWORD, "device_id": "DEV-AR"},
        )
        self.assertEqual(refused.data["code"], "company_suspended")
        self.assertIn("موقوف مؤقتًا", str(refused.data["detail"]))

    def _renew(self):
        payment = SubscriptionPayment.objects.create(
            company=self.company, amount=Decimal("500000.00"), currency="SDG",
            method="cash", recorded_by=self.owner,
        )
        self.as_platform(self.root)
        preview = self.client.get(
            reverse("platform-subscription-payment-renewal", args=[payment.pk])
        ).data
        response = self.client.post(
            reverse("platform-subscription-payment-renew", args=[payment.pk]),
            {"expected": preview["key"]}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        return preview

    def test_approving_a_renewal_lifts_it(self):
        self.suspend()
        preview = self._renew()
        self.assertTrue(preview["lifts_suspension"])
        self.assertEqual(preview["status_after"], Subscription.ACTIVE)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.ACTIVE)
        self.assertEqual(self.subscription.suspension_kind, "")
        self.assertTrue(
            SubscriptionEvent.objects.filter(
                subscription=self.subscription, event_type="suspension_lifted",
                metadata__via="payment",
            ).exists()
        )
        self.assertTrue(
            ActivityLog.objects.filter(
                action="company_suspension_lifted", metadata__via="payment"
            ).exists()
        )
        self.assertEqual(self.login(self.staff).status_code, 200)

    def test_a_manual_suspension_is_not_lifted_by_a_renewal(self):
        self.as_platform(self.root)
        moved = self.client.post(
            reverse("platform-subscription-transition", args=[self.subscription.pk]),
            {"status": "suspended", "reason": "fraud review"}, format="json",
        )
        self.assertEqual(moved.status_code, 200, moved.data)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.suspension_kind, Subscription.SUSPENSION_MANUAL)
        self._renew()
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.SUSPENDED)
        # A manual suspension keeps today's behaviour: staff still sign in.
        self.assertEqual(self.login(self.staff).status_code, 200)

    def test_legacy_suspended_rows_count_as_manual(self):
        Subscription.objects.filter(pk=self.subscription.pk).update(
            status=Subscription.SUSPENDED, suspension_kind="",
        )
        self.assertEqual(self.login(self.staff).status_code, 200)
        self.as_platform(self.root)
        row = next(
            r for r in self.client.get(reverse("platform-company-list")).data["companies"]
            if r["id"] == self.company.pk
        )
        self.assertEqual(row["suspension"]["kind"], "manual")
        lift = self.client.post(
            reverse("platform-company-lift-suspension", args=[self.company.pk]), format="json"
        )
        self.assertEqual(lift.status_code, 400)

    def test_manual_lift_restores_the_previous_state(self):
        self.suspend()
        self.as_platform(self.manager)
        lifted = self.client.post(
            reverse("platform-company-lift-suspension", args=[self.company.pk]), format="json"
        )
        self.assertEqual(lifted.status_code, 200, lifted.data)
        self.subscription.refresh_from_db()
        # Back to active; the lapsed period then reads as grace by the clock.
        self.assertEqual(self.subscription.status, Subscription.ACTIVE)
        self.assertEqual(self.login(self.staff).status_code, 200)

    @override_settings(
        EMAIL_ENABLED=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    )
    def test_owner_is_emailed_on_suspend_and_on_lift(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.suspend()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.owner.email])
        self.assertIn("لحين السداد", mail.outbox[0].subject)
        self.as_platform(self.root)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse("platform-company-lift-suspension", args=[self.company.pk]),
                format="json",
            )
        self.assertEqual(len(mail.outbox), 2)

    def test_no_email_when_email_is_off(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.suspend()
        self.assertEqual(len(mail.outbox), 0)


class SuspendedSyncTests(OwnerControlsBase):
    """Offline tills: work captured before the suspension still uploads;
    anything after it is refused with the platform's reason."""

    def setUp(self):
        super().setUp()
        from inventory.models import Product, Warehouse
        from sales.models import Customer

        self.wh = Warehouse.objects.create(company=self.company, branch=self.branch, name="WH")
        self.product = Product.objects.create(
            company=self.company, sku="SKU1", name="Widget",
            sale_price=Decimal("10"), cost_price=Decimal("4"),
        )
        self.customer = Customer.objects.create(company=self.company, name="Ahmed")
        # Paid up, so only the suspension is in play.
        Subscription.objects.filter(pk=self.subscription.pk).update(
            period_ends_at=timezone.now() + timedelta(days=20)
        )

    def _op(self, occurred_at):
        return {
            "op_type": "pos_checkout", "client_uuid": str(uuid.uuid4()),
            "payload": {
                "warehouse": self.wh.pk, "customer": self.customer.pk,
                "lines": [{"product": self.product.pk, "quantity": "1", "unit_price": "10.00"}],
                "payment": {"method": "cash", "amount": "10.00"},
                "occurred_at": occurred_at.isoformat(),
            },
        }

    def test_pre_suspension_sales_upload_and_later_ones_are_refused(self):
        self.suspend("unpaid since August")
        Subscription.objects.filter(pk=self.subscription.pk).update(
            suspended_at=timezone.now() - timedelta(hours=2)
        )
        self.as_platform(self.staff)
        response = self.client.post(reverse("sync-push"), {
            "batch_uuid": str(uuid.uuid4()), "expected_company": self.company.pk,
            "expected_user": self.staff.pk, "expected_branch": self.branch.pk,
            "operations": [
                self._op(timezone.now() - timedelta(hours=4)),
                self._op(timezone.now() - timedelta(minutes=30)),
            ],
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        before, after = response.data["results"]
        self.assertEqual(before["status"], "applied", before)
        self.assertEqual(after["status"], "error", after)
        self.assertEqual(after["error_field"], "subscription")
        self.assertIn("unpaid since August", after["error"])

    def test_the_upload_endpoint_stays_open_to_a_live_session(self):
        self.assertEqual(self.login(self.staff).status_code, 200)
        self.suspend()
        response = self.client.post(reverse("sync-push"), {
            "batch_uuid": str(uuid.uuid4()), "expected_company": self.company.pk,
            "expected_user": self.staff.pk, "expected_branch": self.branch.pk,
            "operations": [self._op(timezone.now() - timedelta(minutes=5))],
        }, format="json")
        # Not a 403 from the gate: the batch is taken and the item answered.
        self.assertEqual(response.status_code, 201, response.data)


class RegistrationDeleteTests(OwnerControlsBase):
    def _request(self, status, **extra):
        from website.models import RegistrationRequest

        return RegistrationRequest.objects.create(
            company_name=extra.pop("company_name", "Spam Co"), contact_name="X",
            email=f"{uuid.uuid4().hex[:8]}@spam.test", phone="+249900000000", country="SD",
            privacy_version="1", status=status, **extra,
        )

    def test_owner_deletes_a_request_and_it_is_logged(self):
        registration = self._request("submitted")
        url = reverse("platform-registration-request-detail", args=[registration.pk])
        self.as_platform(self.manager)
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.as_platform(self.root)
        self.assertEqual(self.client.delete(url).status_code, 204)
        log = ActivityLog.objects.get(action="delete", entity_type="RegistrationRequest")
        self.assertEqual(log.metadata["company_name"], "Spam Co")
        self.assertEqual(log.metadata["reference"], registration.public_reference)
        self.assertEqual(log.user, self.root)

    def test_an_activated_or_approved_request_is_refused(self):
        provisioned = self._request("provisioned", company=self.company)
        approved = self._request("approved")
        self.as_platform(self.root)
        for registration in (provisioned, approved):
            response = self.client.delete(
                reverse("platform-registration-request-detail", args=[registration.pk])
            )
            self.assertEqual(response.status_code, 400, response.data)
            self.assertEqual(response.data["code"], "registration_in_use")

    def test_bulk_delete_takes_only_rejected_and_withdrawn(self):
        rejected = [self._request("rejected") for _i in range(3)]
        withdrawn = self._request("withdrawn")
        live = self._request("submitted")
        self.as_platform(self.root)
        response = self.client.post(
            reverse("platform-registration-request-bulk-delete"),
            {"ids": [r.pk for r in rejected] + [withdrawn.pk, live.pk]}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["deleted"]), 4)
        self.assertEqual(response.data["skipped"], [live.pk])


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class CompanyDeletionTests(OwnerControlsBase):
    def setUp(self):
        super().setUp()
        call_command(
            "seed_demo", owner=self.owner.email, sales=6, days=5, yes=True, verbosity=0,
            stdout=io.StringIO(),
        )
        self.company.refresh_from_db()
        # Money the platform holds about the company (PROTECTs company + owner).
        SubscriptionPayment.objects.create(
            company=self.company, amount=Decimal("10.00"), currency="SDG", method="cash",
            recorded_by=self.owner,
        )
        self.other = Company.objects.create(name="Other Shop")
        self.other_user = User.objects.create_user(
            email="owner@other.test", password=PASSWORD, company=self.other,
            role=self.owner_role,
        )

    def _delete(self, confirm=None, user=None):
        self.as_platform(user or self.root)
        return self.client.post(
            reverse("platform-company-delete-company", args=[self.company.pk]),
            {"confirm": self.company.slug if confirm is None else confirm, "reason": "closed"},
            format="json",
        )

    def test_typed_confirmation_and_capability_are_required(self):
        self.assertEqual(self._delete(user=self.manager).status_code, 403)
        wrong = self._delete(confirm="nile")
        self.assertEqual(wrong.status_code, 400)
        self.assertEqual(self._delete(confirm="").status_code, 400)
        self.company.refresh_from_db()
        self.assertTrue(self.company.is_active)
        # The name works as well as the slug.
        self.assertEqual(self._delete(confirm="  nile TRADERS ").status_code, 200)

    def test_deletion_closes_the_company_at_once_and_takes_a_backup(self):
        public = self.client.get(f"/s/{self.company.slug}/")
        self.assertEqual(public.status_code, 200)
        self.assertEqual(self.login(self.owner).status_code, 200)
        response = self._delete()
        self.assertEqual(response.status_code, 200, response.data)
        self.company.refresh_from_db()
        self.assertFalse(self.company.is_active)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.CANCELLED)
        deletion = CompanyDeletion.objects.get(company=self.company)
        self.assertEqual(deletion.status, CompanyDeletion.SCHEDULED)
        self.assertAlmostEqual(
            (deletion.purge_after - deletion.requested_at).total_seconds(),
            timedelta(days=30).total_seconds(), delta=60,
        )
        backup = deletion.backup
        self.assertEqual(backup.kind, "deletion")
        self.assertIsNotNone(backup.payload_gz)
        self.assertGreater(backup.keep_until, deletion.purge_after)
        self.assertGreater(deletion.backup_rows, 50)
        self.assertEqual(self.client.get(f"/s/{self.company.slug}/").status_code, 404)
        # The owner's session ends; signing in is refused.
        self.client.force_authenticate(None)
        self.assertEqual(self.login(self.owner).status_code, 403)
        self.assertEqual(self.login(self.owner).data["code"], "company_inactive")
        self.assertTrue(
            ActivityLog.objects.filter(
                action="company_deletion_scheduled", metadata__backup_id=backup.pk
            ).exists()
        )

    def test_a_live_session_ends_when_the_company_is_deleted(self):
        self.assertEqual(self.login(self.owner).status_code, 200)
        from subscriptions.company_deletion import schedule_deletion

        schedule_deletion(self.company, self.root, self.company.slug)
        response = self.client.get(reverse("user-list"))
        self.assertEqual(response.status_code, 401)
        refresh = self.client.post(reverse("auth-refresh"))
        self.assertEqual(refresh.status_code, 401)

    def test_restore_undoes_it(self):
        self._delete()
        response = self.client.post(reverse("platform-company-restore", args=[self.company.pk]))
        self.assertEqual(response.status_code, 200, response.data)
        self.company.refresh_from_db()
        self.assertTrue(self.company.is_active)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.ACTIVE)
        self.assertEqual(
            CompanyDeletion.objects.get(company=self.company).status, CompanyDeletion.RESTORED
        )
        self.assertTrue(ActivityLog.objects.filter(action="company_deletion_cancelled").exists())
        self.assertEqual(self.login(self.owner).status_code, 200)
        # The deletion backup is the platform's, never listed to the tenant.
        listed = self.client.get("/api/ops/backups/")
        self.assertEqual(listed.status_code, 200)
        self.assertNotIn("deletion", [row["kind"] for row in listed.data])

    def test_backup_downloads_as_a_transfer_archive(self):
        self._delete()
        self.as_platform(self.manager)
        refused = self.client.get(reverse("platform-company-backup", args=[self.company.pk]))
        self.assertEqual(refused.status_code, 403)
        self.as_platform(self.root)
        response = self.client.get(reverse("platform-company-backup", args=[self.company.pk]))
        self.assertEqual(response.status_code, 200)
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        payload = json.loads(archive.read("company.json"))
        self.assertEqual(payload["source"]["slug"], self.company.slug)
        self.assertIn("sales.Invoice", payload["objects"])
        self.assertIn("transfer-manifest.json", archive.namelist())

    def _assert_purged(self, deletion):
        from inventory.models import Product
        from ops.models import BackupRecord
        from sales.models import Invoice

        self.assertFalse(Company.objects.filter(pk=deletion.company_ref).exists())
        deletion.refresh_from_db()
        self.assertEqual(deletion.status, CompanyDeletion.PURGED)
        self.assertIsNone(deletion.company_id)
        self.assertEqual(deletion.name, "Nile Traders")
        self.assertFalse(User.objects.filter(email=self.owner.email).exists())
        self.assertFalse(Invoice.objects.filter(company_id=deletion.company_ref).exists())
        self.assertFalse(Product.objects.filter(company_id=deletion.company_ref).exists())
        self.assertFalse(
            SubscriptionPayment.objects.filter(company_id=deletion.company_ref).exists()
        )
        # The backup survives the purge, for the retention window after it.
        backup = BackupRecord.objects.get(pk=deletion.backup_id)
        self.assertIsNone(backup.company_id)
        self.assertGreater(backup.keep_until, timezone.now() + timedelta(days=29))
        # The other company is untouched; the platform's audit trail stays.
        self.assertTrue(User.objects.filter(pk=self.other_user.pk).exists())
        self.assertTrue(
            ActivityLog.objects.filter(action="company_deletion_scheduled").exists()
        )
        self.assertTrue(
            ActivityLog.objects.filter(action="company_purged",
                                       metadata__company_id=deletion.company_ref).exists()
        )
        # The slug stays reserved.
        again = Company.objects.create(name="Nile Traders")
        self.assertNotEqual(again.slug, deletion.slug)

    def test_delete_permanently_now_needs_the_typed_name_again(self):
        self._delete()
        url = reverse("platform-company-purge", args=[self.company.pk])
        self.assertEqual(self.client.post(url, {"confirm": "x"}, format="json").status_code, 400)
        response = self.client.post(url, {"confirm": self.company.slug}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self._assert_purged(CompanyDeletion.objects.get(company_ref=self.company.pk))

    def test_purge_command_waits_thirty_days(self):
        self._delete()
        deletion = CompanyDeletion.objects.get(company=self.company)
        call_command("purge_deleted_companies", stdout=io.StringIO())
        self.assertTrue(Company.objects.filter(pk=self.company.pk).exists())
        CompanyDeletion.objects.filter(pk=deletion.pk).update(
            purge_after=timezone.now() - timedelta(minutes=1)
        )
        out = io.StringIO()
        call_command("run_daily_scans", only="purge_companies", stdout=out)
        self.assertIn("purge_companies: ok", out.getvalue())
        self._assert_purged(deletion)
        self.assertIsNone(deletion.purged_by)
        # The console lists the tombstone.
        self.as_platform(self.root)
        listed = self.client.get(reverse("platform-company-list")).data
        self.assertIn(deletion.company_ref, [row["id"] for row in listed["purged"]])
        self.assertNotIn(deletion.company_ref, [row["id"] for row in listed["companies"]])
