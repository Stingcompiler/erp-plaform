from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from inventory.models import Product, StockBatch, StockMovement, Warehouse
from purchasing.models import Bill, GoodsReceipt, Supplier
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
    invoice_line = serializers.PrimaryKeyRelatedField(
        queryset=InvoiceLine.objects.all(), required=False, allow_null=True
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

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        user = request.user
        company_id = getattr(user, "company_id", None)
        if company_id is None:
            raise serializers.ValidationError("A company-scoped user is required.")

        invoice = validated_data["invoice"]
        _assert_company(self, invoice, "invoice")
        for ln in validated_data["lines"]:
            _assert_company(self, ln["product"], "product")

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
            invoice_line = ln.get("invoice_line")
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
            if invoice_line is not None:
                credit_total += invoice_line.unit_price * ln["quantity"]

        # Rule #6: every return generates a note. Two cases produce none:
        #  * lines with no invoice_line cannot be valued, and a guessed amount
        #    on a document handed to a customer is worse than no document;
        #  * a walk-in sale has no customer to issue the note to (CreditNote
        #    requires one) — that refund is settled in cash at the till.
        if credit_total > 0 and invoice.customer_id:
            CreditNote.objects.create(
                company_id=company_id,
                customer=invoice.customer,
                invoice=invoice,
                sales_return=sales_return,
                amount=credit_total.quantize(Decimal("0.01")),
                reason=validated_data.get("reason", ""),
                created_by=user if user.is_authenticated else None,
            )
        return sales_return

    def to_representation(self, instance):
        return SalesReturnReadSerializer(instance, context=self.context).data


# ---------- Purchase return ----------

class PurchaseReturnLineInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.DecimalField(
        max_digits=16, decimal_places=3, min_value=Decimal("0.001")
    )
    batch = serializers.PrimaryKeyRelatedField(
        queryset=StockBatch.objects.all(), required=False, allow_null=True
    )


class PurchaseReturnLineReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseReturnLine
        fields = ["id", "product", "quantity", "batch", "movement"]


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
    goods_receipt = serializers.PrimaryKeyRelatedField(
        queryset=GoodsReceipt.objects.all(), required=False, allow_null=True
    )
    reason = serializers.CharField(required=False, allow_blank=True)
    client_uuid = serializers.UUIDField(required=False, allow_null=True)
    lines = PurchaseReturnLineInputSerializer(many=True)
    # Rule #6 requires a note for every return. Unlike a sales return — which is
    # priced from the invoice line the goods were sold on — a purchase return
    # line carries no price: PurchaseReturnLine has product and quantity only,
    # and nothing links it to what the supplier charged. So the amount is asked
    # for rather than derived; deriving it from the product's cost price would
    # be inventing a figure and putting it on a document sent to a supplier.
    debit_amount = serializers.DecimalField(
        max_digits=16, decimal_places=2, required=False, allow_null=True,
        min_value=Decimal("0"),
    )
    bill = serializers.PrimaryKeyRelatedField(
        queryset=Bill.objects.all(), required=False, allow_null=True
    )

    def validate_lines(self, lines):
        if not lines:
            raise serializers.ValidationError("At least one line is required.")
        return lines

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
        for ln in validated_data["lines"]:
            _assert_company(self, ln["product"], "product")

        pr = PurchaseReturn.objects.create(
            company_id=company_id, supplier=supplier, warehouse=warehouse,
            goods_receipt=validated_data.get("goods_receipt"),
            reason=validated_data.get("reason", ""),
            created_by=user if user.is_authenticated else None,
            client_uuid=validated_data.get("client_uuid"),
        )
        for ln in validated_data["lines"]:
            # Goods physically leave us -> purchase_return_out (negative), now.
            movement = StockMovement.objects.create(
                company_id=company_id, product=ln["product"], warehouse=warehouse,
                batch=ln.get("batch"),
                movement_type=StockMovement.PURCHASE_RETURN_OUT,
                quantity=-ln["quantity"],
                reference_type="PurchaseReturn", reference_id=str(pr.id),
                created_by=user if user.is_authenticated else None,
            )
            PurchaseReturnLine.objects.create(
                purchase_return=pr, product=ln["product"],
                quantity=ln["quantity"], batch=ln.get("batch"), movement=movement,
            )

        # Rule #6: the note the supplier receives, reducing what we owe them.
        debit_amount = validated_data.get("debit_amount")
        bill = validated_data.get("bill")
        if bill is not None:
            _assert_company(self, bill, "bill")
        if debit_amount:
            DebitNote.objects.create(
                company_id=company_id,
                supplier=supplier,
                bill=bill,
                purchase_return=pr,
                amount=debit_amount,
                reason=validated_data.get("reason", ""),
                created_by=user if user.is_authenticated else None,
            )
        return pr

    def to_representation(self, instance):
        return PurchaseReturnReadSerializer(instance, context=self.context).data


# ---------- Credit / Debit notes ----------

class CreditNoteSerializer(serializers.ModelSerializer):
    # Names so a note list reads as documents rather than as foreign keys.
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    invoice_number = serializers.CharField(
        source="invoice.number_display", read_only=True, default=None
    )

    class Meta:
        model = CreditNote
        fields = [
            "id", "company", "customer", "customer_name",
            "invoice", "invoice_number", "sales_return", "amount",
            "reason", "is_void", "created_by", "created_at", "client_uuid",
        ]
        read_only_fields = ["company", "is_void", "created_by", "created_at"]

    def validate(self, attrs):
        if attrs.get("amount") is None or attrs["amount"] <= 0:
            raise serializers.ValidationError("Amount must be positive.")
        _assert_company(self, attrs.get("customer"), "customer")
        _assert_company(self, attrs.get("invoice"), "invoice")
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data.setdefault("created_by", request.user)
        return super().create(validated_data)


class DebitNoteSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)

    class Meta:
        model = DebitNote
        fields = [
            "id", "company", "supplier", "supplier_name",
            "bill", "purchase_return", "amount",
            "reason", "is_void", "created_by", "created_at", "client_uuid",
        ]
        read_only_fields = ["company", "is_void", "created_by", "created_at"]

    def validate(self, attrs):
        if attrs.get("amount") is None or attrs["amount"] <= 0:
            raise serializers.ValidationError("Amount must be positive.")
        _assert_company(self, attrs.get("supplier"), "supplier")
        _assert_company(self, attrs.get("bill"), "bill")
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data.setdefault("created_by", request.user)
        return super().create(validated_data)
