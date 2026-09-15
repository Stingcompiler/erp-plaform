from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from accounts.models import Role, User
from core import attention
from core.models import AttentionSeen
from inventory.models import Product, StockMovement, Warehouse
from org.models import Branch, Company
from returns.models import SalesReturn, SalesReturnLine
from sales.models import Customer, Invoice, InvoiceLine
from website.models import RegistrationRequest


def role(name, scope):
    return Role.objects.get_or_create(name=name, defaults={"scope_level": scope})[0]


class AttentionBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.company = Company.objects.create(name="Alpha")
        self.khartoum = Branch.objects.create(company=self.company, name="Khartoum", code="KRT")
        self.omdurman = Branch.objects.create(company=self.company, name="Omdurman", code="OMD")
        self.wh_k = Warehouse.objects.create(company=self.company, branch=self.khartoum, name="K")
        self.wh_o = Warehouse.objects.create(company=self.company, branch=self.omdurman, name="O")
        self.owner = User.objects.create_user(
            email="owner@alpha.test", password="passw0rd123", company=self.company,
            branch=self.khartoum, role=role("Business Owner", Role.SCOPE_BUSINESS),
        )
        self.cashier_omd = User.objects.create_user(
            email="till@alpha.test", password="passw0rd123", company=self.company,
            branch=self.omdurman, role=role("Sales Officer", Role.SCOPE_BRANCH),
        )
        self.customer = Customer.objects.create(company=self.company, name="Cust")
        self.product = Product.objects.create(
            company=self.company, sku="P1", name="Thing",
            sale_price=Decimal("10"), cost_price=Decimal("6"),
        )

    def overdue_invoice(self, branch, warehouse, days_overdue=1):
        inv = Invoice.objects.create(
            company=self.company, customer=self.customer, branch=branch, warehouse=warehouse,
            number=Invoice.objects.filter(company=self.company).count() + 1,
            total=Decimal("100"), subtotal=Decimal("100"),
            due_date=timezone.localdate() - timedelta(days=days_overdue),
        )
        InvoiceLine.objects.create(
            invoice=inv, product=self.product, quantity=Decimal("1"),
            unit_price=Decimal("100"), line_subtotal=Decimal("100"), line_total=Decimal("100"),
        )
        return inv

    def client_as(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client


class SourceScopingTests(AttentionBase):
    def test_owner_sees_company_wide_and_cashier_only_own_branch(self):
        self.overdue_invoice(self.khartoum, self.wh_k)
        self.overdue_invoice(self.omdurman, self.wh_o)
        self.assertEqual(attention.counts_for(self.owner, use_cache=False)["counts"]["sales"], 2)
        self.assertEqual(
            attention.counts_for(self.cashier_omd, use_cache=False)["counts"]["sales"], 1
        )

    def test_other_company_is_invisible(self):
        other = Company.objects.create(name="Beta")
        other_branch = Branch.objects.create(company=other, name="B", code="B")
        other_wh = Warehouse.objects.create(company=other, branch=other_branch, name="B")
        other_customer = Customer.objects.create(company=other, name="X")
        Invoice.objects.create(
            company=other, customer=other_customer, branch=other_branch, warehouse=other_wh,
            number=1, total=Decimal("50"), subtotal=Decimal("50"),
            due_date=timezone.localdate() - timedelta(days=3),
        )
        self.assertEqual(attention.counts_for(self.owner, use_cache=False)["counts"], {})

    def test_module_the_role_cannot_read_is_never_counted(self):
        # A cashier has no HR access, so a pending leave request is not their badge.
        from hr.models import Employee, LeaveRequest

        emp = Employee.objects.create(
            company=self.company, branch=self.omdurman, full_name="E", employee_code="E1"
        )
        LeaveRequest.objects.create(
            company=self.company, employee=emp, start_date=timezone.localdate(),
            end_date=timezone.localdate(), status=LeaveRequest.PENDING,
        )
        counts = attention.counts_for(self.cashier_omd, use_cache=False)["counts"]
        self.assertNotIn("hr", counts)
        self.assertEqual(attention.counts_for(self.owner, use_cache=False)["counts"]["hr"], 1)

    def test_platform_keys_only_for_platform_admins_and_vice_versa(self):
        RegistrationRequest.objects.create(
            company_name="New Co", contact_name="N", email="n@new.test", phone="1",
            country="SD", privacy_version="2026-09", status=RegistrationRequest.SUBMITTED,
        )
        admin = User.objects.create_superuser("root@vezano.test", "passw0rd123")
        admin_counts = attention.counts_for(admin, use_cache=False)["counts"]
        self.assertEqual(admin_counts.get("platform-registrations"), 1)
        self.assertNotIn("sales", admin_counts)
        owner_counts = attention.counts_for(self.owner, use_cache=False)["counts"]
        self.assertNotIn("platform-registrations", owner_counts)

    def test_tones_travel_with_counts(self):
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh_k,
            movement_type="sale_out", quantity=Decimal("-3"),
        )
        payload = attention.counts_for(self.owner, use_cache=False)
        self.assertEqual(payload["counts"]["stock"], 1)
        self.assertEqual(payload["tones"]["stock"], attention.TONE_DANGER)


class SeenTests(AttentionBase):
    def test_marking_seen_clears_and_new_items_bring_it_back(self):
        self.overdue_invoice(self.khartoum, self.wh_k, days_overdue=2)
        self.assertEqual(attention.counts_for(self.owner, use_cache=False)["counts"]["sales"], 1)
        attention.mark_seen(self.owner, "sales")
        self.assertEqual(attention.counts_for(self.owner, use_cache=False)["counts"], {})
        # An invoice "appears" the day after its due date. The user last looked
        # a day ago: the first invoice (overdue since two days ago) is old news,
        # the one that became overdue today is new.
        AttentionSeen.objects.filter(user=self.owner, key="sales").update(
            seen_at=timezone.now() - timedelta(days=1)
        )
        self.overdue_invoice(self.khartoum, self.wh_k, days_overdue=1)
        self.assertEqual(attention.counts_for(self.owner, use_cache=False)["counts"]["sales"], 1)

    def test_replayed_offline_sale_with_old_business_time_still_flags_negative_stock(self):
        # The manager looked an hour ago. A sale taken offline three hours ago
        # is replayed now and drives the product negative: its stock movement
        # carries the (old) business time, but the invoice arrived just now.
        attention.mark_seen(self.owner, "stock")
        AttentionSeen.objects.filter(user=self.owner, key="stock").update(
            seen_at=timezone.now() - timedelta(hours=1)
        )
        sold_at = timezone.now() - timedelta(hours=3)
        inv = Invoice.objects.create(
            company=self.company, branch=self.khartoum, warehouse=self.wh_k, number=77,
            total=Decimal("10"), subtotal=Decimal("10"), issued_at=sold_at,
        )
        StockMovement.objects.create(
            company=self.company, product=self.product, warehouse=self.wh_k,
            movement_type=StockMovement.SALE_OUT, quantity=Decimal("-1"),
            reference_type="Invoice", reference_id=str(inv.id), created_at=sold_at,
        )
        StockMovement.objects.filter(reference_id=str(inv.id)).update(created_at=sold_at)
        self.assertEqual(attention.counts_for(self.owner, use_cache=False)["counts"]["stock"], 1)
        # Seen after it arrived: gone, even though the ledger stays negative.
        attention.mark_seen(self.owner, "stock")
        self.assertNotIn("stock", attention.counts_for(self.owner, use_cache=False)["counts"])

    def test_seen_is_per_user(self):
        self.overdue_invoice(self.omdurman, self.wh_o)
        attention.mark_seen(self.owner, "sales")
        self.assertEqual(
            attention.counts_for(self.cashier_omd, use_cache=False)["counts"]["sales"], 1
        )

    def test_unknown_key_is_ignored(self):
        self.assertFalse(attention.mark_seen(self.owner, "nope"))
        self.assertFalse(AttentionSeen.objects.filter(user=self.owner).exists())


class EndpointTests(AttentionBase):
    def test_get_and_seen_round_trip(self):
        invoice = self.overdue_invoice(self.khartoum, self.wh_k)
        SalesReturn.objects.create(company=self.company, invoice=invoice)
        sr = SalesReturn.objects.get()
        line = sr.invoice.lines.first()
        SalesReturnLine.objects.create(
            sales_return=sr, invoice_line=line, product=self.product, quantity=Decimal("1"),
        )
        client = self.client_as(self.owner)
        first = client.get(reverse("attention"))
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["counts"]["returns"], 1)
        self.assertEqual(first.data["tones"]["returns"], "info")
        self.assertGreaterEqual(first.data["total"], 1)

        seen = client.post(reverse("attention-seen"), {"key": "returns"}, format="json")
        self.assertEqual(seen.status_code, 200)
        self.assertTrue(seen.data["known"])
        after = client.get(reverse("attention"))
        self.assertNotIn("returns", after.data["counts"])

    def test_counts_are_cached_briefly_and_invalidated_on_seen(self):
        self.overdue_invoice(self.khartoum, self.wh_k)
        client = self.client_as(self.owner)
        self.assertEqual(client.get(reverse("attention")).data["counts"]["sales"], 1)
        Invoice.objects.filter(company=self.company).update(is_void=True)
        # Still cached.
        self.assertEqual(client.get(reverse("attention")).data["counts"].get("sales"), 1)
        client.post(reverse("attention-seen"), {"key": "hr"}, format="json")
        self.assertNotIn("sales", client.get(reverse("attention")).data["counts"])

    def test_seen_requires_key(self):
        client = self.client_as(self.owner)
        self.assertEqual(client.post(reverse("attention-seen"), {}, format="json").status_code, 400)

    def test_anonymous_is_rejected(self):
        self.assertEqual(APIClient().get(reverse("attention")).status_code, 401)


class StateSourceTests(AttentionBase):
    def test_subscription_badge_stays_after_seen_while_in_grace(self):
        from unittest import mock

        from core.entitlements import EntitlementDecision

        grace = EntitlementDecision("saas", "grace", frozenset({"*"}), {}, True)
        with mock.patch("core.entitlements.resolve_entitlements", return_value=grace), \
                self.settings(VEZANO_DEPLOYMENT_MODE="saas", SUBSCRIPTION_POLICY="enforce"):
            owner = attention.counts_for(self.owner, use_cache=False)["counts"]
            self.assertEqual(owner["subscription"], 1)
            attention.mark_seen(self.owner, "subscription")
            owner = attention.counts_for(self.owner, use_cache=False)["counts"]
            self.assertEqual(owner["subscription"], 1)
            # Not the cashier's concern: the page is owner-only.
            cashier = attention.counts_for(self.cashier_omd, use_cache=False)["counts"]
            self.assertNotIn("subscription", cashier)

    def test_crm_follow_up_due_today_counts_once(self):
        from crm.models import FollowUp, Lead

        lead = Lead.objects.create(company=self.company, name="Lead")
        FollowUp.objects.create(
            company=self.company, lead=lead, due_date=timezone.localdate(), summary="call"
        )
        self.assertEqual(attention.counts_for(self.owner, use_cache=False)["counts"]["crm"], 1)
        attention.mark_seen(self.owner, "crm")
        self.assertNotIn("crm", attention.counts_for(self.owner, use_cache=False)["counts"])
