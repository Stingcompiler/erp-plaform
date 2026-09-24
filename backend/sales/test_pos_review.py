"""POS review 2026-09-24: price floor and discount limit, branch of an owner's
sale, device clock on the online path, the receipt's local date, Arabic
search, cost hidden from cashiers, split tenders, negative discounts."""
import uuid
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Role, User
from core.arabic import fold_arabic
from core.models import ActivityLog
from inventory.models import Product, ProductPack, Warehouse
from org.models import Branch, Company
from sales.models import CompanyBankAccount, Customer, Invoice, Payment


class POSBase(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Shop")  # Africa/Khartoum
        self.branch = Branch.objects.create(company=self.company, name="Main")
        self.warehouse = Warehouse.objects.create(
            company=self.company, branch=self.branch, name="Store"
        )
        self.rice = Product.objects.create(
            company=self.company, sku="RICE", name="أرز بسمتي",
            cost_price=Decimal("80"), sale_price=Decimal("100"),
        )
        self.cashier = User.objects.create_user(
            email="till@shop.test", password="passw0rd12345", company=self.company,
            branch=self.branch,
            role=Role.objects.create(name="Sales Officer", scope_level=Role.SCOPE_BRANCH),
        )
        self.owner = User.objects.create_user(
            email="owner@shop.test", password="passw0rd12345", company=self.company,
            role=Role.objects.create(name="Business Owner", scope_level=Role.SCOPE_BUSINESS),
        )
        self.customer = Customer.objects.create(company=self.company, name="Ali")
        self.client.force_authenticate(self.cashier)

    def sell(self, lines, **extra):
        body = {"warehouse": self.warehouse.id, "lines": lines, **extra}
        return self.client.post(reverse("pos-checkout"), body, format="json")

    def push(self, payload):
        return self.client.post(reverse("sync-push"), {
            "batch_uuid": str(uuid.uuid4()),
            "expected_company": self.company.pk, "expected_user": self.cashier.pk,
            "operations": [{
                "op_type": "pos_checkout", "client_uuid": str(uuid.uuid4()),
                "payload": {"warehouse": self.warehouse.id, **payload},
            }],
        }, format="json")


class PriceRuleTests(POSBase):
    def test_cashier_cannot_sell_below_cost(self):
        r = self.sell([{"product": self.rice.id, "quantity": "10", "unit_price": "1.00"}],
                      payment={"method": "cash", "amount": "10.00"})
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn("RICE", str(r.data["lines"]))
        self.assertFalse(Invoice.objects.exists())

    def test_price_between_cost_and_list_within_the_limit_is_allowed(self):
        r = self.sell([{"product": self.rice.id, "quantity": "1", "unit_price": "91.00"}],
                      payment={"method": "cash", "amount": "91.00"})
        self.assertEqual(r.status_code, 201, r.data)

    def test_a_typed_price_beyond_the_limit_counts_as_a_discount(self):
        # Above cost (80) but 15% under the list price (100); the limit is 10%.
        r = self.sell([{"product": self.rice.id, "quantity": "2", "unit_price": "85.00"}],
                      payment={"method": "cash", "amount": "170.00"})
        self.assertEqual(r.status_code, 400, r.data)
        self.assertEqual(r.data["code"], "price_rule")
        self.assertIn("15.00", str(r.data["lines"]))
        self.assertFalse(Invoice.objects.exists())

    def test_a_typed_price_and_a_discount_add_up(self):
        # 95 is 5% off the list, 6% off that makes 10.7% in all.
        r = self.sell([{"product": self.rice.id, "quantity": "1", "unit_price": "95.00",
                        "discount_percent": "6"}],
                      payment={"method": "cash", "amount": "89.30"})
        self.assertEqual(r.status_code, 400, r.data)
        ok = self.sell([{"product": self.rice.id, "quantity": "1", "unit_price": "95.00",
                         "discount_percent": "5"}],
                       payment={"method": "cash", "amount": "90.25"})
        self.assertEqual(ok.status_code, 201, ok.data)

    def test_a_marked_up_price_leaves_room_for_a_discount(self):
        # 120 less 20% is 96: 4% under the list price.
        r = self.sell([{"product": self.rice.id, "quantity": "1", "unit_price": "120.00",
                        "discount_percent": "20"}],
                      payment={"method": "cash", "amount": "96.00"})
        self.assertEqual(r.status_code, 201, r.data)

    def test_a_pack_is_measured_against_the_pack_price(self):
        pack = ProductPack.objects.create(
            company=self.company, product=self.rice, name="Carton",
            quantity=Decimal("12"), sale_price=Decimal("1100"),
        )
        r = self.sell([{"product": self.rice.id, "pack": pack.id, "quantity": "1",
                        "unit_price": "980.00"}])  # above 960 cost, 10.9% off
        self.assertEqual(r.status_code, 400, r.data)
        ok = self.sell([{"product": self.rice.id, "pack": pack.id, "quantity": "1",
                         "unit_price": "990.00"}],
                       payment={"method": "cash", "amount": "990.00"})
        self.assertEqual(ok.status_code, 201, ok.data)

    def test_an_order_is_invoiced_at_its_agreed_price(self):
        from sales.models import SalesOrder, SalesOrderLine

        order = SalesOrder.objects.create(
            company=self.company, customer=self.customer, branch=self.branch,
            status=SalesOrder.CONFIRMED, subtotal=Decimal("85"), total=Decimal("85"),
        )
        SalesOrderLine.objects.create(
            sales_order=order, product=self.rice, quantity=Decimal("1"),
            unit_price=Decimal("85"), line_total=Decimal("85"),
        )
        r = self.sell([{"product": self.rice.id, "quantity": "1", "unit_price": "85.00"}],
                      customer=self.customer.id, source_order=order.id,
                      payment={"method": "cash", "amount": "85.00"})
        self.assertEqual(r.status_code, 201, r.data)

    def test_a_typed_price_is_kept_offline_and_flagged_with_list_and_sold(self):
        r = self.push({"lines": [{"product": self.rice.id, "quantity": "1",
                                  "unit_price": "85.00"}],
                       "payment": {"method": "cash", "amount": "85.00"}})
        self.assertEqual(r.data["summary"]["applied"], 1, r.data)
        row = ActivityLog.objects.get(action="pos_price_unapproved")
        breach = row.metadata["breaches"][0]
        self.assertEqual(breach["rule"], "discount")
        self.assertEqual(Decimal(breach["list"]), Decimal("100"))
        self.assertEqual(Decimal(breach["sold"]), Decimal("85"))
        self.assertEqual(Decimal(breach["percent"]), Decimal("15"))

    def test_an_approver_may_type_a_lower_price(self):
        self.client.force_authenticate(self.owner)
        r = self.sell([{"product": self.rice.id, "quantity": "1", "unit_price": "85.00"}],
                      payment={"method": "cash", "amount": "85.00"})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(ActivityLog.objects.filter(action="pos_price_override").exists())

    def test_list_price_under_a_risen_cost_is_allowed(self):
        Product.objects.filter(pk=self.rice.pk).update(cost_price=Decimal("120"))
        r = self.sell([{"product": self.rice.id, "quantity": "1"}],
                      payment={"method": "cash", "amount": "100.00"})
        self.assertEqual(r.status_code, 201, r.data)

    def test_pack_below_pack_cost_is_refused(self):
        pack = ProductPack.objects.create(
            company=self.company, product=self.rice, name="Carton",
            quantity=Decimal("12"), sale_price=Decimal("1100"),
        )
        r = self.sell([{"product": self.rice.id, "pack": pack.id, "quantity": "1",
                        "unit_price": "900.00"}])  # 12 x 80 = 960 cost
        self.assertEqual(r.status_code, 400, r.data)
        ok = self.sell([{"product": self.rice.id, "pack": pack.id, "quantity": "1",
                         "unit_price": "1000.00"}],
                       payment={"method": "cash", "amount": "1000.00"})
        self.assertEqual(ok.status_code, 201, ok.data)

    def test_line_discount_above_the_limit_is_refused(self):
        r = self.sell([{"product": self.rice.id, "quantity": "5", "discount_percent": "100"}])
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn("10.00", str(r.data["lines"]))

    def test_discount_within_the_limit_is_allowed(self):
        r = self.sell([{"product": self.rice.id, "quantity": "1", "discount_percent": "10"}],
                      payment={"method": "cash", "amount": "90.00"})
        self.assertEqual(r.status_code, 201, r.data)

    def test_ticket_discount_counts_toward_the_limit(self):
        r = self.sell([{"product": self.rice.id, "quantity": "1", "discount_percent": "5"}],
                      discount_amount="10.00", payment={"method": "cash", "amount": "85.00"})
        self.assertEqual(r.status_code, 400, r.data)

    def test_limit_is_a_company_setting(self):
        Company.objects.filter(pk=self.company.pk).update(max_discount_percent=None)
        r = self.sell([{"product": self.rice.id, "quantity": "1", "discount_percent": "50"}],
                      payment={"method": "cash", "amount": "50.00"})
        self.assertEqual(r.status_code, 201, r.data)
        Company.objects.filter(pk=self.company.pk).update(max_discount_percent=Decimal("0"))
        r = self.sell([{"product": self.rice.id, "quantity": "1", "discount_amount": "1.00"}],
                      payment={"method": "cash", "amount": "99.00"})
        self.assertEqual(r.status_code, 400, r.data)

    def test_approver_override_is_audited(self):
        self.client.force_authenticate(self.owner)
        r = self.sell([{"product": self.rice.id, "quantity": "1", "unit_price": "50.00",
                        "discount_percent": "50"}],
                      payment={"method": "cash", "amount": "25.00"})
        self.assertEqual(r.status_code, 201, r.data)
        row = ActivityLog.objects.get(action="pos_price_override")
        self.assertEqual(row.entity_id, str(r.data["id"]))
        self.assertEqual({b["rule"] for b in row.metadata["breaches"]},
                         {"below_cost", "discount"})

    def test_offline_replay_is_kept_and_flagged_for_review(self):
        r = self.push({"lines": [{"product": self.rice.id, "quantity": "1",
                                  "unit_price": "10.00"}],
                       "payment": {"method": "cash", "amount": "10.00"}})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["summary"]["applied"], 1, r.data)
        invoice = Invoice.objects.get()
        self.assertEqual(invoice.total, Decimal("10.00"))
        row = ActivityLog.objects.get(action="pos_price_unapproved")
        self.assertTrue(row.metadata["needs_review"])
        self.assertEqual(row.entity_id, str(invoice.pk))

    def test_negative_discounts_are_refused(self):
        r = self.sell([{"product": self.rice.id, "quantity": "1", "discount_percent": "-5"}])
        self.assertEqual(r.status_code, 400, r.data)
        r = self.sell([{"product": self.rice.id, "quantity": "1"}], discount_amount="-5.00")
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn("discount_amount", r.data)


class DiscountSettingTests(POSBase):
    def test_owner_sets_the_limit_and_the_till_reads_it(self):
        self.client.force_authenticate(self.owner)
        url = reverse("company-profile")
        self.assertEqual(Decimal(self.client.get(url).data["max_discount_percent"]),
                         Decimal("10"))
        r = self.client.patch(url, {"max_discount_percent": "15"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.company.refresh_from_db()
        self.assertEqual(self.company.max_discount_percent, Decimal("15"))
        self.assertEqual(self.client.patch(url, {"max_discount_percent": "150"},
                                           format="json").status_code, 400)
        r = self.client.patch(url, {"max_discount_percent": ""}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.company.refresh_from_db()
        self.assertIsNone(self.company.max_discount_percent)
        me = self.client.get(reverse("auth-me")).data
        self.assertIsNone(me["max_discount_percent"])

    def test_cashier_cannot_change_the_limit(self):
        manager = User.objects.create_user(
            email="bm@shop.test", password="passw0rd12345", company=self.company,
            branch=self.branch,
            role=Role.objects.create(name="Branch Manager", scope_level=Role.SCOPE_BRANCH),
        )
        self.client.force_authenticate(manager)
        r = self.client.patch(reverse("company-profile"), {"max_discount_percent": "90"},
                              format="json")
        self.assertIn(r.status_code, (403,), r.data)


class BranchTests(POSBase):
    def test_owner_sale_takes_the_warehouse_branch(self):
        self.client.force_authenticate(self.owner)
        r = self.sell([{"product": self.rice.id, "quantity": "1"}],
                      payment={"method": "cash", "amount": "100.00"})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(Invoice.objects.get(pk=r.data["id"]).branch_id, self.branch.id)


class DeviceClockTests(POSBase):
    def _sell_at(self, device_now):
        return self.sell([{"product": self.rice.id, "quantity": "1"}],
                         payment={"method": "cash", "amount": "100.00"},
                         occurred_at=device_now.isoformat(), sent_at=device_now.isoformat())

    def test_slow_device_clock_is_corrected(self):
        r = self._sell_at(timezone.now() - timedelta(hours=26))
        self.assertEqual(r.status_code, 201, r.data)
        issued = Invoice.objects.get(pk=r.data["id"]).issued_at
        self.assertLess(abs((timezone.now() - issued).total_seconds()), 60)

    def test_fast_device_clock_is_not_refused(self):
        r = self._sell_at(timezone.now() + timedelta(minutes=20))
        self.assertEqual(r.status_code, 201, r.data)
        issued = Invoice.objects.get(pk=r.data["id"]).issued_at
        self.assertLess(abs((timezone.now() - issued).total_seconds()), 60)


class ReceiptDateTests(POSBase):
    def test_printed_date_is_the_shop_day(self):
        khartoum = ZoneInfo("Africa/Khartoum")
        today = timezone.localdate(timezone.now(), khartoum)
        moment = timezone.datetime(today.year, today.month, today.day, 0, 30, tzinfo=khartoum)
        if moment > timezone.now():
            moment -= timedelta(days=1)
        r = self.sell([{"product": self.rice.id, "quantity": "1"}],
                      payment={"method": "cash", "amount": "100.00"},
                      occurred_at=moment.isoformat())
        self.assertEqual(r.status_code, 201, r.data)
        doc = self.client.get(reverse("invoice-document", args=[r.data["id"]])).data
        self.assertEqual(doc["issued_at"], moment.date().isoformat())


class SearchTests(POSBase):
    def _count(self, term, name="product-list"):
        return self.client.get(reverse(name), {"search": term}).data["count"]

    def test_fold(self):
        self.assertEqual(fold_arabic("أَرُزّ إ آ ة ى ـ ٣"), "ارز ا ا ه ي  3")

    def test_arabic_spellings_find_the_product(self):
        for term in ("أرز", "ارز", "بسمتى", "ارز بسمتى", "RICE", "rice"):
            self.assertEqual(self._count(term), 1, term)
        self.assertEqual(self._count("سكر"), 0)

    def test_pack_barcode_search_still_works(self):
        ProductPack.objects.create(
            company=self.company, product=self.rice, name="كرتونة",
            quantity=Decimal("12"), barcode="6290001",
        )
        self.assertEqual(self._count("6290001"), 1)
        self.assertEqual(self._count("كرتونه", "productpack-list"), 1)


class CostVisibilityTests(POSBase):
    def test_cashier_does_not_see_cost(self):
        row = self.client.get(reverse("product-list"), {"search": "RICE"}).data["results"][0]
        self.assertNotIn("cost_price", row)
        self.assertNotIn("reference_cost", row)
        self.assertEqual(Decimal(row["sale_price"]), Decimal("100.00"))
        me = self.client.get(reverse("auth-me")).data
        self.assertFalse(me["capabilities"]["inventory.see_cost"])

    def test_owner_sees_cost(self):
        self.client.force_authenticate(self.owner)
        row = self.client.get(reverse("product-list"), {"search": "RICE"}).data["results"][0]
        self.assertEqual(Decimal(row["cost_price"]), Decimal("80.00"))


class SplitTenderTests(POSBase):
    def setUp(self):
        super().setUp()
        self.bankak = CompanyBankAccount.objects.create(
            company=self.company, channel=CompanyBankAccount.CHANNEL_BANKAK,
            bank_name="Bank of Khartoum", account_name="Shop", account_number="1234",
        )

    def _transfer(self, amount, ref="TX1"):
        return {"method": "bank_transfer", "amount": amount,
                "company_bank_account": self.bankak.pk, "sender_bank_name": "Sara",
                "transfer_reference": ref}

    def test_cash_plus_bankak(self):
        r = self.sell([{"product": self.rice.id, "quantity": "2"}],
                      payments=[{"method": "cash", "amount": "50.00"},
                                self._transfer("150.00")])
        self.assertEqual(r.status_code, 201, r.data)
        payments = Payment.objects.filter(invoice_id=r.data["id"])
        self.assertEqual(sorted(p.method for p in payments), ["bank_transfer", "cash"])
        self.assertEqual(sum(p.amount for p in payments), Decimal("200.00"))

    def test_transfer_above_the_amount_due_is_refused(self):
        r = self.sell([{"product": self.rice.id, "quantity": "1"}],
                      customer=self.customer.id,
                      payments=[{"method": "cash", "amount": "50.00"},
                                self._transfer("80.00")])
        self.assertEqual(r.status_code, 400, r.data)
        self.assertFalse(Invoice.objects.exists())


class PriceFlagWorklistTests(POSBase):
    """Sales an offline till kept with a refused price wait for a manager."""

    def setUp(self):
        super().setUp()
        from django.core.cache import cache

        cache.clear()
        self.other_branch = Branch.objects.create(company=self.company, name="Second")
        self.manager = User.objects.create_user(
            email="bm@shop.test", password="passw0rd12345", company=self.company,
            branch=self.branch,
            role=Role.objects.get_or_create(
                name="Branch Manager", defaults={"scope_level": Role.SCOPE_BRANCH}
            )[0],
        )

    def _flag(self, price="85.00"):
        r = self.push({"lines": [{"product": self.rice.id, "quantity": "1", "unit_price": price}],
                       "payment": {"method": "cash", "amount": price}})
        self.assertEqual(r.data["summary"]["applied"], 1, r.data)
        return Invoice.objects.order_by("-pk").first()

    def test_the_owner_lists_flagged_sales_and_marks_one_reviewed(self):
        invoice = self._flag()
        self.client.force_authenticate(self.owner)
        rows = self.client.get(reverse("price-flag-list")).data
        self.assertEqual(rows["count"], 1)
        row = rows["results"][0]
        self.assertEqual(row["invoice"], invoice.pk)
        self.assertEqual(row["invoice_number"], invoice.number_display)
        self.assertEqual(row["cashier"], "till@shop.test")
        self.assertEqual(row["branch"], "Main")
        self.assertEqual(Decimal(row["discount_percent"]), Decimal("15"))
        self.assertEqual(Decimal(row["breaches"][0]["list"]), Decimal("100"))
        self.assertEqual(Decimal(row["breaches"][0]["sold"]), Decimal("85"))

        badge = self.client.get(reverse("attention")).data
        self.assertEqual(badge["counts"].get("price-flags"), 1)

        r = self.client.post(reverse("price-flag-review", args=[invoice.pk]),
                             {"note": "agreed with the customer"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        from sales.models import PriceFlagReview

        review = PriceFlagReview.objects.get(invoice=invoice)
        self.assertEqual(review.reviewed_by, self.owner)
        self.assertIsNotNone(review.reviewed_at)
        self.assertEqual(review.note, "agreed with the customer")
        self.assertTrue(ActivityLog.objects.filter(action="pos_price_reviewed").exists())
        self.assertEqual(self.client.get(reverse("price-flag-list")).data["count"], 0)
        self.assertNotIn("price-flags", self.client.get(reverse("attention")).data["counts"])
        # Twice is harmless: the first review stands.
        again = self.client.post(reverse("price-flag-review", args=[invoice.pk]), {},
                                 format="json")
        self.assertEqual(again.status_code, 200, again.data)
        self.assertEqual(PriceFlagReview.objects.count(), 1)

    def test_a_branch_manager_sees_only_their_branch(self):
        mine = self._flag()
        theirs = self._flag()
        Invoice.objects.filter(pk=theirs.pk).update(branch=self.other_branch)
        self.client.force_authenticate(self.manager)
        rows = self.client.get(reverse("price-flag-list")).data["results"]
        self.assertEqual([row["invoice"] for row in rows], [mine.pk])
        r = self.client.post(reverse("price-flag-review", args=[theirs.pk]), {}, format="json")
        self.assertEqual(r.status_code, 404, r.data)
        self.assertEqual(self.client.get(reverse("auth-me")).data["capabilities"][
            "sales.review_prices"], True)

    def test_a_cashier_cannot_review(self):
        invoice = self._flag()
        self.assertEqual(self.client.get(reverse("price-flag-list")).status_code, 403)
        r = self.client.post(reverse("price-flag-review", args=[invoice.pk]), {}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertNotIn("price-flags", self.client.get(reverse("attention")).data["counts"])
        self.assertFalse(
            self.client.get(reverse("auth-me")).data["capabilities"]["sales.review_prices"]
        )

    def test_an_unflagged_sale_cannot_be_marked(self):
        r = self.sell([{"product": self.rice.id, "quantity": "1"}],
                      payment={"method": "cash", "amount": "100.00"})
        self.assertEqual(r.status_code, 201, r.data)
        self.client.force_authenticate(self.owner)
        r = self.client.post(reverse("price-flag-review", args=[r.data["id"]]), {},
                             format="json")
        self.assertEqual(r.status_code, 400, r.data)

    def test_another_company_never_sees_the_flag(self):
        self._flag()
        other = Company.objects.create(name="Other")
        stranger = User.objects.create_user(
            email="owner@other.test", password="passw0rd12345", company=other,
            role=self.owner.role,
        )
        self.client.force_authenticate(stranger)
        self.assertEqual(self.client.get(reverse("price-flag-list")).data["count"], 0)
