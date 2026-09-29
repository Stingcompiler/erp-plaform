"""Stock count workflow: submit freezes the ledger, approve posts variances.

Every step is a service so the API, the sync queue and tests all run the
same code. Variances are posted as StockAdjustment rows (each with its own
`adjustment` movement), so the count leaves an ordinary, append-only trail
in the ledger and the existing adjustment screens show it.
"""

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from core.activity import log_activity
from core.rbac import APPROVER_ROLES
from inventory.models import StockAdjustment, StockCount, StockMovement


def _locked(count_id, company_id):
    return StockCount.objects.select_for_update(of=("self",)).get(
        pk=count_id, company_id=company_id
    )


def mixed_scope_skus(lines):
    """SKUs counted both as a product total (no lot) and per lot.

    ``lines`` are StockCountLine rows or the serializer's validated dicts.
    A total line and a lot line for one product each see the same stock
    and each post their own difference, so one shortage would be posted
    twice (review F07). A product is counted one way or the other."""
    totals = set()
    lots = set()
    for line in lines:
        if isinstance(line, dict):
            product, batch = line["product"], line.get("batch")
        else:
            product, batch = line.product, line.batch_id
        (lots if batch else totals).add(product)
    return sorted(product.sku for product in totals & lots)


def assert_single_scope(lines):
    skus = mixed_scope_skus(lines)
    if skus:
        raise ValidationError({"lines": _(
            "%(skus)s is counted both as a total and per lot; count it one way only."
        ) % {"skus": ", ".join(skus)}})


@transaction.atomic
def submit_count(count_id, actor, request=None):
    count = _locked(count_id, actor.company_id)
    if count.status != StockCount.DRAFT:
        raise ValidationError(_("Only a draft count can be submitted."))
    lines = list(count.lines.select_related("product"))
    if not lines:
        raise ValidationError(_("Add at least one counted line before submitting."))
    assert_single_scope(lines)
    # Two counts awaiting approval for one warehouse would post the same
    # difference twice.
    if StockCount.objects.filter(
        company_id=count.company_id, warehouse_id=count.warehouse_id,
        status=StockCount.SUBMITTED,
    ).exclude(pk=count.pk).exists():
        raise ValidationError(_(
            "Another count for this warehouse is awaiting approval; "
            "approve or cancel it first."
        ))
    # Expected quantities were frozen when the lines were saved; only a count
    # saved before that rule (no figure yet) is filled in now.
    for line in lines:
        if line.expected_quantity is None:
            line.expected_quantity = line.product.on_hand(
                warehouse=count.warehouse, batch=line.batch
            )
            line.save(update_fields=["expected_quantity"])
    count.status = StockCount.SUBMITTED
    count.counted_by = actor
    count.submitted_at = timezone.now()
    count.save(update_fields=["status", "counted_by", "submitted_at"])
    log_activity(
        action="update", user=actor, request=request,
        entity_type="StockCount", entity_id=count.pk,
        metadata={"status": count.status, "lines": len(lines)},
    )
    return count


def can_approve_count(user):
    role = getattr(user, "role", None)
    return bool(role and role.name in (APPROVER_ROLES | {"Branch Manager"}))


def may_approve(count, user):
    """What approve_count accepts, for the UI to show the right button."""
    return (
        count.status == StockCount.SUBMITTED
        and can_approve_count(user)
        and count.counted_by_id != user.pk
    )


def may_cancel(count, user):
    """The counter may withdraw their own draft or submitted count; a manager
    may cancel any count that is not yet in the ledger."""
    if count.status not in (StockCount.DRAFT, StockCount.SUBMITTED):
        return False
    return count.counted_by_id == user.pk or can_approve_count(user)


@transaction.atomic
def approve_count(count_id, actor, request=None):
    """Post one adjustment per variance line. The approver may not be the
    person who counted: that is the whole point of the second step."""
    if not can_approve_count(actor):
        raise ValidationError(_("Your role cannot approve stock counts."))
    count = _locked(count_id, actor.company_id)
    if count.status != StockCount.SUBMITTED:
        raise ValidationError(_("Only a submitted count can be approved."))
    if count.counted_by_id == actor.pk:
        raise ValidationError(_("The person who counted cannot approve their own count."))
    lines = list(count.lines.select_related("product").order_by("pk"))
    # A count saved before the one-scope rule could still hold both a total
    # and a lot line for one product; posting it would apply the difference
    # twice, so it is refused here as well.
    assert_single_scope(lines)
    posted = 0
    for line in lines:
        variance = line.variance
        if variance is None or variance == 0:
            continue
        movement = StockMovement.objects.create(
            company_id=count.company_id, product=line.product, warehouse=count.warehouse,
            batch=line.batch, movement_type=StockMovement.ADJUSTMENT, quantity=variance,
            # Valued at the product's cost at approval, like a manual
            # adjustment: the standard method's shrinkage figure then keeps
            # this count's worth when the price moves, and a found unit
            # enters the cost layers at a known cost.
            unit_cost=line.product.cost_price,
            reference_type="StockCount", reference_id=str(count.pk),
            note=f"Stock count #{count.pk}", created_by=actor,
        )
        adjustment = StockAdjustment.objects.create(
            company_id=count.company_id, product=line.product, warehouse=count.warehouse,
            batch=line.batch, quantity=variance, reason=f"Stock count #{count.pk}",
            reason_code=StockAdjustment.REASON_COUNT,
            movement=movement, created_by=actor,
        )
        line.adjustment = adjustment
        line.save(update_fields=["adjustment"])
        posted += 1
    count.status = StockCount.APPROVED
    count.approved_by = actor
    count.approved_at = timezone.now()
    count.save(update_fields=["status", "approved_by", "approved_at"])
    log_activity(
        action="approve", user=actor, request=request,
        entity_type="StockCount", entity_id=count.pk, metadata={"adjustments": posted},
    )
    return count, posted


@transaction.atomic
def cancel_count(count_id, actor, request=None):
    count = _locked(count_id, actor.company_id)
    if count.status == StockCount.APPROVED:
        raise ValidationError(_("An approved count is part of the ledger and cannot be cancelled."))
    if count.status == StockCount.CANCELLED:
        raise ValidationError(_("This count is already cancelled."))
    if not may_cancel(count, actor):
        raise ValidationError(_("Only the person who counted or a manager may cancel this count."))
    count.status = StockCount.CANCELLED
    count.save(update_fields=["status"])
    log_activity(
        action="update", user=actor, request=request,
        entity_type="StockCount", entity_id=count.pk, metadata={"status": count.status},
    )
    return count
