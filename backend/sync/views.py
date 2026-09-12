from uuid import UUID

from django.core import signing
from django.core.signing import BadSignature, SignatureExpired
from django.db.models import Q
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
        if company_id is None:
            return Response({"detail": "A company is required."}, status=400)
        # A second tab can replace the shared auth cookie while this tab still
        # holds another user's cart. Never replay it under the new identity.
        expected = {"expected_company": company_id, "expected_user": request.user.pk,
                    "expected_branch": getattr(request.user, "branch_id", None)}
        for field, value in expected.items():
            if field in request.data and request.data[field] != value:
                return Response({"detail": "The signed-in account or branch changed."}, status=409)
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

        try:
            UUID(str(batch_uuid))
            if len(operations) > 100:
                raise ValueError("At most 100 operations per batch.")
            for op in operations:
                if not isinstance(op, dict) or not isinstance(op.get("payload"), dict):
                    raise ValueError("Each operation requires a payload object.")
                cu = op.get("client_uuid") or op["payload"].get("client_uuid")
                if not cu:
                    raise ValueError("Every operation requires client_uuid.")
                UUID(str(cu))
                if op.get("client_uuid") and op["payload"].get("client_uuid"):
                    if str(op["client_uuid"]) != str(op["payload"]["client_uuid"]):
                        raise ValueError("Operation and payload identifiers must match.")
        except (ValueError, TypeError, AttributeError) as exc:
            return Response({"detail": str(exc)}, status=400)

        # Batch-level idempotency: replaying a whole batch is a no-op.
        existing = SyncBatch.objects.filter(
            company_id=company_id, batch_uuid=batch_uuid
        ).first()
        if existing:
            if existing.user_id != request.user.pk:
                return Response({"detail": "Batch identifier is unavailable."}, status=409)
            if existing.operations.count() == existing.operation_count:
                return Response(
                    self._batch_response(existing, replay=True), status=status.HTTP_200_OK
                )
            # A worker/process interruption may have left a partial batch. All
            # operations carry UUIDs, so the same request can safely finish it.
            if existing.operation_count != len(operations):
                return Response({"detail": "Incomplete batch payload does not match."}, status=409)
            batch = existing
        else:
            if SyncBatch.objects.filter(batch_uuid=batch_uuid).exists():
                return Response({"detail": "Batch identifier is unavailable."}, status=409)
            batch = SyncBatch.objects.create(
                company_id=company_id, user=request.user,
                device_id=request.data.get("device_id", ""), batch_uuid=batch_uuid,
                operation_count=len(operations),
            )

        applied = batch.applied_count
        duplicate = batch.duplicate_count
        errored = batch.error_count
        completed_indexes = set(batch.operations.values_list("index", flat=True))
        for i, op in enumerate(operations):
            if i in completed_indexes:
                continue
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
            self._batch_response(batch, replay=existing is not None),
            status=status.HTTP_200_OK if existing is not None else status.HTTP_201_CREATED,
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
        ("customers", Customer, CustomerSerializer, "updated_at", "sales"),
        ("invoices", Invoice, InvoiceSerializer, "updated_at", "sales"),
        ("suppliers", Supplier, SupplierSerializer, "updated_at", "purchasing"),
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
        page_token = request.query_params.get("page_cursor")
        state = {}
        completed = set()
        if page_token:
            try:
                page = signing.loads(page_token, salt="sync-pull", max_age=86400)
                if page.get("company_id") != company_id or page.get("user_id") != request.user.pk:
                    raise BadSignature
                since_raw = page.get("since")
                snapshot = parse_datetime(page["snapshot"])
                state = page.get("state", {})
                completed = set(page.get("completed", []))
            except (BadSignature, SignatureExpired, KeyError, TypeError, ValueError):
                return Response({"detail": "Invalid or expired page_cursor."}, status=400)
        else:
            since_raw = request.query_params.get("since")
            snapshot = timezone.now()
        since = parse_datetime(since_raw) if since_raw else None
        if since_raw and since is None:
            return Response({"detail": "since must be an ISO-8601 datetime."}, status=400)

        changes = {}
        has_more = False
        for key, model, serializer_cls, ts_field, module in _pull_specs():
            if not role_can(request.user, module, write=False):
                continue
            if key in completed:
                changes[key] = []
                continue
            qs = model.objects.filter(company_id=company_id)
            if since is not None:
                qs = qs.filter(**{f"{ts_field}__gt": since})
            qs = qs.filter(**{f"{ts_field}__lte": snapshot})
            marker = state.get(key)
            if marker:
                marker_time = parse_datetime(marker["timestamp"])
                qs = qs.filter(
                    Q(**{f"{ts_field}__gt": marker_time})
                    | Q(**{ts_field: marker_time, "pk__gt": marker["id"]})
                )

            # Branch-bound documents follow the same visibility rules as their
            # normal endpoints. Shared master records remain company-wide.
            role = getattr(request.user, "role", None)
            branch_id = getattr(request.user, "branch_id", None)
            if role and role.scope_level == "branch" and branch_id:
                if key == "invoices":
                    qs = qs.filter(Q(branch_id=branch_id) | Q(branch__isnull=True))
                elif key == "stock_movements":
                    qs = qs.filter(
                        Q(warehouse__branch_id=branch_id) | Q(warehouse__branch__isnull=True)
                    )

            rows = list(qs.order_by(ts_field, "pk")[:501])
            more_for_key = len(rows) > 500
            rows = rows[:500]
            changes[key] = serializer_cls(
                rows, many=True, context={"request": request}
            ).data
            if more_for_key:
                has_more = True
                last = rows[-1]
                state[key] = {
                    "timestamp": getattr(last, ts_field).isoformat(), "id": last.pk,
                }
            else:
                completed.add(key)

        next_page_cursor = None
        if has_more:
            next_page_cursor = signing.dumps(
                {
                    "company_id": company_id,
                    "user_id": request.user.pk,
                    "since": since_raw,
                    "snapshot": snapshot.isoformat(),
                    "state": state,
                    "completed": sorted(completed),
                },
                salt="sync-pull",
                compress=True,
            )
        return Response({
            # Do not advance the durable cursor until every page was delivered.
            "cursor": snapshot.isoformat() if not has_more else since_raw,
            "has_more": has_more,
            "next_page_cursor": next_page_cursor,
            "changes": changes,
        })
