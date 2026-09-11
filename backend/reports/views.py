"""
Reporting endpoints (M9). All read-only, company-scoped, gated to the
`reports` module (M6). Every number is DERIVED from the underlying ledgers and
documents at query time — there are no stored report totals to drift.
"""

import csv
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import (
    Count,
    DecimalField,
    Sum,
)
from django.db.models.functions import Coalesce, TruncDate
from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.rbac import RoleModuleAccess
from finance.metrics import date_range, operating_summary

ZERO = Decimal("0")
MONEY = DecimalField(max_digits=20, decimal_places=2)


class ReportView(APIView):
    permission_classes = [IsAuthenticated, RoleModuleAccess]
    rbac_module = "reports"

    def company_id(self, request):
        return getattr(request.user, "company_id", None)

    def date_range(self, request):
        return date_range(request.query_params)

    def apply_range(self, qs, field, start, end):
        if start:
            qs = qs.filter(**{f"{field}__date__gte": start})
        if end:
            qs = qs.filter(**{f"{field}__date__lte": end})
        return qs

    def csv_response(self, filename, header, rows):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        writer = csv.writer(response)
        writer.writerow(header)
        writer.writerows(rows)
        return response

    def wants_csv(self, request):
        return request.query_params.get("format") == "csv"


class SalesSummaryReport(ReportView):
    def get(self, request):
        from sales.models import Invoice
        cid = self.company_id(request)
        start, end = self.date_range(request)
        qs = self.apply_range(
            Invoice.objects.filter(company_id=cid, is_void=False),
            "issued_at", start, end,
        )
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
        return Response({
            "totals": {k: str(v) if isinstance(v, Decimal) else v
                       for k, v in totals.items()},
            "daily": [
                {"day": d["day"].isoformat(), "count": d["count"],
                 "total": str(d["total"])}
                for d in daily
            ],
        })


class SalesByProductReport(ReportView):
    def get(self, request):
        from sales.models import InvoiceLine
        cid = self.company_id(request)
        start, end = self.date_range(request)
        qs = InvoiceLine.objects.filter(
            invoice__company_id=cid, invoice__is_void=False
        )
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
                ["sku", "name", "units", "revenue"],
                [[r["product__sku"], r["product__name"], r["units"], r["revenue"]]
                 for r in rows],
            )
        return Response([
            {"product": r["product"], "sku": r["product__sku"],
             "name": r["product__name"], "units": str(r["units"]),
             "revenue": str(r["revenue"])}
            for r in rows
        ])


class InventoryValuationReport(ReportView):
    def get(self, request):
        from inventory.costing import METHODS, company_totals
        from inventory.models import Product
        cid = self.company_id(request)
        method = request.query_params.get("method", "standard")
        if method not in METHODS:
            method = "standard"

        if method == "standard":
            products = Product.objects.filter(company_id=cid).annotate(
                on_hand=Coalesce(Sum("stock_movements__quantity"), ZERO)
            )
            rows = []
            total_value = ZERO
            for p in products:
                value = (p.on_hand or ZERO) * p.cost_price
                total_value += value
                rows.append({
                    "product": p.id, "sku": p.sku, "name": p.name,
                    "on_hand": str(p.on_hand or ZERO),
                    "cost_price": str(p.cost_price), "value": str(value),
                })
        else:
            totals = company_totals(cid, method=method)
            rows = []
            total_value = totals["valuation"]
            for p, res in totals["per_product"]:
                rows.append({
                    "product": p.id, "sku": p.sku, "name": p.name,
                    "on_hand": str(res["on_hand"]),
                    "cost_price": str(p.cost_price), "value": str(res["valuation"]),
                })

        if self.wants_csv(request):
            return self.csv_response(
                "inventory_valuation.csv",
                ["sku", "name", "on_hand", "cost_price", "value"],
                [[r["sku"], r["name"], r["on_hand"], r["cost_price"], r["value"]]
                 for r in rows],
            )
        return Response({
            "method": method, "total_value": str(total_value), "items": rows,
        })


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
    def get(self, request):
        from sales.models import Invoice
        cid = self.company_id(request)
        today = date.today()
        per_customer = {}
        invoices = Invoice.objects.filter(
            company_id=cid, is_void=False
        ).select_related("customer")
        for inv in invoices:
            due = inv.amount_due()
            if due <= 0:
                continue
            key = inv.customer_id
            name = inv.customer.name if inv.customer else "(walk-in)"
            # Age by *due date* so buckets mean days overdue, not days since
            # issue. Legacy rows without a due date fall back to issue date.
            reference = inv.due_date or inv.issued_at.date()
            age = (today - reference).days
            entry = per_customer.setdefault(
                key, {"customer": key, "name": name,
                      "current": ZERO, "1_30": ZERO, "31_60": ZERO,
                      "61_90": ZERO, "over_90": ZERO, "total": ZERO}
            )
            entry[_bucket(age)] += due
            entry["total"] += due
        rows = [
            {k: (str(v) if isinstance(v, Decimal) else v) for k, v in e.items()}
            for e in per_customer.values()
        ]
        return Response(rows)


class APAgingReport(ReportView):
    def get(self, request):
        from purchasing.models import Bill
        cid = self.company_id(request)
        today = date.today()
        per_supplier = {}
        bills = Bill.objects.filter(
            company_id=cid, is_void=False
        ).select_related("supplier")
        for bill in bills:
            due = bill.amount_due()
            if due <= 0:
                continue
            key = bill.supplier_id
            # Age by due date (see ARAgingReport) — falls back for legacy rows.
            reference = bill.due_date or bill.created_at.date()
            age = (today - reference).days
            entry = per_supplier.setdefault(
                key, {"supplier": key, "name": bill.supplier.name,
                      "current": ZERO, "1_30": ZERO, "31_60": ZERO,
                      "61_90": ZERO, "over_90": ZERO, "total": ZERO}
            )
            entry[_bucket(age)] += due
            entry["total"] += due
        rows = [
            {k: (str(v) if isinstance(v, Decimal) else v) for k, v in e.items()}
            for e in per_supplier.values()
        ]
        return Response(rows)


class PurchasesSummaryReport(ReportView):
    def get(self, request):
        from purchasing.models import Bill, GoodsReceipt
        cid = self.company_id(request)
        start, end = self.date_range(request)
        bills = self.apply_range(
            Bill.objects.filter(company_id=cid, is_void=False),
            "created_at", start, end,
        )
        receipts = self.apply_range(
            GoodsReceipt.objects.filter(company_id=cid),
            "received_at", start, end,
        )
        agg = bills.aggregate(
            bill_count=Count("id"),
            total=Coalesce(Sum("total"), ZERO, output_field=MONEY),
        )
        return Response({
            "bill_count": agg["bill_count"],
            "purchases_total": str(agg["total"]),
            "receipt_count": receipts.count(),
        })


class ProfitSummaryReport(ReportView):
    def get(self, request):
        start, end = self.date_range(request)
        data = operating_summary(self.company_id(request), start, end,
                                 request.query_params.get("method", "standard"))
        return Response({**data, "cogs_standard_cost": data["cogs"],
                         "note": f"COGS uses {data['method']} costing."})


class IncomeStatementReport(ReportView):
    """
    Profit & Loss for a period. Built entirely from source documents — invoice
    lines for revenue, the costing engine for COGS, recorded expenses for
    operating costs — so it needs no general ledger and cannot drift from the
    documents it summarises.
    """

    def get(self, request):
        start, end = self.date_range(request)
        data = operating_summary(self.company_id(request), start, end,
                                 request.query_params.get("method", "standard"))
        if self.wants_csv(request):
            rows = [["Revenue", data["revenue"]], ["COGS", data["cogs"]],
                    ["Gross profit", data["gross_profit"]],
                    *[[f"Expense — {e['category']}", e["amount"]]
                      for e in data["expenses_by_category"]],
                    ["Total expenses", data["total_expenses"]],
                    ["Net profit", data["net_profit"]]]
            return self.csv_response("income-statement.csv", ["Line", "Amount"], rows)
        return Response(data)


class ReceivablesDueReport(ReportView):
    """
    Collections worklist: invoices already overdue or falling due soon, worst
    first. This is what a reminder would be built on — surfaced in-app because
    no message-delivery channel is configured (see sales/tasks.py).
    `?days=` sets the look-ahead horizon (default 7).
    """

    def get(self, request):
        from sales.tasks import DUE_SOON_DAYS, due_invoices

        cid = self.company_id(request)
        try:
            horizon = int(request.query_params.get("days", DUE_SOON_DAYS))
        except ValueError:
            horizon = DUE_SOON_DAYS

        rows = [
            {
                "invoice": inv.id,
                "number": inv.number_display,
                "customer": inv.customer.name if inv.customer else "(walk-in)",
                "due_date": inv.due_date.isoformat() if inv.due_date else None,
                "days_overdue": inv.days_overdue,
                "amount_due": str(inv.amount_due()),
            }
            for inv in due_invoices(company_id=cid, horizon_days=horizon)
        ]
        rows.sort(key=lambda r: r["days_overdue"], reverse=True)

        if self.wants_csv(request):
            return self.csv_response(
                "receivables-due.csv",
                ["Invoice", "Customer", "Due date", "Days overdue", "Amount due"],
                [
                    [r["number"], r["customer"], r["due_date"] or "",
                     r["days_overdue"], r["amount_due"]]
                    for r in rows
                ],
            )

        return Response({
            "horizon_days": horizon,
            "count": len(rows),
            "overdue_count": sum(1 for r in rows if r["days_overdue"] > 0),
            "rows": rows,
        })


class CashFlowForecastReport(ReportView):
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

        today = date.today()
        horizon = today + timedelta(weeks=weeks)

        # bucket index: -1 = already overdue, 0..weeks-1 = upcoming weeks
        def bucket_of(due):
            if due < today:
                return -1
            return min((due - today).days // 7, weeks - 1)

        buckets = {i: {"inflow": ZERO, "outflow": ZERO} for i in range(-1, weeks)}

        for inv in Invoice.objects.filter(
            company_id=cid, is_void=False, due_date__lte=horizon
        ):
            due = inv.amount_due()
            if due > 0 and inv.due_date:
                buckets[bucket_of(inv.due_date)]["inflow"] += due

        for bill in Bill.objects.filter(
            company_id=cid, is_void=False, due_date__lte=horizon
        ):
            due = bill.amount_due()
            if due > 0 and bill.due_date:
                buckets[bucket_of(bill.due_date)]["outflow"] += due

        # Money is always rendered to 2dp so the client never sees a bare "0"
        # next to a "500.00" in the same column.
        cents = Decimal("0.01")
        rows, running = [], ZERO
        for i in range(-1, weeks):
            net = buckets[i]["inflow"] - buckets[i]["outflow"]
            running += net
            rows.append({
                "bucket": "overdue" if i == -1 else f"week_{i + 1}",
                "starts_on": None if i == -1 else (today + timedelta(weeks=i)).isoformat(),
                "inflow": str(buckets[i]["inflow"].quantize(cents)),
                "outflow": str(buckets[i]["outflow"].quantize(cents)),
                "net": str(net.quantize(cents)),
                "cumulative": str(running.quantize(cents)),
            })

        if self.wants_csv(request):
            return self.csv_response(
                "cash-flow-forecast.csv",
                ["Bucket", "Starts on", "Expected in", "Expected out", "Net", "Cumulative"],
                [[r["bucket"], r["starts_on"] or "", r["inflow"], r["outflow"],
                  r["net"], r["cumulative"]] for r in rows],
            )

        return Response({
            "weeks": weeks,
            "generated_on": today.isoformat(),
            "closing_position": str(running.quantize(cents)),
            "rows": rows,
            "note": "Committed documents only — no modelled or predicted amounts.",
        })


class CfoKpiReport(ReportView):
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
        from sales.models import Invoice, Payment
        cid = self.company_id(request)
        start, end = self.date_range(request)
        data = operating_summary(cid, start, end, request.query_params.get("method", "standard"))
        method = data["method"]
        revenue, cogs, opex, gross_profit, net_profit = (
            Decimal(data[key]) for key in
            ("revenue", "cogs", "total_expenses", "gross_profit", "net_profit")
        )

        # --- Liquidity / working capital ------------------------------------
        receivable = sum(
            (i.amount_due() for i in Invoice.objects.filter(
                company_id=cid, is_void=False
            )), ZERO,
        )
        payable = sum(
            (b.amount_due() for b in Bill.objects.filter(
                company_id=cid, is_void=False
            )), ZERO,
        )
        overdue_receivable = sum(
            (i.amount_due() for i in Invoice.objects.filter(
                company_id=cid, is_void=False
            ) if i.is_overdue), ZERO,
        )

        cash_in = self.apply_range(
            Payment.objects.filter(company_id=cid), "recorded_at", start, end
        ).aggregate(t=Coalesce(Sum("amount"), ZERO, output_field=MONEY))["t"]
        cash_out = self.apply_range(
            SupplierPayment.objects.filter(company_id=cid), "recorded_at", start, end
        ).aggregate(t=Coalesce(Sum("amount"), ZERO, output_field=MONEY))["t"] + opex

        def ratio(numerator, denominator):
            """Percentage, or None when undefined — never a misleading zero."""
            if not denominator:
                return None
            return str(round((numerator / denominator) * 100, 2))

        return Response({
            "method": method,
            "profitability": {
                "revenue": str(revenue),
                "cogs": str(cogs),
                "gross_profit": str(gross_profit),
                "operating_expenses": str(opex),
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
        })


class PayablesDueReport(ReportView):
    """
    The obligations side of the collections worklist: supplier bills already
    overdue or falling due soon, worst first. Lets the CFO see committed cash
    outflows without a general ledger.
    """

    def get(self, request):
        from purchasing.models import Bill

        cid = self.company_id(request)
        try:
            horizon = int(request.query_params.get("days", 7))
        except ValueError:
            horizon = 7
        cutoff = date.today() + timedelta(days=horizon)

        bills = Bill.objects.filter(
            company_id=cid, is_void=False, due_date__lte=cutoff
        ).select_related("supplier")
        rows = [
            {
                "bill": b.id,
                "reference": b.supplier_invoice_number or str(b.id),
                "supplier": b.supplier.name if b.supplier else "",
                "due_date": b.due_date.isoformat() if b.due_date else None,
                "days_overdue": b.days_overdue,
                "amount_due": str(b.amount_due()),
            }
            for b in bills
            if b.amount_due() > 0  # amount_due nets payments, so filter in Python
        ]
        rows.sort(key=lambda r: r["days_overdue"], reverse=True)

        total = sum((Decimal(r["amount_due"]) for r in rows), ZERO)
        if self.wants_csv(request):
            return self.csv_response(
                "payables-due.csv",
                ["Bill", "Supplier", "Due date", "Days overdue", "Amount due"],
                [
                    [r["reference"], r["supplier"], r["due_date"] or "",
                     r["days_overdue"], r["amount_due"]]
                    for r in rows
                ],
            )

        return Response({
            "horizon_days": horizon,
            "count": len(rows),
            "overdue_count": sum(1 for r in rows if r["days_overdue"] > 0),
            "total_due": str(total),
            "rows": rows,
        })


class CashFlowReport(ReportView):
    """
    Direct-method cash flow: actual money received and paid in the period.
    Inflows are customer payments; outflows are supplier payments plus recorded
    expenses. Derived from documents — no GL required.
    """

    def get(self, request):
        from finance.models import Expense
        from purchasing.models import SupplierPayment
        from sales.models import Payment

        cid = self.company_id(request)
        start, end = self.date_range(request)

        inflow_qs = self.apply_range(
            Payment.objects.filter(company_id=cid), "recorded_at", start, end
        )
        outflow_pay_qs = self.apply_range(
            SupplierPayment.objects.filter(company_id=cid), "recorded_at", start, end
        )
        expense_qs = Expense.objects.filter(company_id=cid)
        if start:
            expense_qs = expense_qs.filter(date__gte=start)
        if end:
            expense_qs = expense_qs.filter(date__lte=end)

        def by_method(qs):
            return [
                {"method": r["method"], "amount": str(r["total"])}
                for r in qs.values("method")
                .annotate(total=Coalesce(Sum("amount"), ZERO, output_field=MONEY))
                .order_by("-total")
            ]

        def total(qs): return qs.aggregate(  # noqa: E731
            t=Coalesce(Sum("amount"), ZERO, output_field=MONEY)
        )["t"]

        inflows = total(inflow_qs)
        supplier_out = total(outflow_pay_qs)
        expense_out = total(expense_qs)
        outflows = supplier_out + expense_out

        if self.wants_csv(request):
            rows = [
                ["Cash in — customer payments", str(inflows)],
                ["Cash out — supplier payments", str(supplier_out)],
                ["Cash out — expenses", str(expense_out)],
                ["Net cash flow", str(inflows - outflows)],
            ]
            return self.csv_response("cash-flow.csv", ["Line", "Amount"], rows)

        return Response({
            "inflows": str(inflows),
            "inflows_by_method": by_method(inflow_qs),
            "supplier_payments": str(supplier_out),
            "expenses": str(expense_out),
            "outflows": str(outflows),
            "net_cash_flow": str(inflows - outflows),
        })


# Convenience default range helper (unused by endpoints but handy for clients).
def default_range():
    end = date.today()
    return end - timedelta(days=30), end
