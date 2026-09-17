from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from rest_framework import serializers

from core.activity import log_activity
from core.rbac import can_approve_high_value
from core.scoping import assert_user_branch

from inventory.models import Product, StockMovement, Warehouse
from purchasing.models import Bill, GoodsReceipt, GoodsReceiptLine, Supplier
from returns.models import (
    CreditNote,
    DebitNote,
    PurchaseReturn,
    PurchaseReturnLine,
    SalesReturn,
    SalesReturnLine,
)
from sales.models import Invoice, InvoiceLine


def _assert_company(serializer, obj, label):
    if obj is None:
        return
    request = serializer.context.get("request")
    user = getattr(request, "user", None)
    if user is None or getattr(user, "is_platform_admin", False):
        return
    if obj.company_id != getattr(user, "company_id", None):
        raise serializers.ValidationError({label: "Not your company's record."})


# ---------- Sales return (Rule #5) ----------

class SalesReturnLineInputSerializer(serializers.Serializer):
    # Rule #4: a return is always a child of the original document, never a
    # standalone credit. The id is resolved unscoped here and then tied to the
    # (company-checked) invoice in SalesReturnWriteSerializer.validate — an
    # InvoiceLine carries no company_id of its own to check directly.
    invoice_line = serializers.PrimaryKeyRelatedField(
        queryset=InvoiceLine.objects.all()
    )
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.DecimalField(
        max_digits=16, decimal_places=3, min_value=Decimal("0.001")
    )


class SalesReturnLineReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesReturnLine
        fields = [
            "id", "invoice_line", "product", "quantity", "disposition",
            "restock_warehouse", "restock_movement",
        ]


class SalesReturnReadSerializer(serializers.ModelSerializer):
    lines = SalesReturnLineReadSerializer(many=True, read_only=True)
    is_fully_dispositioned = serializers.BooleanField(read_only=True)

    class Meta:
        model = SalesReturn
        fields = [
            "id", "company", "invoice", "customer", "reason",
            "is_fully_dispositioned", "lines", "client_uuid", "created_at",
        ]


class SalesReturnWriteSerializer(serializers.Serializer):
    invoice = serializers.PrimaryKeyRelatedField(queryset=Invoice.objects.all())
    reason = serializers.CharField(required=False, allow_blank=True)
    client_uuid = serializers.UUIDField(required=False, allow_null=True)
    lines = SalesReturnLineInputSerializer(many=True)

    def validate_lines(self, lines):
        if not lines:
            raise serializers.ValidationError("At least one line is required.")
        return lines

    def validate(self, attrs):
        """
        Rule #4, enforced here rather than in the model because the cap is a
        cumulative one: what's returnable depends on every earlier return
        against the same invoice line, which a per-row DB constraint can't see.

        Three things are checked, in order:
          1. the invoice belongs to the caller's company;
          2. every referenced invoice line is ON that invoice — this is what
             stops another tenant's InvoiceLine id being priced into our credit
             note, since InvoiceLine has no company_id of its own;
          3. quantity returned, counting prior returns and duplicate lines in
             this same payload, never exceeds what was originally sold.
        """
        invoice = attrs["invoice"]
        _assert_company(self, invoice, "invoice")
        assert_user_branch(self.context["request"].user, invoice, "invoice")
        if invoice.is_void:
            raise serializers.ValidationError(
                {"invoice": "A void invoice cannot be returned."}
            )

        errors = []
        # Several payload lines may point at one invoice line; they have to be
        # summed before comparing, or two half-size lines slip past the cap.
        requested = defaultdict(Decimal)
        seen = {}
        for ln in attrs["lines"]:
            _assert_company(self, ln["product"], "product")
            inv_line = ln["invoice_line"]
            if inv_line.invoice_id != invoice.pk:
                errors.append(
                    f"Invoice line {inv_line.pk} is not on invoice "
                    f"{invoice.pk}."
                )
                continue
            if inv_line.product_id != ln["product"].pk:
                errors.append(
                    f"Invoice line {inv_line.pk} is for a different product "
                    f"than the one being returned."
                )
                continue
            seen[inv_line.pk] = inv_line
            requested[inv_line.pk] += ln["quantity"]

        if errors:
            raise serializers.ValidationError({"lines": errors})

        already = dict(
            SalesReturnLine.objects.filter(invoice_line_id__in=requested)
            .values("invoice_line_id")
            .annotate(total=Sum("quantity"))
            .values_list("invoice_line_id", "total")
        )
        for line_id, qty in requested.items():
            inv_line = seen[line_id]
            remaining = inv_line.quantity - already.get(line_id, Decimal("0"))
            if qty > remaining:
                errors.append(
                    f"Cannot return {qty} of {inv_line.product.sku}: only "
                    f"{remaining} of the {inv_line.quantity} sold on invoice "
                    f"line {line_id} remain returnable."
                )
        if errors:
            raise serializers.ValidationError({"lines": errors})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        user = request.user
        company_id = getattr(user, "company_id", None)
        if company_id is None:
            raise serializers.ValidationError("A company-scoped user is required.")

        invoice = validated_data["invoice"]

        # Serialise returns against the same original lines and repeat the cap
        # under the lock; validation alone is vulnerable to concurrent requests.
        requested = defaultdict(Decimal)
        for line in validated_data["lines"]:
            requested[line["invoice_line"].pk] += line["quantity"]
        locked = {
            line.pk: line
            for line in InvoiceLine.objects.select_for_update().filter(pk__in=requested)
        }
        already = dict(
            SalesReturnLine.objects.filter(invoice_line_id__in=requested)
            .values("invoice_line_id")
            .annotate(total=Sum("quantity"))
            .values_list("invoice_line_id", "total")
        )
        for line_id, quantity in requested.items():
            remaining = locked[line_id].quantity - already.get(line_id, Decimal("0"))
            if quantity > remaining:
                raise serializers.ValidationError(
                    {"lines": f"Only {remaining} remains returnable on line {line_id}."}
                )

        sales_return = SalesReturn.objects.create(
            company_id=company_id, invoice=invoice, customer=invoice.customer,
            reason=validated_data.get("reason", ""),
            created_by=user if user.is_authenticated else None,
            client_uuid=validated_data.get("client_uuid"),
        )
        # Rule #5: NO stock movement here. Lines are quarantined until a
        # deliberate disposition restocks them.
        credit_total = Decimal("0")
        for ln in validated_data["lines"]:
            invoice_line = ln["invoice_line"]
            SalesReturnLine.objects.create(
                sales_return=sales_return,
                invoice_line=invoice_line,
                product=ln["product"],
                quantity=ln["quantity"],
                disposition=SalesReturnLine.QUARANTINE,
            )
            # Priced from the original invoice line (Rule #4), never from the
            # product's current price — the customer is owed what they actually
            # paid, which may differ from today's list price.
            # Use the complete original line value, including its snapshotted
            # tax, allocated proportionally for partial returns.
            credit_total += (invoice_line.line_total / invoice_line.quantity) * ln["quantity"]

        # Rule #6: every return generates a note. Walk-in notes carry the
        # invoice as their party reference and intentionally have no customer.
        if credit_total > 0:
            credit_total = credit_total.quantize(Decimal("0.01"))
            locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
            ceiling = locked.total - locked.credited_total()
            if credit_total > ceiling:
                # Rounding of proportional partial returns can overshoot by a
                # cent on the last one; never credit more than the sale.
                credit_total = max(ceiling, Decimal("0"))
            note = CreditNote.objects.create(
                company_id=company_id,
                customer=invoice.customer,
                invoice=invoice,
                sales_return=sales_return,
                amount=credit_total,
                reason=validated_data.get("reason", ""),
                created_by=user if user.is_authenticated else None,
            )
            Invoice.objects.filter(pk=invoice.pk).update(updated_at=note.created_at)
            log_activity(
                action="create", request=request, entity_type="CreditNote",
                entity_id=note.pk,
                metadata={"sales_return": sales_return.pk, "amount": str(note.amount)},
            )
        return sales_return

    def to_representation(self, instance):
        return SalesReturnReadSerializer(instance, context=self.context).data


# ---------- Purchase return ----------

class PurchaseReturnLineInputSerializer(serializers.Serializer):
    goods_receipt_line = serializers.PrimaryKeyRelatedField(
        queryset=GoodsReceiptLine.objects.select_related(
            "receipt", "product", "batch"
        ).all()
    )
    quantity = serializers.DecimalField(
        max_digits=16, decimal_places=3, min_value=Decimal("0.001")
    )


class PurchaseReturnLineReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseReturnLine
        fields = [
            "id", "goods_receipt_line", "product", "quantity", "batch", "movement"
        ]


class PurchaseReturnReadSerializer(serializers.ModelSerializer):
    lines = PurchaseReturnLineReadSerializer(many=True, read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)

    class Meta:
        model = PurchaseReturn
        fields = [
            "id", "company", "supplier", "supplier_name", "warehouse",
            "goods_receipt", "reason", "lines", "client_uuid", "created_at",
        ]


class PurchaseReturnWriteSerializer(serializers.Serializer):
    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.all())
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    goods_receipt = serializers.PrimaryKeyRelatedField(queryset=GoodsReceipt.objects.all())
    reason = serializers.CharField(required=False, allow_blank=True)
    client_uuid = serializers.UUIDField(required=False, allow_null=True)
    lines = PurchaseReturnLineInputSerializer(many=True)
    # Defaults to the actual unit cost on the original receipt lines. An
    # explicit amount is allowed when the supplier's agreed credit differs.
    debit_amount = serializers.DecimalField(
        max_digits=16, decimal_places=2, required=False, allow_null=True,
        min_value=Decimal("0.01"),
    )
    bill = serializers.PrimaryKeyRelatedField(
        queryset=Bill.objects.all(), required=False, allow_null=True
    )

    def validate_lines(self, lines):
        if not lines:
            raise serializers.ValidationError("At least one line is required.")
        return lines

    def validate(self, attrs):
        supplier = attrs["supplier"]
        warehouse = attrs["warehouse"]
        assert_user_branch(
            self.context["request"].user, warehouse, "warehouse"
        )
        receipt = attrs["goods_receipt"]
        for obj, label in (
            (supplier, "supplier"), (warehouse, "warehouse"),
            (receipt, "goods_receipt"),
        ):
            _assert_company(self, obj, label)
        if receipt.supplier_id != supplier.pk:
            raise serializers.ValidationError(
                {"goods_receipt": "Receipt is not for this supplier."}
            )
        if receipt.warehouse_id != warehouse.pk:
            raise serializers.ValidationError(
                {"warehouse": "Return must leave from the receipt warehouse."}
            )

        requested = defaultdict(Decimal)
        for line in attrs["lines"]:
            original = line["goods_receipt_line"]
            if original.receipt_id != receipt.pk:
                raise serializers.ValidationError(
                    {"lines": "Every return line must belong to the selected receipt."}
                )
            requested[original.pk] += line["quantity"]
        already = dict(
            PurchaseReturnLine.objects.filter(goods_receipt_line_id__in=requested)
            .values("goods_receipt_line_id").annotate(total=Sum("quantity"))
            .values_list("goods_receipt_line_id", "total")
        )
        originals = GoodsReceiptLine.objects.in_bulk(requested)
        for line_id, quantity in requested.items():
            remaining = originals[line_id].quantity - already.get(line_id, Decimal("0"))
            if quantity > remaining:
                raise serializers.ValidationError(
                    {"lines": f"Only {remaining} remains returnable on receipt line {line_id}."}
                )
            original = originals[line_id]
            stock_filter = {
                "company_id": receipt.company_id,
                "product_id": original.product_id,
                "warehouse_id": warehouse.pk,
            }
            if original.batch_id:
                stock_filter["batch_id"] = original.batch_id
            available = StockMovement.objects.filter(**stock_filter).aggregate(
                total=Sum("quantity")
            )["total"] or Decimal("0")
            if quantity > available:
                raise serializers.ValidationError(
                    {"lines": f"Only {available} is available for receipt line {line_id}."}
                )

        bill = attrs.get("bill")
        if bill is not None:
            _assert_company(self, bill, "bill")
            if bill.supplier_id != supplier.pk:
                raise serializers.ValidationError({"bill": "Bill is not for this supplier."})
            if bill.goods_receipt_id and bill.goods_receipt_id != receipt.pk:
                raise serializers.ValidationError({"bill": "Bill is not for this receipt."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        user = request.user
        company_id = getattr(user, "company_id", None)
        if company_id is None:
            raise serializers.ValidationError("A company-scoped user is required.")

        supplier = validated_data["supplier"]
        warehouse = validated_data["warehouse"]
        _assert_company(self, supplier, "supplier")
        _assert_company(self, warehouse, "warehouse")
        receipt = validated_data["goods_receipt"]

        requested = defaultdict(Decimal)
        for line in validated_data["lines"]:
            requested[line["goods_receipt_line"].pk] += line["quantity"]
        locked = GoodsReceiptLine.objects.select_for_update().in_bulk(requested)
        already = dict(
            PurchaseReturnLine.objects.filter(goods_receipt_line_id__in=requested)
            .values("goods_receipt_line_id").annotate(total=Sum("quantity"))
            .values_list("goods_receipt_line_id", "total")
        )
        for line_id, quantity in requested.items():
            remaining = locked[line_id].quantity - already.get(line_id, Decimal("0"))
            if quantity > remaining:
                raise serializers.ValidationError(
                    {"lines": f"Only {remaining} remains returnable on receipt line {line_id}."}
                )

        pr = PurchaseReturn.objects.create(
            company_id=company_id, supplier=supplier, warehouse=warehouse,
            goods_receipt=receipt,
            reason=validated_data.get("reason", ""),
            created_by=user if user.is_authenticated else None,
            client_uuid=validated_data.get("client_uuid"),
        )
        for ln in validated_data["lines"]:
            original = ln["goods_receipt_line"]
            # Goods physically leave us -> purchase_return_out (negative), now.
            movement = StockMovement.objects.create(
                company_id=company_id, product=original.product, warehouse=warehouse,
                batch=original.batch,
                movement_type=StockMovement.PURCHASE_RETURN_OUT,
                quantity=-ln["quantity"],
                reference_type="PurchaseReturn", reference_id=str(pr.id),
                created_by=user if user.is_authenticated else None,
            )
            PurchaseReturnLine.objects.create(
                purchase_return=pr, goods_receipt_line=original,
                product=original.product, quantity=ln["quantity"],
                batch=original.batch, movement=movement,
            )

        # Rule #6: the note the supplier receives, reducing what we owe them.
        cost_basis = sum(
            (line["goods_receipt_line"].unit_cost * line["quantity"]
             for line in validated_data["lines"]),
            Decimal("0"),
        ).quantize(Decimal("0.01"))
        debit_amount = validated_data.get("debit_amount")
        if debit_amount is None:
            debit_amount = cost_basis
        elif debit_amount > cost_basis and not can_approve_high_value(user):
            # Claiming more from the supplier than the goods cost us is a
            # negotiated adjustment, not a clerk's data entry.
            raise serializers.ValidationError(
                {"debit_amount": f"The debit note cannot exceed the goods' cost ({cost_basis})."}
            )
        bill = validated_data.get("bill")
        if bill is not None:
            _assert_company(self, bill, "bill")
        note = DebitNote.objects.create(
            company_id=company_id,
            supplier=supplier,
            bill=bill,
            purchase_return=pr,
            amount=debit_amount,
            reason=validated_data.get("reason", ""),
            created_by=user if user.is_authenticated else None,
        )
        log_activity(
            action="create", request=request, entity_type="DebitNote",
            entity_id=note.pk,
            metadata={
                "purchase_return": pr.pk, "amount": str(note.amount),
                **({"cost_basis": str(cost_basis)} if note.amount != cost_basis else {}),
            },
        )
        movement_ids = [line.movement_id for line in pr.lines.all()]
        if movement_ids:
            log_activity(
                action="create", request=request, entity_type="StockMovement",
                entity_id=movement_ids[0],
                metadata={"purchase_return": pr.pk, "movements": movement_ids},
            )
        return pr

    def to_representation(self, instance):
        return PurchaseReturnReadSerializer(instance, context=self.context).data


# ---------- Credit / Debit notes ----------

class CreditNoteSerializer(serializers.ModelSerializer):
    number_display = serializers.CharField(read_only=True)
    refunded_total = serializers.SerializerMethodField()
    remaining_refundable = serializers.SerializerMethodField()

    def get_refunded_total(self, obj):
        return str(obj.refunded_total())

    def get_remaining_refundable(self, obj):
        return str(obj.remaining_refundable())
    # Names so a note list reads as documents rather than as foreign keys.
    customer_name = serializers.CharField(
        source="customer.name", read_only=True, default=None
    )
    invoice_number = serializers.CharField(
        source="invoice.number_display", read_only=True, default=None
    )

    class Meta:
        model = CreditNote
        fields = [
            "id", "company", "customer", "customer_name",
            "invoice", "invoice_number", "sales_return", "amount",
            "reason", "is_void", "created_by", "created_at", "client_uuid",
            "number", "number_display", "refunded_total", "remaining_refundable",
        ]
        read_only_fields = [
            "company", "is_void", "created_by", "created_at", "number", "number_display",
        ]

    def validate(self, attrs):
        if attrs.get("amount") is None or attrs["amount"] <= 0:
            raise serializers.ValidationError("Amount must be positive.")
        _assert_company(self, attrs.get("customer"), "customer")
        _assert_company(self, attrs.get("invoice"), "invoice")
        _assert_company(self, attrs.get("sales_return"), "sales_return")
        customer = attrs.get("customer")
        invoice = attrs.get("invoice")
        sales_return = attrs.get("sales_return")
        if invoice is not None and invoice.customer_id != getattr(customer, "pk", None):
            raise serializers.ValidationError(
                {"customer": "Customer must match the linked invoice."}
            )
        if sales_return is not None:
            if invoice is not None and sales_return.invoice_id != invoice.pk:
                raise serializers.ValidationError(
                    {"sales_return": "Return must belong to the linked invoice."}
                )
            if sales_return.customer_id != getattr(customer, "pk", None):
                raise serializers.ValidationError(
                    {"customer": "Customer must match the linked return."}
                )
        if customer is None and invoice is None:
            raise serializers.ValidationError(
                {"customer": "A customer is required unless this note is linked to an invoice."}
            )
        if invoice is not None:
            if invoice.is_void:
                raise serializers.ValidationError({"invoice": "That invoice is void."})
            ceiling = invoice.total - invoice.credited_total()
            if attrs["amount"] > ceiling:
                raise serializers.ValidationError(
                    {"amount": f"Only {ceiling} of this invoice remains creditable."}
                )
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data.setdefault("created_by", request.user)
        with transaction.atomic():
            invoice = validated_data.get("invoice")
            if invoice is not None:
                invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
                ceiling = invoice.total - invoice.credited_total()
                if validated_data["amount"] > ceiling:
                    raise serializers.ValidationError(
                        {"amount": f"Only {ceiling} of this invoice remains creditable."}
                    )
                validated_data["invoice"] = invoice
            note = super().create(validated_data)
            if note.invoice_id:
                Invoice.objects.filter(pk=note.invoice_id).update(updated_at=note.created_at)
        return note


class DebitNoteSerializer(serializers.ModelSerializer):
    number_display = serializers.CharField(read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)

    class Meta:
        model = DebitNote
        fields = [
            "id", "company", "supplier", "supplier_name",
            "bill", "purchase_return", "amount",
            "reason", "is_void", "created_by", "created_at", "client_uuid",
            "number", "number_display",
        ]
        read_only_fields = [
            "company", "is_void", "created_by", "created_at", "number", "number_display",
        ]

    def validate(self, attrs):
        if attrs.get("amount") is None or attrs["amount"] <= 0:
            raise serializers.ValidationError("Amount must be positive.")
        _assert_company(self, attrs.get("supplier"), "supplier")
        _assert_company(self, attrs.get("bill"), "bill")
        _assert_company(self, attrs.get("purchase_return"), "purchase_return")
        supplier = attrs.get("supplier")
        bill = attrs.get("bill")
        purchase_return = attrs.get("purchase_return")
        if bill is not None and bill.supplier_id != supplier.pk:
            raise serializers.ValidationError({"bill": "Bill is not for this supplier."})
        if purchase_return is not None:
            if purchase_return.supplier_id != supplier.pk:
                raise serializers.ValidationError(
                    {"purchase_return": "Return is not for this supplier."}
                )
            if bill is not None and purchase_return.goods_receipt_id != bill.goods_receipt_id:
                raise serializers.ValidationError(
                    {"purchase_return": "Return and bill must refer to the same receipt."}
                )
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data.setdefault("created_by", request.user)
        return super().create(validated_data)
