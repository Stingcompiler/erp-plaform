"""Stock as a given user sees it.

A branch-scoped user (a cashier, a branch manager) sells and counts from
their own branch's warehouses; a company-wide total hid a shortage there and
showed them other branches' shelves. Shared by the online product screens and
the offline sync pull, so the till and the catalogue page always agree.
"""
from decimal import Decimal

from django.db.models import DecimalField, OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce

from core.scoping import branch_scope_for
from inventory.models import StockMovement


def stock_branch(user):
    """The branch whose stock the user works with: a branch-scoped user's own
    branch, else None (company-wide)."""
    return branch_scope_for(user, "warehouse__branch")


def branch_movements(company_id, user, qs=None):
    """Movements of ``company_id`` limited to the user's branch warehouses.

    Warehouses with no branch are company stock, which a branch user does not
    see (WarehouseViewSet.include_unassigned_branch_rows is False)."""
    if qs is None:
        qs = StockMovement.objects.all()
    qs = qs.filter(company_id=company_id)
    branch_id = stock_branch(user)
    if branch_id is not None:
        qs = qs.filter(warehouse__branch_id=branch_id)
    return qs


def with_on_hand(qs, user):
    """Annotate ``annotated_on_hand`` from the ledger, for the user's branch
    when the user is branch-scoped. One correlated subquery rather than a
    query per product (and no join, so it survives further filtering)."""
    total = (
        branch_movements(OuterRef("company_id"), user)
        .filter(product=OuterRef("pk"))
        .order_by()
        .values("product")
        .annotate(total=Sum("quantity"))
        .values("total")[:1]
    )
    return qs.annotate(annotated_on_hand=Coalesce(
        Subquery(total, output_field=DecimalField()), Decimal("0"),
        output_field=DecimalField(),
    ))
