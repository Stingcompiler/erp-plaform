from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils.translation import gettext as _
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.activity import log_activity
from core.documents import credit_note_document, debit_note_document
from core.rbac import can_approve_high_value
from core.scoping import AppendOnlyScopedViewSet, CompanyScopedQuerySetMixin
from inventory.models import StockMovement, Warehouse
from returns.models import (
    CreditNote,
    DebitNote,
    PurchaseReturn,
    SalesReturn,
    SalesReturnLine,
)
from returns.serializers import (
    CreditNoteSerializer,
    DebitNoteSerializer,
    PurchaseReturnReadSerializer,
    PurchaseReturnWriteSerializer,
    SalesReturnReadSerializer,
    SalesReturnWriteSerializer,
)


class SalesReturnViewSet(
    CompanyScopedQuerySetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    # The `returns` app holds both sides of the business, so the module cannot
    # be inferred from the app label — see core/rbac.APP_MODULE.
    rbac_module = "sales_returns"
    branch_field = "invoice__branch"
    include_unassigned_branch_rows = False
    queryset = SalesReturn.objects.prefetch_related("lines").all()
    serializer_class = SalesReturnReadSerializer

    def create(self, request, *args, **kwargs):
        client_uuid = request.data.get("client_uuid")
        if client_uuid:
            existing = self.get_queryset().filter(client_uuid=client_uuid).first()
            if existing:
                return Response(
                    SalesReturnReadSerializer(
                        existing, context={"request": request}
                    ).data,
                    status=status.HTTP_200_OK,
                )
        serializer = SalesReturnWriteSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        try:
            sales_return = serializer.save()
        except IntegrityError:
            existing = None
            if client_uuid:
                existing = self.get_queryset().filter(client_uuid=client_uuid).first()
            if existing is None:
                raise
            return Response(
                SalesReturnReadSerializer(existing, context={"request": request}).data,
                status=status.HTTP_200_OK,
            )
        log_activity(
            action="create", request=request, entity_type="SalesReturn",
            entity_id=sales_return.id,
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def _restock_warehouses(self, request):
        """
        Warehouses this user may put returned stock into.

        Restocking is the one action that moves goods back into sellable
        inventory, so the destination has to be somewhere the user is actually
        responsible for. Company scope is a correctness boundary (Rule #1);
        branch scope is an authority one — a branch-scoped officer handling a
        return should not be able to push stock into another branch's store.
        Warehouses with no branch are shared and stay available to everyone.
        """
        qs = Warehouse.objects.filter(
            company_id=getattr(request.user, "company_id", None)
        )
        role = getattr(request.user, "role", None)
        branch_id = getattr(request.user, "branch_id", None)
        if role and role.scope_level == "branch" and branch_id:
            qs = qs.filter(Q(branch_id=branch_id) | Q(branch__isnull=True))
        return qs

    @action(detail=False, methods=["get"])
    def restock_warehouses(self, request):
        """Lets the UI offer only the warehouses the disposition call will
        accept, instead of showing every warehouse and failing on submit."""
        return Response(
            [
                {"id": w.id, "name": w.name, "code": w.code}
                for w in self._restock_warehouses(request)
            ]
        )

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def disposition(self, request, pk=None):
        """
        Deliberately decide what happens to quarantined returned stock. This is
        the ONLY path that can put a returned item back into sellable
        inventory (Rule #5): 'restock' posts a sales_return_in movement into a
        sellable warehouse; 'scrap' writes it off with no stock added back.
        Body: {"decisions": [{"line_id", "action": "restock"|"scrap",
                              "warehouse"?}]}.

        Validated in full before anything is written. `transaction.atomic` only
        rolls back on an exception, and these checks answer with a Response — so
        validating as we went would leave the first line's stock movement
        committed while the request reported failure.
        """
        sales_return = self.get_object()
        company_id = getattr(request.user, "company_id", None)
        decisions = request.data.get("decisions", [])
        if not isinstance(decisions, list) or not decisions:
            return Response(
                {"detail": "decisions must be a non-empty list."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        allowed_warehouses = self._restock_warehouses(request)

        # ---- pass 1: validate everything, write nothing ----
        planned = []
        seen = set()
        for d in decisions:
            # Two decisions for one line would both pass validation (the DB
            # still says quarantine) and then apply twice, double-counting the
            # stock.
            if d.get("line_id") in seen:
                return Response(
                    {"detail": _("Line %(line)s appears twice.") % {"line": d.get("line_id")}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            seen.add(d.get("line_id"))
            try:
                line = sales_return.lines.get(id=d.get("line_id"))
            except SalesReturnLine.DoesNotExist:
                return Response(
                    {"detail": _("Line %(line)s not in this return.") % {"line": d.get("line_id")}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if line.disposition != SalesReturnLine.QUARANTINE:
                return Response(
                    {"detail": _("Line %(line)s already dispositioned.") % {"line": line.id}},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            act = d.get("action")
            if act not in ("restock", "scrap"):
                return Response(
                    {"detail": "action must be 'restock' or 'scrap'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            wh_id = None
            if act == "restock":
                wh_id = d.get("warehouse") or sales_return.invoice.warehouse_id
                # The destination arrives in the request body, so it is checked,
                # never trusted: an unchecked id here would let a user post
                # stock into another company's warehouse — or into a branch they
                # have no responsibility for.
                if not allowed_warehouses.filter(pk=wh_id).exists():
                    return Response(
                        {
                            "detail": _(
                                "That warehouse is not one you can restock into. "
                                "Choose a warehouse in your own branch."
                            ),
                            "warehouse": wh_id,
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )
            planned.append((line, act, wh_id))

        # ---- pass 2: apply ----
        results = []
        for line, act, wh_id in planned:
            # The goods come back at the cost they left at — the sale_out
            # movement of the original invoice line carries the snapshot.
            # Costing then reverses exactly the COGS the sale booked; valuing
            # the return at today's price would invent a margin.
            sold = StockMovement.objects.filter(
                reference_type="Invoice",
                reference_id=str(sales_return.invoice_id),
                product_id=line.product_id,
                movement_type=StockMovement.SALE_OUT,
            ).order_by("id").first()
            cost = line.product.cost_price
            if sold is not None and sold.unit_cost is not None:
                cost = sold.unit_cost
            batch_id = line.batch_id or (sold.batch_id if sold else None)
            if act == "restock":
                movement = StockMovement.objects.create(
                    company_id=company_id, product=line.product,
                    warehouse_id=wh_id, batch_id=batch_id,
                    movement_type=StockMovement.SALES_RETURN_IN,
                    quantity=line.quantity, unit_cost=cost,
                    reference_type="SalesReturn",
                    reference_id=str(sales_return.id),
                    created_by=request.user if request.user.is_authenticated else None,
                )
                line.disposition = SalesReturnLine.RESTOCKED
                line.restock_warehouse_id = wh_id
                line.restock_movement = movement
                line.batch_id = batch_id
                line.save(update_fields=[
                    "disposition", "restock_warehouse", "restock_movement", "batch",
                ])
                log_activity(
                    action="create", request=request, entity_type="StockMovement",
                    entity_id=movement.pk,
                    metadata={"sales_return": sales_return.pk, "restock": True},
                )
            else:
                line.disposition = SalesReturnLine.SCRAPPED
                line.written_off_value = (line.quantity * (cost or Decimal("0"))).quantize(
                    Decimal("0.01")
                )
                line.save(update_fields=["disposition", "written_off_value"])
            results.append({"line_id": line.id, "disposition": line.disposition})

        log_activity(
            action="update", request=request, entity_type="SalesReturn",
            entity_id=sales_return.id, metadata={"disposition": results},
        )
        return Response(
            SalesReturnReadSerializer(sales_return, context={"request": request}).data
        )


class PurchaseReturnViewSet(
    CompanyScopedQuerySetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    rbac_module = "purchase_returns"
    branch_field = "warehouse__branch"
    include_unassigned_branch_rows = False
    queryset = PurchaseReturn.objects.prefetch_related("lines").all()
    serializer_class = PurchaseReturnReadSerializer

    def create(self, request, *args, **kwargs):
        client_uuid = request.data.get("client_uuid")
        if client_uuid:
            existing = self.get_queryset().filter(client_uuid=client_uuid).first()
            if existing:
                return Response(
                    PurchaseReturnReadSerializer(
                        existing, context={"request": request}
                    ).data,
                    status=status.HTTP_200_OK,
                )
        serializer = PurchaseReturnWriteSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        try:
            pr = serializer.save()
        except IntegrityError:
            existing = None
            if client_uuid:
                existing = self.get_queryset().filter(client_uuid=client_uuid).first()
            if existing is None:
                raise
            return Response(
                PurchaseReturnReadSerializer(existing, context={"request": request}).data,
                status=status.HTTP_200_OK,
            )
        log_activity(
            action="create", request=request, entity_type="PurchaseReturn",
            entity_id=pr.id,
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CreditNoteViewSet(AppendOnlyScopedViewSet):
    # A credit note reduces what a customer owes — the sales side.
    rbac_module = "sales_returns"
    branch_field = "invoice__branch"
    include_unassigned_branch_rows = False
    queryset = CreditNote.objects.select_related(
        "customer", "invoice", "company", "created_by"
    ).all()
    serializer_class = CreditNoteSerializer
    activity_entity_type = "CreditNote"

    @action(detail=True, methods=["get"])
    def document(self, request, pk=None):
        """The printable note the customer receives. Rule #6 requires one for
        every return, and until now the system created it but gave nobody a way
        to see or hand over the document."""
        return Response(credit_note_document(self.get_object()))

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        """Cancel a wrongly issued note. The row stays (Rule #9); `is_void`
        removes it from every balance. Refused once money was refunded against
        it — reverse the refund first — and reserved for a manager."""
        return _void_note(self, request, "CreditNote")


class DebitNoteViewSet(AppendOnlyScopedViewSet):
    # A debit note reduces what we owe a supplier — the purchasing side.
    rbac_module = "purchase_returns"
    branch_field = "purchase_return__warehouse__branch"
    include_unassigned_branch_rows = False
    queryset = DebitNote.objects.select_related(
        "supplier", "bill", "company", "created_by"
    ).all()
    serializer_class = DebitNoteSerializer
    activity_entity_type = "DebitNote"

    @action(detail=True, methods=["get"])
    def document(self, request, pk=None):
        return Response(debit_note_document(self.get_object()))

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        return _void_note(self, request, "DebitNote")


def _void_note(viewset, request, entity_type):
    if not can_approve_high_value(request.user):
        return Response(
            {"detail": _("Only a manager or owner may void a note.")},
            status=status.HTTP_403_FORBIDDEN,
        )
    reason = str(request.data.get("reason") or "").strip()
    if not reason:
        return Response(
            {"reason": _("A reason is required to void a note.")},
            status=status.HTTP_400_BAD_REQUEST,
        )
    with transaction.atomic():
        # Resolve through the scoped queryset (404 for another tenant), then
        # lock the bare row: FOR UPDATE cannot span the viewset's
        # select_related outer joins on PostgreSQL.
        target = viewset.get_object()
        note = type(target).objects.select_for_update().get(pk=target.pk)
        if note.is_void:
            return Response({"detail": _("This note is already void.")}, status=400)
        if entity_type == "CreditNote" and note.refunds.exists():
            return Response(
                {"detail": _("Money was refunded against this note; it cannot be voided.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Spent as store credit on another sale: voiding it left that sale
        # "paid" by credit that no longer existed.
        if entity_type == "CreditNote" and note.applications.exists():
            return Response(
                {"detail": _("This note was used as store credit on a sale; it cannot be voided.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if entity_type == "CreditNote" and note.invoice_id and note.invoice.is_void:
            return Response(
                {"detail": _("This note voided an invoice; it stands with that invoice.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        note.is_void = True
        suffix = f"VOID: {reason}"
        note.reason = (f"{note.reason} | {suffix}" if note.reason else suffix)[:255]
        note.save(update_fields=["is_void", "reason"])
        log_activity(
            action="void", request=request, entity_type=entity_type, entity_id=note.pk,
            metadata={"reason": reason, "amount": str(note.amount)},
        )
    return Response(viewset.get_serializer(note).data)
