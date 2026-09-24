from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
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
    # Credit control. `credit_limit` is the most this customer may owe in
    # total (null = no limit); `credit_hold` blocks any new sale on account,
    # whatever the limit, until a manager lifts it. Both are checked at POS
    # when a sale is not fully paid; a manager-level role may override the
    # limit (logged), nobody overrides a hold.
    credit_limit = models.DecimalField(
        max_digits=16, decimal_places=2, null=True, blank=True
    )
    credit_hold = models.BooleanField(default=False)
    # Own payment terms; null = the company default applies.
    payment_terms_days = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def effective_payment_terms_days(self):
        if self.payment_terms_days is not None:
            return self.payment_terms_days
        return self.company.default_payment_terms_days

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

    # Where the money actually lands. In Sudan most customer transfers
    # arrive through a bank's app (Bankak, Fawri, O-Cash) rather than a
    # branch account; the channel tells the till which app to look at and
    # lets takings be reported per app.
    CHANNEL_BANK = "bank"
    CHANNEL_BANKAK = "bankak"
    CHANNEL_FAWRI = "fawri"
    CHANNEL_OCASH = "ocash"
    CHANNEL_WALLET = "wallet"
    CHANNEL_CHOICES = [
        (CHANNEL_BANK, "Bank account"),
        (CHANNEL_BANKAK, "Bankak"),
        (CHANNEL_FAWRI, "Fawri"),
        (CHANNEL_OCASH, "O-Cash"),
        (CHANNEL_WALLET, "Other mobile wallet"),
    ]

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="bank_accounts"
    )
    channel = models.CharField(max_length=16, choices=CHANNEL_CHOICES, default=CHANNEL_BANK)
    bank_name = models.CharField(max_length=255)
    account_name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=64, blank=True)
    # Balance the account held when it was added to the system. Everything after
    # that is derived from recorded movements, so the balance can never drift.
    opening_balance = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal("0")
    )
    is_active = models.BooleanField(default=True)
    # Shown to a visitor who ordered from the public page, as the account
    # to transfer to. Off by default: an account is public only on purpose.
    show_to_customers = models.BooleanField(default=False)

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
        """Supplier payments made out of this account, in the company currency
        (a USD payment is converted at its own rate, not counted as SDG)."""
        return self.supplier_payments.aggregate(
            t=Coalesce(Sum(ExpressionWrapper(
                F("amount") * F("exchange_rate"),
                output_field=DecimalField(max_digits=20, decimal_places=2),
            )), Decimal("0"))
        )["t"]

    def refunded_total(self):
        """Money handed back to customers by transfer from this account."""
        return self.refunds.aggregate(t=Coalesce(Sum("amount"), Decimal("0")))["t"]

    def expenses_total(self):
        """Running costs paid by transfer from this account (rent, payroll…).
        They used to leave the balance untouched, overstating the bank and
        the zakat base."""
        return self.expenses.aggregate(t=Coalesce(Sum("amount"), Decimal("0")))["t"]

    def has_movements(self):
        """Whether any money has moved through the account; once it has, the
        opening balance is part of every figure since and stays fixed."""
        return (
            self.payments.exists() or self.supplier_payments.exists()
            or self.refunds.exists() or self.expenses.exists()
        )

    def balance(self):
        """
        Current balance, DERIVED — opening + money in − money out, where money
        out is supplier payments and customer refunds (review F02: refunds
        used to be missing, so the balance and the zakat base ran high).

        This tracks only what the system recorded; it is not a bank feed and
        makes no external calls (PROJECT_RULES Rule #3). A difference against
        the real statement is a reconciliation matter, not a bug here.
        """
        return (
            self.opening_balance + self.received_total()
            - self.paid_total() - self.refunded_total() - self.expenses_total()
        )


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
    # A balance the customer already owed when the company started using
    # Vezano, carried as a line-less invoice so the debt ledger, aging,
    # statements and collection all see it — while sales figures skip it.
    is_opening_balance = models.BooleanField(default=False)
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
        indexes = [
            models.Index(fields=["company", "-issued_at"], name="invoice_co_issued_idx"),
            models.Index(fields=["company", "due_date"], name="invoice_co_due_idx"),
            models.Index(fields=["company", "customer"], name="invoice_co_customer_idx"),
            models.Index(fields=["company", "received_at"], name="invoice_co_received_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"], name="uniq_invoice_number_per_company"
            ),
            # The reference printed on an offline receipt must point at one
            # invoice, or the receipt in the customer's hand is ambiguous.
            models.UniqueConstraint(
                fields=["company", "local_reference"],
                condition=~models.Q(local_reference=""),
                name="uniq_invoice_local_reference_per_company",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.due_date is None and self.issued_at:
            # The company's calendar day, not UTC's: a sale at 01:00 in
            # Khartoum got yesterday's due date, and with no payment terms it
            # showed as overdue the moment it was made.
            from core.timezone import company_zone

            issued = self.issued_at
            if timezone.is_aware(issued):
                issued = timezone.localtime(issued, company_zone(self.company))
            self.due_date = issued.date() + timedelta(days=self.payment_terms_days or 0)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"INV-{self.number:06d}"

    @property
    def days_overdue(self):
        """Days past due; 0 when settled, void or not yet due."""
        if self.is_void or not self.due_date or self.amount_due() <= 0:
            return 0
        return max(0, (timezone.localdate() - self.due_date).days)

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
        """What the customer still owes on this invoice.

        total − payments − credit notes + refunds. A credit note lowers the
        debt; if the customer had already paid, the note leaves them in credit
        (negative due) until a Refund hands the money back, which brings the
        balance to zero. Every figure is derived from append-only rows.
        """
        if self.is_void:
            return Decimal("0")
        return self.ledger_balance()

    def void_settlement(self):
        """What voiding this invoice hands back: ``(money, credit)``.

        The customer is owed what they paid less what earlier notes already
        gave back. Only the money part (cash/transfer) is refunded as money;
        the part paid with store credit goes back as credit on the void
        note — a cash refund of it would turn credit into cash. Earlier
        refunds and credit spent elsewhere come out of the money part."""
        owed_back = max(
            Decimal("0"), self.total - self.credited_total() - self.amount_due()
        )
        money_paid = self.payments.filter(method__in=Payment.MONEY_METHODS).aggregate(
            t=Coalesce(Sum("amount"), Decimal("0"))
        )["t"]
        cents = Decimal("0.01")
        money = max(Decimal("0"), min(
            owed_back, money_paid - self.refunded_total() - self.credit_spent_elsewhere()
        )).quantize(cents)
        return money, (owed_back - money).quantize(cents)

    def ledger_balance(self):
        """`amount_due()` without the void short-cut: the invoice's own rows
        netted. A void invoice owes nothing, but the credit notes on it may
        still hold credit the customer paid for — the part of a voided sale
        paid with store credit is given back as credit, not cash, and stays
        on the void note until it is spent or refunded."""
        return (
            self.total - self.amount_paid() - self._applied_credits()
            + self.refunded_total() + self.credit_spent_elsewhere()
        )

    def credited_total(self):
        return self._applied_credits()

    def refunded_total(self):
        """Money handed back against this invoice's credit notes."""
        return Refund.objects.filter(credit_note__invoice=self).aggregate(
            t=Coalesce(Sum("amount"), Decimal("0"))
        )["t"]

    def credit_spent_elsewhere(self):
        """Credit from this invoice's notes used to settle other invoices.
        Like a refund, it consumes the credit sitting here."""
        return Payment.objects.filter(
            credit_note__invoice=self, method=Payment.STORE_CREDIT
        ).aggregate(t=Coalesce(Sum("amount"), Decimal("0")))["t"]

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

    class Meta:
        indexes = [
            # Sales-by-product and COGS group lines by product across invoices.
            models.Index(fields=["product", "invoice"], name="invoiceline_product_inv_idx"),
        ]

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
    # The expected figure shown when the drawer was counted. Offline sales
    # rung up during the shift can sync after the close and still land here
    # (their cash was in the drawer at the count); the live expected_cash()
    # then includes them, and the gap to this frozen figure is shown as late
    # cash instead of silently rewriting what the cashier was held to.
    expected_at_close = models.DecimalField(
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
    # A refund row is written by the Refund that took the cash out, so the
    # drawer and the customer's account always agree on the same document. A
    # free-standing refund movement (no document) is no longer how money
    # leaves the till.
    refund = models.ForeignKey(
        "sales.Refund", on_delete=models.PROTECT, null=True, blank=True,
        related_name="drawer_movements",
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
    # Store credit: a customer's credit note (from a return on a paid sale)
    # settling a later invoice. No money changes hands, so it is excluded
    # from cash-flow, takings and the verification worklist; it exists so the
    # credit does not have to be handed back in cash first.
    STORE_CREDIT = "credit"
    METHOD_CHOICES = [
        (CASH, "Cash"), (BANK_TRANSFER, "Bank Transfer"), (STORE_CREDIT, "Store credit"),
    ]
    MONEY_METHODS = (CASH, BANK_TRANSFER)

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="payments"
    )
    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name="payments"
    )
    method = models.CharField(max_length=16, choices=METHOD_CHOICES)
    # The credit note this payment draws on when method is STORE_CREDIT.
    credit_note = models.ForeignKey(
        "returns.CreditNote", on_delete=models.PROTECT, null=True, blank=True,
        related_name="applications",
    )
    # Receiving account + sender details apply to bank_transfer only.
    company_bank_account = models.ForeignKey(
        CompanyBankAccount, on_delete=models.PROTECT, null=True, blank=True,
        related_name="payments",
    )
    sender_bank_name = models.CharField(max_length=255, blank=True)
    reference_last4 = models.CharField(max_length=4, blank=True)
    # The app's own transaction id, as the customer's screenshot shows it.
    # Stored in full so a statement export can be matched against it and so
    # the same screenshot cannot be presented twice (see PaymentSerializer).
    transfer_reference = models.CharField(max_length=64, blank=True)
    # One bank transfer settling several invoices: the collect drawer records
    # one Payment per invoice and stamps them all with the same group, so the
    # same transfer reference may repeat inside the group and nowhere else.
    receipt_group = models.UUIDField(null=True, blank=True, db_index=True)
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    # Snapshot per transaction (PROJECT_RULES: currency + rate, no more). A
    # payment inherits its invoice's currency; the rate is the day's.
    currency = models.CharField(max_length=8, blank=True)
    exchange_rate = models.DecimalField(max_digits=14, decimal_places=6, default=1)
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
        indexes = [
            models.Index(fields=["company", "-recorded_at"], name="payment_co_recorded_idx"),
            models.Index(
                fields=["company_bank_account", "transfer_reference"],
                name="payment_acct_ref_idx",
            ),
        ]
        constraints = [
            # The same transfer id can never settle the same invoice twice,
            # whatever two requests raced through validation (review F13).
            # Cross-invoice reuse is legitimate only inside a receipt group
            # and is serialised by the account lock in sales.payments.
            models.UniqueConstraint(
                fields=["company_bank_account", "transfer_reference", "invoice"],
                condition=~models.Q(transfer_reference=""),
                name="uniq_payment_reference_per_invoice",
            ),
        ]

    def __str__(self):
        return f"{self.method} {self.amount} (INV-{self.invoice.number:06d})"


class Refund(models.Model):
    """
    Money handed back to a customer against a Credit Note. Append-only
    (Rule #9) and manual only (Rule #3): cash from the drawer or a bank
    transfer out of one of the company's own accounts, recorded by a person.

    Without this document a credit note on a paid invoice left the customer
    "in credit" forever, while the cash actually left the drawer as a loose
    `CashDrawerMovement` nobody could tie to the note — so the same credit
    could be paid out twice, or never. `sum(refunds) <= credit_note.amount`
    is enforced under a row lock on the note.
    """

    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"
    METHOD_CHOICES = [(CASH, "Cash"), (BANK_TRANSFER, "Bank Transfer")]

    company = models.ForeignKey(
        "org.Company", on_delete=models.CASCADE, related_name="refunds"
    )
    credit_note = models.ForeignKey(
        "returns.CreditNote", on_delete=models.PROTECT, related_name="refunds"
    )
    method = models.CharField(max_length=16, choices=METHOD_CHOICES)
    # Bank transfers: which of our accounts the money left, and the reference.
    company_bank_account = models.ForeignKey(
        CompanyBankAccount, on_delete=models.PROTECT, null=True, blank=True,
        related_name="refunds",
    )
    reference_last4 = models.CharField(max_length=4, blank=True)
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    # Cash refunds come out of an open drawer, which then shows the movement.
    shift = models.ForeignKey(
        CashShift, on_delete=models.PROTECT, null=True, blank=True,
        related_name="refunds",
    )
    note = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="refunds_recorded",
    )
    recorded_at = models.DateTimeField(default=timezone.now, db_index=True)
    received_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)

    class Meta:
        ordering = ["-recorded_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="refund_amount_positive"
            )
        ]

    def __str__(self):
        return f"Refund {self.amount} vs {self.credit_note_id}"
