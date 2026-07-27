from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.activity import log_activity
from core.rbac import role_can
from sync.models import SyncBatch, SyncOperation
from sync.services import APPLIED, DUPLICATE, ERROR, process_operation


class SyncPushView(APIView):
    """
    POST /api/sync/push/
    Body: {device_id?, batch_uuid, operations: [{op_type, client_uuid?, payload}]}

    Applies a queued batch. Idempotent at batch level (re-pushing the same
    batch_uuid returns the stored results) and at op level (each op's
    client_uuid). Partial failures are isolated: a bad op reports an error and
    the rest still apply.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        company_id = getattr(request.user, "company_id", None)
        batch_uuid = request.data.get("batch_uuid")
        operations = request.data.get("operations")

        if not batch_uuid:
            return Response(
                {"detail": "batch_uuid is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(operations, list):
            return Response(
                {"detail": "operations must be a list."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Batch-level idempotency: replaying a whole batch is a no-op.
        existing = SyncBatch.objects.filter(
            company_id=company_id, batch_uuid=batch_uuid
        ).first()
        if existing:
            return Response(
                self._batch_response(existing, replay=True), status=status.HTTP_200_OK
            )

        batch = SyncBatch.objects.create(
            company_id=company_id, user=request.user,
            device_id=request.data.get("device_id", ""), batch_uuid=batch_uuid,
            operation_count=len(operations),
        )

        applied = duplicate = errored = 0
        for i, op in enumerate(operations):
            st, model, rid, err, cu = process_operation(request, op)
            SyncOperation.objects.create(
                batch=batch, index=i, op_type=op.get("op_type", ""),
                client_uuid=cu or None, status=st, result_model=model,
                result_id=rid, error_detail=err or "",
            )
            applied += int(st == APPLIED)
            duplicate += int(st == DUPLICATE)
            errored += int(st == ERROR)

        batch.applied_count = applied
        batch.duplicate_count = duplicate
        batch.error_count = errored
        batch.save(update_fields=[
            "applied_count", "duplicate_count", "error_count",
        ])

        log_activity(
            action="create", request=request, entity_type="SyncBatch",
            entity_id=batch.id,
            metadata={"applied": applied, "duplicate": duplicate, "error": errored},
        )
        return Response(
            self._batch_response(batch, replay=False), status=status.HTTP_201_CREATED
        )

    def _batch_response(self, batch, replay):
        return {
            "batch_uuid": str(batch.batch_uuid),
            "replay": replay,
            "summary": {
                "operations": batch.operation_count,
                "applied": batch.applied_count,
                "duplicate": batch.duplicate_count,
                "error": batch.error_count,
            },
            "results": [op.as_result() for op in batch.operations.all()],
        }


# Curated set of entities a client pulls, with the timestamp field used for the
# delta and the read-module that gates visibility.
def _pull_specs():
    from inventory.models import Product, StockMovement
    from inventory.serializers import ProductSerializer, StockMovementSerializer
    from purchasing.models import Supplier
    from purchasing.serializers import SupplierSerializer
    from sales.models import Customer, Invoice
    from sales.serializers import CustomerSerializer, InvoiceSerializer

    return [
        ("products", Product, ProductSerializer, "updated_at", "inventory"),
        ("stock_movements", StockMovement, StockMovementSerializer, "created_at", "inventory"),
        ("customers", Customer, CustomerSerializer, "created_at", "sales"),
        ("invoices", Invoice, InvoiceSerializer, "issued_at", "sales"),
        ("suppliers", Supplier, SupplierSerializer, "created_at", "purchasing"),
    ]


class SyncPullView(APIView):
    """
    GET /api/sync/pull/?since=<iso8601>
    Returns records changed since `since` for the entities the role may read,
    plus a fresh `cursor` to pass as `since` next time.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        company_id = getattr(request.user, "company_id", None)
        since_raw = request.query_params.get("since")
        since = parse_datetime(since_raw) if since_raw else None
        cursor = timezone.now()

        changes = {}
        for key, model, serializer_cls, ts_field, module in _pull_specs():
            if not role_can(request.user, module, write=False):
                continue
            qs = model.objects.filter(company_id=company_id)
            if since is not None:
                qs = qs.filter(**{f"{ts_field}__gt": since})
            qs = qs.order_by(ts_field)[:500]
            changes[key] = serializer_cls(
                qs, many=True, context={"request": request}
            ).data

        return Response({"cursor": cursor.isoformat(), "changes": changes})
