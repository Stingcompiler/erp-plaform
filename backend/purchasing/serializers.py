from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from inventory.models import Product, StockBatch, StockMovement, Warehouse
from purchasing.models import (
    Bill,
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierPayment,
)

TWO_PLACES = Decimal("0.01")


def _q2(value):
    return Decimal(value).quantize(TWO_PLACES)


def _company_tax_rate_by_id(company_id):
    from org.models import Company
    try:
        profile = getattr(Company.objects.get(pk=company_id), "tax_profile", None)
        return profile.flat_tax_rate if profile else Decimal("0")
    except Company.DoesNotExist:
        return Decimal("0")


class SupplierSerializer(serializers.ModelSerializer):
    ap_balance = serializers.SerializerMethodField()

    class Meta:
        model = Supplier
        fields = [
            "id", "company", "name", "phone", "email", "address",
            "is_active", "ap_balance",
        ]
        read_only_fields = ["company"]

    def get_ap_balance(self, obj):
        return obj.ap_balance()


class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseOrderLine
        fields = [
            "id", "product", "description", "quantity_ordered",
            "unit_cost", "line_total",
        ]
        read_only_fields = ["line_total"]


class PurchaseOrderSerializer(serializers.ModelSerializer):
    lines = PurchaseOrderLineSerializer(many=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            "id", "company", "supplier", "branch", "status", "expected_date",
            "subtotal", "tax_amount", "total", "lines", "created_at",
        ]
        read_only_fields = ["company", "subtotal", "tax_amount", "total", "created_at"]

    def validate(self, attrs):
        _assert_same_company(self, attrs.get("supplier"), "supplier")
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines")
        company_id = validated_data.get("company_id")
        rate = _company_tax_rate_by_id(company_id)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        po = PurchaseOrder.objects.create(**validated_data)
        subtotal = Decimal("0")
        for line in lines:
            lt = _q2(line["quantity_ordered"] * line["unit_cost"])
            PurchaseOrderLine.objects.create(
                purchase_order=po, line_total=lt, **line
            )
            subtotal += lt
        po.subtotal = _q2(subtotal)
        po.tax_amount = _q2(subtotal * rate / 100)
        po.total = po.subtotal + po.tax_amount
        po.save(update_fields=["subtotal", "tax_amount", "total"])
        return po


def _assert_same_company(serializer, obj, label):
    """Reject a referenced object that belongs to another tenant."""
    if obj is None:
        return
    request = serializer.context.get("request")
    user = getattr(request, "user", None)
    if user is None or getattr(user, "is_platform_admin", False):
        return
    if obj.company_id != getattr(user, "company_id", None):
        raise serializers.ValidationError({label: "Not your company's record."})


# ---------- Goods Receipt ----------

class ReceiptLineInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.DecimalField(
        max_digits=16, decimal_places=3, min_value=Decimal("0.001")
    )
    unit_cost = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False
    )
    lot_number = serializers.CharField(required=False, allow_blank=True)
    expiry_date = serializers.DateField(required=False, allow_null=True)


class GoodsReceiptWriteSerializer(serializers.Serializer):
    """
    Atomic, idempotent receiving. Each line posts exactly one `purchase_in`
    stock movement, creating/linking a StockBatch when the product is
    batch-tracked and a lot number is supplied.
    """

    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.all())
    purchase_order = serializers.PrimaryKeyRelatedField(
        queryset=PurchaseOrder.objects.all(), required=False, allow_null=True
    )
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    note = serializers.CharField(required=False, allow_blank=True)
    client_uuid = serializers.UUIDField(required=False, allow_null=True)
    lines = ReceiptLineInputSerializer(many=True)

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
        po = validated_data.get("purchase_order")
        for obj, label in [
            (supplier, "supplier"),
            (warehouse, "warehouse"),
            (po, "purchase_order"),
        ]:
            _assert_same_company(self, obj, label)
        for ln in validated_data["lines"]:
            _assert_same_company(self, ln["product"], "product")

        receipt = GoodsReceipt.objects.create(
            company_id=company_id, supplier=supplier, purchase_order=po,
            warehouse=warehouse, note=validated_data.get("note", ""),
            received_by=user if user.is_authenticated else None,
            client_uuid=validated_data.get("client_uuid"),
        )

        for ln in validated_data["lines"]:
            product = ln["product"]
            qty = ln["quantity"]
            cost = ln.get("unit_cost")
            if cost is None:
                cost = product.cost_price

            batch = None
            lot = ln.get("lot_number") or ""
            if product.track_batches and lot:
                batch, _ = StockBatch.objects.get_or_create(
                    company_id=company_id, product=product, lot_number=lot,
                    defaults={"expiry_date": ln.get("expiry_date")},
                )

            movement = StockMovement.objects.create(
                company_id=company_id, product=product, warehouse=warehouse,
                batch=batch, movement_type=StockMovement.PURCHASE_IN,
                quantity=qty, unit_cost=cost,
                reference_type="GoodsReceipt", reference_id=str(receipt.id),
                created_by=user if user.is_authenticated else None,
            )
            GoodsReceiptLine.objects.create(
                receipt=receipt, product=product, quantity=qty,
                unit_cost=cost, batch=batch, movement=movement,
            )
        return receipt

    def to_representation(self, instance):
        return GoodsReceiptReadSerializer(instance, context=self.context).data


class GoodsReceiptLineReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoodsReceiptLine
        fields = ["id", "product", "quantity", "unit_cost", "batch", "movement"]


class GoodsReceiptReadSerializer(serializers.ModelSerializer):
    lines = GoodsReceiptLineReadSerializer(many=True, read_only=True)

    class Meta:
        model = GoodsReceipt
        fields = [
            "id", "company", "supplier", "purchase_order", "warehouse",
            "note", "received_at", "client_uuid", "lines",
        ]


# ---------- Bill ----------

class BillSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    amount_paid = serializers.SerializerMethodField()
    amount_due = serializers.SerializerMethodField()

    days_overdue = serializers.IntegerField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Bill
        fields = [
            "id", "company", "supplier", "purchase_order", "goods_receipt",
            "supplier_invoice_number", "subtotal", "tax_amount", "total",
            "is_void", "status", "amount_paid", "amount_due", "client_uuid",
            "created_at", "payment_terms_days", "due_date",
            "days_overdue", "is_overdue",
        ]
        read_only_fields = ["company", "is_void", "created_at", "due_date"]

    def get_amount_paid(self, obj):
        return obj.amount_paid()

    def get_amount_due(self, obj):
        return obj.amount_due()

    def validate(self, attrs):
        _assert_same_company(self, attrs.get("supplier"), "supplier")
        if attrs.get("total") is None or attrs["total"] < 0:
            raise serializers.ValidationError("Total must be non-negative.")
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data.setdefault("created_by", request.user)
        return super().create(validated_data)


# ---------- Supplier payment (Rule #3 spirit) ----------

class SupplierPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierPayment
        fields = [
            "id", "company", "supplier", "bill", "method", "from_bank_account",
            "reference_last4", "amount", "recorded_by", "recorded_at",
            "verified_at", "verified_by", "client_uuid",
        ]
        read_only_fields = [
            "company", "recorded_by", "recorded_at", "verified_at", "verified_by",
        ]

    def validate(self, attrs):
        amount = attrs.get("amount")
        if amount is None or amount <= 0:
            raise serializers.ValidationError("Amount must be positive.")

        method = attrs.get("method")
        bank = attrs.get("from_bank_account")
        ref = attrs.get("reference_last4", "")

        if method == SupplierPayment.BANK_TRANSFER:
            if bank is None:
                raise serializers.ValidationError(
                    "Bank transfer requires the paying-from company bank account."
                )
            if not ref or not ref.isdigit() or len(ref) > 4:
                raise serializers.ValidationError(
                    "reference_last4 must be up to 4 digits."
                )
        elif method == SupplierPayment.CASH:
            if bank or ref:
                raise serializers.ValidationError(
                    "Cash payments must not carry bank/reference details."
                )

        _assert_same_company(self, attrs.get("supplier"), "supplier")
        _assert_same_company(self, attrs.get("bill"), "bill")
        _assert_same_company(self, attrs.get("from_bank_account"), "from_bank_account")
        bill = attrs.get("bill")
        supplier = attrs.get("supplier")
        if bill is not None and supplier is not None and bill.supplier_id != supplier.id:
            raise serializers.ValidationError({"bill": "Bill is not for this supplier."})
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data.setdefault("recorded_by", request.user)
        return super().create(validated_data)
