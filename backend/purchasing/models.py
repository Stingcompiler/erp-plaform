from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone


class Supplier(models.Model):
    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="suppliers"
    )
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=64, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def ap_balance(self):
        """Payable in the company currency: each bill's remaining balance at
        the bill's recorded rate, less debit notes not tied to a bill at
        theirs. A supplier invoicing in dollars and one in pounds must not
        be summed as if they were the same unit. Derived, never stored."""
        total = Decimal("0")
        for bill in self.bills.all():
            total += bill.amount_due() * (bill.exchange_rate or Decimal("1"))
        # Debit notes reduce AP; those linked to a bill are already netted
        # inside Bill.amount_due(), so only free-standing ones count here.
        for note in self.debit_notes.filter(is_void=False, bill__isnull=True):
            total -= note.amount * (note.exchange_rate or Decimal("1"))
        return total.quantize(Decimal("0.01"))


class PurchaseOrder(models.Model):
    DRAFT = "draft"
    SENT = "sent"
    CONFIRMED = "confirmed"
    PARTIALLY_RECEIVED = "partially_received"
    RECEIVED = "received"
    CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (DRAFT, "Draft"), (SENT, "Sent"), (CONFIRMED, "Confirmed"),
        (PARTIALLY_RECEIVED, "Partially Received"), (RECEIVED, "Received"),
        (CANCELLED, "Cancelled"),
    ]

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="purchase_orders"
    )
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name="purchase_orders"
    )
    branch = models.ForeignKey(
        "org.Branch", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="purchase_orders",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=DRAFT)
    expected_date = models.DateField(null=True, blank=True)
    # Sudanese importers are billed in USD/AED at a rate that moves weekly.
    # The document keeps its own currency and the rate on the day, so AP and
    # inventory cost can be reconstructed; amounts stay in document currency
    # and `exchange_rate` converts to the company currency.
    currency = models.CharField(max_length=8, blank=True)
    exchange_rate = models.DecimalField(max_digits=14, decimal_places=6, default=1)
    subtotal = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="purchase_orders",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Drives the offline delta pull: a confirmed or received order must reach
    # the other devices even though nothing else on the row changed.
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"PO #{self.id} ({self.supplier.name})"


class PurchaseOrderLine(models.Model):
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name="lines"
    )
    product = models.ForeignKey(
        "inventory.Product", on_delete=models.PROTECT, related_name="po_lines"
    )
    description = models.CharField(max_length=255, blank=True)
    quantity_ordered = models.DecimalField(max_digits=16, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2)
    line_total = models.DecimalField(max_digits=16, decimal_places=2)


class GoodsReceipt(models.Model):
    """
    Receiving stock against a supplier (optionally a PO). APPEND-ONLY (Rule #9)
    and idempotent (Rule #2). Each line posts one `purchase_in` StockMovement
    (see M2 ledger), so on-hand rises by exactly the received quantity.
    """

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="goods_receipts"
    )
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name="goods_receipts"
    )
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="goods_receipts",
    )
    warehouse = models.ForeignKey(
        "inventory.Warehouse", on_delete=models.PROTECT, related_name="goods_receipts"
    )
    note = models.CharField(max_length=255, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="goods_receipts",
    )
    # Business time: when the goods were actually taken in. An offline
    # receipt synced hours later keeps its real time, so the stock it brought
    # in is ordered BEFORE the sales it enabled; otherwise FIFO and average
    # costing treat those sales as oversells.
    received_at = models.DateTimeField(default=timezone.now, db_index=True)
    # Server clock, audit only.
    recorded_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    # Supplier's currency and the day's rate; line costs are in this currency
    # and the stock movement carries the company-currency equivalent.
    currency = models.CharField(max_length=8, blank=True)
    exchange_rate = models.DecimalField(max_digits=14, decimal_places=6, default=1)
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return f"GRN #{self.id} ({self.supplier.name})"


class GoodsReceiptLine(models.Model):
    receipt = models.ForeignKey(
        GoodsReceipt, on_delete=models.CASCADE, related_name="lines"
    )
    product = models.ForeignKey(
        "inventory.Product", on_delete=models.PROTECT, related_name="receipt_lines"
    )
    quantity = models.DecimalField(max_digits=16, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2)
    batch = models.ForeignKey(
        "inventory.StockBatch", on_delete=models.PROTECT, null=True, blank=True,
        related_name="receipt_lines",
    )
    # The stock movement this line generated (one purchase_in per line).
    movement = models.OneToOneField(
        "inventory.StockMovement", on_delete=models.PROTECT,
        related_name="receipt_line",
    )


class Bill(models.Model):
    """
    A supplier's invoice to us (payable). Append-only. Carries the supplier's
    external invoice number as a reference; internal identity is the PK. AP is
    tracked here at the document level (no general ledger).
    """

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="bills"
    )
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name="bills"
    )
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="bills",
    )
    goods_receipt = models.ForeignKey(
        GoodsReceipt, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="bills",
    )
    supplier_invoice_number = models.CharField(max_length=64, blank=True)
    currency = models.CharField(max_length=8, blank=True)
    exchange_rate = models.DecimalField(max_digits=14, decimal_places=6, default=1)
    subtotal = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=16, decimal_places=2)
    is_void = models.BooleanField(default=False)
    # What the company already owed this supplier when it started using
    # Vezano — a bill with no receipt behind it, excluded from purchase totals.
    is_opening_balance = models.BooleanField(default=False)
    # Supplier credit terms — mirrors Invoice on the AR side so AP aging
    # measures lateness rather than age since the bill was entered.
    payment_terms_days = models.PositiveIntegerField(default=0)
    due_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="bills",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.due_date is None and self.created_at:
            self.due_date = self.created_at.date() + timedelta(
                days=self.payment_terms_days or 0
            )
            super().save(update_fields=["due_date"])

    def __str__(self):
        return f"Bill #{self.id} ({self.supplier.name})"

    @property
    def days_overdue(self):
        """Days past due; 0 when settled, void or not yet due."""
        if self.is_void or not self.due_date or self.amount_due() <= 0:
            return 0
        return max(0, (timezone.localdate() - self.due_date).days)

    @property
    def is_overdue(self):
        return self.days_overdue > 0

    def amount_paid(self):
        return self.payments.aggregate(t=Coalesce(Sum("amount"), Decimal("0")))["t"]

    def amount_due(self):
        """total − payments − debit notes raised against this bill. Every AP
        figure (supplier balance, aging, cash-flow forecast, CFO KPIs) reads
        this one method, so a purchase return lowers payables everywhere at
        once instead of only on the supplier card."""
        if self.is_void:
            return Decimal("0")
        from returns.models import applied_debit_total_for_bill
        return self.total - self.amount_paid() - applied_debit_total_for_bill(self)

    @property
    def status(self):
        if self.is_void:
            return "void"
        if self.amount_due() <= 0:
            return "paid"
        if self.amount_paid() > 0:
            return "partially_paid"
        return "open"


class SupplierPayment(models.Model):
    """
    A payment WE make to a supplier. Manual only (Rule #3 spirit) — no gateway,
    no external calls. For bank transfers we record which of the company's own
    accounts it was paid from plus the last-4 transaction reference.
    Append-only; `verified_*` support later reconciliation and never block.
    """

    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"
    METHOD_CHOICES = [(CASH, "Cash"), (BANK_TRANSFER, "Bank Transfer")]

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="supplier_payments"
    )
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name="payments"
    )
    bill = models.ForeignKey(
        Bill, on_delete=models.PROTECT, related_name="payments"
    )
    method = models.CharField(max_length=16, choices=METHOD_CHOICES)
    from_bank_account = models.ForeignKey(
        "sales.CompanyBankAccount", on_delete=models.PROTECT, null=True, blank=True,
        related_name="supplier_payments",
    )
    reference_last4 = models.CharField(max_length=4, blank=True)
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    currency = models.CharField(max_length=8, blank=True)
    exchange_rate = models.DecimalField(max_digits=14, decimal_places=6, default=1)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="supplier_payments_recorded",
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="supplier_payments_verified",
    )
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)

    class Meta:
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"{self.method} {self.amount} -> {self.supplier.name}"
