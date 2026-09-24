from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import serializers

from core.rbac import can_approve_high_value
from core.scoping import assert_user_branch

from inventory.models import (
    Brand,
    Category,
    Product,
    ProductPack,
    StockAdjustment,
    StockBatch,
    StockMovement,
    StockTransfer,
    Unit,
    Warehouse,
)


def _assert_tenant_relations(serializer, attrs, fields):
    request = serializer.context.get("request")
    user = getattr(request, "user", None)
    if user is None or getattr(user, "is_platform_admin", False):
        return
    company_id = getattr(user, "company_id", None)
    for name in fields:
        obj = attrs.get(name)
        if obj is not None and obj.company_id != company_id:
            raise serializers.ValidationError(
                {name: _("Does not belong to your company.")}
            )


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "company", "name", "parent", "is_active"]
        read_only_fields = ["company"]

    def validate(self, attrs):
        _assert_tenant_relations(self, attrs, ("parent",))
        return attrs


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

    def validate(self, attrs):
        _assert_tenant_relations(self, attrs, ("branch",))
        return attrs


class ProductPackSerializer(serializers.ModelSerializer):
    effective_price = serializers.SerializerMethodField()
    product_sku = serializers.CharField(source="product.sku", read_only=True)

    class Meta:
        model = ProductPack
        fields = [
            "id", "company", "product", "product_sku", "name", "quantity", "barcode",
            "sale_price", "effective_price", "is_active",
        ]
        read_only_fields = ["company"]
        # The (product, name) uniqueness is checked in validate() with a
        # sentence a shopkeeper can act on, instead of DRF's "The fields
        # product, name must make a unique set."
        validators = []

    def get_effective_price(self, obj):
        return str(obj.effective_price())

    def _company_id(self, product):
        request = self.context.get("request")
        company_id = getattr(getattr(request, "user", None), "company_id", None)
        if company_id is None and product is not None:
            company_id = product.company_id
        return company_id

    def validate_barcode(self, value):
        return (value or "").strip()

    def validate(self, attrs):
        _assert_tenant_relations(self, attrs, ("product",))
        if attrs.get("quantity") is not None and attrs["quantity"] <= 0:
            raise serializers.ValidationError(
                {"quantity": _("A pack must hold at least one unit.")}
            )
        instance = self.instance
        product = attrs.get("product") or getattr(instance, "product", None)
        is_active = attrs.get("is_active", getattr(instance, "is_active", True))
        if is_active is False:
            # An archived pack gives its barcode back: nothing scans to a
            # pack that is no longer sold, and a new pack (or a product) can
            # take the code without tripping the unique constraint.
            attrs["barcode"] = ""
        name = attrs.get("name")
        if product is not None and name is not None:
            twin = ProductPack.objects.filter(product=product, name=name.strip())
            if instance is not None:
                twin = twin.exclude(pk=instance.pk)
            twin = twin.first()
            if twin is not None:
                message = (
                    _("%(product)s already has a pack named %(name)s; edit that one.")
                    if twin.is_active
                    else _("%(product)s has an archived pack named %(name)s; "
                           "restore it instead of adding it again.")
                )
                raise serializers.ValidationError(
                    {"name": message % {"product": product.name, "name": twin.name}}
                )
            attrs["name"] = name.strip()
        barcode = attrs.get("barcode")
        if barcode and product is not None:
            self._check_barcode(barcode, product, instance)
        return attrs

    def _check_barcode(self, barcode, product, instance):
        """A scan must resolve to one thing: refuse a code already held by a
        product (this pack's own product included — a scan could not tell
        a piece from the carton) or by another active pack."""
        company_id = self._company_id(product)
        holder = Product.objects.filter(company_id=company_id, barcode=barcode).first()
        if holder is not None:
            raise serializers.ValidationError({"barcode": (
                _("This barcode is the product's own; a pack needs a different one.")
                if holder.pk == product.pk
                else _("This barcode already belongs to %(product)s.") % {"product": holder.name}
            )})
        other = ProductPack.objects.filter(company_id=company_id, barcode=barcode)
        if instance is not None:
            other = other.exclude(pk=instance.pk)
        other = other.select_related("product").first()
        if other is not None:
            raise serializers.ValidationError({"barcode": (
                _("This barcode already belongs to the %(pack)s pack of %(product)s.")
                % {"pack": other.name, "product": other.product.name}
            )})

    def _save_guarded(self, write):
        # Two managers saving the same code at the same moment both pass
        # validate(); the unique constraint catches the second. Answer it as
        # the 400 it is, not a 500.
        try:
            with transaction.atomic():
                return write()
        except IntegrityError:
            raise serializers.ValidationError(
                {"barcode": _("This barcode or pack name is already in use; reload and retry.")}
            )

    def create(self, validated_data):
        return self._save_guarded(lambda: super(ProductPackSerializer, self).create(validated_data))

    def update(self, instance, validated_data):
        return self._save_guarded(
            lambda: super(ProductPackSerializer, self).update(instance, validated_data)
        )


class ProductSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    on_hand = serializers.SerializerMethodField()
    # "expired" | "expiring" | None — from the soonest lot that still holds
    # stock (see ProductViewSet.get_queryset); the till warns on it.
    expiry_status = serializers.SerializerMethodField()
    next_expiry = serializers.SerializerMethodField()
    # Selling units (carton, strip, sack) with their base-unit multiplier and
    # price, so the till can offer them without a second request.
    packs = ProductPackSerializer(many=True, read_only=True)
    # Shown beside the quantity at the till so a cashier weighing produce can
    # see whether they are entering kilograms or pieces.
    unit_name = serializers.CharField(
        source="unit.name", read_only=True, default=None
    )
    # reference_price × the company's current rate, rounded to cents: what
    # the shelf price should be today. Only when the view supplies the rate
    # in context (the sync pull does not; the till has no use for it).
    suggested_price = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "company", "sku", "name", "category", "brand", "unit",
            "barcode", "qr_code", "cost_price", "sale_price", "reference_price",
            "reference_cost", "suggested_price", "reorder_level",
            "track_batches", "is_stock_tracked", "is_active", "on_hand",
            "expiry_status", "next_expiry",
            "unit_name", "packs",
            "image_url",
        ]
        read_only_fields = ["company"]
        # A house SKU is allocated when one isn't supplied — see create().
        extra_kwargs = {"sku": {"required": False, "allow_blank": True}}

    # What the goods cost is hidden from roles that only sell or read the
    # catalogue (core.rbac.can_see_cost): a cashier who sees it knows how
    # far a price can be pushed. The till does not need it — the price
    # floor is enforced by the server at checkout.
    COST_FIELDS = ("cost_price", "reference_cost")

    def _sees_cost(self):
        from core.rbac import can_see_cost

        request = self.context.get("request")
        return request is None or can_see_cost(request.user)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self._sees_cost():
            for name in self.COST_FIELDS:
                data.pop(name, None)
        return data

    def get_image_url(self, obj):
        from core.public_media import stored_public_url

        return stored_public_url(obj.image)

    def get_suggested_price(self, obj):
        rate = self.context.get("exchange_rate")
        if not rate or obj.reference_price is None:
            return None
        return (obj.reference_price * rate).quantize(Decimal("0.01"))

    def validate_reference_price(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError(_("Cannot be negative."))
        return value

    def validate_reference_cost(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError(_("Cannot be negative."))
        return value

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

    def validate(self, attrs):
        _assert_tenant_relations(self, attrs, ("category", "brand", "unit"))
        if not self._sees_cost():
            for name in self.COST_FIELDS:
                attrs.pop(name, None)
        instance = self.instance
        if (
            instance is not None and instance.track_batches
            and attrs.get("track_batches") is False
        ):
            # Lots that still hold stock would become invisible: sales would
            # stop drawing them down and the expiry report would keep
            # listing goods long gone. Empty the lots (sell, adjust or count
            # them to zero) first.
            from django.db.models import Sum

            held = list(
                StockBatch.objects.filter(product=instance)
                .annotate(balance=Sum("stock_movements__quantity"))
                .filter(balance__gt=0)
                .values_list("lot_number", flat=True)[:5]
            )
            if held:
                raise serializers.ValidationError({"track_batches": _(
                    "Lots %(lots)s still hold stock; bring them to zero before "
                    "turning off lot tracking."
                ) % {"lots": ", ".join(held)}})
        return attrs

    def validate_barcode(self, value):
        """A barcode must resolve to exactly one thing when scanned. The
        database constraint already refuses a duplicate; this turns the crash
        into a message that names the product holding the code."""
        value = (value or "").strip()
        if not value:
            return value
        request = self.context.get("request")
        company_id = getattr(getattr(request, "user", None), "company_id", None)
        if company_id is None:
            return value
        clash = Product.objects.filter(company_id=company_id, barcode=value)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        holder = clash.first()
        if holder is not None:
            raise serializers.ValidationError(
                _("This barcode already belongs to %(product)s.") % {"product": holder.name}
            )
        pack = ProductPack.objects.filter(company_id=company_id, barcode=value).first()
        if pack is not None:
            raise serializers.ValidationError(
                _("This barcode already belongs to a pack of %(product)s.")
                % {"product": pack.product.name}
            )
        return value

    def get_next_expiry(self, obj):
        return getattr(obj, "next_expiry", None)

    def get_expiry_status(self, obj):
        from inventory.alerts import EXPIRY_HORIZON_DAYS

        expiry = getattr(obj, "next_expiry", None)
        if expiry is None:
            return None
        today = timezone.localdate()
        if expiry < today:
            return "expired"
        if (expiry - today).days <= EXPIRY_HORIZON_DAYS:
            return "expiring"
        return None

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

    def validate(self, attrs):
        _assert_tenant_relations(self, attrs, ("product",))
        return attrs


def check_stockable(serializer, product, batch=None, warehouse=None, outgoing=None,
                    require_lot=True):
    """The rules every hand-made stock document (an adjustment, a transfer, a
    receipt line) follows before it may move a product's stock.

    - an archived product is not moved (restore it first);
    - a product that is not stocked (a bag, a delivery charge) has no stock;
    - a lot-tracked product names its lot, and when stock leaves a lot
      (``outgoing`` = the quantity taken out of ``warehouse``) that lot must
      hold it there.

    Live, a breach is a 400. Replayed from an offline device
    (``context["via_sync"]``) the adjustment or receipt already happened on
    the shop floor, and an old client never sent a lot: it is accepted, and
    the rules it skipped are returned so the caller can audit them once the
    document exists (``audit_bypassed``).
    """
    problems = []
    if product is None:
        return problems
    params = {"sku": product.sku}
    if not product.is_active:
        problems.append(("product", "archived", _(
            "%(sku)s is archived; restore it before moving its stock."
        ) % params))
    if not product.is_stock_tracked:
        problems.append(("product", "not_stock_tracked", _(
            "%(sku)s is not a stocked item, so it has no stock to move."
        ) % params))
    if require_lot and product.track_batches and product.is_stock_tracked:
        if batch is None:
            problems.append(("batch", "lot_missing", _(
                "%(sku)s is tracked by lot: choose the lot."
            ) % params))
        elif outgoing and warehouse is not None:
            available = product.on_hand(warehouse=warehouse, batch=batch)
            if Decimal(outgoing) > available:
                problems.append(("batch", "lot_short", _(
                    "Lot %(lot)s holds only %(available)s at %(warehouse)s."
                ) % {"lot": batch.lot_number, "available": available,
                     "warehouse": warehouse.name}))
    if problems and not serializer.context.get("via_sync"):
        field, _code, message = problems[0]
        raise serializers.ValidationError({field: message})
    return problems


def audit_bypassed(serializer, problems, entity_type, entity_id, product):
    """One audit row per rule a synced document was allowed to skip."""
    if not problems:
        return
    from core.activity import log_activity

    for field, code, message in problems:
        log_activity(
            action="sync_stock_rule_bypassed", request=serializer.context.get("request"),
            entity_type=entity_type, entity_id=entity_id,
            metadata={"via": "sync", "rule": code, "product": product.pk,
                      "sku": product.sku, "field": field},
        )


def _validate_sign(movement_type, quantity):
    """Enforce the sign contract for a movement type (see StockMovement)."""
    if quantity == 0:
        raise serializers.ValidationError(_("Quantity cannot be zero."))
    if movement_type in StockMovement.POSITIVE_TYPES and quantity < 0:
        raise serializers.ValidationError(
            _("%(type)s must have a positive quantity.") % {"type": movement_type}
        )
    if movement_type in StockMovement.NEGATIVE_TYPES and quantity > 0:
        raise serializers.ValidationError(
            _("%(type)s must have a negative quantity.") % {"type": movement_type}
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

    # Movements that carry a document (a receipt, a sale, a return, a
    # transfer) are written by that document's own serializer, which is where
    # the price, the supplier, the invoice and the AP/AR effect live. The raw
    # endpoint therefore accepts only the one type that has no other home:
    # an adjustment. Anything else here would be stock appearing or vanishing
    # with no paper behind it.
    DIRECT_TYPES = {StockMovement.ADJUSTMENT}

    def validate(self, attrs):
        if attrs["movement_type"] not in self.DIRECT_TYPES:
            raise serializers.ValidationError(
                {
                    "movement_type": (
                        _("Only adjustments can be posted directly. Use receiving, the "
                          "POS, returns or transfers for every other movement.")
                    )
                }
            )
        _validate_sign(attrs["movement_type"], attrs["quantity"])
        self._check_same_company(attrs)
        quantity = attrs["quantity"]
        self._bypassed = check_stockable(
            self, attrs.get("product"), attrs.get("batch"), attrs.get("warehouse"),
            outgoing=-quantity if quantity < 0 else None,
        )
        return attrs

    def _check_same_company(self, attrs):
        # Never let a movement staple together objects from another tenant,
        # nor a lot of one product with a movement of another.
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None or getattr(user, "is_platform_admin", False):
            return
        company_id = getattr(user, "company_id", None)
        for key in ("product", "warehouse", "batch"):
            obj = attrs.get(key)
            if obj is not None and obj.company_id != company_id:
                raise serializers.ValidationError(
                    {key: _("Does not belong to your company.")}
                )
            if key == "warehouse":
                assert_user_branch(user, obj, key)
        batch = attrs.get("batch")
        product = attrs.get("product")
        if batch is not None and product is not None and batch.product_id != product.pk:
            raise serializers.ValidationError(
                {"batch": _("That lot belongs to a different product.")}
            )

    def create(self, validated_data):
        request = self.context.get("request")
        if request is not None and request.user.is_authenticated:
            validated_data.setdefault("created_by", request.user)
        movement = super().create(validated_data)
        audit_bypassed(
            self, getattr(self, "_bypassed", None), "StockMovement", movement.pk,
            movement.product,
        )
        return movement


class StockAdjustmentSerializer(serializers.ModelSerializer):
    reason_code_display = serializers.CharField(
        source="get_reason_code_display", read_only=True
    )

    class Meta:
        model = StockAdjustment
        fields = [
            "id", "company", "product", "warehouse", "batch", "quantity",
            "reason_code", "reason_code_display", "reason", "movement", "client_uuid",
            "created_by", "approved_by", "created_at",
        ]
        read_only_fields = [
            "company", "movement", "created_by", "approved_by", "created_at",
        ]

    def validate(self, attrs):
        if attrs["quantity"] == 0:
            raise serializers.ValidationError(_("Adjustment quantity cannot be zero."))
        if not (attrs.get("reason") or "").strip():
            raise serializers.ValidationError(
                {"reason": _("Say why the stock is being adjusted.")}
            )
        StockMovementSerializer._check_same_company(self, attrs)
        # A lot-tracked product is adjusted lot by lot: an adjustment with no
        # lot left the lot balances (and the expiry report) wrong for ever.
        quantity = attrs["quantity"]
        self._bypassed = check_stockable(
            self, attrs.get("product"), attrs.get("batch"), attrs.get("warehouse"),
            outgoing=-quantity if quantity < 0 else None,
        )
        # Above the company's threshold an adjustment is a supervisory act:
        # the same approver roles that sign off payments and till counts.
        request = self.context.get("request")
        user = getattr(request, "user", None)
        company = getattr(user, "company", None)
        threshold = getattr(company, "stock_adjustment_approval_threshold", None) or 0
        if threshold:
            value = abs(attrs["quantity"]) * (attrs["product"].cost_price or Decimal("0"))
            if value >= threshold and not can_approve_high_value(user):
                raise serializers.ValidationError(
                    {
                        "quantity": (
                            _("An adjustment worth %(value)s needs a manager or owner "
                              "(threshold %(threshold)s).")
                            % {"value": value, "threshold": threshold}
                        )
                    }
                )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        user = request.user
        creator = user if user.is_authenticated else None
        company_id = validated_data.get("company_id")
        if company_id is None:
            raise serializers.ValidationError(_("Company context is required."))
        product = validated_data["product"]
        movement = StockMovement.objects.create(
            company_id=company_id,
            product=product,
            warehouse=validated_data["warehouse"],
            batch=validated_data.get("batch"),
            movement_type=StockMovement.ADJUSTMENT,
            quantity=validated_data["quantity"],
            # Valued at the product's cost at the moment of the adjustment,
            # so a write-off shows its worth in the shrinkage figures and a
            # positive correction enters the cost layers at a known cost.
            unit_cost=product.cost_price,
            reference_type="StockAdjustment",
            note=validated_data.get("reason", ""),
            created_by=creator,
        )
        adjustment = StockAdjustment.objects.create(
            movement=movement,
            created_by=creator,
            approved_by=creator if can_approve_high_value(user) else None,
            **validated_data,
        )
        movement.reference_id = str(adjustment.id)
        movement.save(update_fields=["reference_id"])
        audit_bypassed(
            self, getattr(self, "_bypassed", None), "StockAdjustment", adjustment.pk, product
        )
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
            raise serializers.ValidationError(_("Transfer quantity must be positive."))
        if attrs["source_warehouse"] == attrs["dest_warehouse"]:
            raise serializers.ValidationError(
                _("Source and destination warehouses must differ.")
            )
        StockMovementSerializer._check_same_company(
            self,
            {
                "product": attrs.get("product"),
                "warehouse": attrs.get("source_warehouse"),
                "batch": attrs.get("batch"),
            },
        )
        # The destination only has to be ours. A branch manager may send
        # stock to another branch: authority over the SOURCE is what matters,
        # and the receiving branch sees the stock arrive in its own ledger.
        request = self.context.get("request")
        user = getattr(request, "user", None)
        dest = attrs.get("dest_warehouse")
        if (
            dest is not None
            and user is not None
            and dest.company_id != getattr(user, "company_id", None)
        ):
            raise serializers.ValidationError(
                {"dest_warehouse": _("Does not belong to your company.")}
            )
        # A lot-tracked product moves lot by lot, so the lot's balance
        # follows it to the destination. The lot's shortfall at the source
        # is checked under a lock in create().
        self._bypassed = check_stockable(self, attrs.get("product"), attrs.get("batch"))
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        user = request.user
        creator = user if user.is_authenticated else None
        company_id = validated_data.get("company_id")
        if company_id is None:
            raise serializers.ValidationError(_("Company context is required."))
        product = Product.objects.select_for_update().get(pk=validated_data["product"].pk)
        batch = validated_data.get("batch")
        qty = validated_data["quantity"]
        source = validated_data["source_warehouse"]

        # A transfer moves stock that exists. Unlike a sale, nothing physical
        # has already happened when the form is submitted, so a shortfall is
        # a data problem to fix (count the shelf) and not a fact to record:
        # allowing it would invent sellable stock at the destination.
        available = product.on_hand(warehouse=source, batch=batch)
        if Decimal(qty) > available:
            raise serializers.ValidationError(
                {
                    "quantity": (
                        _("Only %(available)s is on hand at %(warehouse)s in lot %(lot)s. "
                          "Count the shelf and adjust before transferring.")
                        % {"available": available, "warehouse": source.name,
                           "lot": batch.lot_number}
                        if batch
                        else _("Only %(available)s is on hand at %(warehouse)s. "
                               "Count the shelf and adjust before transferring.")
                        % {"available": available, "warehouse": source.name}
                    )
                }
            )
        # The receiving side carries the sender's cost so a move between
        # warehouses never re-prices stock.
        cost = product.cost_price
        out_move = StockMovement.objects.create(
            company_id=company_id, product=product,
            warehouse=source, batch=batch,
            movement_type=StockMovement.TRANSFER, quantity=-Decimal(qty),
            unit_cost=cost,
            reference_type="StockTransfer", created_by=creator,
        )
        in_move = StockMovement.objects.create(
            company_id=company_id, product=product,
            warehouse=validated_data["dest_warehouse"], batch=batch,
            movement_type=StockMovement.TRANSFER, quantity=Decimal(qty),
            unit_cost=cost,
            reference_type="StockTransfer", created_by=creator,
        )
        validated_data["product"] = product
        transfer = StockTransfer.objects.create(
            source_movement=out_move, dest_movement=in_move, created_by=creator,
            **validated_data,
        )
        for m in (out_move, in_move):
            m.reference_id = str(transfer.id)
            m.save(update_fields=["reference_id"])
        audit_bypassed(
            self, getattr(self, "_bypassed", None), "StockTransfer", transfer.pk, product
        )
        return transfer


class StockCountLineSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    lot_number = serializers.CharField(source="batch.lot_number", read_only=True, default=None)
    variance = serializers.DecimalField(max_digits=16, decimal_places=3, read_only=True)

    class Meta:
        from inventory.models import StockCountLine

        model = StockCountLine
        fields = [
            "id", "product", "product_sku", "product_name", "batch", "lot_number",
            "counted_quantity", "expected_quantity", "variance", "adjustment",
        ]
        read_only_fields = ["expected_quantity", "adjustment"]

    def validate(self, attrs):
        _assert_tenant_relations(self, attrs, ("product", "batch"))
        batch = attrs.get("batch")
        product = attrs.get("product")
        if batch is not None and product is not None and batch.product_id != product.pk:
            raise serializers.ValidationError(
                {"batch": _("That lot belongs to a different product.")}
            )
        if attrs.get("counted_quantity") is not None and attrs["counted_quantity"] < 0:
            raise serializers.ValidationError(
                {"counted_quantity": _("A count cannot be negative.")}
            )
        if product is not None and product.track_batches and batch is None:
            raise serializers.ValidationError(
                {"batch": _("%(sku)s is tracked by lot: choose the lot you counted.")
                 % {"sku": product.sku}}
            )
        if product is not None and not product.is_active:
            raise serializers.ValidationError(
                {"product": _("%(sku)s is archived; restore it before counting it.")
                 % {"sku": product.sku}}
            )
        return attrs


class StockCountSerializer(serializers.ModelSerializer):
    lines = StockCountLineSerializer(many=True)
    # Worked out by the server, so the buttons match what it will accept:
    # the Approve button used to follow a different rule and ended in a
    # refusal nobody could explain.
    can_approve = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    moved_since = serializers.SerializerMethodField()
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    counted_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()

    class Meta:
        from inventory.models import StockCount

        model = StockCount
        fields = [
            "id", "company", "warehouse", "warehouse_name", "status", "note", "lines",
            "counted_by", "counted_by_name", "submitted_at",
            "approved_by", "approved_by_name", "approved_at", "client_uuid", "created_at",
            "can_approve", "can_cancel", "counted_at", "moved_since",
        ]
        read_only_fields = [
            "company", "status", "counted_by", "submitted_at", "approved_by", "approved_at",
            "created_at", "counted_at",
        ]

    def _person(self, user):
        return (user.full_name or user.email) if user else None

    def get_counted_by_name(self, obj):
        return self._person(obj.counted_by)

    def get_approved_by_name(self, obj):
        return self._person(obj.approved_by)

    def _viewer(self):
        request = self.context.get("request")
        return request.user if request is not None else None

    def get_can_approve(self, obj):
        from inventory.counts import may_approve

        user = self._viewer()
        return bool(user and may_approve(obj, user))

    def get_can_cancel(self, obj):
        from inventory.counts import may_cancel

        user = self._viewer()
        return bool(user and may_cancel(obj, user))

    def get_moved_since(self, obj):
        """Stock movements of the counted products in this warehouse since the
        count was taken. Approval posts the counted difference on top of them
        (it does not reset stock to the count), so they are kept — the
        approver is only told they happened."""
        if obj.status != obj.SUBMITTED or obj.counted_at is None:
            return 0
        products = [line.product_id for line in obj.lines.all()]
        return StockMovement.objects.filter(
            company_id=obj.company_id, warehouse_id=obj.warehouse_id,
            product_id__in=products, created_at__gt=obj.counted_at,
        ).exclude(reference_type="StockCount", reference_id=str(obj.pk)).count()

    def validate_lines(self, lines):
        # An empty draft used to save and then fail at submit, far from the
        # moment the counter could have fixed it.
        if not lines:
            raise serializers.ValidationError(_("Add at least one product to the count."))
        return lines

    def validate(self, attrs):
        _assert_tenant_relations(self, attrs, ("warehouse",))
        warehouse = attrs.get("warehouse")
        if warehouse is not None and not warehouse.is_active:
            raise serializers.ValidationError(
                {"warehouse": _("That warehouse is archived.")}
            )
        request = self.context.get("request")
        if request is not None and attrs.get("warehouse") is not None:
            assert_user_branch(request.user, attrs["warehouse"], "warehouse")
        if self.instance is not None and self.instance.status != self.instance.DRAFT:
            raise serializers.ValidationError(_("Only a draft count can be edited."))
        return attrs

    def _write_lines(self, count, lines):
        from inventory.models import StockCountLine

        count.lines.all().delete()
        seen = set()
        for line in lines:
            key = (line["product"].pk, line.get("batch").pk if line.get("batch") else None)
            if key in seen:
                raise serializers.ValidationError(
                    {
                        "lines": _("%(sku)s is listed twice for the same lot.")
                        % {"sku": line["product"].sku}
                    }
                )
            seen.add(key)
            # Frozen now, when the shelf was counted (see StockCount.counted_at).
            expected = line["product"].on_hand(warehouse=count.warehouse, batch=line.get("batch"))
            StockCountLine.objects.create(count=count, expected_quantity=expected, **line)
        count.counted_at = timezone.now()
        count.save(update_fields=["counted_at"])

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines")
        request = self.context.get("request")
        if request is not None and request.user.is_authenticated:
            validated_data.setdefault("counted_by", request.user)
        count = super().create(validated_data)
        self._write_lines(count, lines)
        return count

    @transaction.atomic
    def update(self, instance, validated_data):
        lines = validated_data.pop("lines", None)
        count = super().update(instance, validated_data)
        if lines is not None:
            self._write_lines(count, lines)
        return count
