from datetime import timezone as dt_timezone
from uuid import UUID

from django.core import signing
from django.core.signing import BadSignature, SignatureExpired
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.activity import log_activity
from core.permissions import EntitlementAccess
from core.rbac import role_can
from core.scoping import apply_branch_scope
from inventory.stock_scope import branch_movements, with_on_hand
from sync.models import DiscardedOperation, SyncBatch, SyncOperation
from sync.services import APPLIED, DUPLICATE, ERROR, RETRY, process_operation


# Business-time fields a queued payload may carry (see validate_business_time).
DEVICE_TIME_FIELDS = ("occurred_at", "recorded_at", "received_at")
CLOCK_TOLERANCE_SECONDS = 120


def correct_device_clock(operations, sent_at):
    """Shift the payload times of a batch by the device's clock error.

    Cheap tablets lose their clock after a power cut. A till running fast
    stamped every sale in the future and the server refused them all (more
    than ten minutes ahead), with no repair on the device. The device sends
    its own `sent_at`; the gap to the server's clock is the device's error,
    and it applies to every time the device stamped. Returns the skew in
    seconds (0 when none was applied)."""
    sent = parse_datetime(str(sent_at)) if sent_at else None
    if sent is None:
        return 0
    if timezone.is_naive(sent):
        sent = timezone.make_aware(sent, dt_timezone.utc)
    skew = timezone.now() - sent
    if abs(skew.total_seconds()) < CLOCK_TOLERANCE_SECONDS:
        return 0
    for op in operations:
        payload = op.get("payload") if isinstance(op, dict) else None
        if not isinstance(payload, dict):
            continue
        for field in DEVICE_TIME_FIELDS:
            stamped = parse_datetime(str(payload.get(field) or "")) if payload.get(field) else None
            if stamped is not None:
                if timezone.is_naive(stamped):
                    stamped = timezone.make_aware(stamped, dt_timezone.utc)
                payload[field] = (stamped + skew).isoformat()
    return int(skew.total_seconds())


class SyncPushView(APIView):
    """
    POST /api/sync/push/
    Body: {device_id?, batch_uuid, operations: [{op_type, client_uuid?, payload}]}

    Applies a queued batch. Idempotent at batch level (re-pushing the same
    batch_uuid returns the stored results) and at op level (each op's
    client_uuid). Partial failures are isolated: a bad op reports an error and
    the rest still apply.
    """

    permission_classes = [IsAuthenticated, EntitlementAccess]

    def is_completed_entitlement_replay(self, request):
        """Allow only a completed, same-user batch to replay while writes are locked."""
        company_id = getattr(request.user, "company_id", None)
        batch_uuid = request.data.get("batch_uuid")
        if not company_id or not batch_uuid:
            return False
        try:
            UUID(str(batch_uuid))
        except (TypeError, ValueError, AttributeError):
            return False
        batch = (
            SyncBatch.objects.filter(
                company_id=company_id,
                user_id=request.user.pk,
                batch_uuid=batch_uuid,
            )
            .annotate(saved_operations=Count(
                "operations", filter=~Q(operations__status=RETRY)
            ))
            .first()
        )
        return bool(batch and batch.saved_operations == batch.operation_count)

    def post(self, request):
        company_id = getattr(request.user, "company_id", None)
        if company_id is None:
            return Response({"detail": _("A company is required.")}, status=400)
        # A second tab can replace the shared auth cookie while this tab still
        # holds another user's cart. Never replay it under the new identity.
        # A client that identifies the account it queued under must send both
        # fields; a partial pair is the one shape that cannot be trusted.
        expected = {
            "expected_company": company_id,
            "expected_user": request.user.pk,
            "expected_branch": getattr(request.user, "branch_id", None),
        }
        for field, value in expected.items():
            if field in request.data and request.data[field] != value:
                return Response(
                    {"detail": _("The signed-in account or branch changed.")}, status=409
                )
        sent = [f for f in ("expected_company", "expected_user") if f in request.data]
        if len(sent) == 1:
            return Response(
                {"detail": "expected_company and expected_user must be sent together."},
                status=400,
            )
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
        skew = correct_device_clock(operations, request.data.get("sent_at"))
        if skew:
            log_activity(
                action="device_clock_corrected", request=request, entity_type="SyncBatch",
                entity_id=str(batch_uuid), metadata={"skew_seconds": skew},
            )

        try:
            UUID(str(batch_uuid))
            if len(operations) > 100:
                raise ValueError(_("At most 100 operations per batch."))
            for op in operations:
                if not isinstance(op, dict) or not isinstance(op.get("payload"), dict):
                    raise ValueError(_("Each operation requires a payload object."))
                cu = op.get("client_uuid") or op["payload"].get("client_uuid")
                if not cu:
                    raise ValueError(_("Every operation requires client_uuid."))
                UUID(str(cu))
                if op.get("client_uuid") and op["payload"].get("client_uuid"):
                    if str(op["client_uuid"]) != str(op["payload"]["client_uuid"]):
                        raise ValueError(
                            _("Operation and payload identifiers must match.")
                        )
        except (ValueError, TypeError, AttributeError) as exc:
            return Response({"detail": str(exc)}, status=400)

        # Batch-level idempotency: replaying a whole batch is a no-op.
        existing = SyncBatch.objects.filter(
            company_id=company_id, batch_uuid=batch_uuid
        ).first()
        if existing:
            if existing.user_id != request.user.pk:
                return Response(
                    {"detail": _("Batch identifier is unavailable.")}, status=409
                )
            # A slot that came back "retry" is not done: the batch is only
            # complete once every slot has a final answer.
            done = existing.operations.exclude(status=RETRY).count()
            if done == existing.operation_count:
                return Response(
                    self._batch_response(existing, replay=True),
                    status=status.HTTP_200_OK,
                )
            # A worker/process interruption may have left a partial batch. All
            # operations carry UUIDs, so the same request can safely finish it.
            if existing.operation_count != len(operations):
                return Response(
                    {"detail": _("Incomplete batch payload does not match.")}, status=409
                )
            batch = existing
        else:
            if SyncBatch.objects.filter(batch_uuid=batch_uuid).exists():
                return Response(
                    {"detail": _("Batch identifier is unavailable.")}, status=409
                )
            try:
                with transaction.atomic():
                    batch = SyncBatch.objects.create(
                        company_id=company_id,
                        user=request.user,
                        device_id=request.data.get("device_id", ""),
                        batch_uuid=batch_uuid,
                        operation_count=len(operations),
                    )
            except IntegrityError:
                # Two tabs pushed the same batch at the same instant. The
                # loser answers 409; the client retries and gets the replay.
                return Response(
                    {"detail": _("This batch is already being processed.")}, status=409
                )

        applied = batch.applied_count
        duplicate = batch.duplicate_count
        errored = batch.error_count
        recorded = dict(batch.operations.values_list("index", "status"))
        for i, op in enumerate(operations):
            previous = recorded.get(i)
            if previous is not None and previous != RETRY:
                continue
            st, model, rid, err, cu, field = process_operation(request, op)
            row = {
                "op_type": op.get("op_type", ""),
                "client_uuid": cu or None,
                "status": st,
                "result_model": model,
                "result_id": rid,
                "error_detail": err or "",
                "error_field": field,
            }
            if previous == RETRY:
                # Re-attempt of a slot that failed temporarily last time.
                # Only a row still marked retry is overwritten: if a
                # concurrent resume settled it first, its answer stands (the
                # op is idempotent, so nothing double-applied).
                if not SyncOperation.objects.filter(
                    batch=batch, index=i, status=RETRY
                ).update(**row):
                    continue
            else:
                try:
                    with transaction.atomic():
                        SyncOperation.objects.create(batch=batch, index=i, **row)
                except IntegrityError:
                    # A concurrent resume already recorded this slot; the op
                    # itself was idempotent, so nothing double-applied.
                    continue
            applied += int(st == APPLIED)
            duplicate += int(st == DUPLICATE)
            errored += int(st == ERROR)

        batch.applied_count = applied
        batch.duplicate_count = duplicate
        batch.error_count = errored
        batch.save(
            update_fields=[
                "applied_count",
                "duplicate_count",
                "error_count",
            ]
        )

        log_activity(
            action="create",
            request=request,
            entity_type="SyncBatch",
            entity_id=batch.id,
            metadata={"applied": applied, "duplicate": duplicate, "error": errored},
        )
        return Response(
            self._batch_response(batch, replay=existing is not None),
            status=(
                status.HTTP_200_OK if existing is not None else status.HTTP_201_CREATED
            ),
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
                "retry": batch.operations.filter(status=RETRY).count(),
            },
            "results": [op.as_result() for op in batch.operations.all()],
        }


# Curated set of entities a client pulls, with the timestamp field used for the
# delta and the read-module that gates visibility.
def _pull_specs():
    """(key, model, serializer, timestamp field, read module, viewset).

    The viewset is the one that serves the entity's normal endpoint: its
    ``branch_field`` / ``include_unassigned_branch_rows`` decide what a
    branch-scoped user may see, and pull applies exactly the same rule (the
    2026-09-20 review found employees, warehouses, orders and bills leaking
    across branches through here while the screens hid them).
    """
    from hr.models import Employee
    from hr.serializers import EmployeeSerializer
    from hr.views import EmployeeViewSet
    from inventory.models import Product, StockMovement, Warehouse
    from inventory.serializers import (
        ProductSerializer,
        StockMovementSerializer,
        WarehouseSerializer,
    )
    from inventory.views import ProductViewSet, StockMovementViewSet, WarehouseViewSet
    from purchasing.models import Bill, PurchaseOrder, Supplier
    from purchasing.serializers import (
        BillSerializer,
        PurchaseOrderSerializer,
        SupplierSerializer,
    )
    from purchasing.views import BillViewSet, PurchaseOrderViewSet, SupplierViewSet
    from sales.models import Customer, Invoice
    from sales.serializers import CustomerSerializer, InvoiceSerializer
    from sales.views import CustomerViewSet, InvoiceViewSet

    # Documents written by offline devices carry BUSINESS time in created_at
    # / issued_at, which may be hours or days before the row reached the
    # server. A delta cursor on business time would skip them for every other
    # device, so those entities page on the server-stamped received_at.
    return [
        ("products", Product, ProductSerializer, "updated_at", "inventory", ProductViewSet),
        ("warehouses", Warehouse, WarehouseSerializer, "updated_at", "inventory",
         WarehouseViewSet),
        ("stock_movements", StockMovement, StockMovementSerializer, "received_at",
         "inventory", StockMovementViewSet),
        ("customers", Customer, CustomerSerializer, "updated_at", "sales", CustomerViewSet),
        ("invoices", Invoice, InvoiceSerializer, "received_at", "sales", InvoiceViewSet),
        ("suppliers", Supplier, SupplierSerializer, "updated_at", "purchasing",
         SupplierViewSet),
        # Receiving against an order and paying a bill both happen on the
        # floor with the connection down; the attendance register too.
        ("purchase_orders", PurchaseOrder, PurchaseOrderSerializer, "updated_at",
         "purchasing", PurchaseOrderViewSet),
        ("bills", Bill, BillSerializer, "updated_at", "purchasing", BillViewSet),
        ("employees", Employee, EmployeeSerializer, "updated_at", "hr", EmployeeViewSet),
    ]


# Shared with the online product screens (inventory.stock_scope), so the
# till's mirror and the catalogue page count the same shelves.
_branch_movements = branch_movements
_with_on_hand = with_on_hand


def _products_moved(company_id, user, since, snapshot):
    """Products whose stock (as this user sees it) moved in (since, snapshot].

    A subquery, so the database bounds it, never a list in Python. Paged on
    the server-stamped received_at like the stock_movements feed, and capped
    at the snapshot so every page of one pull sees the same set."""
    return (
        _branch_movements(company_id, user)
        .filter(received_at__gt=since, received_at__lte=snapshot)
        .values("product_id")
    )


# A device's first pull mirrors the history it can use, not the whole ledger:
# an old invoice is neither sold against nor collected on at the till.
INVOICE_HISTORY_DAYS = 90


class SyncPullView(APIView):
    """
    GET /api/sync/pull/?since=<iso8601>
    Returns records changed since `since` for the entities the role may read,
    plus a fresh `cursor` to pass as `since` next time.
    """

    permission_classes = [IsAuthenticated, EntitlementAccess]

    def get(self, request):
        company_id = getattr(request.user, "company_id", None)
        page_token = request.query_params.get("page_cursor")
        state = {}
        completed = set()
        if page_token:
            try:
                page = signing.loads(page_token, salt="sync-pull", max_age=86400)
                if (
                    page.get("company_id") != company_id
                    or page.get("user_id") != request.user.pk
                ):
                    raise BadSignature
                since_raw = page.get("since")
                snapshot = parse_datetime(page["snapshot"])
                state = page.get("state", {})
                completed = set(page.get("completed", []))
            except (BadSignature, SignatureExpired, KeyError, TypeError, ValueError):
                return Response(
                    {"detail": _("Invalid or expired page_cursor.")}, status=400
                )
        else:
            since_raw = request.query_params.get("since")
            snapshot = timezone.now()
        since = parse_datetime(since_raw) if since_raw else None
        if since_raw and since is None:
            return Response(
                {"detail": "since must be an ISO-8601 datetime."}, status=400
            )

        changes = {}
        has_more = False
        for key, model, serializer_cls, ts_field, module, viewset in _pull_specs():
            if not role_can(request.user, module, write=False):
                continue
            if key in completed:
                changes[key] = []
                continue
            qs = model.objects.filter(company_id=company_id)
            if since is not None:
                changed = Q(**{f"{ts_field}__gt": since})
                if key == "products":
                    # A sale or receipt changes a product's stock without
                    # touching the product row, so updated_at alone would
                    # leave the till's on_hand stale for ever.
                    changed |= Q(pk__in=_products_moved(
                        company_id, request.user, since, snapshot
                    ))
                qs = qs.filter(changed)
            elif key == "invoices":
                qs = qs.filter(
                    received_at__gte=snapshot - timezone.timedelta(days=INVOICE_HISTORY_DAYS)
                )
            qs = qs.filter(**{f"{ts_field}__lte": snapshot})
            marker = state.get(key)
            if marker:
                marker_time = parse_datetime(marker["timestamp"])
                qs = qs.filter(
                    Q(**{f"{ts_field}__gt": marker_time})
                    | Q(**{ts_field: marker_time, "pk__gt": marker["id"]})
                )

            # Exactly the normal endpoint's branch rule, taken from its
            # viewset: company-wide master data stays company-wide, branch
            # documents (and employees, warehouses, orders) stay in-branch.
            qs = apply_branch_scope(
                qs, request.user, viewset.branch_field,
                viewset.include_unassigned_branch_rows,
            )

            if key == "products":
                qs = _with_on_hand(qs, request.user)
            elif key == "customers":
                # One query for the page, not several per invoice per customer.
                from sales.querysets import with_ar_balance

                qs = with_ar_balance(qs)

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
                    "timestamp": getattr(last, ts_field).isoformat(),
                    "id": last.pk,
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
        return Response(
            {
                # Do not advance the durable cursor until every page was delivered.
                "cursor": snapshot.isoformat() if not has_more else since_raw,
                "has_more": has_more,
                "next_page_cursor": next_page_cursor,
                "changes": changes,
            }
        )


class SyncDiscardView(APIView):
    """
    POST /api/sync/discard/
    Body: {client_uuid, op_type, payload, error?, reason, device_id?}

    The device is giving up on a queued operation the server keeps rejecting.
    Nothing is applied here: the payload, the error and the reason are kept
    as evidence and surfaced to managers (attention badge), because the
    transaction already happened at the counter and the books must catch up
    by hand. Idempotent per (company, client_uuid).
    """

    permission_classes = [IsAuthenticated, EntitlementAccess]
    entitlement_exempt = True

    def post(self, request):
        company_id = getattr(request.user, "company_id", None)
        if company_id is None:
            return Response({"detail": _("A company is required.")}, status=400)
        try:
            client_uuid = UUID(str(request.data.get("client_uuid")))
        except (TypeError, ValueError, AttributeError):
            return Response({"client_uuid": _("A valid client_uuid is required.")}, status=400)
        reason = str(request.data.get("reason") or "").strip()
        if not reason:
            return Response(
                {"reason": _("A reason is required to discard an operation.")}, status=400
            )
        payload = request.data.get("payload")
        if not isinstance(payload, dict):
            return Response({"payload": _("The operation payload is required.")}, status=400)
        record, created = DiscardedOperation.objects.get_or_create(
            company_id=company_id,
            client_uuid=client_uuid,
            defaults={
                "user": request.user,
                "branch_id": getattr(request.user, "branch_id", None),
                "device_id": str(request.data.get("device_id") or "")[:128],
                "op_type": str(request.data.get("op_type") or "")[:64],
                "payload": payload,
                "error": str(request.data.get("error") or "")[:2000],
                "reason": reason[:255],
            },
        )
        if created:
            log_activity(
                action="discard", request=request, entity_type="SyncOperation",
                entity_id=str(client_uuid),
                metadata={"op_type": record.op_type, "reason": reason, "error": record.error[:255]},
            )
        return Response(
            {"id": record.id, "client_uuid": str(client_uuid), "status": "discarded"},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class DiscardedOperationListView(APIView):
    """GET /api/sync/discarded/ — what devices gave up on, for managers.
    POST /api/sync/discarded/<id>/resolve/ marks one handled."""

    permission_classes = [IsAuthenticated, EntitlementAccess]

    def get(self, request):
        from core.rbac import can_approve_high_value

        if not can_approve_high_value(request.user):
            return Response({"detail": _("Managers only.")}, status=403)
        rows = DiscardedOperation.objects.filter(
            company_id=request.user.company_id
        ).select_related("user", "branch")
        if request.query_params.get("open") == "1":
            rows = rows.filter(resolved_at__isnull=True)
        return Response([
            {
                "id": r.id, "client_uuid": str(r.client_uuid), "op_type": r.op_type,
                "payload": r.payload, "error": r.error, "reason": r.reason,
                "device_id": r.device_id, "created_at": r.created_at,
                "user": r.user.email if r.user_id else None,
                "branch": r.branch.name if r.branch_id else None,
                "resolved_at": r.resolved_at, "resolution": r.resolution,
            }
            for r in rows[:200]
        ])


class DiscardedOperationResolveView(APIView):
    permission_classes = [IsAuthenticated, EntitlementAccess]

    def post(self, request, pk):
        from core.rbac import can_approve_high_value

        if not can_approve_high_value(request.user):
            return Response({"detail": _("Managers only.")}, status=403)
        try:
            record = DiscardedOperation.objects.get(pk=pk, company_id=request.user.company_id)
        except DiscardedOperation.DoesNotExist:
            return Response({"detail": _("Not found.")}, status=404)
        if record.resolved_at is not None:
            return Response({"detail": _("Already resolved.")}, status=400)
        resolution = str(request.data.get("resolution") or "").strip()
        if not resolution:
            return Response({"resolution": _("Say how it was handled.")}, status=400)
        record.resolved_at = timezone.now()
        record.resolved_by = request.user
        record.resolution = resolution[:255]
        record.save(update_fields=["resolved_at", "resolved_by", "resolution"])
        log_activity(
            action="resolve", request=request, entity_type="DiscardedOperation",
            entity_id=record.pk, metadata={"resolution": record.resolution},
        )
        return Response({"id": record.id, "resolved_at": record.resolved_at})
