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


@transaction.atomic
def submit_count(count_id, actor, request=None):
    count = _locked(count_id, actor.company_id)
    if count.status != StockCount.DRAFT:
        raise ValidationError(_("Only a draft count can be submitted."))
    lines = list(count.lines.select_related("product"))
    if not lines:
        raise ValidationError(_("Add at least one counted line before submitting."))
    for line in lines:
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
    posted = 0
    for line in count.lines.select_related("product").order_by("pk"):
        variance = line.variance
        if variance is None or variance == 0:
            continue
        movement = StockMovement.objects.create(
            company_id=count.company_id, product=line.product, warehouse=count.warehouse,
            batch=line.batch, movement_type=StockMovement.ADJUSTMENT, quantity=variance,
            reference_type="StockCount", reference_id=str(count.pk),
            note=f"Stock count #{count.pk}", created_by=actor,
        )
        adjustment = StockAdjustment.objects.create(
            company_id=count.company_id, product=line.product, warehouse=count.warehouse,
            batch=line.batch, quantity=variance, reason=f"Stock count #{count.pk}",
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
    count.status = StockCount.CANCELLED
    count.save(update_fields=["status"])
    log_activity(
        action="update", user=actor, request=request,
        entity_type="StockCount", entity_id=count.pk, metadata={"status": count.status},
    )
    return count
