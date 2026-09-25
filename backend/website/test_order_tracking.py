"""Order tracking on the public page and fulfilment stages for staff.

Lookup: by reference, email or exact (Arabic-folded) name; one company's
orders only, the last 90 days, at most 10; phone, email, address and full
name never shown; rate-limited per address; misses all read the same. The
private token link shows one order in full. Stages: a strict path per
delivery mode, reasons required to reject/cancel, a history row per
change, an email per change when the customer left one."""

import tempfile
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role, User
from inventory.models import Product, StockMovement, Warehouse
from org.models import Branch, Company
from sales.models import CompanyBankAccount, Invoice, SalesOrder
from website.models import (
    FeaturedProduct, PublicOrder, PublicOrderEvent, PublicOrderLine, PublicOrderPayment, Website,
)

PHONE = "0912345678"


@override_settings(
    EMAIL_ENABLED=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    VEZANO_CANONICAL_HOST="vezano.app",
)
class TrackingTestBase(TestCase):
    def setUp(self):
        cache.clear()
        self.company = Company.objects.create(name="Bakery", slug="bakery", currency="SDG")
        self.branch = Branch.objects.create(
            company=self.company, name="Main", phone="+249900000001"
        )
        self.north = Branch.objects.create(
            company=self.company, name="North", phone="+249900000002"
        )
        self.warehouse = Warehouse.objects.create(
            company=self.company, branch=self.branch, name="Main WH"
        )
        owner_role = Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS)
        sales_role = Role.objects.create(name="Sales Officer", scope_level=Role.SCOPE_BRANCH)
        self.owner = User.objects.create_user(
            email="owner@bakery.test", password="Owner-passw0rd!x", company=self.company,
            role=owner_role, branch=self.branch, full_name="Owner",
        )
        self.north_clerk = User.objects.create_user(
            email="north@bakery.test", password="Clerk-passw0rd!x", company=self.company,
            role=sales_role, branch=self.north,
        )
        self.site = Website.objects.create(
            company=self.company, business_name="مخبز النيل", is_published=True,
            accept_orders=True, contact_phone="+249900000000",
        )
        self.bread = Product.objects.create(
            company=self.company, sku="BR", name="Bread", sale_price=Decimal("500"),
            is_stock_tracked=True,
        )
        StockMovement.objects.create(
            company=self.company, product=self.bread, warehouse=self.warehouse,
            quantity=Decimal("10"), movement_type="adjustment",
        )
        FeaturedProduct.objects.create(company=self.company, website=self.site, product=self.bread)
        self.other = Company.objects.create(name="Other", slug="other", currency="SDG")
        self.other_site = Website.objects.create(
            company=self.other, business_name="Other", is_published=True, accept_orders=True,
        )
        self.visitor = APIClient()
        self.staff = APIClient()
        self.staff.force_authenticate(self.owner)

    def _order(self, *, name="أحمد علي", email="", mode=PublicOrder.PICKUP, site=None,
               address="", branch=None):
        site = site or self.site
        order = PublicOrder.objects.create(
            company=site.company, website=site, branch=branch or (
                self.branch if site is self.site else None
            ),
            reference="W" + str(PublicOrder.objects.count() + 100000)[-6:].rjust(6, "A"),
            contact_name=name, phone=PHONE, email=email, delivery_mode=mode,
            address=address, currency="SDG", total=Decimal("1000.00"), language="ar",
        )
        PublicOrderLine.objects.create(
            order=order, product=self.bread if site is self.site else None, name="Bread",
            quantity=Decimal("2"), unit_price=Decimal("500"),
        )
        PublicOrderEvent.objects.create(
            company=order.company, order=order, to_status=PublicOrder.NEW,
            created_at=order.created_at,
        )
        return order

    def _search(self, query, slug="bakery", ip="10.0.0.1"):
        return self.client.post(f"/s/{slug}/track/", {"q": query}, REMOTE_ADDR=ip)


class TrackingLookupTests(TrackingTestBase):
    def test_reference_lookup_is_exact_case_insensitive_and_shows_first_name_only(self):
        order = self._order(name="أحمد علي محمد", email="ahmed@example.com",
                            mode=PublicOrder.DELIVERY, address="شارع النيل، الخرطوم")
        html = self._search(f"  {order.reference.lower()} ").content.decode()
        self.assertIn(order.reference, html)
        self.assertIn("أحمد", html)
        self.assertNotIn("أحمد علي محمد", html)
        self.assertNotIn(PHONE, html)
        self.assertNotIn("ahmed@example.com", html)
        self.assertNotIn("شارع النيل", html)
        self.assertIn("Bread", html)
        self.assertIn("+249900000001", html)  # the branch, for questions
        # Not a prefix match.
        self.assertNotIn(order.reference, self._search(order.reference[:-1]).content.decode())

    def test_email_lookup_is_exact_and_masks_the_customer(self):
        order = self._order(name="Amal Hassan", email="Amal@Example.com")
        response = self._search("amal@example.COM")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        html = response.content.decode()
        self.assertIn(order.reference, html)
        self.assertIn("A. H.", html)
        for secret in ("Amal Hassan", "Amal@Example.com", "amal@example.com", PHONE):
            self.assertNotIn(secret, html)
        self.assertNotIn(order.reference, self._search("mal@example.com").content.decode())

    def test_name_lookup_is_exact_after_folding_arabic_and_spaces(self):
        order = self._order(name="  أحمد   عليّ ")
        for query in ("احمد علي", "أحمد عليّ", "  اَحمد   على "):
            html = self._search(query).content.decode()
            self.assertIn(order.reference, html, query)
            self.assertIn("أ. ع.", html)
            self.assertNotIn("أحمد", html)
        for miss in ("احمد", "حمد علي", "احمد علي محمد"):
            self.assertNotIn(order.reference, self._search(miss).content.decode(), miss)

    def test_misses_read_the_same(self):
        self._order(name="Amal", email="amal@example.com")
        bodies = {
            self._search(query).content.decode()
            for query in ("nobody@example.com", "Nobody", "WZZZZZZ")
        }
        self.assertEqual(len(bodies), 1)
        self.assertIn("لم نجد طلبات", bodies.pop())

    def test_other_companies_orders_never_show(self):
        mine = self._order(name="Amal", email="amal@example.com")
        theirs = self._order(name="Amal", email="amal@example.com", site=self.other_site)
        html = self._search("amal@example.com").content.decode()
        self.assertIn(mine.reference, html)
        self.assertNotIn(theirs.reference, html)
        self.assertNotIn(theirs.reference, self._search(theirs.reference).content.decode())
        other_html = self._search("Amal", slug="other").content.decode()
        self.assertIn(theirs.reference, other_html)
        self.assertNotIn(mine.reference, other_html)

    def test_only_the_last_90_days(self):
        recent = self._order(email="a@example.com")
        old = self._order(email="a@example.com")
        PublicOrder.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=91)
        )
        html = self._search("a@example.com").content.decode()
        self.assertIn(recent.reference, html)
        self.assertNotIn(old.reference, html)
        self.assertNotIn(old.reference, self._search(old.reference).content.decode())

    def test_at_most_ten_newest_first(self):
        orders = [self._order(email="many@example.com") for _i in range(12)]
        now = timezone.now()
        for age, order in enumerate(reversed(orders)):
            PublicOrder.objects.filter(pk=order.pk).update(created_at=now - timedelta(hours=age))
        html = self._search("many@example.com").content.decode()
        self.assertEqual(html.count('<article class="card">'), 10)
        self.assertLess(html.index(orders[-1].reference), html.index(orders[-2].reference))
        self.assertNotIn(orders[0].reference, html)
        self.assertNotIn(orders[1].reference, html)

    def test_rate_limited_per_address_politely(self):
        order = self._order(email="a@example.com")
        for _i in range(20):
            self.assertIn(order.reference, self._search(order.reference).content.decode())
        blocked = self._search(order.reference).content.decode()
        self.assertNotIn(order.reference, blocked)
        self.assertIn("بحثت كثيراً", blocked)
        # Another address is not affected.
        elsewhere = self._search(order.reference, ip="10.0.0.2").content.decode()
        self.assertIn(order.reference, elsewhere)

    def test_page_renders_rtl_with_the_form_and_the_site_links_to_it(self):
        page = self.client.get("/s/bakery/track/")
        self.assertEqual(page.status_code, 200)
        html = page.content.decode()
        self.assertIn('dir="rtl"', html)
        self.assertIn("Tajawal", html)
        self.assertIn('name="q"', html)
        self.assertIn("noindex", page["X-Robots-Tag"])
        self.assertIn('href="/s/bakery/track/"', self.client.get("/s/bakery/").content.decode())
        self.assertEqual(self.client.get("/s/nope/track/").status_code, 404)


class TrackingTokenTests(TrackingTestBase):
    def test_token_link_shows_the_one_order_with_address_hint_only(self):
        order = self._order(name="Amal Hassan", email="amal@example.com",
                            mode=PublicOrder.DELIVERY, address="Nile Street 12, Khartoum 2")
        self.assertTrue(order.tracking_token and len(order.tracking_token) >= 32)
        response = self.client.get(f"/s/bakery/track/{order.tracking_token}/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(order.reference, html)
        self.assertIn("Amal", html)
        self.assertIn("Nile Street 12", html)
        for secret in ("Amal Hassan", "Khartoum 2", "amal@example.com", PHONE):
            self.assertNotIn(secret, html)
        self.assertNotIn("/pay/?ref=", html)  # no bank account shown to customers
        # Wrong token, or the right token on another company's page: 404.
        self.assertEqual(self.client.get("/s/bakery/track/not-a-token/").status_code, 404)
        self.assertEqual(
            self.client.get(f"/s/other/track/{order.tracking_token}/").status_code, 404
        )

    def test_thank_you_and_first_email_carry_the_tracking_link(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.visitor.post(
                "/api/public/site/bakery/orders/",
                {"contact_name": "Amal Hassan", "phone": PHONE, "email": "amal@example.com",
                 "lines": [{"product": self.bread.pk, "quantity": 1}]},
                format="json",
            )
        self.assertEqual(response.status_code, 201, response.data)
        order = PublicOrder.objects.get(reference=response.data["reference"])
        link = f"https://vezano.app/s/bakery/track/{order.tracking_token}/"
        self.assertEqual(response.data["track_url"], link)
        self.assertEqual(response.data["contact_name"], "Amal")  # first name only
        customer_mail = next(m for m in mail.outbox if m.to == ["amal@example.com"])
        self.assertIn(link, customer_mail.body)
        self.assertEqual(
            list(order.events.values_list("from_status", "to_status")), [("", "new")]
        )


class TrackingTokenPayTests(TrackingTestBase):
    def setUp(self):
        super().setUp()
        CompanyBankAccount.objects.create(
            company=self.company, bank_name="Bank of Khartoum", account_name="Bakery",
            account_number="123456", show_to_customers=True,
        )

    def test_pay_link_only_while_payable(self):
        order = self._order()
        html = self.client.get(f"/s/bakery/track/{order.tracking_token}/").content.decode()
        self.assertIn(f"/s/bakery/pay/?ref={order.reference}", html)
        PublicOrder.objects.filter(pk=order.pk).update(status=PublicOrder.COMPLETED)
        html = self.client.get(f"/s/bakery/track/{order.tracking_token}/").content.decode()
        self.assertNotIn("/pay/?ref=", html)


class StageTests(TrackingTestBase):
    def _stage(self, order, status, note="", client=None):
        with self.captureOnCommitCallbacks(execute=True):
            return (client or self.staff).post(
                f"/api/web-orders/{order.pk}/stage/", {"status": status, "note": note},
                format="json",
            )

    def test_pickup_path_and_history(self):
        order = self._order(email="amal@example.com")
        self.assertEqual(self._stage(order, "preparing").status_code, 400)  # not confirmed yet
        confirmed = self._stage(order, "confirmed", "ok")
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertEqual(confirmed.data["next_steps"], ["preparing", "cancelled"])
        self.assertEqual(self._stage(order, "preparing").data["next_steps"],
                         ["ready", "cancelled"])
        refused = self._stage(order, "delivering")
        self.assertEqual(refused.status_code, 400)
        self.assertIn("status", refused.data)
        self.assertEqual(self._stage(order, "ready").status_code, 200)
        done = self._stage(order, "completed")
        self.assertEqual(done.data["status"], "completed")
        self.assertEqual(done.data["next_steps"], [])
        self.assertEqual(self._stage(order, "cancelled", "late").status_code, 400)
        events = list(order.events.order_by("created_at", "id"))
        self.assertEqual(
            [(e.from_status, e.to_status) for e in events],
            [("", "new"), ("new", "confirmed"), ("confirmed", "preparing"),
             ("preparing", "ready"), ("ready", "completed")],
        )
        self.assertTrue(all(e.actor == self.owner for e in events[1:]))
        self.assertEqual([e["to_status"] for e in done.data["events"]][-1], "completed")
        # The customer's page shows the whole path.
        html = self.client.get(f"/s/bakery/track/{order.tracking_token}/").content.decode()
        for label in ("تم التأكيد", "قيد التجهيز", "جاهز للاستلام", "تم الاستلام"):
            self.assertIn(label, html)

    def test_delivery_path_goes_out_for_delivery(self):
        order = self._order(mode=PublicOrder.DELIVERY, address="Nile St")
        self._stage(order, "confirmed")
        self._stage(order, "preparing")
        self.assertEqual(self._stage(order, "ready").status_code, 400)
        self.assertEqual(self._stage(order, "delivering").status_code, 200)
        self.assertEqual(self._stage(order, "completed").status_code, 200)
        html = self.client.get(f"/s/bakery/track/{order.tracking_token}/").content.decode()
        self.assertIn("خرج للتوصيل", html)
        self.assertIn("تم التوصيل", html)

    def test_reject_and_cancel_need_a_reason_the_customer_sees(self):
        order = self._order(email="amal@example.com")
        self.assertEqual(self._stage(order, "rejected").status_code, 400)
        self.assertEqual(
            self.staff.post(f"/api/web-orders/{order.pk}/reject/", {"note": " "}).status_code,
            400,
        )
        self.assertEqual(self._stage(order, "rejected", "نفدت الكمية").status_code, 200)
        html = self.client.get(f"/s/bakery/track/{order.tracking_token}/").content.decode()
        self.assertIn("نفدت الكمية", html)
        self.assertIn("مرفوض", html)

        other = self._order()
        self._stage(other, "confirmed")
        self.assertEqual(self._stage(other, "cancelled").status_code, 400)
        cancelled = self._stage(other, "cancelled", "العميل اعتذر")
        self.assertEqual(cancelled.data["status"], "cancelled")
        # The sales order the till would have finished is cancelled too.
        self.assertEqual(
            SalesOrder.objects.get(pk=cancelled.data["sales_order"]).status,
            SalesOrder.CANCELLED,
        )
        event = other.events.get(to_status="cancelled")
        self.assertEqual((event.from_status, event.note), ("confirmed", "العميل اعتذر"))

    def test_customer_emailed_on_each_change_only_with_an_email(self):
        order = self._order(email="amal@example.com")
        mail.outbox.clear()
        self._stage(order, "confirmed")
        self._stage(order, "preparing")
        to_customer = [m for m in mail.outbox if m.to == ["amal@example.com"]]
        self.assertEqual(len(to_customer), 2)
        self.assertIn(order.tracking_token, to_customer[-1].body)
        self.assertIn("تجهيز", to_customer[-1].body)
        silent = self._order(email="")
        mail.outbox.clear()
        self._stage(silent, "confirmed")
        self._stage(silent, "preparing")
        self.assertEqual(len(mail.outbox), 0)

    def test_email_failure_never_blocks_the_change(self):
        order = self._order(email="amal@example.com")
        with mock.patch("core.mailer.send_bilingual", side_effect=RuntimeError("smtp down")):
            response = self._stage(order, "confirmed")
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, PublicOrder.CONFIRMED)

    def test_branch_scoping_and_write_permission_apply(self):
        order = self._order()  # Main branch
        self.assertEqual(self._stage(order, "confirmed", client=self._client(self.north_clerk))
                         .status_code, 404)

    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_confirmed_payment_still_invoices_and_moves_stock_and_later_stages_do_not(self):
        bank = CompanyBankAccount.objects.create(
            company=self.company, bank_name="BoK", account_name="Bakery",
            account_number="123456", show_to_customers=True,
        )
        order = self._order()
        claim = PublicOrderPayment.objects.create(
            order=order, company=self.company, bank_account=bank, sender_bank_name="Faisal",
            reference_last4="4321", amount=Decimal("1000.00"),
        )
        response = self.staff.post(
            f"/api/web-orders/{order.pk}/payments/{claim.pk}/confirm/", {}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        claim.refresh_from_db()
        self.assertTrue(Invoice.objects.filter(pk=claim.invoice_id).exists())
        self.assertEqual(self.bread.on_hand(), Decimal("8"))
        movements = StockMovement.objects.count()
        invoices = Invoice.objects.count()
        for stage in ("preparing", "ready", "completed"):
            self.assertEqual(self._stage(order, stage).status_code, 200)
        self.assertEqual(StockMovement.objects.count(), movements)
        self.assertEqual(Invoice.objects.count(), invoices)
        self.assertEqual(self.bread.on_hand(), Decimal("8"))
        html = self.client.get(f"/s/bakery/track/{order.tracking_token}/").content.decode()
        self.assertIn("تم التحقق من التحويل", html)

    def test_payable_while_in_progress(self):
        CompanyBankAccount.objects.create(
            company=self.company, bank_name="BoK", account_name="Bakery",
            account_number="123456", show_to_customers=True,
        )
        order = self._order()
        self._stage(order, "confirmed")
        self._stage(order, "preparing")
        page = self.visitor.get(f"/api/public/site/bakery/orders/{order.reference}/").data
        self.assertTrue(page["can_pay"])

    def test_list_filters_several_stages_and_badge_still_counts_new(self):
        from website.attention import new_public_orders

        since = timezone.now() - timedelta(minutes=1)
        fresh = self._order()
        moving = self._order()
        self._stage(moving, "confirmed")
        self._stage(moving, "preparing")
        listing = self.staff.get("/api/web-orders/?status=confirmed,preparing,ready,delivering")
        rows = listing.data.get("results", listing.data)
        self.assertEqual([r["reference"] for r in rows], [moving.reference])
        self.assertEqual(new_public_orders(self.owner, since), 1)
        self.assertEqual(fresh.status, PublicOrder.NEW)


class TrackingTransferTests(TrackingTestBase):
    def test_orders_and_their_history_move_with_the_company(self):
        from ops.transfer import import_company, read_export, verify_transfer, write_export

        from website.tracking import change_stage

        # The other company: no stock or sales rows that protect its deletion.
        order = self._order(email="amal@example.com", site=self.other_site)
        change_stage(order, None, PublicOrder.CANCELLED, "moved away")
        token = order.tracking_token
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "company.zip"
            write_export(self.other, path, include_media=False)
            payload, archive = read_export(path)
            self.other.delete()
            target = Company.objects.create(name="Imported", slug="imported")
            try:
                import_company(payload, target, archive=archive)
            finally:
                archive.close()
        self.assertEqual(verify_transfer(payload, target), [])
        moved = PublicOrder.objects.get(company=target)
        self.assertEqual(moved.tracking_token, token)
        self.assertEqual(moved.status, PublicOrder.CANCELLED)
        self.assertEqual(
            list(moved.events.values_list("to_status", "note")),
            [("new", ""), ("cancelled", "moved away")],
        )
        self.assertTrue(all(e.company_id == target.pk for e in moved.events.all()))
