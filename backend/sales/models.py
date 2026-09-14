from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone


class Customer(models.Model):
    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="customers"
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

    def ar_balance(self):
        """
        Outstanding receivable = sum of unpaid amounts across this customer's
        invoices. Tracked at the document level only (no general ledger),
        derived — never stored — so it can't drift.
        """
        total = Decimal("0")
        for inv in self.invoices.all():
            total += inv.amount_due()
        return total


class CompanyBankAccount(models.Model):
    """The company's own receiving account, referenced by bank-transfer payments."""

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="bank_accounts"
    )
    bank_name = models.CharField(max_length=255)
    account_name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=64, blank=True)
    # Balance the account held when it was added to the system. Everything after
    # that is derived from recorded movements, so the balance can never drift.
    opening_balance = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal("0")
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["bank_name"]

    def __str__(self):
        return f"{self.bank_name} — {self.account_name}"

    def received_total(self):
        """Customer bank transfers paid into this account."""
        return self.payments.aggregate(
            t=Coalesce(Sum("amount"), Decimal("0"))
        )["t"]

    def paid_total(self):
        """Supplier payments made out of this account."""
        return self.supplier_payments.aggregate(
            t=Coalesce(Sum("amount"), Decimal("0"))
        )["t"]

    def balance(self):
        """
        Current balance, DERIVED — opening + money in − money out.

        This tracks only what the system recorded; it is not a bank feed and
        makes no external calls (PROJECT_RULES Rule #3). A difference against
        the real statement is a reconciliation matter, not a bug here.
        """
        return self.opening_balance + self.received_total() - self.paid_total()


class InvoiceSequence(models.Model):
    """
    Per-company invoice counter. Numbers are allocated under a row lock inside
    the same transaction as the invoice insert, so a rolled-back sale never
    consumes a number — this is what keeps numbering sequential AND gapless
    per company (M3 acceptance).
    """

    company = models.OneToOneField(
        "org.Company", on_delete=models.CASCADE, related_name="invoice_sequence"
    )
    last_number = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"InvoiceSequence<{self.company_id}: {self.last_number}>"


class Quotation(models.Model):
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    CONVERTED = "converted"
    STATUS_CHOICES = [
        (DRAFT, "Draft"), (SENT, "Sent"), (ACCEPTED, "Accepted"),
        (EXPIRED, "Expired"), (CONVERTED, "Converted"),
    ]

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="quotations"
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="quotations"
    )
    branch = models.ForeignKey(
        "org.Branch", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="quotations",
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=DRAFT)
    valid_until = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)
    subtotal = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="quotations",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Quotation #{self.id} ({self.customer.name})"


class QuotationLine(models.Model):
    quotation = models.ForeignKey(
        Quotation, on_delete=models.CASCADE, related_name="lines"
    )
    product = models.ForeignKey(
        "inventory.Product", on_delete=models.PROTECT, related_name="quotation_lines"
    )
    description = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(max_digits=16, decimal_places=3)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    line_total = models.DecimalField(max_digits=16, decimal_places=2)


class SalesOrder(models.Model):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (DRAFT, "Draft"), (CONFIRMED, "Confirmed"),
        (FULFILLED, "Fulfilled"), (CANCELLED, "Cancelled"),
    ]

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="sales_orders"
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="sales_orders"
    )
    branch = models.ForeignKey(
        "org.Branch", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sales_orders",
    )
    source_quotation = models.ForeignKey(
        Quotation, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sales_orders",
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=DRAFT)
    subtotal = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sales_orders",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"SalesOrder #{self.id} ({self.customer.name})"


class SalesOrderLine(models.Model):
    sales_order = models.ForeignKey(
        SalesOrder, on_delete=models.CASCADE, related_name="lines"
    )
    product = models.ForeignKey(
        "inventory.Product", on_delete=models.PROTECT, related_name="sales_order_lines"
    )
    description = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(max_digits=16, decimal_places=3)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    line_total = models.DecimalField(max_digits=16, decimal_places=2)


class Invoice(models.Model):
    """
    Append-only (Rule #9). Status is DERIVED from payments, not a mutable field
    that gets edited — a void/correction is a Credit Note (M5), never an
    in-place edit. `number` is gapless per company (see InvoiceSequence). Tax
    is applied from the company's TaxProfile (Rule #7), snapshotted here so the
    invoice is reproducible even if the profile later changes.
    """

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="invoices"
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, null=True, blank=True,
        related_name="invoices",
    )
    branch = models.ForeignKey(
        "org.Branch", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="invoices",
    )
    warehouse = models.ForeignKey(
        "inventory.Warehouse", on_delete=models.PROTECT, related_name="invoices"
    )
    source_order = models.ForeignKey(
        SalesOrder, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="invoices",
    )
    number = models.PositiveIntegerField()
    currency = models.CharField(max_length=8, default="SDG")
    exchange_rate = models.DecimalField(max_digits=14, decimal_places=6, default=1)
    tax_rate_snapshot = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    # Sum of every line's discount (line discounts plus the invoice-level
    # discount allocated across lines). `subtotal` is already net of it.
    discount_total = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    is_void = models.BooleanField(default=False)  # set only via a Credit Note (M5)
    # Business time vs. audit time. `issued_at` is WHEN THE SALE HAPPENED and
    # is what every report, tax period, and costing walk reads; an offline
    # sale sends it from the till and it may legitimately be hours or days
    # before the row is written. `received_at` is when the server saw it and
    # exists only for the audit trail.
    issued_at = models.DateTimeField(default=timezone.now, db_index=True)
    received_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Credit terms. 0 = due on receipt. `due_date` is derived from issue date +
    # terms when not set explicitly, so aging measures *lateness*, not merely
    # age since issue.
    payment_terms_days = models.PositiveIntegerField(default=0)
    due_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="invoices",
    )
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)
    # The human-readable reference the till printed BEFORE the server assigned
    # `number` (e.g. "MAIN-7F3A-000012"): branch code, device id, per-device
    # counter. Lets a receipt handed to a customer during an outage be matched
    # to this invoice afterwards. Blank for online sales.
    local_reference = models.CharField(max_length=48, blank=True, db_index=True)

    class Meta:
        ordering = ["-number"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"], name="uniq_invoice_number_per_company"
            )
        ]

    def save(self, *args, **kwargs):
        if self.due_date is None and self.issued_at:
            self.due_date = self.issued_at.date() + timedelta(
                days=self.payment_terms_days or 0
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"INV-{self.number:06d}"

    @property
    def days_overdue(self):
        """Days past due; 0 when settled, void or not yet due."""
        if self.is_void or not self.due_date or self.amount_due() <= 0:
            return 0
        return max(0, (date.today() - self.due_date).days)

    @property
    def is_overdue(self):
        return self.days_overdue > 0

    @property
    def number_display(self):
        return f"INV-{self.number:06d}"

    def amount_paid(self):
        return self.payments.aggregate(
            t=Coalesce(Sum("amount"), Decimal("0"))
        )["t"]

    def amount_due(self):
        if self.is_void:
            return Decimal("0")
        return self.total - self.amount_paid() - self._applied_credits()

    def _applied_credits(self):
        # M5 extension: credit notes reduce AR. Lazy import avoids a
        # sales<->returns import cycle. Additive only — no schema change here.
        from returns.models import applied_credit_total
        return applied_credit_total(self)

    @property
    def status(self):
        if self.is_void:
            return "void"
        due = self.amount_due()
        if due <= 0:
            return "paid"
        if self.amount_paid() > 0:
            return "partially_paid"
        return "issued"


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(
        "inventory.Product", on_delete=models.PROTECT, related_name="invoice_lines"
    )
    description = models.CharField(max_length=255, blank=True)
    # Always in the product's BASE unit (pieces, kg): the ledger movement is
    # written from these two fields. When the sale was rung by the pack, the
    # pack fields below keep what the customer actually saw on the receipt.
    quantity = models.DecimalField(max_digits=16, decimal_places=3)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    pack = models.ForeignKey(
        "inventory.ProductPack", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="invoice_lines",
    )
    pack_name = models.CharField(max_length=64, blank=True)   # snapshot: "Carton"
    pack_quantity = models.DecimalField(                      # snapshot: 12.000
        max_digits=16, decimal_places=3, null=True, blank=True
    )
    packs_sold = models.DecimalField(max_digits=16, decimal_places=3, null=True, blank=True)
    # Money taken off this line before tax (its own discount plus its share
    # of any invoice-level discount). unit_price stays the gross list price
    # so the receipt can show "was / now"; line_subtotal is net of this.
    discount_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    line_subtotal = models.DecimalField(max_digits=16, decimal_places=2)
    line_tax = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=16, decimal_places=2)

    def returned_quantity(self):
        """
        How much of this line has already come back (Rule #4). Summed in
        Python rather than via aggregate() so that a caller which prefetched
        `lines__return_lines` pays no extra query per line.
        """
        return sum(
            (rl.quantity for rl in self.return_lines.all()), Decimal("0")
        )

    def returnable_quantity(self):
        """What a new return may still claim against this line."""
        return self.quantity - self.returned_quantity()

    def __str__(self):
        return f"{self.product.sku} x{self.quantity}"


class CashShift(models.Model):
    """
    One till session: opened with a counted float, closed with a physical count.

    This is the control that makes cash accountable. Every other money path in
    the system names a person — a payment has `recorded_by`, a bank transfer has
    a reference — but notes in a drawer name nobody. A shift binds a stretch of
    cash takings to one person, so "the drawer is short" becomes a question with
    an owner instead of an unanswerable one.

    `expected_cash` is DERIVED (opening float + cash takings + drawer movements)
    and never stored, like every other balance here — a stored expectation could
    drift from the payments it is supposed to summarise, which is precisely the
    number you cannot afford to have wrong. Card and bank-transfer payments are
    excluded: they never touch the drawer.

    Closing is the one designed post-hoc write, mirroring Payment.verify: the
    count is recorded once and the shift cannot reopen (Rule #9). A miscount is
    corrected by a drawer movement, not by editing history.
    """

    OPEN = "open"
    CLOSED = "closed"
    STATUS_CHOICES = [(OPEN, "Open"), (CLOSED, "Closed")]

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="cash_shifts"
    )
    branch = models.ForeignKey(
        "org.Branch", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="cash_shifts",
    )
    # PROTECT, not SET_NULL: the whole point of a shift is attribution, and a
    # shift whose holder had been nulled out would be worse than no record.
    # Users are archived rather than deleted, so this never blocks in practice.
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="cash_shifts_opened",
    )
    opening_float = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal("0")
    )
    opened_at = models.DateTimeField(auto_now_add=True)

    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="cash_shifts_closed",
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    # What was physically in the drawer at close. Null while open.
    counted_cash = models.DecimalField(
        max_digits=16, decimal_places=2, null=True, blank=True
    )
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default=OPEN)
    note = models.CharField(max_length=255, blank=True)

    # A manager signing off on the variance. Never blocks the close — leaving
    # drawers open overnight waiting for a manager would defeat the purpose.
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="cash_shifts_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    client_uuid = models.UUIDField(null=True, blank=True, unique=True)

    class Meta:
        ordering = ["-opened_at"]
        constraints = [
            # One drawer per person. Two open shifts would make every takings
            # figure ambiguous — a payment could belong to either.
            models.UniqueConstraint(
                fields=["company", "opened_by"],
                condition=models.Q(status="open"),
                name="uniq_open_cash_shift_per_user",
            )
        ]

    def __str__(self):
        return f"Shift #{self.id} ({self.status})"

    def cash_sales(self):
        """Cash taken in through the till during this shift. Bank transfers are
        excluded — they never reach the drawer."""
        return self.payments.filter(method=Payment.CASH).aggregate(
            t=Coalesce(Sum("amount"), Decimal("0"))
        )["t"]

    def drawer_movements_total(self):
        """Signed total of non-sale cash: refunds and drops out, floats in."""
        return self.drawer_movements.aggregate(
            t=Coalesce(Sum("amount"), Decimal("0"))
        )["t"]

    def expected_cash(self):
        return self.opening_float + self.cash_sales() + self.drawer_movements_total()

    def variance(self):
        """Counted minus expected. Negative = short. None while still open."""
        if self.counted_cash is None:
            return None
        return self.counted_cash - self.expected_cash()


class CashDrawerMovement(models.Model):
    """
    Cash entering or leaving the drawer for a reason other than a sale.

    Without this the drawer can never reconcile: a walk-in refund hands money
    back with nothing recording it, and a mid-shift drop to the safe looks
    identical to a shortfall. Append-only (Rule #9) — a mistake is another,
    offsetting row.

    `amount` is SIGNED (positive into the drawer, negative out) so the expected
    balance is a plain SUM, the same convention StockMovement uses for quantity.
    """

    REFUND = "refund"
    DROP = "drop"
    PETTY = "petty"
    FLOAT_ADD = "float_add"
    CORRECTION = "correction"
    KIND_CHOICES = [
        (REFUND, "Refund to customer"),
        (DROP, "Drop to safe"),
        (PETTY, "Petty cash out"),
        (FLOAT_ADD, "Cash added to drawer"),
        (CORRECTION, "Correction"),
    ]
    # Money that can only leave; validated on write so a typo can't silently
    # turn a refund into a deposit.
    NEGATIVE_ONLY = {REFUND, DROP, PETTY}
    POSITIVE_ONLY = {FLOAT_ADD}

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="drawer_movements"
    )
    shift = models.ForeignKey(
        CashShift, on_delete=models.PROTECT, related_name="drawer_movements"
    )
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    reason = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="drawer_movements",
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)

    class Meta:
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"{self.kind} {self.amount}"


class Payment(models.Model):
    """
    Manually-recorded payment (PROJECT_RULES Rule #3). NEVER integrates a
    payment gateway — there are no external API calls anywhere near this model.
    `verified_at`/`verified_by` support later manual reconciliation by a
    manager but never block a sale. Append-only (Rule #9).
    """

    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"
    METHOD_CHOICES = [(CASH, "Cash"), (BANK_TRANSFER, "Bank Transfer")]

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="payments"
    )
    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name="payments"
    )
    method = models.CharField(max_length=16, choices=METHOD_CHOICES)
    # Receiving account + sender details apply to bank_transfer only.
    company_bank_account = models.ForeignKey(
        CompanyBankAccount, on_delete=models.PROTECT, null=True, blank=True,
        related_name="payments",
    )
    sender_bank_name = models.CharField(max_length=255, blank=True)
    reference_last4 = models.CharField(max_length=4, blank=True)
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    # Which till session took this money. Nullable: payments recorded outside a
    # shift (an office receipt, a bank transfer, anything from before shifts
    # existed) legitimately belong to none, and an offline sale carries the
    # shift id it was rung under so a late sync still lands in the right drawer.
    shift = models.ForeignKey(
        CashShift, on_delete=models.PROTECT, null=True, blank=True,
        related_name="payments",
    )

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="payments_recorded",
    )
    # Business time (when the money changed hands, client-supplied for offline
    # sales) vs. audit time; see Invoice.issued_at.
    recorded_at = models.DateTimeField(default=timezone.now, db_index=True)
    received_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    # Manual reconciliation, filled later; never gates the sale.
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="payments_verified",
    )
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)

    class Meta:
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"{self.method} {self.amount} (INV-{self.invoice.number:06d})"
