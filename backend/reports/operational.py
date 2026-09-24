"""Operational reports the build plan named beside the financial ones
(M5 "Returns Report", M9 "Payment Reconciliation report (recorded vs.
verified)" and CRM reports). Same contract as every report here: company
scoped, branch scoped for branch-level roles, `?start=&end=`, `?format=csv`."""
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from rest_framework.response import Response

from core.timezone import company_zone
from reports.views import MONEY, ZERO, ReportView

QTY = DecimalField(max_digits=16, decimal_places=3)
BASE = ExpressionWrapper(F("amount") * F("exchange_rate"), output_field=MONEY)


def _money(value):
    return str(Decimal(value or 0).quantize(Decimal("0.01")))


def _total(qs, expression):
    return qs.aggregate(t=Coalesce(Sum(expression), ZERO, output_field=MONEY))["t"]


def _qty(value):
    return str(Decimal(value or 0).normalize()) if value else "0"


# CSV cells carry words, not codes: the model choices' labels are English and
# untranslated, so the export has its own translated labels.
DISPOSITIONS = {
    "quarantine": gettext_lazy("Quarantine (pending)"),
    "restocked": gettext_lazy("Restocked to sellable"),
    "scrapped": gettext_lazy("Scrapped / written off"),
}
STAGES = {
    "new": gettext_lazy("New"),
    "contacted": gettext_lazy("Contacted"),
    "qualified": gettext_lazy("Qualified"),
    "proposal": gettext_lazy("Proposal sent"),
    "won": gettext_lazy("Won"),
    "lost": gettext_lazy("Lost"),
}
PAYMENT_METHODS = {
    "cash": gettext_lazy("Cash"),
    "bank_transfer": gettext_lazy("Bank transfer"),
    "credit": gettext_lazy("Store credit"),
}


def _label(labels, code):
    return str(labels[code]) if code in labels else code


def _local(request, moment, fmt="%Y-%m-%d %H:%M"):
    """A timestamp as the company's clock reads it — a sale at 00:30 in
    Khartoum is that day's, not the previous day's UTC date."""
    if not moment:
        return ""
    company = getattr(request.user, "company", None)
    return timezone.localtime(moment, company_zone(company)).strftime(fmt)


class SalesReturnsReport(ReportView):
    """What customers brought back, where it went (quarantine, restocked,
    scrapped) and what it cost in credit notes, refunds and write-offs."""

    report_area = "sales"

    def get(self, request):
        from returns.models import CreditNote, SalesReturn, SalesReturnLine
        from sales.models import Refund

        cid = self.company_id(request)
        start, end = self.date_range(request)
        returns = self.apply_branch(
            request,
            self.apply_range(
                SalesReturn.objects.filter(company_id=cid), "created_at", start, end
            ),
            "invoice__branch",
        )
        lines = SalesReturnLine.objects.filter(sales_return__in=returns)
        notes = CreditNote.objects.filter(sales_return__in=returns, is_void=False)
        refunds = Refund.objects.filter(credit_note__in=notes)

        if self.wants_csv(request):
            rows = [
                [
                    line.sales_return_id,
                    _local(request, line.sales_return.created_at),
                    line.sales_return.invoice.number if line.sales_return.invoice_id else "",
                    line.sales_return.customer.name if line.sales_return.customer_id else "",
                    line.product.sku, line.product.name, line.quantity,
                    _label(DISPOSITIONS, line.disposition),
                    line.sales_return.reason,
                ]
                for line in lines.select_related(
                    "sales_return__invoice", "sales_return__customer", "product"
                ).order_by("sales_return__created_at", "id")
            ]
            return self.csv_response(
                "sales-returns.csv",
                [_("Return"), _("Date"), _("Invoice"), _("Customer"), _("SKU"), _("Product"),
                 _("Quantity"), _("Disposition"), _("Reason")],
                rows,
            )

        totals = lines.aggregate(
            n=Count("id"),
            qty=Coalesce(Sum("quantity"), Decimal("0"), output_field=QTY),
            written_off=Coalesce(Sum("written_off_value"), ZERO, output_field=MONEY),
        )
        by_disposition = [
            {"disposition": row["disposition"], "quantity": _qty(row["qty"])}
            for row in lines.values("disposition").annotate(
                qty=Coalesce(Sum("quantity"), Decimal("0"), output_field=QTY)
            ).order_by("disposition")
        ]
        top_products = [
            {"product": row["product"], "name": row["product__name"], "quantity": _qty(row["qty"])}
            for row in lines.values("product", "product__name").annotate(
                qty=Sum("quantity")
            ).order_by("-qty")[:10]
        ]
        by_reason = [
            {"reason": row["reason"] or "", "count": row["n"]}
            for row in returns.values("reason").annotate(n=Count("id")).order_by("-n")[:10]
        ]
        return Response({
            "return_count": returns.count(),
            "line_count": totals["n"],
            "quantity": _qty(totals["qty"]),
            "credit_total": _money(_total(notes, BASE)),
            "refund_total": _money(_total(refunds, "amount")),
            "written_off_total": _money(totals["written_off"]),
            "by_disposition": by_disposition,
            "by_reason": by_reason,
            "top_products": top_products,
        })


class PurchaseReturnsReport(ReportView):
    """What went back to suppliers and the debit notes it raised."""

    report_area = "purchasing"

    def get(self, request):
        from returns.models import DebitNote, PurchaseReturn, PurchaseReturnLine

        cid = self.company_id(request)
        start, end = self.date_range(request)
        returns = self.apply_branch(
            request,
            self.apply_range(
                PurchaseReturn.objects.filter(company_id=cid), "created_at", start, end
            ),
            "warehouse__branch",
        )
        lines = PurchaseReturnLine.objects.filter(purchase_return__in=returns)
        notes = DebitNote.objects.filter(purchase_return__in=returns, is_void=False)

        if self.wants_csv(request):
            rows = [
                [
                    line.purchase_return_id,
                    _local(request, line.purchase_return.created_at),
                    line.purchase_return.supplier.name,
                    line.product.sku, line.product.name, line.quantity,
                    line.purchase_return.reason,
                ]
                for line in lines.select_related(
                    "purchase_return__supplier", "product"
                ).order_by("purchase_return__created_at", "id")
            ]
            return self.csv_response(
                "purchase-returns.csv",
                [_("Return"), _("Date"), _("Supplier"), _("SKU"), _("Product"), _("Quantity"),
                 _("Reason")],
                rows,
            )

        totals = lines.aggregate(
            n=Count("id"), qty=Coalesce(Sum("quantity"), Decimal("0"), output_field=QTY)
        )
        by_supplier = [
            {
                "supplier": row["supplier"], "name": row["supplier__name"],
                "count": row["n"], "amount": _money(row["amount"]),
            }
            for row in notes.values("supplier", "supplier__name").annotate(
                n=Count("id"), amount=Coalesce(Sum(BASE), ZERO, output_field=MONEY)
            ).order_by("-amount")[:10]
        ]
        top_products = [
            {"product": row["product"], "name": row["product__name"], "quantity": _qty(row["qty"])}
            for row in lines.values("product", "product__name").annotate(
                qty=Sum("quantity")
            ).order_by("-qty")[:10]
        ]
        return Response({
            "return_count": returns.count(),
            "line_count": totals["n"],
            "quantity": _qty(totals["qty"]),
            "debit_total": _money(_total(notes, BASE)),
            "by_supplier": by_supplier,
            "top_products": top_products,
        })


class PaymentReconciliationReport(ReportView):
    """Recorded vs verified (M9): every payment taken in the period, how much
    of it a manager has confirmed against the bank, and what is still waiting
    — per receiving account, because that is how a statement is checked."""

    report_area = "finance"

    def get(self, request):
        from sales.models import Payment

        cid = self.company_id(request)
        start, end = self.date_range(request)
        payments = self.apply_branch(
            request,
            self.apply_range(
                Payment.objects.filter(company_id=cid).exclude(method=Payment.STORE_CREDIT),
                "recorded_at", start, end,
            ),
            "invoice__branch",
        )

        if self.wants_csv(request):
            rows = [
                [
                    p.pk, _local(request, p.recorded_at), p.invoice.number_display,
                    p.invoice.customer.name if p.invoice.customer_id else "",
                    _label(PAYMENT_METHODS, p.method),
                    p.company_bank_account.bank_name if p.company_bank_account_id else "",
                    p.transfer_reference, p.amount, p.currency,
                    _("Verified") if p.verified_at else _("Unverified"),
                    _local(request, p.verified_at),
                ]
                for p in payments.select_related(
                    "invoice__customer", "company_bank_account"
                ).order_by("recorded_at", "id")
            ]
            return self.csv_response(
                "payment-reconciliation.csv",
                [_("Payment"), _("Recorded at"), _("Invoice"), _("Customer"), _("Method"),
                 _("Account"), _("Reference"), _("Amount"), _("Currency"), _("Status"),
                 _("Verified at")],
                rows,
            )

        def bucket(qs):
            agg = qs.aggregate(n=Count("id"), t=Coalesce(Sum(BASE), ZERO, output_field=MONEY))
            return {"count": agg["n"], "amount": _money(agg["t"])}

        verified_qs = payments.filter(verified_at__isnull=False)
        unverified_qs = payments.filter(verified_at__isnull=True)
        recorded = bucket(payments)
        verified = bucket(verified_qs)
        unverified = bucket(unverified_qs)
        rate = (
            round(verified["count"] * 100 / recorded["count"], 1) if recorded["count"] else None
        )
        oldest = unverified_qs.order_by("recorded_at").values_list("recorded_at", flat=True).first()
        by_account = [
            {
                "account": row["company_bank_account"],
                # Two accounts at one bank (a current account and its Bankak
                # wallet, say) must read apart, the way a statement shows
                # them: bank · account name · last four digits.
                "name": " · ".join(
                    part for part in (
                        row["company_bank_account__bank_name"],
                        row["company_bank_account__account_name"],
                        (row["company_bank_account__account_number"] or "")[-4:],
                    ) if part
                ),
                "method": row["method"],
                "recorded": _money(row["recorded"]),
                "verified": _money(row["verified"]),
                "unverified": _money(row["recorded"] - row["verified"]),
            }
            for row in payments.values(
                "company_bank_account", "company_bank_account__bank_name",
                "company_bank_account__account_name",
                "company_bank_account__account_number", "method",
            ).annotate(
                recorded=Coalesce(Sum(BASE), ZERO, output_field=MONEY),
                verified=Coalesce(
                    Sum(BASE, filter=Q(verified_at__isnull=False)), ZERO, output_field=MONEY
                ),
            ).order_by("method", "company_bank_account__bank_name")
        ]
        return Response({
            "recorded": recorded,
            "verified": verified,
            "unverified": unverified,
            "verified_rate": rate,
            "oldest_unverified_days": (timezone.now() - oldest).days if oldest else None,
            "by_account": by_account,
        })


class CrmReport(ReportView):
    """The pipeline now (leads by stage and open value), what came in during
    the period, win rate of closed leads, and follow-ups that are late."""

    report_area = "sales"
    # Leads carry names and phone numbers: the sales report area is not
    # enough, the reader must be allowed into the CRM itself.
    report_module = "crm"

    OPEN_STAGES = ("new", "contacted", "qualified", "proposal")

    def get(self, request):
        from crm.models import FollowUp, Lead

        cid = self.company_id(request)
        start, end = self.date_range(request)
        leads = self.apply_branch(request, Lead.objects.filter(company_id=cid), "branch")

        if self.wants_csv(request):
            rows = [
                [
                    lead.pk, _local(request, lead.created_at, "%Y-%m-%d"), lead.name,
                    lead.contact_name, lead.phone, lead.source, _label(STAGES, lead.stage),
                    lead.estimated_value,
                    lead.assigned_to.email if lead.assigned_to_id else "",
                ]
                for lead in self.apply_range(leads, "created_at", start, end)
                .select_related("assigned_to").order_by("created_at", "id")
            ]
            return self.csv_response(
                "crm-leads.csv",
                [_("Lead"), _("Created"), _("Name"), _("Contact"), _("Phone"), _("Source"),
                 _("Stage"), _("Estimated value"), _("Assigned to")],
                rows,
            )

        stages = {
            row["stage"]: row
            for row in leads.values("stage").annotate(
                n=Count("id"),
                value=Coalesce(Sum("estimated_value"), ZERO, output_field=MONEY),
            )
        }
        order = [choice[0] for choice in Lead._meta.get_field("stage").choices]
        won = stages.get("won", {}).get("n", 0)
        lost = stages.get("lost", {}).get("n", 0)
        pipeline = sum(
            (stages[s]["value"] for s in self.OPEN_STAGES if s in stages), Decimal("0")
        )
        today = timezone.localdate()
        follow_ups = FollowUp.objects.filter(lead__in=leads)
        done_in_range = self.apply_range(follow_ups.filter(done=True), "done_at", start, end)
        by_source = [
            {"source": row["source"] or "", "count": row["n"]}
            for row in self.apply_range(leads, "created_at", start, end)
            .values("source").annotate(n=Count("id")).order_by("-n")[:10]
        ]
        return Response({
            "stages": [
                {"stage": s, "count": stages.get(s, {}).get("n", 0),
                 "value": _money(stages.get(s, {}).get("value", 0))}
                for s in order
            ],
            "new_leads": self.apply_range(leads, "created_at", start, end).count(),
            "won": won,
            "lost": lost,
            "conversion_rate": round(won * 100 / (won + lost), 1) if (won + lost) else None,
            "pipeline_value": _money(pipeline),
            "by_source": by_source,
            "follow_ups": {
                "overdue": follow_ups.filter(done=False, due_date__lt=today).count(),
                "due_today": follow_ups.filter(done=False, due_date=today).count(),
                "done_in_range": done_in_range.count(),
            },
        })
