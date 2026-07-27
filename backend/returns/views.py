from django.db import transaction
from django.db.models import Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.activity import log_activity
from core.documents import credit_note_document, debit_note_document
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
        sales_return = serializer.save()
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
                    {"detail": f"Line {d.get('line_id')} appears twice."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            seen.add(d.get("line_id"))
            try:
                line = sales_return.lines.get(id=d.get("line_id"))
            except SalesReturnLine.DoesNotExist:
                return Response(
                    {"detail": f"Line {d.get('line_id')} not in this return."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if line.disposition != SalesReturnLine.QUARANTINE:
                return Response(
                    {"detail": f"Line {line.id} already dispositioned."},
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
                            "detail": (
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
            if act == "restock":
                movement = StockMovement.objects.create(
                    company_id=company_id, product=line.product,
                    warehouse_id=wh_id, movement_type=StockMovement.SALES_RETURN_IN,
                    quantity=line.quantity, reference_type="SalesReturn",
                    reference_id=str(sales_return.id),
                    created_by=request.user if request.user.is_authenticated else None,
                )
                line.disposition = SalesReturnLine.RESTOCKED
                line.restock_warehouse_id = wh_id
                line.restock_movement = movement
                line.save(update_fields=[
                    "disposition", "restock_warehouse", "restock_movement",
                ])
            else:
                line.disposition = SalesReturnLine.SCRAPPED
                line.save(update_fields=["disposition"])
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
        pr = serializer.save()
        log_activity(
            action="create", request=request, entity_type="PurchaseReturn",
            entity_id=pr.id,
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CreditNoteViewSet(AppendOnlyScopedViewSet):
    # A credit note reduces what a customer owes — the sales side.
    rbac_module = "sales_returns"
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


class DebitNoteViewSet(AppendOnlyScopedViewSet):
    # A debit note reduces what we owe a supplier — the purchasing side.
    rbac_module = "purchase_returns"
    queryset = DebitNote.objects.select_related(
        "supplier", "bill", "company", "created_by"
    ).all()
    serializer_class = DebitNoteSerializer
    activity_entity_type = "DebitNote"

    @action(detail=True, methods=["get"])
    def document(self, request, pk=None):
        return Response(debit_note_document(self.get_object()))
