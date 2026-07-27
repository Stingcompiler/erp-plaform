from decimal import Decimal

from django.conf import settings
from django.db import models


class SalesReturn(models.Model):
    """
    A customer returning goods against an invoice. APPEND-ONLY (Rule #9).

    Rule #5 is the whole point of this model: creating a return does NOT add
    anything back to sellable stock. Each line starts in `quarantine`, and only
    a deliberate disposition (restock/scrap) posts a `sales_return_in` movement
    into a chosen sellable warehouse. Until then, sellable on-hand is unchanged.
    """

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="sales_returns"
    )
    invoice = models.ForeignKey(
        "sales.Invoice", on_delete=models.PROTECT, related_name="sales_returns"
    )
    customer = models.ForeignKey(
        "sales.Customer", on_delete=models.PROTECT, null=True, blank=True,
        related_name="sales_returns",
    )
    reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sales_returns",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"SalesReturn #{self.id} (INV-{self.invoice.number:06d})"

    @property
    def is_fully_dispositioned(self):
        return not self.lines.filter(
            disposition=SalesReturnLine.QUARANTINE
        ).exists()


class SalesReturnLine(models.Model):
    QUARANTINE = "quarantine"
    RESTOCKED = "restocked"
    SCRAPPED = "scrapped"
    DISPOSITION_CHOICES = [
        (QUARANTINE, "Quarantine (pending)"),
        (RESTOCKED, "Restocked to sellable"),
        (SCRAPPED, "Scrapped / written off"),
    ]

    sales_return = models.ForeignKey(
        SalesReturn, on_delete=models.CASCADE, related_name="lines"
    )
    invoice_line = models.ForeignKey(
        "sales.InvoiceLine", on_delete=models.PROTECT, null=True, blank=True,
        related_name="return_lines",
    )
    product = models.ForeignKey(
        "inventory.Product", on_delete=models.PROTECT, related_name="return_lines"
    )
    quantity = models.DecimalField(max_digits=16, decimal_places=3)
    # Rule #5: starts in quarantine; never sellable until deliberately restocked.
    disposition = models.CharField(
        max_length=16, choices=DISPOSITION_CHOICES, default=QUARANTINE
    )
    restock_warehouse = models.ForeignKey(
        "inventory.Warehouse", on_delete=models.PROTECT, null=True, blank=True,
        related_name="restocked_return_lines",
    )
    # The sales_return_in movement created on restock (null while quarantined).
    restock_movement = models.OneToOneField(
        "inventory.StockMovement", on_delete=models.PROTECT, null=True, blank=True,
        related_name="sales_return_line",
    )

    def __str__(self):
        return f"{self.product.sku} x{self.quantity} [{self.disposition}]"


class PurchaseReturn(models.Model):
    """
    Returning goods to a supplier. Append-only. Unlike sales returns, the goods
    physically LEAVE us, so each line immediately posts a `purchase_return_out`
    movement (−qty) from the source warehouse — there is nothing to quarantine.
    """

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="purchase_returns"
    )
    supplier = models.ForeignKey(
        "purchasing.Supplier", on_delete=models.PROTECT, related_name="purchase_returns"
    )
    warehouse = models.ForeignKey(
        "inventory.Warehouse", on_delete=models.PROTECT, related_name="purchase_returns"
    )
    goods_receipt = models.ForeignKey(
        "purchasing.GoodsReceipt", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="purchase_returns",
    )
    reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="purchase_returns",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"PurchaseReturn #{self.id} ({self.supplier.name})"


class PurchaseReturnLine(models.Model):
    purchase_return = models.ForeignKey(
        PurchaseReturn, on_delete=models.CASCADE, related_name="lines"
    )
    product = models.ForeignKey(
        "inventory.Product", on_delete=models.PROTECT, related_name="purchase_return_lines"
    )
    quantity = models.DecimalField(max_digits=16, decimal_places=3)
    batch = models.ForeignKey(
        "inventory.StockBatch", on_delete=models.PROTECT, null=True, blank=True,
        related_name="purchase_return_lines",
    )
    movement = models.OneToOneField(
        "inventory.StockMovement", on_delete=models.PROTECT,
        related_name="purchase_return_line",
    )


class CreditNote(models.Model):
    """
    Reduces what a customer owes us (against a sales return or standalone).
    Append-only; a mistake is corrected by voiding and issuing another.
    Reflected in AR via sales.Invoice.amount_due (extended in M5).
    """

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="credit_notes"
    )
    customer = models.ForeignKey(
        "sales.Customer", on_delete=models.PROTECT, related_name="credit_notes"
    )
    invoice = models.ForeignKey(
        "sales.Invoice", on_delete=models.PROTECT, null=True, blank=True,
        related_name="credit_notes",
    )
    sales_return = models.ForeignKey(
        SalesReturn, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="credit_notes",
    )
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    reason = models.CharField(max_length=255, blank=True)
    is_void = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="credit_notes",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"CreditNote #{self.id} {self.amount}"


class DebitNote(models.Model):
    """
    Reduces what we owe a supplier (against a purchase return or standalone).
    Append-only. Reflected in AP via purchasing.Supplier.ap_balance (extended
    in M5).
    """

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="debit_notes"
    )
    supplier = models.ForeignKey(
        "purchasing.Supplier", on_delete=models.PROTECT, related_name="debit_notes"
    )
    bill = models.ForeignKey(
        "purchasing.Bill", on_delete=models.PROTECT, null=True, blank=True,
        related_name="debit_notes",
    )
    purchase_return = models.ForeignKey(
        PurchaseReturn, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="debit_notes",
    )
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    reason = models.CharField(max_length=255, blank=True)
    is_void = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="debit_notes",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"DebitNote #{self.id} {self.amount}"


# Helper used by the AR/AP extensions in sales/purchasing (imported lazily
# there to avoid an import cycle).
def applied_credit_total(invoice):
    from django.db.models import Sum
    from django.db.models.functions import Coalesce
    return invoice.credit_notes.filter(is_void=False).aggregate(
        t=Coalesce(Sum("amount"), Decimal("0"))
    )["t"]


def applied_debit_total(supplier):
    from django.db.models import Sum
    from django.db.models.functions import Coalesce
    return supplier.debit_notes.filter(is_void=False).aggregate(
        t=Coalesce(Sum("amount"), Decimal("0"))
    )["t"]
