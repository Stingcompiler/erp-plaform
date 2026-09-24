from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.db.models import Sum
from django.db.models.functions import Coalesce
from rest_framework import serializers

from core.activity import log_activity
from core.rbac import can_approve_high_value
from core.scoping import assert_user_branch

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
    opening_balance = serializers.SerializerMethodField()

    class Meta:
        model = Supplier
        fields = [
            "id", "company", "name", "phone", "email", "address",
            "is_active", "ap_balance", "opening_balance", "updated_at",
        ]
        read_only_fields = ["company", "updated_at"]

    def get_ap_balance(self, obj):
        return obj.ap_balance()

    def get_opening_balance(self, obj):
        opening = obj.bills.filter(is_opening_balance=True, is_void=False).first()
        if opening is None:
            return None
        return {"amount": str(opening.total), "as_of": opening.due_date, "bill": opening.id}


class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    # What has already arrived against this line, so the receiving screen
    # can prefill the remainder and the order page can show progress.
    received_quantity = serializers.SerializerMethodField()
    remaining_quantity = serializers.SerializerMethodField()
    product_name = serializers.CharField(source="product.name", read_only=True, default="")
    product_sku = serializers.CharField(source="product.sku", read_only=True, default="")
    # The receiving screen asks for lot and expiry only on these lines; it
    # used to assume "not tracked" for every order line, and the server then
    # refused the receipt with no field to type the lot into.
    product_track_batches = serializers.BooleanField(
        source="product.track_batches", read_only=True, default=False
    )

    class Meta:
        model = PurchaseOrderLine
        fields = [
            "id", "product", "product_name", "product_sku", "description", "quantity_ordered",
            "unit_cost", "line_total", "received_quantity", "remaining_quantity",
            "product_track_batches",
        ]
        read_only_fields = ["line_total"]

    def _received(self, obj):
        if obj.pk is None:
            return Decimal("0")
        return GoodsReceiptLine.objects.filter(
            receipt__purchase_order_id=obj.purchase_order_id, product_id=obj.product_id,
        ).aggregate(t=Coalesce(Sum("quantity"), Decimal("0")))["t"]

    def get_received_quantity(self, obj):
        return str(self._received(obj))

    def get_remaining_quantity(self, obj):
        return str(max(obj.quantity_ordered - self._received(obj), Decimal("0")))


class PurchaseOrderSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True, default="")

    lines = PurchaseOrderLineSerializer(many=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            "id", "company", "supplier", "supplier_name", "branch", "status", "expected_date",
            "currency", "exchange_rate",
            "subtotal", "tax_amount", "total", "lines", "created_at",
        ]
        read_only_fields = ["company", "subtotal", "tax_amount", "total", "created_at"]

    def validate(self, attrs):
        _assert_same_company(self, attrs.get("supplier"), "supplier")
        _assert_same_company(self, attrs.get("branch"), "branch")
        for line in attrs.get("lines", []):
            _assert_same_company(self, line.get("product"), "product")
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
        raise serializers.ValidationError({label: _("Not your company's record.")})


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
    # When the goods actually arrived (offline receipts send it); the server
    # clock is only right for a live receipt.
    occurred_at = serializers.DateTimeField(required=False, allow_null=True)
    # Supplier currency and the day's rate. Line costs are in that currency;
    # the ledger is kept in the company currency.
    currency = serializers.CharField(required=False, allow_blank=True, max_length=8)
    exchange_rate = serializers.DecimalField(
        max_digits=14, decimal_places=6, required=False, min_value=Decimal("0.000001")
    )
    lines = ReceiptLineInputSerializer(many=True)

    def validate_occurred_at(self, value):
        from sales.serializers import validate_business_time

        return validate_business_time(value)

    def validate_lines(self, lines):
        if not lines:
            raise serializers.ValidationError(_("At least one line is required."))
        today = timezone.localdate()
        for line in lines:
            product = line["product"]
            # A batch-tracked product received without a lot would land as
            # untracked stock the expiry report can never see — the whole
            # point of tracking it is lost at the door.
            if product.track_batches and not (line.get("lot_number") or "").strip():
                raise serializers.ValidationError(
                    _("%(sku)s is batch-tracked: enter the lot number.")
                    % {"sku": product.sku}
                )
            expiry = line.get("expiry_date")
            if expiry is not None and expiry < today:
                raise serializers.ValidationError(
                    _("%(sku)s: the expiry date %(date)s is already past; "
                      "expired goods are returned, not received.")
                    % {"sku": product.sku, "date": expiry}
                )
        return lines

    def validate(self, attrs):
        supplier = attrs.get("supplier")
        po = attrs.get("purchase_order")
        if po is not None and supplier is not None and po.supplier_id != supplier.pk:
            raise serializers.ValidationError(
                {"purchase_order": _("Purchase order is not for this supplier.")}
            )
        if po is not None:
            if po.status == PurchaseOrder.CANCELLED:
                raise serializers.ValidationError(
                    {"purchase_order": _("A cancelled purchase order cannot be received.")}
                )
            # A draft was never sent or approved: goods cannot arrive against
            # it (receiving one brought stock in on an order nobody agreed).
            if po.status == PurchaseOrder.DRAFT:
                raise serializers.ValidationError(
                    {"purchase_order": _("Send or confirm the purchase order before receiving it.")}
                )
            ordered_products = set(po.lines.values_list("product_id", flat=True))
            unknown = [
                line["product"].pk for line in attrs.get("lines", [])
                if line["product"].pk not in ordered_products
            ]
            if unknown:
                raise serializers.ValidationError(
                    {"lines": _("Every received product must be on the purchase order.")}
                )
            requested = defaultdict(Decimal)
            products = {}
            for line in attrs.get("lines", []):
                requested[line["product"].pk] += line["quantity"]
                products[line["product"].pk] = line["product"]
            ordered = dict(
                po.lines.values("product_id").annotate(total=Sum("quantity_ordered"))
                .values_list("product_id", "total")
            )
            received = dict(
                GoodsReceiptLine.objects.filter(receipt__purchase_order=po)
                .values("product_id").annotate(total=Sum("quantity"))
                .values_list("product_id", "total")
            )
            for product_id, quantity in requested.items():
                remaining = ordered[product_id] - received.get(product_id, Decimal("0"))
                if quantity > remaining:
                    raise serializers.ValidationError(
                        {
                            "lines": _("Only %(remaining)s remains receivable for %(sku)s.")
                            % {"remaining": remaining, "sku": products[product_id].sku}
                        }
                    )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        user = request.user
        company_id = getattr(user, "company_id", None)
        if company_id is None:
            raise serializers.ValidationError(_("A company-scoped user is required."))

        supplier = validated_data["supplier"]
        warehouse = validated_data["warehouse"]
        po = validated_data.get("purchase_order")
        for obj, label in [
            (supplier, "supplier"),
            (warehouse, "warehouse"),
            (po, "purchase_order"),
        ]:
            _assert_same_company(self, obj, label)
        assert_user_branch(user, warehouse, "warehouse")
        for ln in validated_data["lines"]:
            _assert_same_company(self, ln["product"], "product")

        from django.utils import timezone

        from org.models import Company

        company = Company.objects.get(pk=company_id)
        currency = (validated_data.get("currency") or "").upper() or (
            (po.currency if po is not None and po.currency else company.currency)
        )
        rate = validated_data.get("exchange_rate")
        if rate is None:
            same = po is not None and po.currency == currency
            rate = po.exchange_rate if same else Decimal("1")
        if currency == company.currency and rate != 1:
            raise serializers.ValidationError(
                {"exchange_rate": _("A receipt in the company currency has a rate of 1.")}
            )
        if (
            currency != company.currency and rate == 1
            and validated_data.get("exchange_rate") is None
        ):
            raise serializers.ValidationError(
                {
                    "exchange_rate": _("Give the %(from)s->%(to)s rate.")
                    % {"from": currency, "to": company.currency}
                }
            )
        occurred_at = validated_data.get("occurred_at") or timezone.now()

        if po is not None:
            # Two receipts against one order at the same moment would each
            # pass the validate() check and over-receive; re-check under a
            # lock on the order.
            po = PurchaseOrder.objects.select_for_update().get(pk=po.pk)
            requested = defaultdict(Decimal)
            products = {}
            for ln in validated_data["lines"]:
                requested[ln["product"].pk] += ln["quantity"]
                products[ln["product"].pk] = ln["product"]
            ordered = dict(
                po.lines.values("product_id").annotate(total=Sum("quantity_ordered"))
                .values_list("product_id", "total")
            )
            received = dict(
                GoodsReceiptLine.objects.filter(receipt__purchase_order=po)
                .values("product_id").annotate(total=Sum("quantity"))
                .values_list("product_id", "total")
            )
            for product_id, quantity in requested.items():
                remaining = (
                    ordered.get(product_id, Decimal("0"))
                    - received.get(product_id, Decimal("0"))
                )
                if quantity > remaining:
                    raise serializers.ValidationError(
                        {
                            "lines": _("Only %(remaining)s remains receivable for %(sku)s.")
                            % {"remaining": remaining, "sku": products[product_id].sku}
                        }
                    )

        receipt = GoodsReceipt.objects.create(
            company_id=company_id, supplier=supplier, purchase_order=po,
            warehouse=warehouse, note=validated_data.get("note", ""),
            received_by=user if user.is_authenticated else None,
            received_at=occurred_at, currency=currency, exchange_rate=rate,
            client_uuid=validated_data.get("client_uuid"),
        )

        for ln in validated_data["lines"]:
            product = ln["product"]
            qty = ln["quantity"]
            cost = ln.get("unit_cost")
            if cost is None:
                # Catalogue cost is in company currency; express it in the
                # receipt's currency so the line and the ledger agree.
                cost = product.cost_price
                if rate:
                    cost = (product.cost_price / rate).quantize(Decimal("0.01"))
            # Ledger cost is always company currency.
            ledger_cost = (cost * rate).quantize(Decimal("0.01"))

            batch = None
            lot = ln.get("lot_number") or ""
            if product.track_batches and lot:
                batch, _created = StockBatch.objects.get_or_create(
                    company_id=company_id, product=product, lot_number=lot,
                    defaults={"expiry_date": ln.get("expiry_date")},
                )

            movement = StockMovement.objects.create(
                company_id=company_id, product=product, warehouse=warehouse,
                batch=batch, movement_type=StockMovement.PURCHASE_IN,
                quantity=qty, unit_cost=ledger_cost,
                reference_type="GoodsReceipt", reference_id=str(receipt.id),
                created_by=user if user.is_authenticated else None,
                created_at=occurred_at,
            )
            GoodsReceiptLine.objects.create(
                receipt=receipt, product=product, quantity=qty,
                unit_cost=cost, batch=batch, movement=movement,
            )
            # Roll the standard cost forward to the latest landed cost, so
            # "standard" valuation follows what the company actually pays
            # instead of a number someone typed once. Logged as a change.
            # ...unless a receipt of this product dated later already set it:
            # an offline receipt synced late must not wind the cost back.
            newer = GoodsReceiptLine.objects.filter(
                product=product, receipt__received_at__gt=occurred_at,
            ).exclude(receipt=receipt).exists() if occurred_at else False
            if ledger_cost and ledger_cost != product.cost_price and not newer:
                previous = product.cost_price
                Product.objects.filter(pk=product.pk).update(cost_price=ledger_cost)
                log_activity(
                    action="cost_update", request=request, entity_type="Product",
                    entity_id=product.pk,
                    metadata={"before": str(previous), "after": str(ledger_cost),
                              "receipt": receipt.pk},
                )
        self._advance_po_status(po)
        log_activity(
            action="create", request=request, entity_type="StockMovement",
            entity_id=receipt.lines.first().movement_id,
            metadata={"goods_receipt": receipt.pk,
                      "movements": list(receipt.lines.values_list("movement_id", flat=True))},
        )
        return receipt

    @staticmethod
    def _advance_po_status(po):
        """Derive the order's status from what has been received."""
        if po is None:
            return
        ordered = dict(
            po.lines.values("product_id").annotate(total=Sum("quantity_ordered"))
            .values_list("product_id", "total")
        )
        received = dict(
            GoodsReceiptLine.objects.filter(receipt__purchase_order=po)
            .values("product_id").annotate(total=Sum("quantity"))
            .values_list("product_id", "total")
        )
        complete = all(received.get(pid, Decimal("0")) >= qty for pid, qty in ordered.items())
        new_status = PurchaseOrder.RECEIVED if complete else PurchaseOrder.PARTIALLY_RECEIVED
        if po.status != new_status:
            PurchaseOrder.objects.filter(pk=po.pk).update(status=new_status)

    def to_representation(self, instance):
        return GoodsReceiptReadSerializer(instance, context=self.context).data


class GoodsReceiptLineReadSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    returnable_quantity = serializers.SerializerMethodField()

    class Meta:
        model = GoodsReceiptLine
        fields = [
            "id", "product", "product_name", "product_sku", "quantity",
            "returnable_quantity", "unit_cost", "batch", "movement",
        ]

    def get_returnable_quantity(self, obj):
        returned = obj.return_lines.aggregate(total=Sum("quantity"))["total"] or Decimal("0")
        return str(obj.quantity - returned)


class GoodsReceiptReadSerializer(serializers.ModelSerializer):
    lines = GoodsReceiptLineReadSerializer(many=True, read_only=True)

    class Meta:
        model = GoodsReceipt
        fields = [
            "id", "company", "supplier", "purchase_order", "warehouse",
            "note", "received_at", "recorded_at", "currency", "exchange_rate",
            "client_uuid", "lines",
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
            "supplier_invoice_number", "currency", "exchange_rate",
            "subtotal", "tax_amount", "total",
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
        for field in ("supplier", "purchase_order", "goods_receipt"):
            _assert_same_company(self, attrs.get(field), field)
        supplier = attrs.get("supplier", getattr(self.instance, "supplier", None))
        po = attrs.get("purchase_order", getattr(self.instance, "purchase_order", None))
        receipt = attrs.get(
            "goods_receipt", getattr(self.instance, "goods_receipt", None)
        )
        if po is not None and supplier is not None and po.supplier_id != supplier.pk:
            raise serializers.ValidationError(
                {"purchase_order": _("Purchase order is not for this supplier.")}
            )
        # The supplier's own invoice number is recorded once: entering the
        # same paper invoice twice is how a supplier gets paid twice.
        number = (attrs.get("supplier_invoice_number") or "").strip()
        if number and supplier is not None:
            same = Bill.objects.filter(
                company_id=supplier.company_id, supplier=supplier, is_void=False,
                supplier_invoice_number__iexact=number,
            )
            if self.instance is not None:
                same = same.exclude(pk=self.instance.pk)
            if same.exists():
                raise serializers.ValidationError({"supplier_invoice_number": _(
                    "Invoice %(number)s from this supplier is already recorded."
                ) % {"number": number}})
        if receipt is not None and supplier is not None:
            if receipt.supplier_id != supplier.pk:
                raise serializers.ValidationError(
                    {"goods_receipt": _("Goods receipt is not for this supplier.")}
                )
            if po is not None and receipt.purchase_order_id != po.pk:
                raise serializers.ValidationError(
                    {"goods_receipt": _("Goods receipt is not for this purchase order.")}
                )
            # One receipt, one bill. A second bill for the same goods is how
            # a supplier gets paid twice.
            already = Bill.objects.filter(goods_receipt=receipt, is_void=False)
            if self.instance is not None:
                already = already.exclude(pk=self.instance.pk)
            if already.exists():
                raise serializers.ValidationError(
                    {"goods_receipt": _("This receipt already has a bill; void that one first.")}
                )
            # Three-way match: the bill should cover what was received.
            received_value = sum(
                (line.quantity * line.unit_cost for line in receipt.lines.all()), Decimal("0")
            ).quantize(Decimal("0.01"))
            claimed = attrs.get("subtotal", getattr(self.instance, "subtotal", None))
            request = self.context.get("request")
            tolerance = max(received_value * Decimal("0.02"), Decimal("1"))
            if (
                claimed is not None
                and received_value
                and abs(claimed - received_value) > tolerance
                and not can_approve_high_value(getattr(request, "user", None))
            ):
                raise serializers.ValidationError(
                    {
                        "subtotal": (
                            _("The bill (%(claimed)s) does not match the receipt "
                              "(%(received)s). A manager must approve the difference.")
                            % {"claimed": claimed, "received": received_value}
                        )
                    }
                )
        subtotal = attrs.get("subtotal", getattr(self.instance, "subtotal", None))
        tax = attrs.get("tax_amount", getattr(self.instance, "tax_amount", None))
        total = attrs.get("total", getattr(self.instance, "total", None))
        if total is None or total < 0:
            raise serializers.ValidationError(_("Total must be non-negative."))
        if subtotal is not None and tax is not None and _q2(subtotal + tax) != total:
            raise serializers.ValidationError(
                {"total": _("Total must equal subtotal plus tax amount.")}
            )
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data.setdefault("created_by", request.user)
        return super().create(validated_data)


# ---------- Supplier payment (Rule #3 spirit) ----------

class SupplierPaymentSerializer(serializers.ModelSerializer):
    # Display fields for the payments ledger and its verification worklist.
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    bill_number = serializers.CharField(
        source="bill.supplier_invoice_number", read_only=True, default=None
    )
    from_bank_account_name = serializers.CharField(
        source="from_bank_account.bank_name", read_only=True, default=None
    )
    recorded_by_name = serializers.CharField(
        source="recorded_by.full_name", read_only=True, default=None
    )
    verified_by_name = serializers.CharField(
        source="verified_by.full_name", read_only=True, default=None
    )

    class Meta:
        model = SupplierPayment
        fields = [
            "id", "company", "supplier", "supplier_name", "bill", "bill_number",
            "method", "from_bank_account", "from_bank_account_name",
            "reference_last4", "amount", "currency", "exchange_rate",
            "recorded_by", "recorded_by_name", "recorded_at",
            "verified_at", "verified_by", "verified_by_name", "client_uuid",
        ]
        read_only_fields = [
            "company", "recorded_by", "recorded_at", "verified_at", "verified_by",
        ]
        # A payment settles a bill: the column is NOT NULL, and a payment sent
        # without one crashed the server (and failed every sync retry). An
        # advance to a supplier needs its own document; until then it is
        # refused with a field error instead of a 500.
        extra_kwargs = {"bill": {"required": True, "allow_null": False}}

    def validate(self, attrs):
        amount = attrs.get("amount")
        if amount is None or amount <= 0:
            raise serializers.ValidationError(_("Amount must be positive."))

        method = attrs.get("method")
        bank = attrs.get("from_bank_account")
        ref = attrs.get("reference_last4", "")

        if method == SupplierPayment.BANK_TRANSFER:
            if bank is None:
                raise serializers.ValidationError(
                    _("Bank transfer requires the paying-from company bank account.")
                )
            if not ref or not ref.isdigit() or len(ref) > 4:
                raise serializers.ValidationError(
                    _("reference_last4 must be up to 4 digits.")
                )
        elif method == SupplierPayment.CASH:
            if bank or ref:
                raise serializers.ValidationError(
                    _("Cash payments must not carry bank/reference details.")
                )

        _assert_same_company(self, attrs.get("supplier"), "supplier")
        _assert_same_company(self, attrs.get("bill"), "bill")
        _assert_same_company(self, attrs.get("from_bank_account"), "from_bank_account")
        bill = attrs.get("bill")
        supplier = attrs.get("supplier")
        if bill is not None and supplier is not None and bill.supplier_id != supplier.id:
            raise serializers.ValidationError({"bill": _("Bill is not for this supplier.")})
        if bill is not None and bill.is_void:
            raise serializers.ValidationError({"bill": _("That bill is void.")})
        if bill is not None and amount > bill.amount_due():
            raise serializers.ValidationError(
                {
                    "amount": _("Amount exceeds the balance due on this bill (%(due)s).")
                    % {"due": bill.amount_due()}
                }
            )
        if bill is not None and not attrs.get("currency"):
            attrs["currency"] = bill.currency
            attrs.setdefault("exchange_rate", bill.exchange_rate)
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data.setdefault("recorded_by", request.user)
        bill = validated_data.get("bill")
        if bill is None:
            # An advance to the supplier (common when importing): recorded
            # against the supplier and applied to a bill later.
            return super().create(validated_data)
        with transaction.atomic():
            locked = Bill.objects.select_for_update().get(pk=bill.pk)
            due = locked.amount_due()
            if validated_data["amount"] > due:
                raise serializers.ValidationError(
                    {
                        "amount": _("Amount exceeds the balance due on this bill (%(due)s).")
                        % {"due": due}
                    }
                )
            validated_data["bill"] = locked
            return super().create(validated_data)
