"""The restore drill, scaled down (docs/restore-drill.md).

A demo company with rows in every module — purchasing with lots, returns and
refunds, a till shift, stock counts, payroll, expenses and budgets, CRM, a web
order paid by bank transfer, a reviewed price flag, the vendor's subscription
rows — is exported the two ways a company leaves the platform:

* the owner's full export (Settings → Backups → download), and
* the deletion backup the platform takes when it deletes a company (#206),

then imported into an empty tenant with the platform's import command. The
restored company must fingerprint exactly like the original: the rows of
every table, every decimal total, stock per product / warehouse / lot, every
customer's, supplier's and bank account's balance, and the report outputs
for the period.
"""
import io
import shutil
import tempfile
import unittest
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db.models import F
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role, User
from core.activity import log_activity
from inventory.models import Product, StockBatch, Warehouse
from ops.company_fingerprint import comparable_rows, diff, fingerprint
from ops.transfer import (
    _auto_timestamp_fields,
    company_queryset,
    export_company,
    transferable_models,
)
from org.models import Branch, Company
from purchasing.models import Supplier
from returns.models import CreditNote
from sales.models import CompanyBankAccount, Customer, Invoice, Payment
from subscriptions import company_deletion, renewals
from subscriptions.models import Plan, PlanVersion, Subscription, SubscriptionPayment
from website.models import PublicOrder

MEDIA = tempfile.mkdtemp(prefix="restore-drill-media-")
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00"
    b"\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


# Assertions outside a test method (the company is built once, in
# setUpTestData).
_CHECK = unittest.TestCase()


class _Api:
    """The API as one user; every call must succeed."""

    def __init__(self, test, user):
        self.test = test
        self.client = APIClient()
        if user is not None:
            self.client.force_authenticate(user)

    def __call__(self, method, url, data=None, fmt="json", expect=(200, 201)):
        response = getattr(self.client, method)(url, data or {}, format=fmt)
        self.test.assertIn(
            response.status_code, expect, f"{method.upper()} {url}: {response.content[:600]}"
        )
        return getattr(response, "data", None)


def _previous_month(today):
    first = today.replace(day=1)
    return (first - timedelta(days=1)).replace(day=1)


def populate_every_module(owner, test=_CHECK):
    """The drill's extra activity (scratch script activity.py in the drill),
    through the API, on top of seed_demo."""
    company = owner.company
    branch = owner.branch
    today = timezone.localdate()
    roles = {role.name: role for role in Role.objects.all()}

    def member(email, role, with_branch=True):
        return User.objects.create_user(
            email=email, password=None, company=company, role=roles[role],
            branch=branch if with_branch else None,
        )

    cfo = member("drill-cfo@vezano.test", "Chief Financial Officer", with_branch=False)
    gm = member("drill-gm@vezano.test", "General Manager", with_branch=False)
    seller = member("drill-seller@vezano.test", "Sales Officer")
    O, C, G, S = (_Api(test, u) for u in (owner, cfo, gm, seller))
    public = _Api(test, None)

    main_wh = Warehouse.objects.filter(company=company).order_by("pk").first()
    products = list(Product.objects.filter(company=company, sku__startswith="DEMO-")
                    .order_by("sku"))
    suppliers = list(Supplier.objects.filter(company=company).order_by("pk"))
    customers = list(Customer.objects.filter(company=company).order_by("pk"))
    bank = CompanyBankAccount.objects.filter(company=company).order_by("pk").first()

    # master data
    branch2 = O("post", "/api/branches/", {"name": "فرع بحري", "code": "BHR"})
    wh2 = O("post", "/api/warehouses/", {"name": "مخزن بحري", "branch": branch2["id"]})["id"]
    bank2 = O("post", "/api/bank-accounts/", {
        "bank_name": "بنكك", "account_name": company.name, "account_number": "7788",
        "channel": "bankak", "opening_balance": "250000",
    })["id"]
    O("patch", f"/api/bank-accounts/{bank.pk}/", {"show_to_customers": True})
    lot_pid = O("post", "/api/products/", {
        "name": "حليب بالتشغيلة", "sku": "DRILL-LOT-1", "sale_price": "12500",
        "cost_price": "9000", "track_batches": True, "barcode": "6299999000017",
    })["id"]
    O("post", "/api/customer-groups/", {"name": "عملاء الجملة"})
    O("post", "/api/brands/", {"name": "نستله"})
    O("post", "/api/product-packs/", {
        "product": products[1].pk, "name": "كرتون", "quantity": "12",
        "barcode": "6299999000024",
    })
    O("post", "/api/departments/", {"name": "المبيعات", "branch": branch.pk})
    O("post", "/api/exchange-rates/", {"currency": "USD", "rate": "2500"})

    # purchasing: an order received in two lots, billed, paid, part returned
    p1, p2 = products[0], products[1]
    po = O("post", "/api/purchase-orders/", {
        "supplier": suppliers[0].pk,
        "lines": [{"product": lot_pid, "quantity_ordered": "40", "unit_cost": "9000"},
                  {"product": p1.pk, "quantity_ordered": "20",
                   "unit_cost": str(p1.cost_price)}],
    })
    O("post", f"/api/purchase-orders/{po['id']}/set_status/", {"status": "confirmed"})
    gr1 = O("post", "/api/receivings/", {
        "supplier": suppliers[0].pk, "warehouse": main_wh.pk, "purchase_order": po["id"],
        "lines": [
            {"product": lot_pid, "quantity": "25", "unit_cost": "9000",
             "lot_number": "L-A", "expiry_date": (today + timedelta(days=200)).isoformat()},
            {"product": lot_pid, "quantity": "15", "unit_cost": "9200",
             "lot_number": "L-B", "expiry_date": (today + timedelta(days=400)).isoformat()},
            {"product": p1.pk, "quantity": "20", "unit_cost": str(p1.cost_price)},
        ],
    })
    gr2 = O("post", "/api/receivings/", {
        "supplier": suppliers[1].pk, "warehouse": main_wh.pk,
        "lines": [{"product": p2.pk, "quantity": "30", "unit_cost": str(p2.cost_price)}],
    })
    bills = []
    for receipt, supplier in ((gr1, suppliers[0]), (gr2, suppliers[1])):
        value = sum(
            Decimal(str(line["quantity"])) * Decimal(str(line["unit_cost"]))
            for line in receipt["lines"]
        ).quantize(Decimal("0.01"))
        bills.append(O("post", "/api/bills/", {
            "supplier": supplier.pk, "goods_receipt": receipt["id"], "subtotal": str(value),
            "tax_amount": "0", "total": str(value),
            "supplier_invoice_number": f"SUP-{receipt['id']}",
        }))
    O("post", "/api/supplier-payments/", {
        "supplier": suppliers[0].pk, "bill": bills[0]["id"], "method": "cash",
        "amount": str((Decimal(bills[0]["total"]) / 2).quantize(Decimal("1"))),
    })
    paid = O("post", "/api/supplier-payments/", {
        "supplier": suppliers[1].pk, "bill": bills[1]["id"], "method": "bank_transfer",
        "amount": bills[1]["total"], "from_bank_account": bank.pk, "reference_last4": "5521",
    })
    C("post", f"/api/supplier-payments/{paid['id']}/verify/")
    O("post", "/api/purchase-returns/", {
        "supplier": suppliers[1].pk, "warehouse": main_wh.pk, "goods_receipt": gr2["id"],
        "lines": [{"goods_receipt_line": gr2["lines"][0]["id"], "quantity": "2"}],
    })

    # a till shift: sales (lots included), a return refunded in cash, a drop
    shift = O("post", "/api/cash-shifts/", {"opening_float": "50000"})["id"]
    sales = []
    for index in range(3):
        if index == 2:
            # A cost rise between sales: each sale's cost of goods is the
            # snapshot on its own stock movement, found by the invoice's id.
            O("patch", f"/api/products/{lot_pid}/", {"cost_price": "9900"})
        lines = [{"product": products[3 + index].pk, "quantity": "2"},
                 {"product": lot_pid, "quantity": "1"}]
        total = sum(Decimal(line["quantity"]) * Product.objects.get(pk=line["product"])
                    .sale_price for line in lines)
        sales.append(O("post", "/api/pos/checkout/", {
            "warehouse": main_wh.pk, "shift": shift, "lines": lines,
            "client_uuid": str(uuid.uuid4()),
            "payment": {"method": "cash", "amount": str(total)},
        }))
    invoice = Invoice.objects.get(pk=sales[0]["id"])
    line = invoice.lines.order_by("pk").first()
    returned = O("post", "/api/sales-returns/", {
        "invoice": invoice.pk, "reason": "عيب",
        "lines": [{"invoice_line": line.pk, "product": line.product_id, "quantity": "1"}],
    })
    O("post", f"/api/sales-returns/{returned['id']}/disposition/", {
        "decisions": [{"line_id": item["id"], "action": "restock"}
                      for item in returned["lines"]],
    })
    note = CreditNote.objects.get(sales_return_id=returned["id"])
    O("post", "/api/refunds/", {"credit_note": note.pk, "method": "cash",
                                "amount": str(note.amount), "shift": shift})
    O("post", "/api/drawer-movements/", {"shift": shift, "kind": "drop",
                                         "amount": "-20000", "reason": "إيداع"})
    expected = O("get", "/api/cash-shifts/current/")["expected_cash"]
    O("post", f"/api/cash-shifts/{shift}/close/",
      {"counted_cash": str(Decimal(str(expected)) - 500), "note": "عجز"})
    G("post", f"/api/cash-shifts/{shift}/review/")

    # a quotation through to its invoice
    quote = O("post", "/api/quotations/", {
        "customer": customers[0].pk,
        "lines": [{"product": p1.pk, "quantity": "3", "unit_price": str(p1.sale_price)}],
    })
    order = O("post", f"/api/quotations/{quote['id']}/convert_to_order/")
    O("post", f"/api/sales-orders/{order['id']}/set_status/", {"status": "confirmed"})
    O("post", "/api/pos/checkout/", {
        "warehouse": main_wh.pk, "customer": customers[0].pk, "source_order": order["id"],
        "lines": [{"product": p1.pk, "quantity": "3"}], "client_uuid": str(uuid.uuid4()),
    })

    # bank transfers on credit invoices: one from a statement, one by hand
    owed = [inv for inv in Invoice.objects.filter(company=company, customer__isnull=False)
            .order_by("pk") if inv.amount_due() > 0][:2]
    recorded = [O("post", "/api/payments/", {
        "invoice": inv.pk, "method": "bank_transfer",
        "amount": str((inv.amount_due() / 2).quantize(Decimal("1"))),
        "company_bank_account": bank.pk, "sender_bank_name": "بنك فيصل",
        "transfer_reference": f"TRX{inv.pk:05d}",
    }) for inv in owed]
    statement = io.BytesIO((
        "date,reference,amount,sender\n"
        f"{today.isoformat()},{recorded[0]['transfer_reference']},{recorded[0]['amount']},x\n"
    ).encode())
    statement.name = "statement.csv"
    C("post", "/api/payments/reconcile/", {"account": bank.pk, "file": statement},
      fmt="multipart")
    C("post", f"/api/payments/{recorded[1]['id']}/verify/")
    O("post", "/api/credit-notes/", {"customer": owed[1].customer_id, "invoice": owed[1].pk,
                                     "amount": "1000", "reason": "تسوية"})

    # an offline sale under cost by a sales officer, reviewed by the owner; it was
    # captured two hours ago while the till had no connection (a sale captured
    # online is refused instead of flagged)
    under = (products[5].cost_price * Decimal("0.8")).quantize(Decimal("1"))
    S("post", "/api/sync/push/", {
        "batch_uuid": str(uuid.uuid4()), "expected_company": company.pk,
        "expected_user": seller.pk,
        "operations": [{"op_type": "pos_checkout", "client_uuid": str(uuid.uuid4()),
                        "payload": {"warehouse": main_wh.pk,
                                    "lines": [{"product": products[5].pk, "quantity": "1",
                                               "unit_price": str(under)}],
                                    "payment": {"method": "cash", "amount": str(under)},
                                    "occurred_at": (timezone.now() - timedelta(hours=2)).isoformat()}}],
    })
    flagged = O("get", "/api/price-flags/")
    flagged = flagged.get("results", flagged) if isinstance(flagged, dict) else flagged
    test.assertTrue(flagged, "the under-cost offline sale was not flagged")
    O("post", f"/api/price-flags/{flagged[0]['invoice']}/review/", {"note": "موافق"})

    # stock: transfers, adjustments and counts, lot by lot where tracked
    lots = {b.lot_number: b.pk for b in StockBatch.objects.filter(company=company)}
    O("post", "/api/stock-transfers/", {"product": products[6].pk,
                                        "source_warehouse": main_wh.pk,
                                        "dest_warehouse": wh2, "quantity": "5"})
    O("post", "/api/stock-transfers/", {"product": lot_pid, "source_warehouse": main_wh.pk,
                                        "dest_warehouse": wh2, "quantity": "4",
                                        "batch": lots["L-A"]})
    O("post", "/api/stock-adjustments/", {"product": products[7].pk,
                                          "warehouse": main_wh.pk, "quantity": "-2",
                                          "reason": "كسر", "reason_code": "damage"})
    O("post", "/api/stock-adjustments/", {"product": lot_pid, "warehouse": main_wh.pk,
                                          "quantity": "-1", "reason": "انتهاء",
                                          "reason_code": "expiry", "batch": lots["L-B"]})
    for body in (
        {"warehouse": wh2, "lines": [{"product": products[6].pk, "counted_quantity": "4"}]},
        {"warehouse": main_wh.pk, "lines": [
            {"product": lot_pid, "batch": lots["L-A"], "counted_quantity": "17"},
            {"product": lot_pid, "batch": lots["L-B"], "counted_quantity": "14"},
        ]},
    ):
        count = O("post", "/api/stock-counts/", body)
        O("post", f"/api/stock-counts/{count['id']}/submit/")
        G("post", f"/api/stock-counts/{count['id']}/approve/")

    # HR: employees, attendance, leave, an advance, a deduction, payroll
    month = _previous_month(today)
    position = O("post", "/api/positions/", {"title": "بائع", "base_salary": "600000"})
    employees = [O("post", "/api/employees/", {
        "full_name": name, "base_salary_override": salary, "branch": branch.pk,
        "hire_date": (month - timedelta(days=60)).isoformat(), "position": position["id"],
    }) for name, salary in (("أحمد", "600000"), ("سارة", "750000"))]
    for employee in employees:
        for offset, status in ((3, "present"), (2, "absent"), (1, "present")):
            O("post", "/api/attendance/", {
                "employee": employee["id"], "status": status,
                "date": (today - timedelta(days=offset)).isoformat(),
            })
    leave = O("post", "/api/leave-requests/", {
        "employee": employees[0]["id"], "leave_type": "annual",
        "start_date": (today + timedelta(days=5)).isoformat(),
        "end_date": (today + timedelta(days=6)).isoformat(),
    })
    O("post", f"/api/leave-requests/{leave['id']}/approve/")
    advance = O("post", "/api/salary-advances/", {"employee": employees[1]["id"],
                                                  "amount": "100000"})
    O("post", f"/api/salary-advances/{advance['id']}/approve/")
    O("post", "/api/deductions/", {"employee": employees[0]["id"], "amount": "25000",
                                   "date": (month + timedelta(days=9)).isoformat()})
    O("post", "/api/performance-records/", {"employee": employees[0]["id"], "rating": 4,
                                            "review_date": today.isoformat()})
    O("post", "/api/work-policies/", {"name": "السلوك", "violation_type": "misconduct"})
    O("post", "/api/leave-accrual-policies/", {"leave_type": "sick", "annual_days": "10"})
    O("post", "/api/leave-accrual-policies/generate/", {"year": today.year})
    run = O("post", "/api/payroll-runs/", {"period": month.strftime("%Y-%m")})
    O("post", f"/api/payroll-runs/{run['id']}/approve/")

    # finance: expenses (one reversed), a budget
    O("post", "/api/expenses/", {"category": "إيجار", "amount": "900000", "method": "cash",
                                 "date": today.isoformat()})
    O("post", "/api/expenses/", {"category": "كهرباء", "amount": "120000",
                                 "method": "bank_transfer", "company_bank_account": bank2,
                                 "date": today.isoformat()})
    wrong = O("post", "/api/expenses/", {"category": "نقل", "amount": "30000",
                                         "method": "cash", "date": today.isoformat()})
    O("post", "/api/expenses/", {"category": "نقل", "amount": "-30000", "method": "cash",
                                 "date": today.isoformat(), "reverses": wrong["id"]})
    budget = O("post", "/api/budgets/", {
        "name": "موازنة", "period_start": today.isoformat(),
        "period_end": (today + timedelta(days=90)).isoformat(),
        "lines": [{"kind": "expense", "category": "إيجار", "planned_amount": "2700000"}],
    })
    C("post", f"/api/budgets/{budget['id']}/approve/")

    # CRM: a lead won and converted
    lead = O("post", "/api/leads/", {"name": "مطعم النيل", "phone": "+249912000111",
                                     "estimated_value": "5000000"})
    O("post", "/api/crm-notes/", {"lead": lead["id"], "body": "طلب عرض سعر"})
    O("patch", f"/api/leads/{lead['id']}/", {"stage": "won"})
    O("post", f"/api/leads/{lead['id']}/convert/")

    # web orders: one paid by bank transfer and delivered, one claim with a
    # proof picture rejected, one order rejected
    O("patch", "/api/website/page/", {"accept_orders": True})
    placed = [public("post", f"/api/public/site/{company.slug}/orders/", {
        "contact_name": name, "phone": phone,
        "lines": [{"product": products[0].pk, "quantity": 1}],
    }) for name, phone in (("أمل", "0912345678"), ("خالد", "0923456789"),
                           ("منى", "0934567890"))]
    orders = [PublicOrder.objects.get(reference=row["reference"]) for row in placed]
    claim = public("post", f"/api/public/site/{company.slug}/orders/{orders[0].reference}/", {
        "bank_account": bank.pk, "sender_bank_name": "بنك فيصل", "reference_last4": "4321",
        "amount": str(products[0].sale_price),
    })
    O("post", f"/api/web-orders/{orders[0].pk}/payments/{claim['id']}/confirm/",
      {"warehouse": main_wh.pk})
    for stage in ("preparing", "ready", "completed"):
        O("post", f"/api/web-orders/{orders[0].pk}/stage/", {"status": stage})
    proof = public("post", f"/api/public/site/{company.slug}/orders/{orders[1].reference}/", {
        "bank_account": bank.pk, "sender_bank_name": "بنك أمدرمان",
        "reference_last4": "8765", "amount": "1000",
        "proof": SimpleUploadedFile("proof.png", PNG, content_type="image/png"),
    }, fmt="multipart")
    O("post", f"/api/web-orders/{orders[1].pk}/payments/{proof['id']}/reject/",
      {"note": "غير مطابق"})
    O("post", f"/api/web-orders/{orders[2].pk}/reject/", {"note": "نفد المخزون"})

    # the vendor's side: a paid renewal; and a nightly-style snapshot
    payment = SubscriptionPayment.objects.create(
        company=company, amount=Decimal("30"), currency="USD", method="cash",
        recorded_by=owner,
    )
    operator = User.objects.get(email="drill-operator@vezano.test")
    renewals.renew_with_payment(payment.pk, operator)
    O("post", "/api/ops/backups/")
    O("patch", "/api/ops/preferences/", {"language": "ar"})


def age_history(company, days=45):
    """Every other row's server timestamps move back, as for a shop that has
    been working for months (reports read several of them)."""
    for model in transferable_models():
        fields = _auto_timestamp_fields(model)
        if not fields:
            continue
        pks = list(company_queryset(model, company).order_by("pk")
                   .values_list("pk", flat=True))[::2]
        model._base_manager.filter(pk__in=pks).update(
            **{field.attname: F(field.attname) - timedelta(days=days) for field in fields}
        )


@override_settings(MEDIA_ROOT=MEDIA, SUBSCRIPTION_POLICY="disabled")
class RestoreDrillTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_roles", verbosity=0)
        plan = Plan.objects.create(code="drill", name="Drill")
        version = PlanVersion.objects.create(
            plan=plan, version=1, currency="USD", price=Decimal("30"), modules=["*"],
            published_at=timezone.now(),
        )
        operator = User.objects.create_user(
            email="drill-operator@vezano.test", password=None, is_staff=True,
            is_superuser=True, role=Role.objects.get(name="Super Administrator"),
        )
        company = Company.objects.create(name="متجر التمرين", slug="drill-store",
                                         currency="SDG")
        branch = Branch.objects.create(company=company, name="الفرع الرئيسي", code="MAIN")
        owner = User.objects.create_user(
            email="drill-owner@vezano.test", password=None, company=company, branch=branch,
            role=Role.objects.get(name="Business Owner"),
        )
        now = timezone.now()
        Subscription.objects.create(
            company=company, plan_version=version, status=Subscription.ACTIVE,
            starts_at=now - timedelta(days=60), period_ends_at=now + timedelta(days=5),
        )
        # A platform operator's audit row about the company: the operator
        # does not travel with it.
        log_activity(action="create", user=operator, company=company,
                     entity_type="RegistrationProvision", entity_id=company.pk)
        call_command("seed_demo", owner=owner.email, sales=12, scale=Decimal(2500), yes=True,
                     stdout=io.StringIO(), stderr=io.StringIO())
        populate_every_module(owner)
        age_history(company)
        cls.company_id, cls.owner_id, cls.operator_id = company.pk, owner.pk, operator.pk

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.company = Company.objects.get(pk=self.company_id)
        self.owner = User.objects.get(pk=self.owner_id)
        self.operator = User.objects.get(pk=self.operator_id)
        today = timezone.localdate()
        self.period = (today - timedelta(days=30), today)

    def snapshot(self, company):
        """Fingerprint plus the id-free rows of every table."""
        payload, _ = export_company(company, include_media=False)
        return fingerprint(company, *self.period), comparable_rows(payload)

    def assertSame(self, before, after, ignore=()):
        problems = diff(before[0], after[0], ignore=ignore) + diff(
            before[1], after[1], ignore=ignore
        )
        self.assertEqual(problems, [], "\n".join(problems[:40]))

    def owner_download(self):
        client = APIClient()
        client.force_authenticate(self.owner)
        response = client.get("/api/ops/backups/export/")
        self.assertEqual(response.status_code, 200)
        return response.content

    def import_file(self, name, content):
        path = Path(tempfile.mkdtemp(prefix="restore-drill-")) / name
        path.write_bytes(content)
        try:
            call_command("import_company", archive=str(path), stdout=io.StringIO())
        finally:
            shutil.rmtree(path.parent, ignore_errors=True)
        return Company.objects.get(slug=self.company.slug)

    def test_every_module_has_rows(self):
        counts = fingerprint(self.company, *self.period)["counts"]
        for label in (
            "purchasing.Bill", "purchasing.SupplierPayment", "returns.PurchaseReturn",
            "returns.SalesReturn", "returns.CreditNote", "sales.Refund",
            "inventory.StockBatch", "inventory.StockCountLine", "inventory.StockTransfer",
            "inventory.StockAdjustment", "hr.PayrollEntry", "hr.Attendance",
            "hr.SalaryAdvance", "finance.Expense", "finance.BudgetLine", "crm.Lead",
            "website.PublicOrderEvent", "website.PublicOrderPayment", "sales.CashShift",
            "sales.CashDrawerMovement", "sales.PriceFlagReview", "ops.BackupRecord",
        ):
            self.assertGreater(counts[label], 0, label)

    def test_deleted_then_restored_company_comes_back_whole(self):
        before = self.snapshot(self.company)
        deletion = company_deletion.schedule_deletion(
            self.company, self.operator, self.company.slug
        )
        company_deletion.restore_company(self.company, self.operator)
        self.company.refresh_from_db()
        self.assertTrue(self.company.is_active)
        self.assertEqual(Subscription.objects.get(company=self.company).status,
                         Subscription.ACTIVE)
        # The only new rows are the lifecycle's own: two audit entries and
        # the deletion backup.
        after = self.snapshot(self.company)
        self.assertSame(before, after, ignore=(
            "counts.core.ActivityLog", "counts.ops.BackupRecord", "core.ActivityLog",
            "ops.BackupRecord",
        ))
        self.assertEqual(after[0]["counts"]["ops.BackupRecord"],
                         before[0]["counts"]["ops.BackupRecord"] + 1)
        self.assertEqual(deletion.backup_rows, sum(before[0]["counts"].values()))

    def test_owner_export_and_deletion_backup_restore_into_an_empty_tenant(self):
        before = self.snapshot(self.company)
        download = self.owner_download()
        # The download writes its own audit row after reading the company;
        # the deletion backup, taken next, carries it.
        before_backup = self.snapshot(self.company)
        self.assertEqual(before_backup[0]["counts"]["core.ActivityLog"],
                         before[0]["counts"]["core.ActivityLog"] + 1)

        # Deleted and purged at once: the tombstone stays, nothing else.
        deletion = company_deletion.schedule_deletion(
            self.company, self.operator, self.company.slug
        )
        company_deletion.purge_company(deletion, actor=self.operator)
        deletion.refresh_from_db()
        self.assertEqual(deletion.status, deletion.PURGED)
        self.assertIsNone(deletion.company_id)
        self.assertFalse(Company.objects.filter(pk=self.company_id).exists())
        self.assertFalse(Invoice.objects.filter(company_id=self.company_id).exists())

        # 1. The deletion backup, as the platform downloads it.
        restored = self.import_file("backup.zip", company_deletion.backup_archive(deletion))
        self.assertSame(before_backup, self.snapshot(restored))
        self.assertFalse(restored.users.get(email=self.owner.email).has_usable_password())

        # 2. The owner's own download (bare JSON), after that copy is gone.
        again = company_deletion.schedule_deletion(restored, self.operator, restored.slug)
        company_deletion.purge_company(again, actor=self.operator)
        restored = self.import_file("owner-export.json", download)
        after = self.snapshot(restored)
        self.assertSame(before, after)

        # The check is not blind: one payment changed by a pound shows up.
        payment = Payment.objects.filter(company=restored).order_by("pk").first()
        Payment.objects.filter(pk=payment.pk).update(amount=F("amount") + 1)
        self.assertTrue(diff(before[0], self.snapshot(restored)[0]))

    def test_restored_company_keeps_numbering_and_selling(self):
        download = self.owner_download()
        deletion = company_deletion.schedule_deletion(
            self.company, self.operator, self.company.slug
        )
        company_deletion.purge_company(deletion, actor=self.operator)
        restored = self.import_file("owner-export.json", download)
        last = Invoice.objects.filter(company=restored).order_by("-number").first().number
        owner = restored.users.get(email=self.owner.email)
        client = APIClient()
        client.force_authenticate(owner)
        product = Product.objects.filter(company=restored, sku="DEMO-010").get()
        response = client.post("/api/pos/checkout/", {
            "warehouse": Warehouse.objects.filter(company=restored).order_by("pk").first().pk,
            "customer": Customer.objects.filter(company=restored).order_by("pk").first().pk,
            "lines": [{"product": product.pk, "quantity": "1"}],
            "client_uuid": str(uuid.uuid4()),
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content[:400])
        self.assertEqual(response.data["number"], last + 1)
