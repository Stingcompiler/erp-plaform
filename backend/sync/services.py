"""
Dispatch for offline sync operations.

Each op_type reuses the SAME serializer the online endpoint uses, so there is
one code path for "create a sale" whether it arrives live or via sync. Every
op is:
  - RBAC-checked per its module (M6),
  - idempotent (skipped as a duplicate if its client_uuid already exists),
  - isolated in its own savepoint (one bad op never rolls back the batch).
"""

from dataclasses import dataclass

from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from core.rbac import role_can
from inventory.models import StockAdjustment, StockMovement, StockTransfer
from inventory.serializers import (
    StockAdjustmentSerializer,
    StockMovementSerializer,
    StockTransferSerializer,
)
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
from sales.models import Invoice, Payment
from sales.serializers import PaymentSerializer, POSCheckoutSerializer

APPLIED = "applied"
DUPLICATE = "duplicate"
ERROR = "error"

# "model" ops are ModelSerializers that need company injected on save();
# "plain" ops are Serializers whose .create() reads the company off request.user.
MODEL = "model"
PLAIN = "plain"


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
        return ERROR, "", "", f"Unknown op_type '{op_type}'.", client_uuid

    user = request.user
    company_id = getattr(user, "company_id", None)

    if not role_can(user, spec.module, write=True):
        return ERROR, "", "", "Your role does not permit this operation.", client_uuid

    # Idempotency: if this op's client_uuid already produced a record, skip it.
    if client_uuid:
        existing = spec.model.objects.filter(
            company_id=company_id, client_uuid=client_uuid
        ).first()
        if existing:
            return DUPLICATE, spec.model.__name__, str(existing.pk), "", client_uuid
        payload["client_uuid"] = str(client_uuid)

    try:
        with transaction.atomic():  # savepoint — isolates this op
            serializer = spec.serializer(data=payload, context={"request": request})
            serializer.is_valid(raise_exception=True)
            if spec.kind == MODEL:
                obj = serializer.save(company_id=company_id)
            else:
                obj = serializer.save()
        return APPLIED, spec.model.__name__, str(obj.pk), "", client_uuid
    except ValidationError as exc:
        return ERROR, "", "", _stringify(exc.detail), client_uuid
    except IntegrityError as exc:
        # Two devices (or two tabs) pushed the same client_uuid at once: the
        # pre-check above missed it, the unique index caught it. That is a
        # duplicate, not a failure — report the row that won so the client
        # clears its queue instead of retrying forever.
        if client_uuid:
            existing = spec.model.objects.filter(
                company_id=company_id, client_uuid=client_uuid
            ).first()
            if existing:
                return DUPLICATE, spec.model.__name__, str(existing.pk), "", client_uuid
        return ERROR, "", "", str(exc), client_uuid
    except Exception as exc:  # noqa: BLE001 - report, don't crash the batch
        return ERROR, "", "", str(exc), client_uuid


def _stringify(detail):
    if isinstance(detail, (list, dict)):
        return str(detail)
    return str(detail)
