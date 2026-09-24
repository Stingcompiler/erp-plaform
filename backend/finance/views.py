from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter, OrderingFilter
from finance.metrics import date_range, in_range, operating_summary
from rest_framework.response import Response

from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from rest_framework import status

from core.activity import log_activity
from core.rbac import can_approve_high_value
from core.deletion import NoDeleteMixin
from core.scoping import CompanyScopedModelViewSet
from finance.models import Budget, BudgetLine, Expense
from finance.serializers import BudgetSerializer, ExpenseSerializer


class ExpenseViewSet(NoDeleteMixin, CompanyScopedModelViewSet):
    """
    Expenses are tier A: an expense feeds the income statement and every budget
    variance, and because those figures are derived, deleting one silently
    changes both with nothing left behind to reconcile against. Corrections are
    made with an offsetting negative expense.

    Corrections use a new offsetting entry, preserving the original evidence.
    """

    queryset = Expense.objects.select_related("company", "recorded_by").all()
    serializer_class = ExpenseSerializer
    activity_entity_type = "Expense"
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["category", "description"]
    ordering_fields = ["date", "amount", "category"]
    ordering = ["-date", "-id"]
    delete_denied_detail = gettext_lazy(
        "An expense cannot be deleted because it feeds the income statement "
        "and budget variance. Record an offsetting negative expense instead."
    )

    @action(detail=False, methods=["get"])
    def categories(self, request):
        """The category names this company already uses — on expenses and on
        budget lines — so the expense form and the budget editor offer one
        vocabulary. Budgets match expenses by exact category, so a free-text
        field with no shared list could never line up."""
        from finance.models import BudgetLine

        company_id = getattr(request.user, "company_id", None)
        used = set(
            Expense.objects.filter(company_id=company_id)
            .exclude(category="").values_list("category", flat=True).distinct()
        )
        planned = set(
            BudgetLine.objects.filter(budget__company_id=company_id, kind=BudgetLine.EXPENSE)
            .exclude(category="").values_list("category", flat=True).distinct()
        )
        return Response(sorted(used | planned, key=str.casefold))

    def update(self, request, *args, **kwargs):
        return Response(
            {"detail": _("Expenses are append-only. Record an offsetting correction.")},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        start, end = date_range(self.request.query_params)
        qs = in_range(qs, "date", start, end)
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)
        return qs

    @action(detail=False, methods=["get"])
    def summary(self, request):
        start, end = date_range(request.query_params)
        data = operating_summary(
            getattr(request.user, "company_id", None), start, end,
            request.query_params.get("method", "standard"),
        )
        return Response({**data, "expenses": data["total_expenses"], "net": data["net_profit"]})


class BudgetViewSet(CompanyScopedModelViewSet):
    """
    Category-level budgets. Creating and editing is ordinary finance work, but
    **activating** one is a control point: only an approver role (CFO / owner /
    GM) may approve, because the approved budget becomes the baseline every
    variance is measured against.
    """

    queryset = Budget.objects.prefetch_related("lines").select_related(
        "approved_by"
    ).all()
    serializer_class = BudgetSerializer
    activity_entity_type = "Budget"

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def destroy(self, request, *args, **kwargs):
        """A draft budget is a working document and may be thrown away. An
        approved one is the baseline every variance report is measured against,
        and carries a named approver — deleting it would erase that approval.
        Reopen it to draft first, which is itself an approver-only action."""
        budget = self.get_object()
        if budget.status != Budget.DRAFT:
            return Response(
                {
                    "detail": _(
                        "An approved budget cannot be deleted because variance "
                        "reports are measured against it. Reopen it to draft "
                        "first if it must be removed."
                    )
                },
                status=status.HTTP_405_METHOD_NOT_ALLOWED,
            )
        return super().destroy(request, *args, **kwargs)

    def _guard_approver(self, request):
        if not can_approve_high_value(request.user):
            return Response(
                {"detail": _("Only a CFO, owner or general manager may approve a budget.")},
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        budget = self.get_object()
        denied = self._guard_approver(request)
        if denied:
            return denied
        if budget.status == Budget.APPROVED:
            return Response(
                {"detail": _("This budget is already approved.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not budget.lines.exists():
            return Response(
                {"detail": _("A budget needs at least one line before approval.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        budget.status = Budget.APPROVED
        budget.approved_by = request.user
        budget.approved_at = timezone.now()
        budget.save(update_fields=["status", "approved_by", "approved_at"])
        log_activity(
            action="approve", request=request, entity_type="Budget",
            entity_id=budget.pk,
            metadata={"changes": {"status": {"before": "draft", "after": "approved"}}},
        )
        return Response(self.get_serializer(budget).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        """Send an approved budget back to draft (also approver-only)."""
        budget = self.get_object()
        denied = self._guard_approver(request)
        if denied:
            return denied
        before = budget.status
        budget.status = Budget.DRAFT
        budget.approved_by = None
        budget.approved_at = None
        budget.save(update_fields=["status", "approved_by", "approved_at"])
        log_activity(
            action="update", request=request, entity_type="Budget",
            entity_id=budget.pk,
            metadata={"changes": {"status": {"before": before, "after": "draft"}}},
        )
        return Response(self.get_serializer(budget).data)

    @action(detail=True, methods=["get"])
    def variance(self, request, pk=None):
        """
        Planned vs actual for this budget's period, per category.

        Actuals come from the same sources the income statement uses — recorded
        expenses and invoice revenue — so the two reports can never disagree.
        """
        budget = self.get_object()
        cid = budget.company_id
        cents = Decimal("0.01")

        expense_actuals = dict(
            Expense.objects.filter(
                company_id=cid,
                date__gte=budget.period_start,
                date__lte=budget.period_end,
            )
            .values_list("category")
            .annotate(total=Coalesce(Sum("amount"), Decimal("0")))
        )

        from finance.metrics import net_revenue

        # The income statement's revenue (returns and credit notes netted),
        # not gross invoice lines: the two screens disagreed on any return.
        revenue_actual = net_revenue(cid, budget.period_start, budget.period_end)

        rows = []
        revenue_counted = False
        for line in budget.lines.all():
            if line.kind == BudgetLine.REVENUE:
                # Company revenue is one figure; a second revenue line used to
                # receive it again and show revenue twice.
                actual = Decimal("0") if revenue_counted else revenue_actual
                revenue_counted = True
                # Revenue: under plan is unfavourable.
                variance = actual - line.planned_amount
            else:
                actual = expense_actuals.get(line.category, Decimal("0"))
                # Expense: over plan is unfavourable, so invert the sign.
                variance = line.planned_amount - actual
            planned = line.planned_amount
            rows.append({
                "kind": line.kind,
                "category": line.category,
                "planned": str(planned.quantize(cents)),
                "actual": str(Decimal(actual).quantize(cents)),
                "variance": str(Decimal(variance).quantize(cents)),
                "variance_pct": (
                    str(round((Decimal(variance) / planned) * 100, 2))
                    if planned else None
                ),
                "favourable": Decimal(variance) >= 0,
            })

        return Response({
            "budget": budget.id,
            "name": budget.name,
            "status": budget.status,
            "period": {
                "start": budget.period_start.isoformat(),
                "end": budget.period_end.isoformat(),
            },
            "rows": rows,
        })
