"""
Dispatch for offline sync operations.

Each op_type reuses the SAME serializer the online endpoint uses, so there is
one code path for "create a sale" whether it arrives live or via sync. Every
op is:
  - RBAC-checked per its module (M6),
  - idempotent (skipped as a duplicate if its client_uuid already exists),
  - isolated in its own savepoint (one bad op never rolls back the batch).
"""

import logging
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from core.activity import log_activity
from core.rbac import role_can
from inventory.models import StockAdjustment, StockMovement, StockTransfer
from inventory.serializers import (
    StockAdjustmentSerializer,
    StockMovementSerializer,
    StockTransferSerializer,
)
from hr.models import Attendance
from hr.serializers import AttendanceSerializer
from purchasing.models import GoodsReceipt, SupplierPayment
from purchasing.serializers import (
    GoodsReceiptWriteSerializer,
    SupplierPaymentSerializer,
)
from returns.models import CreditNote, DebitNote, PurchaseReturn, SalesReturn
from returns.serializers import (
    CreditNoteSerializer,
    DebitNoteSerializer,
    PurchaseReturnWriteSerializer,
    SalesReturnWriteSerializer,
)
from sales.models import Invoice, Payment, Refund
from sales.serializers import PaymentSerializer, POSCheckoutSerializer, RefundSerializer

APPLIED = "applied"
DUPLICATE = "duplicate"
ERROR = "error"

# "model" ops are ModelSerializers that need company injected on save();
# "plain" ops are Serializers whose .create() reads the company off request.user.
MODEL = "model"
PLAIN = "plain"

logger = logging.getLogger(__name__)


@dataclass
class OpSpec:
    serializer: type
    model: type
    module: str
    kind: str


OP_REGISTRY = {
    "stock_movement": OpSpec(StockMovementSerializer, StockMovement, "inventory", MODEL),
    "stock_adjustment": OpSpec(StockAdjustmentSerializer, StockAdjustment, "inventory", MODEL),
    "stock_transfer": OpSpec(StockTransferSerializer, StockTransfer, "inventory", MODEL),
    "pos_checkout": OpSpec(POSCheckoutSerializer, Invoice, "sales", PLAIN),
    "payment": OpSpec(PaymentSerializer, Payment, "sales", MODEL),
    "goods_receipt": OpSpec(GoodsReceiptWriteSerializer, GoodsReceipt, "purchasing", PLAIN),
    "supplier_payment": OpSpec(SupplierPaymentSerializer, SupplierPayment, "purchasing", MODEL),
    # Split by side of the business, matching the viewsets — an offline queue
    # must not become a way around the module gate.
    "sales_return": OpSpec(
        SalesReturnWriteSerializer, SalesReturn, "sales_returns", PLAIN
    ),
    "purchase_return": OpSpec(
        PurchaseReturnWriteSerializer, PurchaseReturn, "purchase_returns", PLAIN
    ),
    "credit_note": OpSpec(CreditNoteSerializer, CreditNote, "sales_returns", MODEL),
    # One row per employee per day; the serializer upserts, so a day marked
    # twice offline (present, then corrected to half day) lands as one row.
    "attendance": OpSpec(AttendanceSerializer, Attendance, "hr", MODEL),
    "refund": OpSpec(RefundSerializer, Refund, "sales_returns", MODEL),
    "debit_note": OpSpec(DebitNoteSerializer, DebitNote, "purchase_returns", MODEL),
}


def process_operation(request, op):
    """
    Apply one queued op. Returns (status, result_model, result_id, error, uuid).
    Never raises — failures come back as ERROR so the batch keeps going.
    """
    op_type = op.get("op_type")
    payload = dict(op.get("payload") or {})
    client_uuid = op.get("client_uuid") or payload.get("client_uuid")

    spec = OP_REGISTRY.get(op_type)
    if spec is None:
        error = _("Unknown op_type '%(op_type)s'.") % {"op_type": op_type}
        return ERROR, "", "", error, client_uuid, ""

    user = request.user
    company_id = getattr(user, "company_id", None)

    if not role_can(user, spec.module, write=True):
        return ERROR, "", "", _("Your role does not permit this operation."), client_uuid, ""

    # Idempotency: if this op's client_uuid already produced a record, skip it.
    # Attendance carries no client_uuid; it is idempotent by nature (one row
    # per employee and day, upserted by its serializer).
    idempotent_by_uuid = any(f.name == "client_uuid" for f in spec.model._meta.get_fields())
    if client_uuid and idempotent_by_uuid:
        existing = spec.model.objects.filter(
            company_id=company_id, client_uuid=client_uuid
        ).first()
        if existing:
            return DUPLICATE, spec.model.__name__, str(existing.pk), "", client_uuid, ""
        payload["client_uuid"] = str(client_uuid)

    try:
        with transaction.atomic():  # savepoint — isolates this op
            serializer = spec.serializer(
                data=payload, context={"request": request, "via_sync": True}
            )
            serializer.is_valid(raise_exception=True)
            if spec.kind == MODEL:
                obj = serializer.save(company_id=company_id)
            else:
                obj = serializer.save()
            if getattr(serializer, "superseded", False):
                # An attendance mark taken before the row's latest write (an
                # HR correction made while the device was offline): the row
                # stands. Not an error — the device has nothing to repair —
                # so it clears its queue as for any duplicate.
                log_activity(
                    action="sync_superseded", request=request,
                    entity_type=spec.model.__name__, entity_id=obj.pk,
                    metadata={"via": "sync", "op_type": op_type},
                )
                return DUPLICATE, spec.model.__name__, str(obj.pk), "", client_uuid, ""
            # Rule #8: the document exists now; its audit row must too. The
            # live endpoints log in their views, which a synced op never hits.
            log_activity(
                action="create", request=request, entity_type=spec.model.__name__,
                entity_id=obj.pk, metadata={"via": "sync", "op_type": op_type},
            )
        return APPLIED, spec.model.__name__, str(obj.pk), "", client_uuid, ""
    except ValidationError as exc:
        return ERROR, "", "", _stringify(exc.detail), client_uuid, _first_field(exc.detail)
    except IntegrityError:
        # Two devices (or two tabs) pushed the same client_uuid at once: the
        # pre-check above missed it, the unique index caught it. That is a
        # duplicate, not a failure — report the row that won so the client
        # clears its queue instead of retrying forever.
        if client_uuid and idempotent_by_uuid:
            existing = spec.model.objects.filter(
                company_id=company_id, client_uuid=client_uuid
            ).first()
            if existing:
                return DUPLICATE, spec.model.__name__, str(existing.pk), "", client_uuid, ""
        # The raw message names constraints and tables; a client only needs
        # to know the identifier is taken.
        return ERROR, "", "", _("This operation identifier is already in use."), client_uuid, ""
    except Exception:  # noqa: BLE001 - report, don't crash the batch
        # The exception text is for us, not the cashier: it is English and
        # names internals. Keep it in the log; send a sentence.
        logger.exception("sync op %s failed", op_type)
        return (
            ERROR, "", "", _("The server could not apply this operation; it has been reported."),
            client_uuid, "",
        )


def _first_field(detail):
    """Which field the refusal is about ("customer", "payment", "shift"), so
    the till can offer the right repair instead of only retry or discard."""
    if isinstance(detail, dict):
        for key in detail:
            if key != "non_field_errors":
                return str(key)[:64]
    return ""


def _stringify(detail):
    """A validation error as a sentence a cashier can read, not the
    serializer's Python repr. Field keys are dropped — the messages already
    say what is wrong — and several problems are joined on one line."""
    messages = []

    def walk(node):
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value)
        elif node is not None:
            text = str(node).strip()
            if text and text not in messages:
                messages.append(text)

    walk(detail)
    return " · ".join(messages) if messages else str(detail)
