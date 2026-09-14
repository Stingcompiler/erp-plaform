from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone


class Category(models.Model):
    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="categories"
    )
    name = models.CharField(max_length=255)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"], name="uniq_category_name_per_company"
            )
        ]

    def __str__(self):
        return self.name


class Brand(models.Model):
    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="brands"
    )
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"], name="uniq_brand_name_per_company"
            )
        ]

    def __str__(self):
        return self.name


class Unit(models.Model):
    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="units"
    )
    name = models.CharField(max_length=64)  # e.g. "Kilogram", "Piece"
    symbol = models.CharField(max_length=16, blank=True)  # e.g. "kg", "pcs"
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"], name="uniq_unit_name_per_company"
            )
        ]

    def __str__(self):
        return self.symbol or self.name


class Warehouse(models.Model):
    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="warehouses"
    )
    branch = models.ForeignKey(
        "org.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="warehouses",
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=32, blank=True)
    is_active = models.BooleanField(default=True)
    # Lets the offline sync pull warehouses as a delta like every other
    # mirrored record; a till cannot ring a sale without one.
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"], name="uniq_warehouse_name_per_company"
            )
        ]

    def __str__(self):
        return self.name


class Product(models.Model):
    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="products"
    )
    sku = models.CharField(max_length=64)
    name = models.CharField(max_length=255)
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="products"
    )
    brand = models.ForeignKey(
        Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name="products"
    )
    unit = models.ForeignKey(
        Unit, on_delete=models.SET_NULL, null=True, blank=True, related_name="products"
    )
    barcode = models.CharField(max_length=128, blank=True)
    qr_code = models.CharField(max_length=255, blank=True)
    cost_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    sale_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # Low-stock threshold; on-hand <= this flags the product (see low_stock).
    reorder_level = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    track_batches = models.BooleanField(default=False)
    # False for things that are sold but not stocked: a bag, a delivery charge,
    # or the catch-all "miscellaneous" line a shop rings up for an item that
    # isn't in the catalogue. Selling one posts no stock movement, so its
    # on-hand stays 0 instead of drifting ever more negative and dragging the
    # low-stock list down with it. Stock is still derived from movements
    # everywhere — these products simply never generate any.
    is_stock_tracked = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "sku"], name="uniq_product_sku_per_company"
            ),
            # A barcode must resolve to exactly one product, otherwise a scan
            # would pick the wrong item and hit the wrong stock. Conditional so
            # the many products with no barcode aren't forced into uniqueness.
            models.UniqueConstraint(
                fields=["company", "barcode"],
                condition=~models.Q(barcode=""),
                name="uniq_product_barcode_per_company",
            ),
        ]

    def __str__(self):
        return f"{self.sku} — {self.name}"

    def on_hand(self, warehouse=None, batch=None):
        """
        Current quantity, ALWAYS derived by summing the movement ledger — there
        is deliberately no stored quantity field to drift out of sync
        (M2 acceptance criterion).
        """
        qs = self.stock_movements.all()
        if warehouse is not None:
            qs = qs.filter(warehouse=warehouse)
        if batch is not None:
            qs = qs.filter(batch=batch)
        return qs.aggregate(total=Coalesce(Sum("quantity"), Decimal("0")))["total"]


class StockBatch(models.Model):
    """
    Identity of a received lot (lot number + expiry). Deliberately holds NO
    quantity — a batch's remaining quantity is summed from movements that
    reference it, same as everything else.
    """

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="stock_batches"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="batches"
    )
    lot_number = models.CharField(max_length=128)
    expiry_date = models.DateField(null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["expiry_date", "lot_number"]
        verbose_name_plural = "stock batches"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "product", "lot_number"],
                name="uniq_batch_lot_per_product",
            )
        ]

    def __str__(self):
        return f"{self.product.sku} / lot {self.lot_number}"


class StockMovement(models.Model):
    """
    The single source of truth for stock. APPEND-ONLY (PROJECT_RULES Rule #9):
    rows are never edited or deleted — a correction is a new offsetting
    movement. `quantity` is SIGNED (positive = increases on-hand at that
    warehouse, negative = decreases), so on-hand for any slice is a plain
    SUM(quantity). Sign is validated against `movement_type` on write.
    """

    PURCHASE_IN = "purchase_in"
    SALE_OUT = "sale_out"
    ADJUSTMENT = "adjustment"
    TRANSFER = "transfer"
    SALES_RETURN_IN = "sales_return_in"
    PURCHASE_RETURN_OUT = "purchase_return_out"

    MOVEMENT_TYPES = [
        (PURCHASE_IN, "Purchase In"),
        (SALE_OUT, "Sale Out"),
        (ADJUSTMENT, "Adjustment"),
        (TRANSFER, "Transfer"),
        (SALES_RETURN_IN, "Sales Return In"),
        (PURCHASE_RETURN_OUT, "Purchase Return Out"),
    ]

    # Required sign per type. None = either sign allowed (adjustment/transfer).
    POSITIVE_TYPES = {PURCHASE_IN, SALES_RETURN_IN}
    NEGATIVE_TYPES = {SALE_OUT, PURCHASE_RETURN_OUT}
    EITHER_SIGN_TYPES = {ADJUSTMENT, TRANSFER}

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="stock_movements"
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="stock_movements"
    )
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, related_name="stock_movements"
    )
    batch = models.ForeignKey(
        StockBatch,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    movement_type = models.CharField(max_length=32, choices=MOVEMENT_TYPES)
    quantity = models.DecimalField(max_digits=16, decimal_places=3)
    unit_cost = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )

    # Loose link back to the source document (Invoice, Receiving, Adjustment,
    # Transfer, Return...) without a hard FK per type.
    reference_type = models.CharField(max_length=64, blank=True)
    reference_id = models.CharField(max_length=64, blank=True)
    note = models.CharField(max_length=255, blank=True)

    # Idempotency for offline replay (PROJECT_RULES Rule #2): a client-generated
    # UUID makes re-submitting the same queued movement a no-op instead of
    # double-applying it. Globally unique when present.
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    # Business time of the movement (the ledger is walked in this order for
    # FIFO/average costing); an offline sale stamps it from the till. The
    # server's own clock is kept separately for audit.
    created_at = models.DateTimeField(default=timezone.now)
    received_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["company", "product", "warehouse"],
                name="stockmove_co_prod_wh_idx",
            ),
            models.Index(fields=["movement_type"], name="stockmove_type_idx"),
        ]

    def __str__(self):
        return f"{self.movement_type} {self.quantity} of {self.product.sku}"


class StockAdjustment(models.Model):
    """
    A manual correction to on-hand quantity. Generates exactly one typed
    `adjustment` StockMovement (signed delta). Append-only — an adjustment is
    never edited; you post another adjustment to correct one.
    """

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="stock_adjustments"
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="adjustments"
    )
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, related_name="adjustments"
    )
    batch = models.ForeignKey(
        StockBatch, on_delete=models.PROTECT, null=True, blank=True,
        related_name="adjustments",
    )
    quantity = models.DecimalField(max_digits=16, decimal_places=3)  # signed delta
    reason = models.CharField(max_length=255, blank=True)
    movement = models.OneToOneField(
        StockMovement, on_delete=models.PROTECT, related_name="adjustment"
    )
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="stock_adjustments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Adjustment {self.quantity} of {self.product.sku}"


class StockTransfer(models.Model):
    """
    Moves quantity from one warehouse to another within the same company.
    Generates TWO `transfer` StockMovements (negative at source, positive at
    destination), so company-wide totals are unchanged while per-warehouse
    totals move. Append-only.
    """

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="stock_transfers"
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="transfers"
    )
    batch = models.ForeignKey(
        StockBatch, on_delete=models.PROTECT, null=True, blank=True,
        related_name="transfers",
    )
    source_warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, related_name="transfers_out"
    )
    dest_warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, related_name="transfers_in"
    )
    quantity = models.DecimalField(max_digits=16, decimal_places=3)  # positive
    note = models.CharField(max_length=255, blank=True)
    source_movement = models.OneToOneField(
        StockMovement, on_delete=models.PROTECT, related_name="transfer_source"
    )
    dest_movement = models.OneToOneField(
        StockMovement, on_delete=models.PROTECT, related_name="transfer_dest"
    )
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="stock_transfers",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"Transfer {self.quantity} of {self.product.sku} "
            f"{self.source_warehouse_id}->{self.dest_warehouse_id}"
        )


class BarcodeSequence(models.Model):
    """
    Per-company counter for internally generated EAN-13 barcodes (see
    inventory/barcodes.py). Allocated under a row lock inside the caller's
    transaction, mirroring InvoiceSequence, so two concurrent generations can
    never produce the same code.
    """

    company = models.OneToOneField(
        "org.Company", on_delete=models.CASCADE, related_name="barcode_sequence"
    )
    last_number = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"BarcodeSequence<{self.company_id}: {self.last_number}>"


class StockCount(models.Model):
    """
    A periodic physical count of one warehouse. The counter records what is
    on the shelf; the system compares it with the ledger and a manager
    approves the differences, which are then posted as ordinary
    `adjustment` movements — the count itself never edits the ledger.

    Two people, two steps: the person who counts is not the person who makes
    the books agree with the count. That separation is what makes a stock
    count evidence rather than an edit.
    """

    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (SUBMITTED, "Submitted"),
        (APPROVED, "Approved"),
        (CANCELLED, "Cancelled"),
    ]

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="stock_counts"
    )
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, related_name="stock_counts"
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=DRAFT)
    note = models.CharField(max_length=255, blank=True)
    # Ledger balances are frozen into the lines at submission so approval
    # compares against what the counter saw, not against later sales.
    counted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="stock_counts_counted",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="stock_counts_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"StockCount #{self.pk} {self.warehouse.name} [{self.status}]"


class StockCountLine(models.Model):
    count = models.ForeignKey(StockCount, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="count_lines")
    batch = models.ForeignKey(
        StockBatch, on_delete=models.PROTECT, null=True, blank=True, related_name="count_lines"
    )
    counted_quantity = models.DecimalField(max_digits=16, decimal_places=3)
    # Snapshot of the ledger at submission; None until then.
    expected_quantity = models.DecimalField(
        max_digits=16, decimal_places=3, null=True, blank=True
    )
    # The adjustment posted on approval (only for lines with a variance).
    adjustment = models.OneToOneField(
        StockAdjustment, on_delete=models.PROTECT, null=True, blank=True,
        related_name="count_line",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["count", "product", "batch"], name="uniq_count_line_per_product_batch"
            )
        ]

    @property
    def variance(self):
        if self.expected_quantity is None:
            return None
        return self.counted_quantity - self.expected_quantity
