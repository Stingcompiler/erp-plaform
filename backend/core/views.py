from decimal import Decimal

from django.utils import timezone
from django.db import connection
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from core.models import ActivityLog
from core.permissions import IsAuditViewer
from core.rbac import access_map, role_can
from core.serializers import ActivityLogSerializer


class ActivityLogViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """
    Read-only audit trail (System Logs). Restricted to administrators
    (IsAuditViewer): platform admins see every company's activity; a company
    owner sees only their own company's. Append-only source (ActivityLog),
    exposed with filters by user, action, entity type, date range, and free text.
    """

    serializer_class = ActivityLogSerializer
    permission_classes = [IsAuditViewer]
    # user__role is joined so the serializer's user_role doesn't fire a query
    # per row.
    queryset = ActivityLog.objects.select_related(
        "user", "user__role", "company"
    ).all()

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        # Platform admins see all companies; everyone else is confined to theirs.
        if not getattr(user, "is_platform_admin", False):
            qs = qs.filter(company_id=getattr(user, "company_id", None))

        p = self.request.query_params
        if p.get("user"):
            qs = qs.filter(user_id=p["user"])
        if p.get("action"):
            qs = qs.filter(action=p["action"])
        if p.get("entity_type"):
            qs = qs.filter(entity_type__iexact=p["entity_type"])
        if p.get("start"):
            qs = qs.filter(created_at__date__gte=p["start"])
        if p.get("end"):
            qs = qs.filter(created_at__date__lte=p["end"])
        search = p.get("search")
        if search:
            qs = qs.filter(
                Q(user__email__icontains=search)
                | Q(user__full_name__icontains=search)
                | Q(entity_type__icontains=search)
                | Q(entity_id__icontains=search)
                | Q(action__icontains=search)
            )
        return qs


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """
    Unauthenticated liveness/readiness probe.

    Returns 200 with basic status info, including whether the configured
    database is reachable, so Render (and CI) can confirm the service is
    actually up rather than just "the process started".
    """
    db_ok = True
    try:
        connection.ensure_connection()
    except Exception:
        db_ok = False

    return Response(
        {
            "status": "ok",
            "service": "erp-api",
            "database": "ok" if db_ok else "unreachable",
        },
        status=200,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def rbac_access(request):
    """The current user's {module: level} access map, for building the UI nav."""
    return Response(access_map(request.user))


def _dashboard_branch(user):
    """
    The branch a branch-scoped user is confined to, or None when no branch
    narrowing applies (business/platform roles, or a branch role with no branch
    assigned). Mirrors CompanyScopedQuerySetMixin._branch_scope so the dashboard
    aggregates match exactly what the user can see on the module pages.
    """
    role = getattr(user, "role", None)
    if not (role and getattr(role, "scope_level", None) == "branch"):
        return None
    return getattr(user, "branch_id", None)


def _scope_branch(qs, branch_id, field="branch"):
    """Own-branch rows plus unassigned ones — same rule the viewsets apply."""
    if branch_id is None:
        return qs
    return qs.filter(Q(**{f"{field}_id": branch_id}) | Q(**{f"{field}__isnull": True}))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard(request):
    """
    Role-scoped dashboard: each section is included only if the user's role has
    at least read access to that module (M6). Company-scoped throughout, and
    additionally branch-scoped for branch-level roles on models that carry a
    branch dimension (invoices), so a branch manager sees their branch only.
    """
    user = request.user
    company_id = getattr(user, "company_id", None)
    branch_id = _dashboard_branch(user)
    sections = {}

    if role_can(user, "sales", write=False):
        from sales.models import Invoice
        from sales.querysets import overdue_invoices
        inv = _scope_branch(Invoice.objects.filter(company_id=company_id, is_void=False), branch_id)
        # Top products by revenue — powers the dashboard chart, scoped the same
        # way as the totals above it.
        top = (
            inv.values("lines__product__name")
            .annotate(revenue=Coalesce(Sum("lines__line_total"), Decimal("0")))
            .exclude(lines__product__name=None)
            .order_by("-revenue")[:5]
        )
        sections["sales"] = {
            "invoice_count": inv.count(),
            "today_total": str(inv.filter(issued_at__date=timezone.localdate()).aggregate(
                t=Coalesce(Sum("total"), Decimal("0")))["t"]),
            "overdue_count": overdue_invoices(inv).count(),
            "revenue_total": str(
                inv.aggregate(t=Coalesce(Sum("total"), Decimal("0")))["t"]
            ),
            "top_products": [
                {"label": r["lines__product__name"], "value": str(r["revenue"])}
                for r in top
            ],
        }

    if role_can(user, "inventory", write=False):
        from django.db.models import F
        from inventory.models import Product
        products = Product.objects.filter(company_id=company_id)
        low = products.annotate(
            oh=Coalesce(Sum("stock_movements__quantity"), Decimal("0"))
        ).filter(oh__lte=F("reorder_level"))
        sections["inventory"] = {
            "product_count": products.count(),
            "low_stock_count": low.count(),
        }

    if role_can(user, "purchasing", write=False):
        from purchasing.models import Bill, Supplier
        sections["purchasing"] = {
            "supplier_count": Supplier.objects.filter(company_id=company_id).count(),
            "bill_count": Bill.objects.filter(company_id=company_id).count(),
        }

    # Quarantined lines are customer returns awaiting disposition, so this tile
    # belongs to whoever holds the sales-returns module — not purchasing.
    if role_can(user, "sales_returns", write=False):
        from returns.models import SalesReturnLine
        pending = SalesReturnLine.objects.filter(
            sales_return__company_id=company_id, disposition="quarantine"
        ).count()
        sections["returns"] = {"pending_disposition_count": pending}

    if role_can(user, "crm", write=False):
        from crm.models import Lead
        open_leads = Lead.objects.filter(company_id=company_id).exclude(
            stage__in=Lead.CLOSED_STAGES
        )
        sections["crm"] = {
            "open_lead_count": open_leads.count(),
            "pipeline_value": str(
                open_leads.aggregate(
                    t=Coalesce(Sum("estimated_value"), Decimal("0"))
                )["t"]
            ),
        }

    if role_can(user, "hr", write=False):
        from hr.models import Employee, LeaveRequest
        sections["hr"] = {
            "employee_count": Employee.objects.filter(company_id=company_id)
            .exclude(status=Employee.STATUS_TERMINATED)
            .count(),
            "pending_leave_count": LeaveRequest.objects.filter(
                company_id=company_id, status=LeaveRequest.PENDING
            ).count(),
        }

    if role_can(user, "finance", write=False):
        from finance.metrics import operating_summary
        figures = operating_summary(company_id)
        sections["finance"] = {
            **figures, "expenses": figures["total_expenses"], "net": figures["net_profit"],
        }

    if role_can(user, "website", write=False):
        from website.models import Section, Website
        site = Website.objects.filter(company_id=company_id).first()
        sections["website"] = {
            "is_published": bool(site and site.is_published),
            "section_count": Section.objects.filter(company_id=company_id).count(),
            "published_at": (
                site.published_at.isoformat() if site and site.published_at else None
            ),
        }

    setup = []
    if company_id and role_can(user, "settings", write=True):
        from accounts.models import User
        from inventory.models import Product, StockMovement, Warehouse
        from sales.models import Invoice
        company = user.company
        checks = [
            ("companyStep",
             "/settings",
             bool(
                 company.name and company.currency and (
                     company.phone or company.email)),
                "settings"),
            ("warehouseStep",
             "/org",
             Warehouse.objects.filter(
                 company_id=company_id,
                 is_active=True).exists(),
                "org"),
            ("productStep",
             "/inventory",
             Product.objects.filter(
                 company_id=company_id,
                 is_active=True).exists() and (
                 StockMovement.objects.filter(
                     company_id=company_id,
                     quantity__gt=0).exists() or not Product.objects.filter(
                     company_id=company_id,
                     is_active=True,
                     is_stock_tracked=True).exists()),
             "inventory"),
            ("userStep",
             "/users",
             User.objects.filter(
                 company_id=company_id,
                 is_active=True).exists(),
             "users"),
            ("saleStep",
             "/sales",
             Invoice.objects.filter(
                 company_id=company_id,
                 is_void=False).exists(),
             "sales"),
        ]
        setup = [{"key": key, "href": href, "done": done} for key, href, done, module in checks
                 if role_can(user, module, write=True)]
    return Response({"role": getattr(user.role, "name", None), "sections": sections,
                     "setup": setup, "currency": user.company.currency if company_id else None})
