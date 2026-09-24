"""
Reporting endpoints (M9). All read-only, company-scoped, gated to the
`reports` module (M6). Every number is DERIVED from the underlying ledgers and
documents at query time — there are no stored report totals to drift.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import (
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    Q,
    Sum,
)
from django.db.models.functions import Coalesce, TruncDate
from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.utils import timezone
from django.utils.translation import gettext as _

from core.csvexport import rows_download
from core.permissions import PayrollReportAccess, ReportAreaAccess
from core.rbac import RoleModuleAccess
from finance.metrics import date_range, operating_summary
from purchasing.querysets import open_bills, payable_total
from sales.querysets import open_invoices, receivable_total

ZERO = Decimal("0")
MONEY = DecimalField(max_digits=20, decimal_places=2)
MAX_HORIZON_DAYS = 365


def walk_in_label():
    return _("(walk-in)")


def _in_base(field):
    """A purchasing amount in the company currency (row's own rate)."""
    return ExpressionWrapper(F(field) * F("exchange_rate"), output_field=MONEY)


class ReportView(APIView):
    permission_classes = [IsAuthenticated, RoleModuleAccess, ReportAreaAccess]
    rbac_module = "reports"

    def company_id(self, request):
        return getattr(request.user, "company_id", None)

    def branch_id(self, request):
        role = getattr(request.user, "role", None)
        if role and role.scope_level == "branch":
            return getattr(request.user, "branch_id", None)
        return None

    def apply_branch(self, request, qs, field):
        branch_id = self.branch_id(request)
        return qs.filter(**{f"{field}_id": branch_id}) if branch_id else qs

    def date_range(self, request):
        return date_range(request.query_params)

    def apply_range(self, qs, field, start, end):
        if start:
            qs = qs.filter(**{f"{field}__date__gte": start})
        if end:
            qs = qs.filter(**{f"{field}__date__lte": end})
        return qs

    def csv_response(self, filename, header, rows):
        # BOM for Excel's Arabic; text cells that would run as formulas are
        # neutralised (a customer named "=HYPERLINK(...)" stays text).
        return rows_download(filename, header, rows)

    def horizon_days(self, request, default):
        """`?days=` look-ahead, clamped to a year: a huge value overflowed
        the date arithmetic into a 500."""
        try:
            days = int(request.query_params.get("days", default))
        except (TypeError, ValueError):
            return default
        return max(0, min(days, MAX_HORIZON_DAYS))

    def wants_csv(self, request):
        return request.query_params.get("format") == "csv"


class HrSummaryReport(ReportView):
    report_area = "hr"

    def get(self, request):
        from hr.models import Attendance, Deduction, Employee, LeaveRequest, SalaryAdvance
        from hr.leave_sync import refresh_employee_leave_statuses

        cid = self.company_id(request)
        refresh_employee_leave_statuses(cid)
        start, end = self.date_range(request)
        employees = Employee.objects.filter(company_id=cid)
        attendance = Attendance.objects.filter(company_id=cid)
        leave = LeaveRequest.objects.filter(company_id=cid)
        advances = SalaryAdvance.objects.filter(company_id=cid)
        deductions = Deduction.objects.filter(company_id=cid)
        employees = self.apply_branch(request, employees, "branch")
        # Headcount is who works here: a terminated employee stays in the
        # status breakdown but not in the total or the departments.
        current = employees.exclude(status=Employee.STATUS_TERMINATED)
        attendance = self.apply_branch(request, attendance, "employee__branch")
        leave = self.apply_branch(request, leave, "employee__branch")
        advances = self.apply_branch(request, advances, "employee__branch")
        deductions = self.apply_branch(request, deductions, "employee__branch")

        if start:
            attendance = attendance.filter(date__gte=start)
            leave = leave.filter(end_date__gte=start)
            advances = advances.filter(created_at__date__gte=start)
            deductions = deductions.filter(
                Q(date__gte=start) | Q(date__isnull=True, created_at__date__gte=start)
            )
        if end:
            attendance = attendance.filter(date__lte=end)
            leave = leave.filter(start_date__lte=end)
            advances = advances.filter(created_at__date__lte=end)
            deductions = deductions.filter(
                Q(date__lte=end) | Q(date__isnull=True, created_at__date__lte=end)
            )

        def counts(queryset, field="status"):
            return {
                row[field]: row["count"]
                for row in queryset.values(field).annotate(count=Count("id"))
            }

        advance_total = advances.filter(status=SalaryAdvance.APPROVED).aggregate(
            total=Coalesce(Sum("amount"), ZERO, output_field=MONEY)
        )["total"]
        deduction_total = deductions.aggregate(
            total=Coalesce(Sum("amount"), ZERO, output_field=MONEY)
        )["total"]
        departments = list(
            current.exclude(department__isnull=True)
            .values("department__name")
            .annotate(count=Count("id"))
            .order_by("department__name")
        )

        return Response(
            {
                "employees": counts(employees),
                "employee_total": current.count(),
                "attendance": counts(attendance),
                "leave": counts(leave),
                "advances": {**counts(advances), "approved_total": str(advance_total)},
                "deductions": {"count": deductions.count(), "total": str(deduction_total)},
                "departments": [
                    {"name": row["department__name"], "count": row["count"]} for row in departments
                ],
            }
        )


class PayrollReport(ReportView):
    """Monthly payroll snapshots, available to the HR reporting area."""

    report_area = "hr"
    permission_classes = [IsAuthenticated, RoleModuleAccess, PayrollReportAccess]

    def get(self, request):
        from hr.models import PayrollRun

        cid = self.company_id(request)
        start, end = self.date_range(request)
        runs = PayrollRun.objects.filter(company_id=cid).prefetch_related("entries")
        if start:
            runs = runs.filter(period__gte=start.replace(day=1))
        if end:
            runs = runs.filter(period__lte=end.replace(day=1))

        rows = []
        for run in runs:
            entries = list(run.entries.all())
            rows.append(
                {
                    "id": run.id,
                    "period": run.period.isoformat(),
                    "status": run.status,
                    "employee_count": len(entries),
                    "base_total": str(sum((entry.base_salary for entry in entries), ZERO)),
                    "deductions_total": str(
                        sum((entry.deductions_total for entry in entries), ZERO)
                    ),
                    "advances_total": str(sum((entry.advances_total for entry in entries), ZERO)),
                    "net_total": str(sum((entry.net_salary for entry in entries), ZERO)),
                    "entries": [
                        {
                            "employee_name": entry.employee_name,
                            "department_name": entry.department_name,
                            "position_title": entry.position_title,
                            "base_salary": str(entry.base_salary),
                            "deductions_total": str(entry.deductions_total),
                            "advances_total": str(entry.advances_total),
                            "net_salary": str(entry.net_salary),
                        }
                        for entry in entries
                    ],
                }
            )
        if self.wants_csv(request):
            return self.csv_response(
                "payroll_report.csv",
                [
                    _("Period"),
                    _("Status"),
                    _("Employee"),
                    _("Department"),
                    _("Position"),
                    _("Base salary"),
                    _("Deductions"),
                    _("Advances"),
                    _("Net salary"),
                ],
                [
                    [
                        row["period"],
                        row["status"],
                        item["employee_name"],
                        item["department_name"],
                        item["position_title"],
                        item["base_salary"],
                        item["deductions_total"],
                        item["advances_total"],
                        item["net_salary"],
                    ]
                    for row in rows
                    for item in row["entries"]
                ],
            )
        return Response(rows)


class SalesSummaryReport(ReportView):
    report_area = "sales"

    def get(self, request):
        from sales.models import Invoice

        cid = self.company_id(request)
        start, end = self.date_range(request)
        qs = self.apply_range(
            Invoice.objects.filter(company_id=cid, is_void=False, is_opening_balance=False),
            "issued_at",
            start,
            end,
        )
        qs = self.apply_branch(request, qs, "branch")
        totals = qs.aggregate(
            invoice_count=Count("id"),
            subtotal=Coalesce(Sum("subtotal"), ZERO, output_field=MONEY),
            tax=Coalesce(Sum("tax_amount"), ZERO, output_field=MONEY),
            total=Coalesce(Sum("total"), ZERO, output_field=MONEY),
        )
        daily = list(
            qs.annotate(day=TruncDate("issued_at"))
            .values("day")
            .annotate(
                count=Count("id"),
                total=Coalesce(Sum("total"), ZERO, output_field=MONEY),
            )
            .order_by("day")
        )
        return Response(
            {
                "totals": {k: str(v) if isinstance(v, Decimal) else v for k, v in totals.items()},
                "daily": [
                    {"day": d["day"].isoformat(), "count": d["count"], "total": str(d["total"])}
                    for d in daily
                ],
            }
        )


class SalesByProductReport(ReportView):
    report_area = "sales"

    def get(self, request):
        from sales.models import InvoiceLine

        cid = self.company_id(request)
        start, end = self.date_range(request)
        qs = InvoiceLine.objects.filter(invoice__company_id=cid, invoice__is_void=False)
        qs = self.apply_branch(request, qs, "invoice__branch")
        qs = self.apply_range(qs, "invoice__issued_at", start, end)
        rows = list(
            qs.values("product", "product__sku", "product__name")
            .annotate(
                units=Coalesce(Sum("quantity"), ZERO),
                revenue=Coalesce(Sum("line_subtotal"), ZERO, output_field=MONEY),
            )
            .order_by("-revenue")
        )
        if self.wants_csv(request):
            return self.csv_response(
                "sales_by_product.csv",
                [_("SKU"), _("Product"), _("Units"), _("Revenue before returns")],
                [[r["product__sku"], r["product__name"], r["units"], r["revenue"]] for r in rows],
            )
        return Response(
            [
                {
                    "product": r["product"],
                    "sku": r["product__sku"],
                    "name": r["product__name"],
                    "units": str(r["units"]),
                    "revenue": str(r["revenue"]),
                }
                for r in rows
            ]
        )


class InventoryValuationReport(ReportView):
    report_area = "inventory"

    def get(self, request):
        from inventory.costing import METHODS, company_totals
        from inventory.models import Product

        cid = self.company_id(request)
        method = request.query_params.get("method", "standard")
        if method not in METHODS:
            method = "standard"
        # Stock held at the end of that local day; today's stock without it.
        # The reports page passes the end of its date range.
        raw_as_of = request.query_params.get("as_of")
        try:
            as_of = parse_date(raw_as_of) if raw_as_of else None
        except (ValueError, TypeError):
            as_of = None
        if raw_as_of and as_of is None:
            raise ValidationError({"as_of": _("Use a valid YYYY-MM-DD date.")})

        if method == "standard":
            products = Product.objects.filter(company_id=cid)
            branch_id = self.branch_id(request)
            if branch_id:
                products = products.filter(stock_movements__warehouse__branch_id=branch_id)
            held = Q(stock_movements__created_at__date__lte=as_of) if as_of else None
            products = products.annotate(on_hand=Coalesce(
                Sum("stock_movements__quantity", filter=held), ZERO,
            ))
            rows = []
            total_value = ZERO
            for p in products:
                value = (p.on_hand or ZERO) * p.cost_price
                total_value += value
                rows.append(
                    {
                        "product": p.id,
                        "sku": p.sku,
                        "name": p.name,
                        "on_hand": str(p.on_hand or ZERO),
                        "cost_price": str(p.cost_price),
                        "value": str(value),
                    }
                )
        else:
            if self.branch_id(request):
                return Response(
                    {"detail": _("Branch valuation currently supports standard costing only.")},
                    status=400,
                )
            totals = company_totals(cid, method=method, as_of=as_of)
            rows = []
            total_value = totals["valuation"]
            for p, res in totals["per_product"]:
                rows.append(
                    {
                        "product": p.id,
                        "sku": p.sku,
                        "name": p.name,
                        "on_hand": str(res["on_hand"]),
                        "cost_price": str(p.cost_price),
                        "value": str(res["valuation"]),
                    }
                )

        if self.wants_csv(request):
            return self.csv_response(
                "inventory_valuation.csv",
                [_("SKU"), _("Product"), _("On hand"), _("Cost price"), _("Value")],
                [[r["sku"], r["name"], r["on_hand"], r["cost_price"], r["value"]] for r in rows],
            )
        return Response(
            {
                "method": method,
                # Standard cost values the stock held then at today's cost;
                # average and FIFO replay the ledger up to that day.
                "as_of": as_of.isoformat() if as_of else None,
                "total_value": str(total_value),
                "items": rows,
            }
        )


def _bucket(days):
    if days <= 0:
        return "current"
    if days <= 30:
        return "1_30"
    if days <= 60:
        return "31_60"
    if days <= 90:
        return "61_90"
    return "over_90"


class ARAgingReport(ReportView):
    report_area = "sales"

    def get(self, request):
        from sales.models import Invoice

        cid = self.company_id(request)
        # The company's calendar, not UTC's: a bucket boundary must flip at
        # local midnight, the same moment the dashboard and debt ledger use.
        today = timezone.localdate()
        per_customer = {}
        # Balances are annotated in SQL (one query) rather than computed per
        # invoice in Python (three queries each) — the difference between a
        # report and a timeout at 50k invoices.
        invoices = open_invoices(
            Invoice.objects.filter(company_id=cid)
        ).select_related("customer").only(
            "id", "customer_id", "customer__name", "due_date", "issued_at", "branch_id",
        )
        invoices = self.apply_branch(request, invoices, "branch")
        for inv in invoices.iterator(chunk_size=2000):
            due = inv.outstanding
            key = inv.customer_id
            name = inv.customer.name if inv.customer else walk_in_label()
            # Age by *due date* so buckets mean days overdue, not days since
            # issue. Legacy rows without a due date fall back to issue date.
            reference = inv.due_date or inv.issued_at.date()
            age = (today - reference).days
            entry = per_customer.setdefault(
                key,
                {
                    "customer": key,
                    "name": name,
                    "current": ZERO,
                    "1_30": ZERO,
                    "31_60": ZERO,
                    "61_90": ZERO,
                    "over_90": ZERO,
                    "total": ZERO,
                },
            )
            entry[_bucket(age)] += due
            entry["total"] += due
        rows = [
            {k: (str(v) if isinstance(v, Decimal) else v) for k, v in e.items()}
            for e in per_customer.values()
        ]
        return Response(rows)


class APAgingReport(ReportView):
    report_area = "purchasing"

    def get(self, request):
        from purchasing.models import Bill

        cid = self.company_id(request)
        today = timezone.localdate()
        per_supplier = {}
        bills = open_bills(Bill.objects.filter(company_id=cid)).select_related("supplier")
        for bill in bills.iterator(chunk_size=2000):
            due = bill.outstanding_base
            key = bill.supplier_id
            # Age by due date (see ARAgingReport) — falls back for legacy rows.
            reference = bill.due_date or bill.created_at.date()
            age = (today - reference).days
            entry = per_supplier.setdefault(
                key,
                {
                    "supplier": key,
                    "name": bill.supplier.name,
                    "current": ZERO,
                    "1_30": ZERO,
                    "31_60": ZERO,
                    "61_90": ZERO,
                    "over_90": ZERO,
                    "total": ZERO,
                },
            )
            entry[_bucket(age)] += due
            entry["total"] += due
        rows = [
            {k: (str(v) if isinstance(v, Decimal) else v) for k, v in e.items()}
            for e in per_supplier.values()
        ]
        return Response(rows)


class PurchasesSummaryReport(ReportView):
    report_area = "purchasing"

    def get(self, request):
        from purchasing.models import Bill, GoodsReceipt

        cid = self.company_id(request)
        start, end = self.date_range(request)
        bills = self.apply_range(
            Bill.objects.filter(company_id=cid, is_void=False, is_opening_balance=False),
            "created_at",
            start,
            end,
        )
        receipts = self.apply_branch(
            request,
            self.apply_range(
                GoodsReceipt.objects.filter(company_id=cid), "received_at", start, end,
            ),
            "warehouse__branch",
        )
        agg = bills.aggregate(
            bill_count=Count("id"),
            # A USD bill is USD 1,000, not 1,000 of the company currency.
            total=Coalesce(Sum(_in_base("total")), ZERO, output_field=MONEY),
        )
        return Response(
            {
                "bill_count": agg["bill_count"],
                "purchases_total": str(agg["total"]),
                "receipt_count": receipts.count(),
            }
        )


class ProfitSummaryReport(ReportView):
    report_area = "finance"

    def get(self, request):
        start, end = self.date_range(request)
        data = operating_summary(
            self.company_id(request), start, end, request.query_params.get("method", "standard")
        )
        methods = {
            "standard": _("standard"), "average": _("weighted average"), "fifo": _("FIFO"),
        }
        return Response(
            {
                **data,
                "cogs_standard_cost": data["cogs"],
                # A code the client translates; `note` stays for older clients.
                "note_code": "cogs_method",
                "note": _("COGS uses %(method)s costing.") % {
                    "method": methods.get(data["method"], data["method"]),
                },
            }
        )


class IncomeStatementReport(ReportView):
    report_area = "finance"
    """
    Profit & Loss for a period. Built entirely from source documents — invoice
    lines for revenue, the costing engine for COGS, recorded expenses for
    operating costs — so it needs no general ledger and cannot drift from the
    documents it summarises.
    """

    def get(self, request):
        start, end = self.date_range(request)
        data = operating_summary(
            self.company_id(request), start, end, request.query_params.get("method", "standard")
        )
        if self.wants_csv(request):
            rows = [
                [_("Revenue"), data["revenue"]],
                [_("Cost of goods sold"), data["cogs"]],
                [_("Gross profit"), data["gross_profit"]],
                [_("Stock adjustments (counts, damage)"), data["stock_adjustments"]],
                *[
                    [_("Expense — %(category)s") % {"category": e["category"]}, e["amount"]]
                    for e in data["expenses_by_category"]
                ],
                [_("Total expenses"), data["total_expenses"]],
                [_("Net profit"), data["net_profit"]],
            ]
            return self.csv_response(
                "income-statement.csv", [_("Line"), _("Amount")], rows
            )
        return Response(data)


class ReceivablesDueReport(ReportView):
    report_area = "sales"
    """
    Collections worklist: invoices already overdue or falling due soon, worst
    first. This is what a reminder would be built on — surfaced in-app because
    no message-delivery channel is configured (see sales/tasks.py).
    `?days=` sets the look-ahead horizon (default 7).
    """

    def get(self, request):
        from sales.models import Invoice
        from sales.tasks import DUE_SOON_DAYS

        cid = self.company_id(request)
        horizon = self.horizon_days(request, DUE_SOON_DAYS)

        today = timezone.localdate()
        invoices = open_invoices(
            Invoice.objects.filter(company_id=cid, due_date__lte=today + timedelta(days=horizon))
        ).select_related("customer")
        invoices = self.apply_branch(request, invoices, "branch")
        rows = [
            {
                "invoice": inv.id,
                "number": inv.number_display,
                "customer": inv.customer.name if inv.customer else walk_in_label(),
                "due_date": inv.due_date.isoformat() if inv.due_date else None,
                "days_overdue": max(0, (today - inv.due_date).days) if inv.due_date else 0,
                "amount_due": str(inv.outstanding),
            }
            for inv in invoices.iterator(chunk_size=2000)
        ]
        rows.sort(key=lambda r: r["days_overdue"], reverse=True)

        if self.wants_csv(request):
            return self.csv_response(
                "receivables-due.csv",
                [_("Invoice"), _("Customer"), _("Due date"), _("Days overdue"), _("Amount due")],
                [
                    [
                        r["number"],
                        r["customer"],
                        r["due_date"] or "",
                        r["days_overdue"],
                        r["amount_due"],
                    ]
                    for r in rows
                ],
            )

        return Response(
            {
                "horizon_days": horizon,
                "count": len(rows),
                "overdue_count": sum(1 for r in rows if r["days_overdue"] > 0),
                "rows": rows,
            }
        )


class CashFlowForecastReport(ReportView):
    report_area = "finance"
    """
    Forward-looking cash position, bucketed by week.

    Projects committed money only — customer invoices and supplier bills that
    already exist and carry a due date. It is a *commitment* forecast, not a
    prediction: nothing is modelled or extrapolated, so every figure traces to a
    real document. Anything already past due lands in the "overdue" bucket
    rather than being spread forward, since that cash is owed right now.
    """

    def get(self, request):
        from purchasing.models import Bill
        from sales.models import Invoice

        cid = self.company_id(request)
        try:
            weeks = max(1, min(int(request.query_params.get("weeks", 8)), 52))
        except ValueError:
            weeks = 8

        today = timezone.localdate()
        horizon = today + timedelta(weeks=weeks)

        # bucket index: -1 = already overdue, 0..weeks-1 = upcoming weeks
        def bucket_of(due):
            if due < today:
                return -1
            return min((due - today).days // 7, weeks - 1)

        buckets = {i: {"inflow": ZERO, "outflow": ZERO} for i in range(-1, weeks)}

        invoices = open_invoices(
            Invoice.objects.filter(company_id=cid, due_date__lte=horizon, due_date__isnull=False)
        ).values_list("due_date", "outstanding")
        invoices = self.apply_branch(request, invoices, "branch")
        for due_date, due in invoices.iterator(chunk_size=5000):
            buckets[bucket_of(due_date)]["inflow"] += due

        bills = open_bills(
            Bill.objects.filter(company_id=cid, due_date__lte=horizon, due_date__isnull=False)
        ).values_list("due_date", "outstanding_base")
        for due_date, due in bills.iterator(chunk_size=5000):
            buckets[bucket_of(due_date)]["outflow"] += due

        # Money is always rendered to 2dp so the client never sees a bare "0"
        # next to a "500.00" in the same column.
        cents = Decimal("0.01")
        rows, running = [], ZERO
        for i in range(-1, weeks):
            net = buckets[i]["inflow"] - buckets[i]["outflow"]
            running += net
            rows.append(
                {
                    "bucket": "overdue" if i == -1 else f"week_{i + 1}",
                    "starts_on": None if i == -1 else (today + timedelta(weeks=i)).isoformat(),
                    "inflow": str(buckets[i]["inflow"].quantize(cents)),
                    "outflow": str(buckets[i]["outflow"].quantize(cents)),
                    "net": str(net.quantize(cents)),
                    "cumulative": str(running.quantize(cents)),
                }
            )

        if self.wants_csv(request):
            return self.csv_response(
                "cash-flow-forecast.csv",
                [_("Period"), _("Starts on"), _("Expected in"), _("Expected out"), _("Net"),
                 _("Cumulative")],
                [
                    [
                        _("Overdue") if r["bucket"] == "overdue"
                        else _("Week %(number)s") % {"number": r["bucket"].split("_")[1]},
                        r["starts_on"] or "",
                        r["inflow"],
                        r["outflow"],
                        r["net"],
                        r["cumulative"],
                    ]
                    for r in rows
                ],
            )

        return Response(
            {
                "weeks": weeks,
                "generated_on": today.isoformat(),
                "closing_position": str(running.quantize(cents)),
                "rows": rows,
                "note": _("Committed documents only — no modelled or predicted amounts."),
            }
        )


class CfoKpiReport(ReportView):
    report_area = "finance"
    """
    Headline financial KPIs for the finance dashboard — liquidity, profitability
    and working-capital position in one call, so the UI makes a single request
    instead of stitching five reports together.

    Every figure is derived from documents (invoices, bills, expenses); nothing
    here needs a general ledger. Ratios return null rather than 0 when the
    denominator is zero, so the UI can show "—" instead of a misleading value.
    """

    def get(self, request):
        from purchasing.models import Bill, SupplierPayment
        from sales.models import Invoice, Payment, Refund

        cid = self.company_id(request)
        start, end = self.date_range(request)
        data = operating_summary(cid, start, end, request.query_params.get("method", "standard"))
        method = data["method"]
        revenue, cogs, opex, gross_profit, net_profit = (
            Decimal(data[key])
            for key in ("revenue", "cogs", "total_expenses", "gross_profit", "net_profit")
        )

        # --- Liquidity / working capital ------------------------------------
        # Three aggregates instead of three passes over every invoice and
        # bill in Python. Branch-scoped users see their branch's receivables;
        # payables carry no branch and stay company-wide (see the plan).
        invoices = self.apply_branch(
            request, Invoice.objects.filter(company_id=cid), "branch"
        )
        receivable = receivable_total(invoices)
        payable = payable_total(Bill.objects.filter(company_id=cid))
        overdue_receivable = receivable_total(
            invoices.filter(due_date__lt=timezone.localdate())
        )

        cash_in = self.apply_range(
            Payment.objects.filter(company_id=cid).exclude(method=Payment.STORE_CREDIT),
            "recorded_at", start, end,
        ).aggregate(t=Coalesce(Sum("amount"), ZERO, output_field=MONEY))["t"]
        cash_out = (
            self.apply_range(
                SupplierPayment.objects.filter(company_id=cid), "recorded_at", start, end
            ).aggregate(t=Coalesce(Sum(_in_base("amount")), ZERO, output_field=MONEY))["t"]
            + self.apply_range(
                Refund.objects.filter(company_id=cid), "recorded_at", start, end
            ).aggregate(t=Coalesce(Sum("amount"), ZERO, output_field=MONEY))["t"]
            + opex
        )

        def ratio(numerator, denominator):
            """Percentage, or None when undefined — never a misleading zero."""
            if not denominator:
                return None
            return str(round((numerator / denominator) * 100, 2))

        return Response(
            {
                "method": method,
                "profitability": {
                    "revenue": str(revenue),
                    "cogs": str(cogs),
                    "gross_profit": str(gross_profit),
                    "operating_expenses": str(opex),
                    "stock_adjustments": data["stock_adjustments"],
                    "net_profit": str(net_profit),
                    "gross_margin_pct": ratio(gross_profit, revenue),
                    "net_margin_pct": ratio(net_profit, revenue),
                },
                "liquidity": {
                    "cash_in": str(cash_in),
                    "cash_out": str(cash_out),
                    "net_cash_flow": str(cash_in - cash_out),
                    # Short-term cover: receivables against payables.
                    "working_capital": str(receivable - payable),
                    "current_ratio_pct": ratio(receivable, payable),
                },
                "receivables": {
                    "outstanding": str(receivable),
                    "overdue": str(overdue_receivable),
                    "overdue_pct": ratio(overdue_receivable, receivable),
                },
                "payables": {"outstanding": str(payable)},
            }
        )


class PayablesDueReport(ReportView):
    report_area = "purchasing"
    """
    The obligations side of the collections worklist: supplier bills already
    overdue or falling due soon, worst first. Lets the CFO see committed cash
    outflows without a general ledger.
    """

    def get(self, request):
        from purchasing.models import Bill

        cid = self.company_id(request)
        horizon = self.horizon_days(request, 7)
        today = timezone.localdate()
        cutoff = today + timedelta(days=horizon)

        bills = open_bills(
            Bill.objects.filter(company_id=cid, due_date__lte=cutoff)
        ).select_related("supplier")
        rows = [
            {
                "bill": b.id,
                "reference": b.supplier_invoice_number or str(b.id),
                "supplier": b.supplier.name if b.supplier else "",
                "due_date": b.due_date.isoformat() if b.due_date else None,
                "days_overdue": max(0, (today - b.due_date).days) if b.due_date else 0,
                "amount_due": str(b.outstanding_base),
            }
            for b in bills.iterator(chunk_size=2000)
        ]
        rows.sort(key=lambda r: r["days_overdue"], reverse=True)

        total = sum((Decimal(r["amount_due"]) for r in rows), ZERO)
        if self.wants_csv(request):
            return self.csv_response(
                "payables-due.csv",
                [_("Bill"), _("Supplier"), _("Due date"), _("Days overdue"), _("Amount due")],
                [
                    [
                        r["reference"],
                        r["supplier"],
                        r["due_date"] or "",
                        r["days_overdue"],
                        r["amount_due"],
                    ]
                    for r in rows
                ],
            )

        return Response(
            {
                "horizon_days": horizon,
                "count": len(rows),
                "overdue_count": sum(1 for r in rows if r["days_overdue"] > 0),
                "total_due": str(total),
                "rows": rows,
            }
        )


class CashFlowReport(ReportView):
    report_area = "finance"
    """
    Direct-method cash flow: actual money received and paid in the period.
    Inflows are customer payments; outflows are supplier payments plus recorded
    expenses. Derived from documents — no GL required.
    """

    def get(self, request):
        from finance.models import Expense
        from purchasing.models import SupplierPayment
        from sales.models import Payment, Refund

        cid = self.company_id(request)
        start, end = self.date_range(request)

        # Store credit settles a debt without money arriving.
        inflow_qs = self.apply_range(
            Payment.objects.filter(company_id=cid).exclude(method=Payment.STORE_CREDIT),
            "recorded_at", start, end,
        )
        outflow_pay_qs = self.apply_range(
            SupplierPayment.objects.filter(company_id=cid), "recorded_at", start, end
        )
        # Money handed back to customers leaves the drawer or the bank just
        # like a supplier payment does (review F03).
        refund_qs = self.apply_range(
            Refund.objects.filter(company_id=cid), "recorded_at", start, end
        )
        expense_qs = Expense.objects.filter(company_id=cid)
        if start:
            expense_qs = expense_qs.filter(date__gte=start)
        if end:
            expense_qs = expense_qs.filter(date__lte=end)

        # Supplier payments can be in a foreign currency; everything else here
        # is in the company currency. Sum each in the company currency.
        def by_method(qs, amount="amount"):
            return [
                {"method": r["method"], "amount": str(r["total"])}
                for r in qs.values("method")
                .annotate(total=Coalesce(Sum(amount), ZERO, output_field=MONEY))
                .order_by("-total")
            ]

        def total(qs, amount="amount"):
            return qs.aggregate(t=Coalesce(Sum(amount), ZERO, output_field=MONEY))["t"]

        inflows = total(inflow_qs)
        supplier_out = total(outflow_pay_qs, _in_base("amount"))
        refund_out = total(refund_qs)
        expense_out = total(expense_qs)
        outflows = supplier_out + refund_out + expense_out

        if self.wants_csv(request):
            rows = [
                [_("Cash in — customer payments"), str(inflows)],
                [_("Cash out — supplier payments"), str(supplier_out)],
                [_("Cash out — customer refunds"), str(refund_out)],
                [_("Cash out — expenses"), str(expense_out)],
                [_("Net cash flow"), str(inflows - outflows)],
            ]
            return self.csv_response("cash-flow.csv", [_("Line"), _("Amount")], rows)

        return Response(
            {
                "inflows": str(inflows),
                "inflows_by_method": by_method(inflow_qs),
                "supplier_payments": str(supplier_out),
                "customer_refunds": str(refund_out),
                "refunds_by_method": by_method(refund_qs),
                "expenses": str(expense_out),
                "outflows": str(outflows),
                "net_cash_flow": str(inflows - outflows),
            }
        )


class ZakatReport(ReportView):
    """Zakat on trade goods for the hawl day: stock, cash, bank, receivables
    less payables, at 2.5%. `valuation=sale|cost`, `exclude_doubtful=1` drops
    receivables more than 90 days overdue. The Hijri date is tabular."""

    report_area = "finance"

    def get(self, request):
        from core.hijri import format_hijri, next_occurrence, to_hijri
        from reports.zakat import zakat_base

        cid = self.company_id(request)
        valuation = request.query_params.get("valuation", "sale")
        exclude_doubtful = request.query_params.get("exclude_doubtful") in ("1", "true")
        # The owner's own count of the cash held replaces the estimate.
        raw_cash = (request.query_params.get("cash_on_hand") or "").strip()
        cash_on_hand = None
        if raw_cash:
            try:
                cash_on_hand = Decimal(raw_cash)
            except (ArithmeticError, ValueError):
                cash_on_hand = None
            if cash_on_hand is None or not cash_on_hand.is_finite() or cash_on_hand < 0:
                raise ValidationError(
                    {"cash_on_hand": _("Enter the cash on hand as an amount of zero or more.")}
                )
        data = zakat_base(
            cid, valuation=valuation, exclude_doubtful=exclude_doubtful,
            cash_on_hand=cash_on_hand,
        )
        today = timezone.localdate()
        year, month, day = to_hijri(today)
        data.update({
            "as_of": today.isoformat(),
            "hijri": {"year": year, "month": month, "day": day},
            "hijri_ar": format_hijri(today, "ar"),
            "hijri_en": format_hijri(today, "en"),
        })
        # Optional hawl anniversary (Hijri month/day) → next Gregorian date.
        try:
            hm, hd = int(request.query_params.get("hawl_month", 0)), int(
                request.query_params.get("hawl_day", 0)
            )
        except (TypeError, ValueError):
            hm = hd = 0
        if 1 <= hm <= 12 and 1 <= hd <= 30:
            data["next_hawl"] = next_occurrence(today, hm, hd).isoformat()
        if self.wants_csv(request):
            lines = [
                ("stock_at_sale", _("Stock at sale price")),
                ("stock_at_cost", _("Stock at cost")),
                ("stock", _("Stock counted")),
                ("cash_in_tills", _("Cash in tills")),
                ("bank", _("Bank balances")),
                ("receivables", _("Receivables")),
                ("doubtful_receivables", _("Doubtful receivables")),
                ("counted_receivables", _("Receivables counted")),
                ("payables", _("Payables")),
                ("base", _("Zakat base")),
                ("zakat", _("Zakat due")),
            ]
            return self.csv_response(
                "zakat.csv", [_("Line"), _("Amount")],
                [[label, str(data[key])] for key, label in lines],
            )
        return Response({k: (str(v) if isinstance(v, Decimal) else v) for k, v in data.items()})
