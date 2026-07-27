from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from inventory.models import (
    Brand,
    Category,
    Product,
    StockAdjustment,
    StockBatch,
    StockMovement,
    StockTransfer,
    Unit,
    Warehouse,
)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "company", "name", "parent", "is_active"]
        read_only_fields = ["company"]


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ["id", "company", "name", "is_active"]
        read_only_fields = ["company"]


class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = ["id", "company", "name", "symbol", "is_active"]
        read_only_fields = ["company"]


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = ["id", "company", "branch", "name", "code", "is_active"]
        read_only_fields = ["company"]


class ProductSerializer(serializers.ModelSerializer):
    on_hand = serializers.SerializerMethodField()
    # Shown beside the quantity at the till so a cashier weighing produce can
    # see whether they are entering kilograms or pieces.
    unit_name = serializers.CharField(
        source="unit.name", read_only=True, default=None
    )

    class Meta:
        model = Product
        fields = [
            "id", "company", "sku", "name", "category", "brand", "unit",
            "barcode", "qr_code", "cost_price", "sale_price", "reorder_level",
            "track_batches", "is_stock_tracked", "is_active", "on_hand",
            "unit_name",
        ]
        read_only_fields = ["company"]
        # A house SKU is allocated when one isn't supplied — see create().
        extra_kwargs = {"sku": {"required": False, "allow_blank": True}}

    def create(self, validated_data):
        """Fill in a SKU when the caller left it blank.

        Deliberately only on create: regenerating on edit would change the code
        a shop may already have printed on a shelf label.
        """
        if not validated_data.get("sku"):
            from inventory.barcodes import next_internal_sku

            company_id = validated_data.get("company_id") or getattr(
                validated_data.get("company"), "id", None
            )
            request = self.context.get("request")
            if company_id is None and request is not None:
                company_id = getattr(request.user, "company_id", None)
            if company_id is not None:
                validated_data["sku"] = next_internal_sku(company_id)
        return super().create(validated_data)

    def get_on_hand(self, obj):
        # Uses the annotated value when present (list view), else computes it.
        annotated = getattr(obj, "annotated_on_hand", None)
        if annotated is not None:
            return annotated
        return obj.on_hand()


class StockBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockBatch
        fields = ["id", "company", "product", "lot_number", "expiry_date", "received_at"]
        read_only_fields = ["company", "received_at"]


def _validate_sign(movement_type, quantity):
    """Enforce the sign contract for a movement type (see StockMovement)."""
    if quantity == 0:
        raise serializers.ValidationError("Quantity cannot be zero.")
    if movement_type in StockMovement.POSITIVE_TYPES and quantity < 0:
        raise serializers.ValidationError(
            f"{movement_type} must have a positive quantity."
        )
    if movement_type in StockMovement.NEGATIVE_TYPES and quantity > 0:
        raise serializers.ValidationError(
            f"{movement_type} must have a negative quantity."
        )


class StockMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockMovement
        fields = [
            "id", "company", "product", "warehouse", "batch", "movement_type",
            "quantity", "unit_cost", "reference_type", "reference_id", "note",
            "client_uuid", "created_by", "created_at",
        ]
        read_only_fields = ["company", "created_by", "created_at"]

    def validate(self, attrs):
        _validate_sign(attrs["movement_type"], attrs["quantity"])
        self._check_same_company(attrs)
        return attrs

    def _check_same_company(self, attrs):
        # Never let a movement staple together objects from another tenant.
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None or getattr(user, "is_platform_admin", False):
            return
        company_id = getattr(user, "company_id", None)
        for key in ("product", "warehouse", "batch"):
            obj = attrs.get(key)
            if obj is not None and obj.company_id != company_id:
                raise serializers.ValidationError(
                    {key: "Does not belong to your company."}
                )

    def create(self, validated_data):
        request = self.context.get("request")
        if request is not None and request.user.is_authenticated:
            validated_data.setdefault("created_by", request.user)
        return super().create(validated_data)


class StockAdjustmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockAdjustment
        fields = [
            "id", "company", "product", "warehouse", "batch", "quantity",
            "reason", "movement", "client_uuid", "created_by", "created_at",
        ]
        read_only_fields = ["company", "movement", "created_by", "created_at"]

    def validate(self, attrs):
        if attrs["quantity"] == 0:
            raise serializers.ValidationError("Adjustment quantity cannot be zero.")
        StockMovementSerializer._check_same_company(self, attrs)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        user = request.user
        creator = user if user.is_authenticated else None
        company_id = validated_data.get("company_id")
        if company_id is None:
            raise serializers.ValidationError("Company context is required.")
        movement = StockMovement.objects.create(
            company_id=company_id,
            product=validated_data["product"],
            warehouse=validated_data["warehouse"],
            batch=validated_data.get("batch"),
            movement_type=StockMovement.ADJUSTMENT,
            quantity=validated_data["quantity"],
            reference_type="StockAdjustment",
            note=validated_data.get("reason", ""),
            created_by=creator,
        )
        adjustment = StockAdjustment.objects.create(
            movement=movement,
            created_by=creator,
            **validated_data,
        )
        movement.reference_id = str(adjustment.id)
        movement.save(update_fields=["reference_id"])
        return adjustment


class StockTransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockTransfer
        fields = [
            "id", "company", "product", "batch", "source_warehouse",
            "dest_warehouse", "quantity", "note", "source_movement",
            "dest_movement", "client_uuid", "created_by", "created_at",
        ]
        read_only_fields = [
            "company", "source_movement", "dest_movement", "created_by", "created_at",
        ]

    def validate(self, attrs):
        if attrs["quantity"] <= 0:
            raise serializers.ValidationError("Transfer quantity must be positive.")
        if attrs["source_warehouse"] == attrs["dest_warehouse"]:
            raise serializers.ValidationError(
                "Source and destination warehouses must differ."
            )
        StockMovementSerializer._check_same_company(
            self,
            {
                "product": attrs.get("product"),
                "warehouse": attrs.get("source_warehouse"),
                "batch": attrs.get("batch"),
            },
        )
        # dest warehouse company check
        StockMovementSerializer._check_same_company(
            self, {"warehouse": attrs.get("dest_warehouse")}
        )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        user = request.user
        creator = user if user.is_authenticated else None
        company_id = validated_data.get("company_id")
        if company_id is None:
            raise serializers.ValidationError("Company context is required.")
        product = validated_data["product"]
        batch = validated_data.get("batch")
        qty = validated_data["quantity"]

        out_move = StockMovement.objects.create(
            company_id=company_id, product=product,
            warehouse=validated_data["source_warehouse"], batch=batch,
            movement_type=StockMovement.TRANSFER, quantity=-Decimal(qty),
            reference_type="StockTransfer", created_by=creator,
        )
        in_move = StockMovement.objects.create(
            company_id=company_id, product=product,
            warehouse=validated_data["dest_warehouse"], batch=batch,
            movement_type=StockMovement.TRANSFER, quantity=Decimal(qty),
            reference_type="StockTransfer", created_by=creator,
        )
        transfer = StockTransfer.objects.create(
            source_movement=out_move, dest_movement=in_move, created_by=creator,
            **validated_data,
        )
        for m in (out_move, in_move):
            m.reference_id = str(transfer.id)
            m.save(update_fields=["reference_id"])
        return transfer
