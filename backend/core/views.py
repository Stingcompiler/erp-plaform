from decimal import Decimal

from django.conf import settings
from django.utils import timezone
from django.db import connection
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from rest_framework import mixins, viewsets
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from core.models import ActivityLog
from core.permissions import IsAuditViewer
from core.rbac import access_map, can_approve_high_value, role_can
from core.serializers import ActivityLogSerializer


class ActivityLogViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """
    Read-only audit trail (System Logs). Restricted to company oversight roles;
    platform staff do not receive tenant activity through this endpoint.
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
@authentication_classes([])
@permission_classes([AllowAny])
def health_check(request):
    """
    Unauthenticated liveness/readiness probe. It deliberately skips JWT
    authentication too: a stale cookie or unavailable user table must not turn
    the endpoint Render uses for recovery into an opaque 500 response.

    Returns 200 with basic status info, including whether the configured
    database is reachable, so Render (and CI) can confirm the service is
    actually up rather than just "the process started".
    """
    db_ok = True
    try:
        connection.ensure_connection()
    except Exception:
        db_ok = False

    from config.deployment import get_deployment_config
    from ops.release import application_version

    from core.public_media import media_health

    config = get_deployment_config()
    payload = {
        "status": "ok",
        "service": "erp-api",
        "database": "ok" if db_ok else "unreachable",
        "deployment_mode": config.mode,
        "version": application_version(),
        # Uploads: on ephemeral storage every deploy wipes them; a picture a
        # merchant uploaded then 404s. The first thing to check.
        "media": media_health(),
    }
    # On a customer's server this is what support asks for first: which
    # installation, which release, and whether the licence is the problem.
    # No secrets — the installation id is not a credential, the licence is
    # bound to it by signature.
    if config.is_standalone and db_ok:
        try:
            from licensing.models import Installation
            from licensing.services import active_license, resolve_license_entitlements

            installation = Installation.objects.order_by("pk").first()
            activation = active_license()
            decision = resolve_license_entitlements()
            payload["installation_id"] = (
                str(installation.installation_id) if installation else None
            )
            payload["licence"] = {
                "state": decision.state,
                "allow_writes": decision.allow_writes,
                "kind": activation.kind if activation else None,
                "usable_until": (
                    activation.usable_until.isoformat()
                    if activation and activation.usable_until else None
                ),
                "max_application_version": (
                    activation.max_application_version if activation else None
                ),
            }
        except Exception:  # noqa: BLE001 - health must never 500 on a licence problem
            payload["licence"] = {"state": "unknown"}
    return Response(payload, status=200)


@api_view(["GET"])
@permission_classes([AllowAny])
def api_index(request):
    """
    Root of the Django service. The REST API lives under /api/ and the UI is a
    separate Next.js app — in development that app runs on its own origin
    (the first CORS_ALLOWED_ORIGINS entry, normally http://localhost:3000),
    and in production the exported build is served from this same origin by
    core/frontend.py.

    This view is wired in only when DEBUG is True (see config/urls.py), so
    production's "/" still resolves to the served frontend index.html. Its only
    job is to answer a hand-typed API-root request with a useful pointer
    instead of a bare Django 404.
    """
    dev_origin = next(iter(settings.CORS_ALLOWED_ORIGINS), None)
    return Response(
        {
            "service": "erp-api",
            "status": "ok",
            "api_root": request.build_absolute_uri("/api/"),
            "health": request.build_absolute_uri("/api/health/"),
            "admin": request.build_absolute_uri("/admin/"),
            # In dev the UI is not served here — point at the Next.js app.
            "ui": dev_origin or "served from this origin",
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
    narrowing applies. A branch role with no branch is rejected before it can
    reach this endpoint; retaining no fallback here keeps aggregates fail-closed
    if that invariant is ever bypassed.
    """
    role = getattr(user, "role", None)
    if not (role and getattr(role, "scope_level", None) == "branch"):
        return None
    return getattr(user, "branch_id", None)


def _scope_branch(qs, branch_id, field="branch"):
    """Restrict a branch-scoped aggregate to its assigned branch exactly."""
    if branch_id is None:
        return qs
    return qs.filter(**{f"{field}_id": branch_id})


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
        from sales.debt_queries import debt_summary
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
        # Receivables use the same derived calculation as the debt ledger so
        # the overview can never show a balance that disagrees with its detail.
        sections["debts"] = debt_summary(user)

    if role_can(user, "inventory", write=False):
        from django.db.models import F
        from inventory.models import Product
        products = Product.objects.filter(company_id=company_id)
        low = products.annotate(
            oh=Coalesce(Sum("stock_movements__quantity"), Decimal("0"))
        ).filter(oh__lte=F("reorder_level"))
        from inventory.alerts import expiring_batches, negative_stock
        sections["inventory"] = {
            "product_count": products.count(),
            "low_stock_count": low.count(),
            # Lots expiring within 30 days (or already expired) that still
            # have stock, and ledger balances below zero left by offline sales
            # — both need a person, not just a number.
            "expiring_batch_count": expiring_batches(company_id).count(),
            "negative_stock_count": negative_stock(company_id).count(),
        }

    if role_can(user, "purchasing", write=False):
        from purchasing.models import Bill, Supplier
        # Bills and suppliers have no branch key yet. Do not expose company
        # totals to a branch user while their storage model remains shared.
        if branch_id is None:
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
        employees = _scope_branch(
            Employee.objects.filter(company_id=company_id), branch_id
        )
        leave_requests = _scope_branch(
            LeaveRequest.objects.filter(company_id=company_id), branch_id,
            field="employee__branch",
        )
        sections["hr"] = {
            "employee_count": employees
            .exclude(status=Employee.STATUS_TERMINATED)
            .count(),
            "pending_leave_count": leave_requests.filter(status=LeaveRequest.PENDING).count(),
        }

    # Salary advances remain HR requests, but the financial decision belongs
    # to the CFO/executive approver. Keep this alert out of every other
    # dashboard so a request's amount and count do not leak across roles.
    if company_id and can_approve_high_value(user):
        from hr.models import SalaryAdvance
        pending_advances = SalaryAdvance.objects.filter(
            company_id=company_id, status=SalaryAdvance.PENDING
        )
        sections["salary_advances"] = {
            "pending_count": pending_advances.count(),
            "pending_total": str(
                pending_advances.aggregate(t=Coalesce(Sum("amount"), Decimal("0")))["t"]
            ),
        }

    # HR submits and follows up salary-advance requests but cannot decide
    # them. Give HR a concise status summary so the team knows whether action
    # is still pending with finance or a decision has been made.
    if (
        company_id
        and role_can(user, "hr", write=True)
        and not can_approve_high_value(user)
    ):
        from hr.models import SalaryAdvance
        advance_requests = SalaryAdvance.objects.filter(company_id=company_id)
        sections["advance_requests"] = {
            "pending_count": advance_requests.filter(status=SalaryAdvance.PENDING).count(),
            "approved_count": advance_requests.filter(status=SalaryAdvance.APPROVED).count(),
            "rejected_count": advance_requests.filter(status=SalaryAdvance.REJECTED).count(),
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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def attention(request):
    """Badge counts for the signed-in user: what appeared since they last looked."""
    from core import attention as attention_service

    return Response(attention_service.counts_for(request.user))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def attention_seen(request):
    """The user opened `key`; its badge starts again from now."""
    from core import attention as attention_service

    key = str(request.data.get("key") or "").strip()
    if not key:
        return Response({"key": ["This field is required."]}, status=400)
    known = attention_service.mark_seen(request.user, key)
    return Response({"key": key, "known": known, "seen_at": timezone.now().isoformat()})
