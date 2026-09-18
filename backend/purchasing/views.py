from django.db import IntegrityError
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.activity import log_activity
from core.deletion import ArchiveOnDeleteMixin
from core.documents import supplier_payment_document
from core.permissions import CanVerifyPayment
from core.rbac import APPROVER_ROLES, RoleModuleAccess, can_approve_high_value
from core.records import assemble as assemble_records
from core.records import csv_response as records_csv
from core.records import data_change_events
from core.records import event as record_event
from core.scoping import (
    AppendOnlyScopedViewSet,
    CompanyScopedModelViewSet,
    CompanyScopedQuerySetMixin,
)
from purchasing.models import (
    Bill,
    GoodsReceipt,
    PurchaseOrder,
    Supplier,
    SupplierPayment,
)
from purchasing.serializers import (
    BillSerializer,
    GoodsReceiptReadSerializer,
    GoodsReceiptWriteSerializer,
    PurchaseOrderSerializer,
    SupplierPaymentSerializer,
    SupplierSerializer,
)


class SupplierViewSet(ArchiveOnDeleteMixin, CompanyScopedModelViewSet):
    """Archived, not deleted — bills, payments and the supplier records timeline
    cite this row, and a payable balance belongs to someone."""

    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    activity_entity_type = "Supplier"

    def _status(self, supplier):
        """Account state with this supplier: nothing owed = settled."""
        if not supplier.is_active:
            return "suspended"
        return "owing" if supplier.ap_balance() > 0 else "settled"

    @action(detail=False, methods=["post"], url_path="import",
            parser_classes=[MultiPartParser, FormParser])
    def import_sheet(self, request):
        """Bulk import from .xlsx/.csv; `dry_run=1` previews without writing."""
        from core.opening_balances import record_supplier_opening_balance
        from core.party_import import run_import

        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise ValidationError({"file": [_("Choose a file to import.")]})
        dry_run = str(request.data.get("dry_run", "")).lower() in ("1", "true", "yes")

        def opening(party, user=None, amount=None):
            if amount is None:
                return party.bills.filter(is_opening_balance=True, is_void=False).exists()
            return record_supplier_opening_balance(party, user, {"amount": str(amount)})

        result = run_import(
            Supplier, request.user.company, request.user, uploaded,
            dry_run=dry_run, opening_balance_fn=opening, supports_terms=False,
        )
        if not dry_run:
            log_activity(
                action="import", request=request, entity_type="Supplier", entity_id="",
                metadata=result["summary"],
            )
        return Response(result)

    @action(detail=True, methods=["post"])
    def opening_balance(self, request, pk=None):
        """What the company already owed this supplier when the books started
        here — a receipt-less bill, so AP, aging and payments see it."""
        from core.opening_balances import record_supplier_opening_balance

        bill = record_supplier_opening_balance(self.get_object(), request.user, request.data)
        log_activity(
            action="create", request=request, entity_type="Bill", entity_id=bill.pk,
            metadata={"opening_balance": str(bill.total), "supplier": bill.supplier_id},
        )
        return Response(BillSerializer(bill, context={"request": request}).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def records(self, request, pk=None):
        """
        Complete supplier record: profile, account balance, and every
        transaction (purchase orders, goods receipts, bills, payments, returns,
        debit notes, data changes) in one chronological stream.
        `?format=csv` exports it.

        Scoped by the company queryset (cross-tenant ids 404) and gated to the
        `purchasing` module by RoleModuleAccess.
        """
        supplier = self.get_object()
        events = []

        for po in supplier.purchase_orders.all():
            events.append(
                record_event(
                    "purchase_order",
                    "Purchase order",
                    po.created_at,
                    po.id,
                    po.total,
                    po.status,
                )
            )
        for gr in supplier.goods_receipts.all():
            events.append(
                record_event(
                    "goods_receipt",
                    "Goods receipt",
                    gr.received_at,
                    gr.id,
                    None,
                    gr.note,
                )
            )
        for bill in supplier.bills.all():
            events.append(
                record_event(
                    "bill",
                    "Bill",
                    bill.created_at,
                    bill.supplier_invoice_number or bill.id,
                    bill.total,
                    "void" if bill.is_void else f"due {bill.amount_due()}",
                )
            )
        for pay in supplier.payments.select_related("bill").all():
            events.append(
                record_event(
                    "payment",
                    "Payment",
                    pay.recorded_at,
                    (pay.bill.supplier_invoice_number or pay.bill_id) if pay.bill_id else "",
                    pay.amount,
                    pay.get_method_display(),
                    entity_id=pay.id,
                )
            )
        for pr in supplier.purchase_returns.all():
            events.append(
                record_event(
                    "return",
                    "Purchase return",
                    pr.created_at,
                    pr.id,
                    None,
                    pr.reason,
                )
            )
        for dn in supplier.debit_notes.all():
            events.append(
                record_event(
                    "debit_note",
                    "Debit note",
                    dn.created_at,
                    dn.number_display,
                    dn.amount,
                    dn.reason,
                    entity_id=dn.id,
                )
            )

        events += data_change_events(supplier.company_id, "Supplier", supplier.pk)
        events = assemble_records(events, request.query_params)

        profile = {
            "id": supplier.id,
            "name": supplier.name,
            "phone": supplier.phone,
            "email": supplier.email,
            "address": supplier.address,
            "is_active": supplier.is_active,
            "created_at": supplier.created_at,
            "status": self._status(supplier),
            "balance": str(supplier.ap_balance()),
        }

        if request.query_params.get("format") == "csv":
            log_activity(
                action="export",
                request=request,
                entity_type="Supplier",
                entity_id=supplier.pk,
                metadata={"export": "records_csv"},
            )
            return records_csv(profile, events, f"supplier-{supplier.id}-records.csv")

        log_activity(
            action="view",
            request=request,
            entity_type="Supplier",
            entity_id=supplier.pk,
            metadata={"view": "records"},
        )
        return Response({"supplier": profile, "events": events})


class PurchaseOrderViewSet(AppendOnlyScopedViewSet):
    branch_field = "branch"
    include_unassigned_branch_rows = False
    queryset = PurchaseOrder.objects.prefetch_related("lines").all()
    serializer_class = PurchaseOrderSerializer
    activity_entity_type = "PurchaseOrder"

    # Which manual moves are legal. Receipt-driven states (partially
    # received, received) are derived from goods receipts and never set by
    # hand; a cancelled or received order is final.
    TRANSITIONS = {
        PurchaseOrder.DRAFT: {PurchaseOrder.SENT, PurchaseOrder.CONFIRMED, PurchaseOrder.CANCELLED},
        PurchaseOrder.SENT: {PurchaseOrder.CONFIRMED, PurchaseOrder.CANCELLED, PurchaseOrder.DRAFT},
        PurchaseOrder.CONFIRMED: {PurchaseOrder.CANCELLED},
        PurchaseOrder.PARTIALLY_RECEIVED: set(),
        PurchaseOrder.RECEIVED: set(),
        PurchaseOrder.CANCELLED: set(),
    }

    @action(detail=True, methods=["post"])
    def set_status(self, request, pk=None):
        po = self.get_object()
        new_status = request.data.get("status")
        if new_status not in dict(PurchaseOrder.STATUS_CHOICES):
            return Response({"detail": "Invalid status."}, status=status.HTTP_400_BAD_REQUEST)
        if new_status not in self.TRANSITIONS.get(po.status, set()):
            return Response(
                {"detail": f"An order that is {po.status} cannot be set to {new_status}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if new_status == PurchaseOrder.CANCELLED and po.goods_receipts.exists():
            return Response(
                {"detail": "Goods were received against this order; it cannot be cancelled."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        po.status = new_status
        po.save(update_fields=["status"])
        log_activity(
            action="update",
            request=request,
            entity_type="PurchaseOrder",
            entity_id=po.id,
            metadata={"status": new_status},
        )
        return Response(self.get_serializer(po).data)


class GoodsReceiptViewSet(
    CompanyScopedQuerySetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    Read here; create via POST /api/receivings/ (the write endpoint below,
    which posts the purchase_in movements atomically).
    """

    branch_field = "warehouse__branch"
    include_unassigned_branch_rows = False
    queryset = GoodsReceipt.objects.prefetch_related("lines__product").all()
    serializer_class = GoodsReceiptReadSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        supplier_id = self.request.query_params.get("supplier")
        if supplier_id:
            qs = qs.filter(supplier_id=supplier_id)
        return qs


class GoodsReceiptCreateView(APIView):
    """POST /api/receivings/ — atomic, idempotent goods receipt."""

    permission_classes = [IsAuthenticated, RoleModuleAccess]
    rbac_module = "purchasing"

    def post(self, request):
        client_uuid = request.data.get("client_uuid")
        if client_uuid:
            company_id = getattr(request.user, "company_id", None)
            existing = GoodsReceipt.objects.filter(
                company_id=company_id, client_uuid=client_uuid
            ).first()
            if existing:
                return Response(
                    GoodsReceiptReadSerializer(existing, context={"request": request}).data,
                    status=status.HTTP_200_OK,
                )

        serializer = GoodsReceiptWriteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            receipt = serializer.save()
        except IntegrityError:
            existing = (
                GoodsReceipt.objects.filter(
                    company_id=getattr(request.user, "company_id", None),
                    client_uuid=client_uuid,
                ).first()
                if client_uuid else None
            )
            if existing is None:
                raise
            return Response(
                GoodsReceiptReadSerializer(existing, context={"request": request}).data,
                status=status.HTTP_200_OK,
            )
        log_activity(
            action="create",
            request=request,
            entity_type="GoodsReceipt",
            entity_id=receipt.id,
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class BillViewSet(AppendOnlyScopedViewSet):
    queryset = Bill.objects.select_related("supplier").all()
    serializer_class = BillSerializer
    activity_entity_type = "Bill"

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        """A bill keyed wrongly (1,000,000 for 100,000) inflated payables for
        ever, because nothing could touch it. Voiding keeps the row and drops
        it from AP (Rule #9); a bill with payments cannot be voided — record a
        debit note or correct the payment instead. Manager-only."""
        if not can_approve_high_value(request.user):
            return Response(
                {"detail": "Only a manager or owner may void a bill."},
                status=status.HTTP_403_FORBIDDEN,
            )
        reason = str(request.data.get("reason") or "").strip()
        if not reason:
            return Response(
                {"reason": "A reason is required to void a bill."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from django.db import transaction

        with transaction.atomic():
            bill = Bill.objects.select_for_update().get(pk=self.get_object().pk)
            if bill.is_void:
                return Response({"detail": "This bill is already void."}, status=400)
            if bill.payments.exists():
                return Response(
                    {"detail": "Payments were recorded against this bill; it cannot be voided."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            bill.is_void = True
            bill.save(update_fields=["is_void"])
            log_activity(
                action="void", request=request, entity_type="Bill", entity_id=bill.pk,
                metadata={"reason": reason, "total": str(bill.total)},
            )
        return Response(self.get_serializer(bill).data)


class SupplierPaymentViewSet(AppendOnlyScopedViewSet):
    queryset = SupplierPayment.objects.select_related(
        "supplier",
        "bill",
        "company",
        "from_bank_account",
        "recorded_by",
        "verified_by",
    ).all()
    serializer_class = SupplierPaymentSerializer
    activity_entity_type = "SupplierPayment"
    approval_module = "purchasing"
    # The treasurer verifies these (CanVerifyPayment already lets finance
    # write do so) and reads them in the money ledger.
    rbac_read_modules = ("finance",)

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("unverified") == "1":
            return qs.filter(verified_at__isnull=True).order_by("recorded_at", "pk")
        if params.get("method") in (SupplierPayment.CASH, SupplierPayment.BANK_TRANSFER):
            qs = qs.filter(method=params["method"])
        if params.get("supplier"):
            qs = qs.filter(supplier_id=params["supplier"])
        return qs.order_by("-recorded_at", "-pk")

    @action(detail=True, methods=["get"])
    def document(self, request, pk=None):
        """Printable voucher for money paid out to a supplier."""
        return Response(supplier_payment_document(self.get_object()))

    def get_permissions(self):
        if getattr(self, "action", None) == "verify":
            return [IsAuthenticated(), CanVerifyPayment()]
        return super().get_permissions()

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        payment = self.get_object()
        if payment.verified_at is not None:
            return Response({"detail": "Already verified."}, status=status.HTTP_400_BAD_REQUEST)
        # Segregation of duties — mirrors the AR side: the recorder of an
        # outgoing payment cannot also be its approver.
        if payment.recorded_by_id and payment.recorded_by_id == request.user.id:
            return Response(
                {
                    "detail": "You recorded this payment, so you cannot verify it. "
                    "Verification must be done by a different user."
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        # Outgoing money above the threshold needs approver-role sign-off.
        threshold = getattr(payment.company, "payment_approval_threshold", 0) or 0
        if threshold and payment.amount >= threshold and not can_approve_high_value(request.user):
            return Response(
                {
                    "detail": (
                        f"Payments of {threshold} or more must be approved by a "
                        "CFO, owner or general manager."
                    ),
                    "threshold": str(threshold),
                    "requires_role": sorted(APPROVER_ROLES),
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        payment.verified_at = timezone.now()
        payment.verified_by = request.user if request.user.is_authenticated else None
        payment.save(update_fields=["verified_at", "verified_by"])
        log_activity(
            action="update",
            request=request,
            entity_type="SupplierPayment",
            entity_id=payment.id,
            metadata={"verified": True, "verified_by": request.user.email},
        )
        return Response(self.get_serializer(payment).data)
