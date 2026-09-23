from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.activity import log_activity
from core.deletion import ArchiveOnDeleteMixin
from core.documents import payment_receipt_document
from core.permissions import CanVerifyPayment
from core.rbac import APPROVER_ROLES, RoleModuleAccess, can_approve_high_value
from core.records import assemble as assemble_records
from core.records import csv_response as records_csv
from core.records import data_change_events
from core.records import event as record_event
from core.records import rows_csv as records_rows_csv
from core.scoping import (
    valid_client_uuid,
    AppendOnlyScopedViewSet,
    CompanyScopedModelViewSet,
    CompanyScopedQuerySetMixin,
)
from sales.models import (
    Refund,
    CashDrawerMovement,
    CashShift,
    CompanyBankAccount,
    Customer,
    Invoice,
    Payment,
    Quotation,
    SalesOrder,
    SalesOrderLine,
)
from inventory.models import StockMovement
from sales.debt_queries import customer_debts, debt_summary, statement_for_period
from sales.serializers import (
    RefundSerializer,
    CashDrawerMovementSerializer,
    CashShiftSerializer,
    CompanyBankAccountSerializer,
    CustomerSerializer,
    InvoiceSerializer,
    PaymentSerializer,
    POSCheckoutSerializer,
    QuotationSerializer,
    SalesOrderSerializer,
)


class CustomerViewSet(ArchiveOnDeleteMixin, CompanyScopedModelViewSet):
    """Archived, not deleted — invoices and the customer records timeline cite
    this row, and a receivable balance belongs to someone."""

    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    activity_entity_type = "Customer"

    def _status(self, customer):
        """Account state, driven by real credit terms: any invoice past its
        `due_date` marks the customer overdue; otherwise an outstanding
        balance is simply 'owing'."""
        if not customer.is_active:
            return "suspended"
        if customer.ar_balance() <= 0:
            return "active"
        overdue = any(inv.is_overdue for inv in customer.invoices.filter(is_void=False))
        return "overdue" if overdue else "owing"

    @action(detail=True, methods=["get"])
    def credit(self, request, pk=None):
        """Credit notes of this customer with credit still on them — what the
        till can apply to a new sale or hand back."""
        customer = self.get_object()
        notes = []
        for note in customer.credit_notes.filter(is_void=False).select_related("invoice"):
            remaining = note.remaining_refundable()
            if remaining > 0:
                notes.append({
                    "id": note.id, "number": note.number_display, "remaining": str(remaining),
                    "invoice": note.invoice.number_display if note.invoice_id else None,
                    "reason": note.reason,
                })
        total = sum((Decimal(n["remaining"]) for n in notes), Decimal("0"))
        return Response({"total": str(total), "notes": notes})

    @action(detail=False, methods=["post"], url_path="import",
            parser_classes=[MultiPartParser, FormParser])
    def import_sheet(self, request):
        """Bulk import from .xlsx/.csv; `dry_run=1` previews without writing."""
        from core.opening_balances import record_customer_opening_balance
        from core.party_import import run_import

        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise ValidationError({"file": [_("Choose a file to import.")]})
        dry_run = str(request.data.get("dry_run", "")).lower() in ("1", "true", "yes")

        def opening(party, user=None, amount=None):
            if amount is None:
                return party.invoices.filter(is_opening_balance=True, is_void=False).exists()
            return record_customer_opening_balance(party, user, {"amount": str(amount)})

        result = run_import(
            Customer, request.user.company, request.user, uploaded,
            dry_run=dry_run, opening_balance_fn=opening, supports_terms=True,
        )
        if not dry_run:
            log_activity(
                action="import", request=request, entity_type="Customer", entity_id="",
                metadata=result["summary"],
            )
        return Response(result)

    @action(detail=True, methods=["post"])
    def opening_balance(self, request, pk=None):
        """What this customer already owed when the books started here —
        recorded as a line-less invoice so every debt view sees it."""
        from core.opening_balances import record_customer_opening_balance

        invoice = record_customer_opening_balance(self.get_object(), request.user, request.data)
        log_activity(
            action="create", request=request, entity_type="Invoice", entity_id=invoice.pk,
            metadata={"opening_balance": str(invoice.total), "customer": invoice.customer_id},
        )
        return Response(InvoiceSerializer(invoice, context={"request": request}).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def records(self, request, pk=None):
        """
        Complete customer record: profile, account status, and every operation
        (quotations, orders, invoices, payments, returns, credit notes, and
        data changes) as one chronological stream. `?format=csv` exports it.

        `get_object` resolves through the company-scoped queryset, so another
        tenant's customer id 404s — and the whole action is already gated to the
        `sales` module by RoleModuleAccess.
        """
        customer = self.get_object()
        events = []

        for q in customer.quotations.all():
            events.append(
                record_event(
                    "quotation",
                    "Quotation",
                    q.created_at,
                    q.id,
                    q.total,
                    q.status,
                )
            )
        for so in customer.sales_orders.all():
            events.append(
                record_event(
                    "order",
                    "Sales order",
                    so.created_at,
                    so.id,
                    so.total,
                    so.status,
                )
            )
        for inv in customer.invoices.all():
            events.append(
                record_event(
                    "invoice",
                    "Invoice",
                    inv.issued_at,
                    inv.number_display,
                    inv.total,
                    "void" if inv.is_void else f"due {inv.amount_due()}",
                    entity_id=inv.id,
                )
            )
            for pay in inv.payments.all():
                events.append(
                    record_event(
                        "payment",
                        "Payment",
                        pay.recorded_at,
                        inv.number_display,
                        pay.amount,
                        pay.get_method_display(),
                        entity_id=pay.id,
                    )
                )
        for sr in customer.sales_returns.all():
            events.append(
                record_event(
                    "return",
                    "Sales return",
                    sr.created_at,
                    sr.id,
                    None,
                    sr.reason,
                )
            )
        for cn in customer.credit_notes.all():
            events.append(
                record_event(
                    "credit_note",
                    "Credit note",
                    cn.created_at,
                    cn.number_display,
                    cn.amount,
                    cn.reason,
                    entity_id=cn.id,
                )
            )
            # Money handed back is a movement in its own right on the account.
            for refund in cn.refunds.all():
                events.append(
                    record_event(
                        "refund",
                        "Refund",
                        refund.recorded_at,
                        cn.number_display,
                        refund.amount,
                        refund.get_method_display(),
                        entity_id=refund.id,
                    )
                )

        events += data_change_events(customer.company_id, "Customer", customer.pk)
        events = assemble_records(events, request.query_params)

        profile = {
            "id": customer.id,
            "name": customer.name,
            "phone": customer.phone,
            "email": customer.email,
            "address": customer.address,
            "is_active": customer.is_active,
            "created_at": customer.created_at,
            "status": self._status(customer),
            "balance": str(customer.ar_balance()),
        }

        if request.query_params.get("format") == "csv":
            log_activity(
                action="export",
                request=request,
                entity_type="Customer",
                entity_id=customer.pk,
                metadata={"export": "records_csv"},
            )
            return records_csv(profile, events, f"customer-{customer.id}-records.csv")

        log_activity(
            action="view",
            request=request,
            entity_type="Customer",
            entity_id=customer.pk,
            metadata={"view": "records"},
        )
        return Response({"customer": profile, "events": events})

    @action(detail=True, methods=["get"], url_path="debt-statement")
    def debt_statement(self, request, pk=None):
        """A derived receivables statement for one customer.

        This deliberately reads the same invoices, payments and credit notes as
        the debt list. There is no editable balance to drift from the source
        documents, and ``get_object`` preserves company isolation.
        """
        customer = self.get_object()
        payload = statement_for_period(request.user, customer, request.query_params)
        payload["customer"] = {
            "id": customer.id,
            "name": customer.name,
            "phone": customer.phone,
        }
        log_activity(
            action="view",
            request=request,
            entity_type="Customer",
            entity_id=customer.pk,
            metadata={"view": "debt_statement"},
        )
        return Response(payload)


class DebtCustomerListView(APIView):
    """Read-only customer receivables list, derived from financial documents."""

    permission_classes = [IsAuthenticated, RoleModuleAccess]
    rbac_module = "sales"

    def get(self, request):
        return Response(customer_debts(request.user, request.query_params))


class DebtSummaryView(APIView):
    """Headline receivables figures used by the debt ledger screen."""

    permission_classes = [IsAuthenticated, RoleModuleAccess]
    rbac_module = "sales"

    def get(self, request):
        return Response(debt_summary(request.user))


class CompanyBankAccountViewSet(ArchiveOnDeleteMixin, CompanyScopedModelViewSet):
    """Archived, not deleted: the account's balance is derived from the payments
    that reference it, so removing it would silently drop money from the
    company's cash position."""

    queryset = CompanyBankAccount.objects.all()
    serializer_class = CompanyBankAccountSerializer
    activity_entity_type = "CompanyBankAccount"
    # Supplier payments and the money ledger name the paying account.
    rbac_read_modules = ("purchasing", "finance")
    # Exception to the archive default: a bank account is treasury, not
    # catalogue data. Anyone with sales write can record against it, but
    # retiring one is a manager's call.
    manager_only_delete = True


class CashShiftViewSet(AppendOnlyScopedViewSet):
    """
    Till sessions. Open, close with a count, and (optionally) have a manager
    sign off the variance.

    List/retrieve/create only — a shift is never edited or deleted. `close` and
    `review` are the two designed one-time transitions, the same shape as
    Payment.verify.
    """

    rbac_module = "sales"
    branch_field = "branch"
    include_unassigned_branch_rows = False
    queryset = (
        CashShift.objects.select_related("opened_by", "closed_by", "reviewed_by")
        .prefetch_related("drawer_movements", "payments")
        .all()
    )
    serializer_class = CashShiftSerializer
    activity_entity_type = "CashShift"

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        if self.request.query_params.get("mine") in ("1", "true"):
            qs = qs.filter(opened_by=self.request.user)
        # The sign-off worklist: counted drawers no manager has accepted yet.
        if self.request.query_params.get("unreviewed") == "1":
            qs = qs.filter(status=CashShift.CLOSED, reviewed_at__isnull=True)
        return qs.order_by("-opened_at", "-pk")

    def perform_create(self, serializer):
        # A second open drawer would make every takings figure ambiguous. The DB
        # constraint is the real guard; this turns it into a clear message.
        existing = CashShift.objects.filter(
            company_id=getattr(self.request.user, "company_id", None),
            opened_by=self.request.user,
            status=CashShift.OPEN,
        ).first()
        if existing:
            raise ValidationError(
                {
                    "detail": _("You already have an open till session. Close it "
                                "before opening another."),
                    "shift": existing.id,
                }
            )
        # Must go through the parent chain, which is what injects `company` and
        # the branch and writes the audit row. `opened_by` is stamped by the
        # serializer from the request, never taken from the body.
        super().perform_create(serializer)

    @action(detail=False, methods=["get"])
    def current(self, request):
        """The caller's own open session, so the till can resume after a reload
        without the cashier hunting for it."""
        shift = CashShift.objects.filter(
            company_id=getattr(request.user, "company_id", None),
            opened_by=request.user,
            status=CashShift.OPEN,
        ).first()
        if shift is None:
            return Response({"shift": None})
        return Response(self.get_serializer(shift).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        """
        Record the physical count and close the drawer.

        The count is required and taken as given — the system does not offer a
        default, because pre-filling the expected figure is an invitation to
        confirm it without counting, which would make the whole control
        decorative.
        """
        shift = self.get_object()
        # A drawer is one person's responsibility. Only its holder — or a
        # manager stepping in — may declare the count that closes it; a
        # colleague closing someone else's drawer would leave the variance
        # with no owner.
        if shift.opened_by_id != request.user.pk and not can_approve_high_value(request.user):
            return Response(
                {"detail": _(
                    "Only the cashier who opened this drawer, or a manager, may close it."
                )},
                status=status.HTTP_403_FORBIDDEN,
            )
        with transaction.atomic():
            shift = CashShift.objects.select_for_update().get(pk=shift.pk)
            return self._close_locked(request, shift)

    def _close_locked(self, request, shift):
        if shift.status == CashShift.CLOSED:
            return Response(
                {"detail": _("This session is already closed.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        raw = request.data.get("counted_cash")
        if raw is None or str(raw).strip() == "":
            return Response(
                {"counted_cash": _("Count the drawer and enter the amount.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            counted = Decimal(str(raw))
        except (InvalidOperation, TypeError):
            return Response(
                {"counted_cash": _("Must be a number.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if counted < 0:
            return Response(
                {"counted_cash": _("A drawer cannot hold less than nothing.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        expected = shift.expected_cash()
        shift.expected_at_close = expected
        shift.counted_cash = counted
        shift.closed_by = request.user
        shift.closed_at = timezone.now()
        shift.status = CashShift.CLOSED
        if request.data.get("note"):
            shift.note = str(request.data["note"])[:255]
        shift.save(
            update_fields=[
                "counted_cash",
                "expected_at_close",
                "closed_by",
                "closed_at",
                "status",
                "note",
            ]
        )
        log_activity(
            action="update",
            request=request,
            entity_type="CashShift",
            entity_id=shift.pk,
            metadata={
                "closed": True,
                "expected": str(expected),
                "counted": str(counted),
                "variance": str(counted - expected),
            },
        )
        return Response(self.get_serializer(shift).data)

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        """
        A manager signing off a closed drawer.

        Segregation of duties, same principle as payment verification: whoever
        counted the cash cannot also be the one who accepts the count, or the
        variance has no independent witness.
        """
        shift = self.get_object()
        if shift.status != CashShift.CLOSED:
            return Response(
                {"detail": _("Only a closed session can be reviewed.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not can_approve_high_value(request.user):
            return Response(
                {"detail": _("Only a manager or owner may sign off a till count.")},
                status=status.HTTP_403_FORBIDDEN,
            )
        if shift.closed_by_id and shift.closed_by_id == request.user.id:
            return Response(
                {
                    "detail": _(
                        "You closed this session, so you cannot also sign "
                        "off its count. Another manager must review it."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        if shift.reviewed_at is not None:
            return Response(
                {"detail": _("Already reviewed.")}, status=status.HTTP_400_BAD_REQUEST
            )
        shift.reviewed_by = request.user
        shift.reviewed_at = timezone.now()
        shift.save(update_fields=["reviewed_by", "reviewed_at"])
        log_activity(
            action="approve",
            request=request,
            entity_type="CashShift",
            entity_id=shift.pk,
            metadata={"variance": str(shift.variance())},
        )
        return Response(self.get_serializer(shift).data)


class CashDrawerMovementViewSet(AppendOnlyScopedViewSet):
    """Non-sale cash in and out of an open drawer. Append-only (Rule #9)."""

    rbac_module = "sales"
    branch_field = "shift__branch"
    include_unassigned_branch_rows = False
    queryset = CashDrawerMovement.objects.select_related("shift", "recorded_by").all()
    serializer_class = CashDrawerMovementSerializer
    activity_entity_type = "CashDrawerMovement"

    def get_queryset(self):
        qs = super().get_queryset()
        shift = self.request.query_params.get("shift")
        if shift:
            qs = qs.filter(shift_id=shift)
        return qs


class QuotationViewSet(AppendOnlyScopedViewSet):
    branch_field = "branch"
    include_unassigned_branch_rows = False
    queryset = Quotation.objects.prefetch_related("lines").all()
    serializer_class = QuotationSerializer
    activity_entity_type = "Quotation"

    @action(detail=True, methods=["post"])
    def set_status(self, request, pk=None):
        quotation = self.get_object()
        new_status = request.data.get("status")
        valid = dict(Quotation.STATUS_CHOICES)
        if new_status not in valid:
            return Response(
                {"detail": _("Invalid status.")}, status=status.HTTP_400_BAD_REQUEST
            )
        quotation.status = new_status
        quotation.save(update_fields=["status"])
        log_activity(
            action="update",
            request=request,
            entity_type="Quotation",
            entity_id=quotation.id,
            metadata={"status": new_status},
        )
        return Response(self.get_serializer(quotation).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def convert_to_order(self, request, pk=None):
        quotation = self.get_queryset().select_for_update().get(pk=pk)
        existing = quotation.sales_orders.order_by("id").first()
        if existing is not None:
            return Response(
                SalesOrderSerializer(existing, context={"request": request}).data,
                status=status.HTTP_200_OK,
            )
        order = SalesOrder.objects.create(
            company_id=quotation.company_id,
            customer=quotation.customer,
            branch=quotation.branch,
            source_quotation=quotation,
            subtotal=quotation.subtotal,
            tax_amount=quotation.tax_amount,
            total=quotation.total,
            created_by=request.user if request.user.is_authenticated else None,
        )
        for line in quotation.lines.all():
            SalesOrderLine.objects.create(
                sales_order=order,
                product=line.product,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                line_total=line.line_total,
            )
        quotation.status = Quotation.CONVERTED
        quotation.save(update_fields=["status"])
        log_activity(
            action="create",
            request=request,
            entity_type="SalesOrder",
            entity_id=order.id,
        )
        return Response(
            SalesOrderSerializer(order, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class SalesOrderViewSet(AppendOnlyScopedViewSet):
    branch_field = "branch"
    include_unassigned_branch_rows = False
    queryset = SalesOrder.objects.prefetch_related("lines").all()
    serializer_class = SalesOrderSerializer
    activity_entity_type = "SalesOrder"

    # Fulfilment happens only by invoicing the order (POS checkout with
    # source_order); here the buyer's side of the lifecycle.
    TRANSITIONS = {
        SalesOrder.DRAFT: {SalesOrder.CONFIRMED, SalesOrder.CANCELLED},
        SalesOrder.CONFIRMED: {SalesOrder.CANCELLED, SalesOrder.DRAFT},
        SalesOrder.FULFILLED: set(),
        SalesOrder.CANCELLED: set(),
    }

    @action(detail=True, methods=["post"])
    def set_status(self, request, pk=None):
        order = self.get_object()
        new_status = request.data.get("status")
        if new_status not in self.TRANSITIONS.get(order.status, set()):
            return Response(
                {"detail": _("An order that is %(current)s cannot be set to %(target)s.")
                 % {"current": order.status, "target": new_status}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.status = new_status
        order.save(update_fields=["status"])
        log_activity(
            action="update", request=request, entity_type="SalesOrder",
            entity_id=order.pk, metadata={"status": new_status},
        )
        return Response(self.get_serializer(order).data)


class InvoiceViewSet(
    CompanyScopedQuerySetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    Read-only. Invoices are created only through POS checkout (append-only,
    Rule #9); there is no direct create/update/delete path.
    """

    branch_field = "branch"
    include_unassigned_branch_rows = False

    # `lines__return_lines` feeds InvoiceLine.returned_quantity() from the
    # prefetch cache — without it each line would issue its own COUNT.
    queryset = Invoice.objects.prefetch_related(
        "lines__return_lines", "lines__product", "payments"
    ).all()
    serializer_class = InvoiceSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        customer_id = params.get("customer", "").strip()
        if customer_id.isdigit():
            qs = qs.filter(customer_id=int(customer_id))
        if params.get("overdue") == "1":
            from sales.querysets import overdue_invoices

            qs = overdue_invoices(qs)
        elif params.get("open") == "1":
            # The collection drawer: a customer's unpaid invoices, oldest
            # first, so a payment settles the longest-standing debt first.
            from sales.querysets import open_invoices

            return open_invoices(qs).order_by("issued_at", "pk")
        search = params.get("search", "").strip()
        if search:
            from django.db.models import Q

            condition = Q(customer__name__icontains=search)
            number = search.upper().removeprefix("INV-")
            if number.isdigit():
                condition |= Q(number=int(number))
            qs = qs.filter(condition)
        return qs.order_by("-issued_at", "-pk")

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        """
        Cancel an invoice by offsetting entries, never by editing it (Rule #9).

        Body: {"reason": "...", "refund": {method, company_bank_account?,
        reference_last4?, shift?}} — `refund` is required when anything was
        paid, so the money the customer handed over is accounted for.

        Writes, atomically: a full-value Credit Note, a Refund of whatever was
        paid, one `sales_return_in` movement reversing each `sale_out` of the
        sale (same warehouse, lot and cost), then `is_void`. Refused when the
        invoice already has a return against it: those goods were credited by
        their own note and voiding on top would credit them twice.
        """
        from returns.models import CreditNote

        if not can_approve_high_value(request.user):
            return Response(
                {"detail": _("Only a manager or owner may void an invoice.")},
                status=status.HTTP_403_FORBIDDEN,
            )
        reason = str(request.data.get("reason") or "").strip()
        if not reason:
            return Response(
                {"reason": _("A reason is required to void an invoice.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            invoice = Invoice.objects.select_for_update().get(pk=self.get_object().pk)
            if invoice.is_void:
                return Response(
                    {"detail": _("This invoice is already void.")},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if invoice.sales_returns.exists():
                return Response(
                    {
                        "detail": _(
                            "This invoice has a return against it. Return the "
                            "remaining lines instead of voiding the whole sale."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            paid = invoice.amount_paid()
            refund_body = request.data.get("refund")
            if paid > 0 and not isinstance(refund_body, dict):
                return Response(
                    {
                        "refund": _(
                            "%(paid)s was paid on this invoice. Say how it is being "
                            "refunded (method, account/reference or till session)."
                        ) % {"paid": paid}
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            remaining_credit = invoice.total - invoice.credited_total()
            note = CreditNote.objects.create(
                company_id=invoice.company_id, customer=invoice.customer,
                invoice=invoice, amount=remaining_credit, reason=reason,
                created_by=request.user,
            )
            log_activity(
                action="create", request=request, entity_type="CreditNote",
                entity_id=note.pk, metadata={"invoice": invoice.pk, "void": True},
            )
            refund = None
            if paid > 0:
                serializer = RefundSerializer(
                    data={**refund_body, "credit_note": note.pk, "amount": str(paid),
                          "note": f"Void {invoice.number_display}: {reason}"[:255]},
                    context={"request": request},
                )
                serializer.is_valid(raise_exception=True)
                refund = serializer.save(company_id=invoice.company_id)
            reversed_ids = []
            sold = StockMovement.objects.filter(
                company_id=invoice.company_id, reference_type="Invoice",
                reference_id=str(invoice.pk), movement_type=StockMovement.SALE_OUT,
            )
            for movement in sold:
                back = StockMovement.objects.create(
                    company_id=invoice.company_id, product_id=movement.product_id,
                    warehouse_id=movement.warehouse_id, batch_id=movement.batch_id,
                    movement_type=StockMovement.SALES_RETURN_IN,
                    quantity=-movement.quantity, unit_cost=movement.unit_cost,
                    reference_type="InvoiceVoid", reference_id=str(invoice.pk),
                    note=reason[:255], created_by=request.user,
                )
                reversed_ids.append(back.pk)
            invoice.is_void = True
            invoice.save(update_fields=["is_void", "updated_at"])
            log_activity(
                action="void", request=request, entity_type="Invoice",
                entity_id=invoice.pk,
                metadata={
                    "reason": reason, "credit_note": note.pk,
                    "refund": refund.pk if refund else None,
                    "movements": reversed_ids, "total": str(invoice.total),
                },
            )
        return Response(self.get_serializer(invoice).data)

    @action(detail=False, methods=["get"])
    def export(self, request):
        """
        CSV of the invoice list. Runs through the same scoped queryset as the
        list view, so an export can never contain a row the caller could not
        already see — including branch scoping.
        """
        invoices = self.filter_queryset(self.get_queryset()).select_related("customer")
        log_activity(
            action="export",
            request=request,
            entity_type="Invoice",
            metadata={"count": invoices.count()},
        )
        return records_rows_csv(
            "invoices.csv",
            [
                "Number",
                "Date",
                "Due date",
                "Customer",
                "Status",
                "Subtotal",
                "Tax",
                "Total",
                "Paid",
                "Balance",
            ],
            [
                [
                    inv.number_display,
                    inv.issued_at.date().isoformat() if inv.issued_at else "",
                    inv.due_date.isoformat() if inv.due_date else "",
                    inv.customer.name if inv.customer_id else "",
                    inv.status,
                    inv.subtotal,
                    inv.tax_amount,
                    inv.total,
                    inv.amount_paid(),
                    inv.amount_due(),
                ]
                for inv in invoices
            ],
        )


class PaymentViewSet(AppendOnlyScopedViewSet):
    branch_field = "invoice__branch"
    include_unassigned_branch_rows = False

    def perform_create(self, serializer):
        super().perform_create(serializer)
    queryset = Payment.objects.select_related(
        "invoice__customer",
        "company",
        "company_bank_account",
        "recorded_by",
        "verified_by",
    ).all()
    serializer_class = PaymentSerializer
    activity_entity_type = "Payment"
    approval_module = "sales"

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        # The verification worklist: money recorded that no second person
        # has confirmed yet, oldest first so nothing waits forever.
        if params.get("unverified") == "1":
            # Store credit moved no money; there is nothing to confirm.
            return (
                qs.filter(verified_at__isnull=True)
                .exclude(method=Payment.STORE_CREDIT)
                .order_by("recorded_at", "pk")
            )
        if params.get("method") in dict(Payment.METHOD_CHOICES):
            qs = qs.filter(method=params["method"])
        return qs.order_by("-recorded_at", "-pk")

    @action(detail=True, methods=["get"])
    def document(self, request, pk=None):
        """Printable receipt for money received. Invoice totals on it are
        recomputed from the payment ledger, so the receipt and the account can
        never disagree."""
        return Response(payment_receipt_document(self.get_object()))

    def get_permissions(self):
        # Verification is a treasury action — see CanVerifyPayment. Recording a
        # payment still requires sales write via the normal module gate.
        if getattr(self, "action", None) in ("verify", "reconcile"):
            return [IsAuthenticated(), CanVerifyPayment()]
        return super().get_permissions()

    @action(detail=False, methods=["post"],
            parser_classes=[MultiPartParser, FormParser, JSONParser])
    def reconcile(self, request):
        """Match a bank-app statement (.xlsx/.csv) against this account's
        recorded transfers. `dry_run=1` previews; otherwise every matched,
        unverified transfer not recorded by the caller is marked verified."""
        from sales.reconcile import reconcile

        account_id = request.data.get("account")
        account = CompanyBankAccount.objects.filter(
            pk=account_id or 0, company_id=request.user.company_id,
        ).first()
        if account is None:
            return Response({"account": [_("Choose a receiving account.")]}, status=400)
        uploaded = request.FILES.get("file")
        if uploaded is None:
            return Response({"file": [_("Upload the statement export.")]}, status=400)
        dry_run = str(request.data.get("dry_run", "")).lower() in ("1", "true", "yes")
        result = reconcile(
            request.user.company, account, uploaded, request.user, dry_run=dry_run,
        )
        if not dry_run and result["applied"]:
            log_activity(
                action="update", request=request, entity_type="Payment", entity_id="bulk",
                metadata={"reconciled": result["applied"], "account": account.pk,
                          "rows": result["rows"]},
            )
        return Response(result)

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        """
        Manager reconciliation (Rule #3): fills verified_at/verified_by. This is
        the one designed post-hoc field-set on a payment — amount/method remain
        immutable, so append-only integrity holds.
        """
        payment = self.get_object()
        if payment.verified_at is not None:
            return Response(
                {"detail": _("Already verified.")}, status=status.HTTP_400_BAD_REQUEST
            )
        # Segregation of duties: the person who recorded the money may not be
        # the one who confirms it. This is the control that makes the
        # verified_by pair meaningful rather than a rubber stamp.
        if payment.recorded_by_id and payment.recorded_by_id == request.user.id:
            return Response(
                {
                    "detail": _(
                        "You recorded this payment, so you cannot verify it. "
                        "Verification must be done by a different user."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        # Second approval tier: above the company threshold, any second user is
        # not enough — it takes an approver role (CFO / owner / GM).
        threshold = getattr(payment.company, "payment_approval_threshold", 0) or 0
        if (
            threshold
            and payment.amount >= threshold
            and not can_approve_high_value(request.user)
        ):
            return Response(
                {
                    "detail": _(
                        "Payments of %(threshold)s or more must be approved by a "
                        "CFO, owner or general manager."
                    ) % {"threshold": threshold},
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
            entity_type="Payment",
            entity_id=payment.id,
            metadata={"verified": True, "verified_by": request.user.email},
        )
        return Response(self.get_serializer(payment).data)


class POSCheckoutView(APIView):
    """
    POST /api/pos/checkout/ — offline-capable, idempotent sale completion.
    """

    permission_classes = [IsAuthenticated, RoleModuleAccess]
    rbac_module = "sales"

    def is_completed_entitlement_replay(self, request):
        client_uuid = valid_client_uuid(request.data.get("client_uuid"))
        company_id = getattr(request.user, "company_id", None)
        return bool(
            client_uuid
            and company_id
            and Invoice.objects.filter(
                company_id=company_id, client_uuid=client_uuid
            ).exists()
        )

    def post(self, request):
        client_uuid = valid_client_uuid(request.data.get("client_uuid"))
        if client_uuid:
            company_id = getattr(request.user, "company_id", None)
            existing = Invoice.objects.filter(
                company_id=company_id, client_uuid=client_uuid
            ).first()
            if existing:
                # Replay of an already-synced offline sale — return it, don't
                # ring it up again (Rule #2).
                return Response(
                    InvoiceSerializer(existing, context={"request": request}).data,
                    status=status.HTTP_200_OK,
                )

        serializer = POSCheckoutSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        try:
            invoice = serializer.save()
        except IntegrityError:
            # Two requests with the same client_uuid raced past the pre-check
            # (a retry after a dropped response, two tabs). The unique index
            # kept the second sale out; answer with the first, as a replay.
            existing = (
                Invoice.objects.filter(
                    company_id=getattr(request.user, "company_id", None),
                    client_uuid=client_uuid,
                ).first()
                if client_uuid else None
            )
            if existing is None:
                raise
            return Response(
                InvoiceSerializer(existing, context={"request": request}).data,
                status=status.HTTP_200_OK,
            )
        log_activity(
            action="create",
            request=request,
            entity_type="Invoice",
            entity_id=invoice.id,
            metadata={"number": invoice.number, "total": str(invoice.total)},
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class RefundViewSet(AppendOnlyScopedViewSet):
    """Money handed back against a credit note. Append-only, like every other
    money row; the drawer movement it creates is written in the same
    transaction (see RefundSerializer.create)."""

    rbac_module = "sales_returns"
    branch_field = "credit_note__invoice__branch"
    include_unassigned_branch_rows = False
    queryset = Refund.objects.select_related(
        "credit_note__invoice", "credit_note__customer", "company_bank_account",
        "recorded_by", "shift",
    ).all()
    serializer_class = RefundSerializer
    activity_entity_type = "Refund"
    rbac_read_modules = ("finance",)

    def get_queryset(self):
        qs = super().get_queryset()
        method = self.request.query_params.get("method")
        if method in (Refund.CASH, Refund.BANK_TRANSFER):
            qs = qs.filter(method=method)
        return qs.order_by("-recorded_at", "-pk")

    def perform_create(self, serializer):
        # RefundSerializer.create already writes the audit row with the note
        # and amount; the generic mixin entry would duplicate it.
        CompanyScopedQuerySetMixin.perform_create(self, serializer)

    @action(detail=True, methods=["get"])
    def document(self, request, pk=None):
        from core.documents import refund_voucher_document

        return Response(refund_voucher_document(self.get_object()))
