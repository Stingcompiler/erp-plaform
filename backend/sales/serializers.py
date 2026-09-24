from collections import defaultdict
from datetime import timedelta
import re
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.exceptions import APIException

from core.activity import log_activity
from core.rbac import can_approve_high_value
from core.scoping import assert_user_branch

from inventory.models import Product, ProductPack, StockBatch, StockMovement, Warehouse
from sales.models import (
    Refund,
    CashDrawerMovement,
    CashShift,
    CompanyBankAccount,
    Customer,
    Invoice,
    InvoiceLine,
    Payment,
    Quotation,
    QuotationLine,
    SalesOrder,
    SalesOrderLine,
)
from sales.numbering import allocate_invoice_number
from sales.price_rules import (
    check_document_lines,
    price_breaches,
    record_document_check,
    refuse as refuse_price,
)

TWO_PLACES = Decimal("0.01")


def _q2(value):
    return Decimal(value).quantize(TWO_PLACES)


def validate_business_time(value):
    """A client-supplied business timestamp for an offline-capable write.

    Accepted window: not in the future beyond clock skew, and not older than
    VEZANO_MAX_BACKDATE_DAYS (default 31) so a forgotten queue cannot rewrite
    a closed period. Returns the value unchanged; the server's own clock is
    recorded separately in `received_at` for audit.
    """
    from django.conf import settings
    from django.utils import timezone

    if value is None:
        return None
    now = timezone.now()
    if value > now + timedelta(minutes=10):
        raise serializers.ValidationError(_("occurred_at cannot be in the future."))
    max_days = getattr(settings, "VEZANO_MAX_BACKDATE_DAYS", 31)
    if value < now - timedelta(days=max_days):
        raise serializers.ValidationError(
            _("occurred_at is older than %(days)s days; contact your manager to backdate.")
            % {"days": max_days}
        )
    return value


def rung_while_open(shift, when):
    """Money that moved while the shift was open belongs to that drawer, even
    when an offline device reports it after the close: the cash was in that
    drawer when it was counted. Refusing it lost a paid sale or refund for
    good (the device could only discard it)."""
    return bool(when and shift.closed_at and shift.opened_at <= when <= shift.closed_at)


def late_money_shift(serializer, shift, when, entity_type):
    """The drawer for money an offline device reports after `shift` closed
    (and outside its open hours). Refusing it lost a payment or refund that
    physically happened, while a POS sale in the same position is kept. The
    money goes to the same cashier's drawer that was open at `when`, or to
    no drawer; either way an audit row says so, as for a sale."""
    replacement = None
    if when is not None:
        replacement = (
            CashShift.objects.filter(
                company_id=shift.company_id, opened_by_id=shift.opened_by_id,
                opened_at__lte=when,
            )
            .filter(Q(closed_at__isnull=True, status=CashShift.OPEN) | Q(closed_at__gte=when))
            .exclude(pk=shift.pk)
            .order_by("-opened_at")
            .first()
        )
    log_activity(
        action="money_outside_closed_shift", request=serializer.context.get("request"),
        entity_type=entity_type, entity_id=shift.pk,
        metadata={
            "via": "sync", "shift": shift.pk, "recorded_at": str(when),
            "moved_to_shift": replacement.pk if replacement else None,
        },
    )
    return replacement


# The column's width; a suffix on a colliding reference must still fit.
LOCAL_REFERENCE_MAX = 48


def _free_local_reference(company_id, reference):
    taken = Invoice.objects.filter(company_id=company_id)
    if not taken.filter(local_reference=reference).exists():
        return reference
    for n in range(2, 10000):
        suffix = f"-{n}"
        candidate = reference[: LOCAL_REFERENCE_MAX - len(suffix)] + suffix
        if not taken.filter(local_reference=candidate).exists():
            return candidate
    return ""  # unreachable in practice; a sale is never lost over a label


def create_with_local_reference(request, printed, fields):
    """Create the invoice under the reference the till printed.

    Two tills (or two cashiers who shared one tablet before the counter was
    made per device) can print the same provisional reference. The sale
    happened and the customer holds a receipt: a collision must never lose
    it. The second invoice keeps the printed reference with a suffix, and an
    audit row records the reference on the paper so the receipt can still be
    matched."""
    printed = (printed or "").strip()
    for _attempt in range(5):
        reference = _free_local_reference(fields["company_id"], printed) if printed else ""
        try:
            with transaction.atomic():
                invoice = Invoice.objects.create(local_reference=reference, **fields)
        except IntegrityError:
            client_uuid = fields.get("client_uuid")
            if not printed or (
                client_uuid and Invoice.objects.filter(client_uuid=client_uuid).exists()
            ):
                raise
            continue  # another till took the same reference this instant
        if reference != printed:
            holder = (
                Invoice.objects.filter(company_id=fields["company_id"], local_reference=printed)
                .exclude(pk=invoice.pk).values_list("pk", flat=True).first()
            )
            log_activity(
                action="local_reference_renumbered", request=request,
                entity_type="Invoice", entity_id=invoice.pk,
                metadata={"printed": printed, "stored": reference, "other_invoice": holder},
            )
        return invoice
    # Not the sale's fault: answered as temporary, so a queued sale is
    # retried by the device instead of refused.
    exc = APIException(_("The receipt reference could not be saved; try again."))
    exc.status_code = 503
    raise exc


def _company_tax_rate(company):
    """Headline rate from the company's TaxProfile (Rule #7) — never hardcoded.
    Kept for the snapshot written on the invoice; the arithmetic itself goes
    through the jurisdiction handler (see tax_handler_for)."""
    profile = getattr(company, "tax_profile", None)
    return profile.flat_tax_rate if profile else Decimal("0")


def tax_handler_for(company):
    from tax.handlers import get_handler

    return get_handler(getattr(company, "tax_profile", None))


def _assert_tenant_relations(serializer, attrs, fields):
    request = serializer.context.get("request")
    user = getattr(request, "user", None)
    if user is None or getattr(user, "is_platform_admin", False):
        return
    company_id = getattr(user, "company_id", None)
    role = getattr(user, "role", None)
    for name in fields:
        obj = attrs.get(name)
        if obj is not None and obj.company_id != company_id:
            raise serializers.ValidationError(
                {name: _("Not your company's record.")}
            )
        if obj is not None and role and role.scope_level == "branch":
            object_branch_id = (
                obj.pk if name == "branch" else getattr(obj, "branch_id", None)
            )
            if object_branch_id is not None and object_branch_id != user.branch_id:
                raise serializers.ValidationError(
                    {name: _("This record is outside your assigned branch.")}
                )


class CustomerSerializer(serializers.ModelSerializer):
    ar_balance = serializers.SerializerMethodField()
    opening_balance = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            "id", "company", "name", "phone", "email", "address",
            "is_active", "credit_limit", "credit_hold", "payment_terms_days",
            "ar_balance", "opening_balance", "updated_at",
        ]
        read_only_fields = ["company", "updated_at"]

    def get_ar_balance(self, obj):
        # Lists and the sync pull annotate the balance in SQL
        # (sales.querysets.with_ar_balance); a single row falls back to the
        # model method, which gives the same number.
        annotated = getattr(obj, "ar_balance_sql", None)
        return annotated if annotated is not None else obj.ar_balance()

    def get_opening_balance(self, obj):
        opening = obj.invoices.filter(is_opening_balance=True, is_void=False).first()
        if opening is None:
            return None
        return {"amount": str(opening.total), "as_of": opening.due_date, "invoice": opening.id,
                "number": opening.number_display}

    def validate(self, attrs):
        # Credit terms are a manager's decision, not a data-entry field.
        request = self.context.get("request")
        touching_credit = "credit_limit" in attrs or "credit_hold" in attrs
        if touching_credit and request is not None:
            current_limit = getattr(self.instance, "credit_limit", None)
            current_hold = getattr(self.instance, "credit_hold", False)
            changed = (
                attrs.get("credit_limit", current_limit) != current_limit
                or attrs.get("credit_hold", current_hold) != current_hold
            )
            if changed and not can_approve_high_value(request.user):
                raise serializers.ValidationError(
                    {"credit_limit": _("Only a manager may set credit terms.")}
                )
        return attrs


def normalise_reference(value):
    """A transfer reference as the app printed it, minus spaces and dashes."""
    return re.sub(r"[^0-9A-Za-z]", "", str(value or "")).upper()


def transfer_details(attrs, bank_account):
    """Validate a bank-transfer's reference fields and return reference_last4.

    Accepts the app's full transaction id (`transfer_reference`), the last 4
    digits (`reference_last4`), or both. The full id is what a statement is
    matched on and what stops the same screenshot being presented twice on
    the same receiving account; the last 4 stays for the receipt.
    """
    ref = str(attrs.get("reference_last4") or "").strip()
    full = normalise_reference(attrs.get("transfer_reference"))
    attrs["transfer_reference"] = full
    if full:
        digits = re.sub(r"\D", "", full)
        if not ref:
            ref = digits[-4:] if digits else full[-4:]
            attrs["reference_last4"] = ref
        duplicates = Payment.objects.filter(
            company_bank_account=bank_account, transfer_reference=full,
        )
        group = attrs.get("receipt_group")
        if group:
            # Same transfer split over several invoices in one collection.
            duplicates = duplicates.exclude(receipt_group=group)
        duplicate = duplicates.select_related("invoice").first()
        if duplicate is not None:
            raise serializers.ValidationError({
                "transfer_reference": _(
                    "Reference %(ref)s was already recorded on %(when)s "
                    "for invoice INV-%(number)06d."
                ) % {
                    "ref": full, "when": duplicate.recorded_at.date().isoformat(),
                    "number": duplicate.invoice.number,
                }
            })
    # Typed by hand the last-4 must be digits; derived from a full id it may
    # be letters when the app's id has no digits at all.
    if not ref or len(ref) > 4 or (not full and not ref.isdigit()):
        raise serializers.ValidationError(
            _("Enter the transfer reference (or its last 4 digits).")
        )
    return ref


class CompanyBankAccountSerializer(serializers.ModelSerializer):
    # Derived, never stored — see CompanyBankAccount.balance().
    balance = serializers.SerializerMethodField()
    channel_display = serializers.CharField(source="get_channel_display", read_only=True)
    received_total = serializers.SerializerMethodField()
    paid_total = serializers.SerializerMethodField()
    refunded_total = serializers.SerializerMethodField()

    class Meta:
        model = CompanyBankAccount
        fields = [
            "id", "company", "channel", "channel_display", "bank_name", "account_name",
            "account_number", "opening_balance", "is_active", "show_to_customers",
            "balance", "received_total", "paid_total", "refunded_total",
        ]
        read_only_fields = ["company"]

    # Where customers are told to send money, and the figure the bank
    # balance (and zakat) start from: a sales officer could repoint the
    # public-order account to their own number or inflate the balance.
    SENSITIVE = ("account_number", "show_to_customers", "opening_balance")

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        instance = self.instance
        changed = [
            field for field in self.SENSITIVE
            if field in attrs and (
                instance is None and attrs[field] not in ("", None, False, 0)
                or instance is not None and attrs[field] != getattr(instance, field)
            )
        ]
        if changed and not can_approve_high_value(user):
            raise serializers.ValidationError(
                {changed[0]: _("Only a manager or owner may change this bank detail.")}
            )
        if instance is not None and "opening_balance" in changed and instance.has_movements():
            raise serializers.ValidationError({"opening_balance": _(
                "Money has already moved through this account; its opening balance is fixed."
            )})
        return attrs

    def get_balance(self, obj):
        return str(obj.balance())

    def get_received_total(self, obj):
        return str(obj.received_total())

    def get_paid_total(self, obj):
        return str(obj.paid_total())

    def get_refunded_total(self, obj):
        return str(obj.refunded_total())


# ---------- Quotation ----------

class QuotationLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True, default="")
    product_sku = serializers.CharField(source="product.sku", read_only=True, default="")

    class Meta:
        model = QuotationLine
        fields = [
            "id", "product", "product_name", "product_sku", "description",
            "quantity", "unit_price", "line_total",
        ]
        read_only_fields = ["line_total"]
        # A quote for -3 units totalled -300.00.
        extra_kwargs = {
            "quantity": {"min_value": Decimal("0.001")},
            "unit_price": {"min_value": Decimal("0")},
        }


class QuotationSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True, default="")

    lines = QuotationLineSerializer(many=True)

    class Meta:
        model = Quotation
        fields = [
            "id", "company", "customer", "customer_name", "branch", "status", "valid_until",
            "note", "subtotal", "tax_amount", "total", "lines", "created_at",
            "price_approved_by", "price_approved_at",
        ]
        # Status moves through set_status / convert_to_order only.
        read_only_fields = [
            "company", "subtotal", "tax_amount", "total", "created_at", "status",
            "price_approved_by", "price_approved_at",
        ]

    def validate(self, attrs):
        _assert_tenant_relations(self, attrs, ("customer", "branch"))
        for line in attrs.get("lines", []):
            _assert_tenant_relations(self, line, ("product",))
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines")
        company_id = validated_data.get("company_id")
        from org.models import Company
        company = Company.objects.get(pk=company_id)
        handler = tax_handler_for(company)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        # The price rule of the till (sales.price_rules): a quote is where
        # the customer is promised the price, so it is held to it here.
        breaches = check_document_lines(
            company, [(ln["product"], ln["quantity"], ln["unit_price"]) for ln in lines], user
        )
        if request and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        quotation = Quotation.objects.create(**validated_data)
        subtotal = Decimal("0")
        tax_total = Decimal("0")
        for line in lines:
            lt = _q2(line["quantity"] * line["unit_price"])
            QuotationLine.objects.create(quotation=quotation, line_total=lt, **line)
            subtotal += lt
            tax_total += handler.compute_tax(lt, line.get("product"))
        quotation.subtotal = _q2(subtotal)
        quotation.tax_amount = _q2(tax_total)
        quotation.total = quotation.subtotal + quotation.tax_amount
        quotation.save(update_fields=["subtotal", "tax_amount", "total"])
        record_document_check(quotation, breaches, user, request, "quote_price_override")
        return quotation


# ---------- Sales Order ----------

class SalesOrderLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True, default="")
    product_sku = serializers.CharField(source="product.sku", read_only=True, default="")
    # The till measures a discount on an order it invoices from here when
    # the order's prices are not trusted (SalesOrder.prices_trusted).
    list_price = serializers.DecimalField(
        source="product.sale_price", max_digits=14, decimal_places=2, read_only=True,
        default=None,
    )

    class Meta:
        model = SalesOrderLine
        fields = [
            "id", "product", "product_name", "product_sku", "description",
            "quantity", "unit_price", "list_price", "line_total",
        ]
        read_only_fields = ["line_total"]
        # A quote for -3 units totalled -300.00.
        extra_kwargs = {
            "quantity": {"min_value": Decimal("0.001")},
            "unit_price": {"min_value": Decimal("0")},
        }


class SalesOrderSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True, default="")
    invoice_id = serializers.SerializerMethodField()

    lines = SalesOrderLineSerializer(many=True)

    class Meta:
        model = SalesOrder
        fields = [
            "id", "company", "customer", "customer_name", "branch", "source_quotation", "status",
            "subtotal", "tax_amount", "total", "lines", "invoice_id", "created_at",
            "price_approved_by", "price_approved_at", "prices_trusted",
        ]
        # Status moves through set_status (and invoicing); the source quote
        # through convert_to_order. Writable, an order could be created
        # already "fulfilled", or tied to a quote to get round one-per-quote.
        read_only_fields = [
            "company", "subtotal", "tax_amount", "total", "created_at",
            "status", "source_quotation", "price_approved_by", "price_approved_at",
        ]

    def get_invoice_id(self, obj):
        invoice = obj.invoices.order_by("pk").first()
        return invoice.pk if invoice else None

    def validate(self, attrs):
        _assert_tenant_relations(
            self, attrs, ("customer", "branch", "source_quotation")
        )
        quotation = attrs.get("source_quotation")
        customer = attrs.get("customer")
        if quotation is not None and customer is not None:
            if quotation.customer_id != customer.pk:
                raise serializers.ValidationError(
                    {"source_quotation": _("Quotation and order customer must match.")}
                )
        for line in attrs.get("lines", []):
            _assert_tenant_relations(self, line, ("product",))
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines")
        company_id = validated_data.get("company_id")
        from org.models import Company
        company = Company.objects.get(pk=company_id)
        handler = tax_handler_for(company)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        # Held to the till's price rule: otherwise an order at a deep
        # discount would be invoiced at its own price (sales.price_rules).
        breaches = check_document_lines(
            company, [(ln["product"], ln["quantity"], ln["unit_price"]) for ln in lines], user
        )
        if request and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        order = SalesOrder.objects.create(**validated_data)
        subtotal = Decimal("0")
        tax_total = Decimal("0")
        for line in lines:
            lt = _q2(line["quantity"] * line["unit_price"])
            SalesOrderLine.objects.create(sales_order=order, line_total=lt, **line)
            subtotal += lt
            tax_total += handler.compute_tax(lt, line.get("product"))
        order.subtotal = _q2(subtotal)
        order.tax_amount = _q2(tax_total)
        order.total = order.subtotal + order.tax_amount
        order.save(update_fields=["subtotal", "tax_amount", "total"])
        record_document_check(order, breaches, user, request, "order_price_override")
        return order


# ---------- Invoice (read) ----------

class InvoiceLineSerializer(serializers.ModelSerializer):
    # Lets the returns UI cap its quantity input at the same number the server
    # enforces (Rule #4), instead of letting the user submit and be rejected.
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    returned_quantity = serializers.DecimalField(
        max_digits=16, decimal_places=3, read_only=True
    )
    returnable_quantity = serializers.DecimalField(
        max_digits=16, decimal_places=3, read_only=True
    )

    class Meta:
        model = InvoiceLine
        fields = [
            "id", "product", "description", "quantity", "unit_price", "discount_amount",
            "pack", "pack_name", "pack_quantity", "packs_sold",
            "tax_rate", "line_subtotal", "line_tax", "line_total",
            "product_name", "product_sku",
            "returned_quantity", "returnable_quantity",
        ]


class InvoiceSerializer(serializers.ModelSerializer):
    lines = InvoiceLineSerializer(many=True, read_only=True)
    number_display = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    amount_paid = serializers.SerializerMethodField()
    amount_due = serializers.SerializerMethodField()
    days_overdue = serializers.IntegerField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True, default=None)

    class Meta:
        model = Invoice
        fields = [
            "id", "company", "customer", "customer_name", "branch", "warehouse", "number",
            "number_display", "local_reference", "received_at", "currency", "exchange_rate",
            "tax_rate_snapshot",
            "subtotal", "discount_total", "tax_amount", "total", "is_void", "status",
            "amount_paid", "amount_due", "lines", "client_uuid", "issued_at",
            "payment_terms_days", "due_date", "days_overdue", "is_overdue",
            "updated_at",
        ]
        read_only_fields = ["due_date", "updated_at"]

    def get_amount_paid(self, obj):
        return obj.amount_paid()

    def get_amount_due(self, obj):
        return obj.amount_due()


# ---------- Payment (Rule #3) ----------

def assert_store_credit(note, invoice, amount, company_id):
    """The rules for paying an invoice with a customer's credit note: same
    company, same customer, note alive, and no more than the credit actually
    left on it (`remaining_refundable` already nets refunds, earlier
    applications and what the note settled on its own invoice)."""
    if note is None:
        raise serializers.ValidationError(
            {"credit_note": _("Store credit needs the credit note it draws on.")}
        )
    if note.company_id != company_id:
        raise serializers.ValidationError({"credit_note": _("Not your company's credit note.")})
    if note.is_void:
        raise serializers.ValidationError({"credit_note": _("That credit note is void.")})
    if invoice.customer_id is None or note.customer_id != invoice.customer_id:
        raise serializers.ValidationError(
            {"credit_note": _("A credit note can only pay an invoice of the same customer.")}
        )
    if note.invoice_id == invoice.pk:
        raise serializers.ValidationError(
            {"credit_note": _("This note already reduces that invoice; it cannot pay it twice.")}
        )
    remaining = note.remaining_refundable()
    if amount > remaining:
        raise serializers.ValidationError(
            {"amount": _("Only %(remaining)s of %(note)s is still available.")
             % {"remaining": remaining, "note": note.number_display}}
        )


class PaymentSerializer(serializers.ModelSerializer):
    # Display fields for the verification worklist and payment lists.
    invoice_number = serializers.CharField(source="invoice.number_display", read_only=True)
    customer_name = serializers.CharField(
        source="invoice.customer.name", read_only=True, default=""
    )
    recorded_by_name = serializers.CharField(
        source="recorded_by.full_name", read_only=True, default=""
    )
    verified_by_name = serializers.CharField(
        source="verified_by.full_name", read_only=True, default=""
    )
    credit_note_number = serializers.CharField(
        source="credit_note.number_display", read_only=True, default=None
    )
    bank_account_name = serializers.CharField(
        source="company_bank_account.bank_name", read_only=True, default=""
    )
    bank_channel = serializers.CharField(
        source="company_bank_account.channel", read_only=True, default=""
    )

    class Meta:
        model = Payment
        fields = [
            "id", "company", "invoice", "invoice_number", "customer_name",
            "method", "company_bank_account", "bank_account_name", "bank_channel",
            "credit_note", "credit_note_number",
            "sender_bank_name", "reference_last4", "transfer_reference", "receipt_group",
            "amount", "currency", "exchange_rate",
            "shift", "recorded_by", "recorded_by_name",
            "recorded_at", "received_at", "verified_at", "verified_by", "verified_by_name",
            "client_uuid",
        ]
        # Currency and rate are a snapshot of the invoice, never client input
        # (review F04: a caller could post currency=USD, exchange_rate=0).
        read_only_fields = [
            "company", "recorded_by", "received_at", "verified_at", "verified_by",
            "currency", "exchange_rate",
        ]
        extra_kwargs = {"recorded_at": {"required": False}}
        # The (account, reference, invoice) constraint is enforced by the
        # database and answered by sales.payments with a field error; DRF's
        # auto-generated unique-together validator would instead make the
        # reference a required field and report a non-field error.
        validators = []

    def validate_recorded_at(self, value):
        return validate_business_time(value)

    def validate(self, attrs):
        method = attrs.get("method")
        amount = attrs.get("amount")
        if amount is None or amount <= 0:
            raise serializers.ValidationError(_("Amount must be positive."))

        bank_account = attrs.get("company_bank_account")
        sender = attrs.get("sender_bank_name", "")
        ref = attrs.get("reference_last4", "")
        transfer_reference = attrs.get("transfer_reference", "")

        if method == Payment.BANK_TRANSFER:
            if bank_account is None:
                raise serializers.ValidationError(
                    _("Bank transfer requires the receiving company bank account.")
                )
            if not sender:
                raise serializers.ValidationError(
                    _("Bank transfer requires the sender's bank name.")
                )
            ref = transfer_details(attrs, bank_account)
        elif method == Payment.CASH:
            if bank_account or sender or ref or transfer_reference:
                raise serializers.ValidationError(
                    _("Cash payments must not carry bank/reference details.")
                )
        elif method == Payment.STORE_CREDIT:
            if bank_account or sender or ref or attrs.get("shift"):
                raise serializers.ValidationError(
                    _("Store credit is not money: no bank, reference or till details.")
                )

        self._check_company(attrs)
        invoice = attrs.get("invoice") or getattr(self.instance, "invoice", None)
        if method == Payment.STORE_CREDIT and invoice is not None:
            request = self.context.get("request")
            company_id = getattr(getattr(request, "user", None), "company_id", None)
            assert_store_credit(attrs.get("credit_note"), invoice, amount, company_id)
        elif attrs.get("credit_note") is not None:
            raise serializers.ValidationError(
                {"credit_note": _("Only a store-credit payment names a credit note.")}
            )
        if invoice is not None and amount is not None:
            due = invoice.amount_due()
            if amount > due:
                raise serializers.ValidationError(
                    {
                        "amount": (
                            _("Amount exceeds the balance due (%(due)s). Record the "
                              "surplus separately instead of overpaying the invoice.")
                            % {"due": due}
                        )
                    }
                )
        return attrs

    def _check_company(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None or getattr(user, "is_platform_admin", False):
            return
        company_id = getattr(user, "company_id", None)
        invoice = attrs.get("invoice")
        if invoice is not None and invoice.company_id != company_id:
            raise serializers.ValidationError({"invoice": _("Not your company's invoice.")})
        assert_user_branch(user, invoice, "invoice")
        ba = attrs.get("company_bank_account")
        if ba is not None and ba.company_id != company_id:
            raise serializers.ValidationError(
                {"company_bank_account": _("Not your company's bank account.")}
            )
        shift = attrs.get("shift")
        if shift is not None:
            # A counter collection lands in the drawer that took it, so the
            # shift's expected cash includes it. Only the holder of an open
            # drawer (or a manager) may book money into it.
            if shift.company_id != company_id:
                raise serializers.ValidationError({"shift": _("Not your company's till session.")})
            if shift.opened_by_id != user.pk and not can_approve_high_value(user):
                raise serializers.ValidationError(
                    {"shift": _("You can only record cash into your own open drawer.")}
                )
            if shift.status != CashShift.OPEN and not rung_while_open(
                shift, attrs.get("recorded_at")
            ):
                if not self.context.get("via_sync"):
                    raise serializers.ValidationError(
                        {"shift": _("That till session is closed — open a new one.")}
                    )
                # Taken offline, reported after the drawer was closed on
                # another device: the money was received. Keep it (as a POS
                # sale is kept) in the drawer open at the time, or none.
                attrs["shift"] = late_money_shift(self, shift, attrs.get("recorded_at"), "Payment")

    def create(self, validated_data):
        # validate() pre-checked without a lock; sales.payments.record_payment
        # re-checks the balance under a row lock so two tills (or a sync
        # replay racing a live payment) can never both commit.
        from sales.payments import record_payment

        request = self.context.get("request")
        recorded_by = validated_data.get("recorded_by")
        if recorded_by is None and request and request.user.is_authenticated:
            recorded_by = request.user
        return record_payment(
            validated_data["invoice"],
            amount=validated_data["amount"], method=validated_data["method"],
            recorded_by=recorded_by,
            company_bank_account=validated_data.get("company_bank_account"),
            sender_bank_name=validated_data.get("sender_bank_name", ""),
            reference_last4=validated_data.get("reference_last4", ""),
            transfer_reference=validated_data.get("transfer_reference", ""),
            receipt_group=validated_data.get("receipt_group"),
            shift=validated_data.get("shift"), credit_note=validated_data.get("credit_note"),
            client_uuid=validated_data.get("client_uuid"),
            recorded_at=validated_data.get("recorded_at"),
        )


# ---------- POS checkout ----------

class POSLineSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    # A scanned lot. Optional: without it a batch-tracked product is drawn
    # down first-expired-first-out (inventory/fefo.py).
    batch = serializers.PrimaryKeyRelatedField(
        queryset=StockBatch.objects.all(), required=False, allow_null=True
    )
    # Sell by the pack: `quantity` is then the number of packs and unit_price
    # (if given) the price per pack; both are converted to base units before
    # anything is written.
    pack = serializers.PrimaryKeyRelatedField(
        queryset=ProductPack.objects.all(), required=False, allow_null=True
    )
    quantity = serializers.DecimalField(max_digits=16, decimal_places=3, min_value=Decimal("0.001"))
    unit_price = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, min_value=Decimal("0")
    )
    description = serializers.CharField(required=False, allow_blank=True)
    # Either a percentage of the line or a fixed amount, never both.
    discount_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False,
        min_value=Decimal("0"), max_value=Decimal("100"),
    )
    discount_amount = serializers.DecimalField(
        max_digits=16, decimal_places=2, required=False, min_value=Decimal("0")
    )

    def validate(self, attrs):
        if attrs.get("discount_percent") is not None and attrs.get("discount_amount") is not None:
            raise serializers.ValidationError(
                _("Use either discount_percent or discount_amount on a line, not both.")
            )
        return attrs


class POSPaymentSerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=Payment.METHOD_CHOICES)
    company_bank_account = serializers.PrimaryKeyRelatedField(
        queryset=CompanyBankAccount.objects.all(), required=False, allow_null=True
    )
    sender_bank_name = serializers.CharField(required=False, allow_blank=True)
    reference_last4 = serializers.CharField(required=False, allow_blank=True)
    transfer_reference = serializers.CharField(
        required=False, allow_blank=True, max_length=64
    )
    amount = serializers.DecimalField(max_digits=16, decimal_places=2)


class POSApplyCreditSerializer(serializers.Serializer):
    credit_note = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=16, decimal_places=2, min_value=Decimal("0.01"))


class CashDrawerMovementSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    recorded_by_name = serializers.CharField(
        source="recorded_by.full_name", read_only=True, default=None
    )

    class Meta:
        model = CashDrawerMovement
        fields = [
            "id", "shift", "kind", "kind_display", "amount", "reason",
            "recorded_by_name", "recorded_at", "client_uuid", "refund",
        ]
        read_only_fields = ["recorded_at", "refund"]

    def validate(self, attrs):
        kind = attrs.get("kind")
        amount = attrs.get("amount")
        if amount is None or amount == 0:
            raise serializers.ValidationError(_("Amount must not be zero."))
        # A refund moves the drawer from its return or invoice, which links
        # the document; a loose "refund" typed here paid the customer a
        # second time, or left their credit open.
        if kind == CashDrawerMovement.REFUND:
            raise serializers.ValidationError(
                {"kind": _(
                    "Record a refund from its return or invoice; the drawer is updated for you."
                )}
            )
        # The sign carries the meaning, so a typo must not turn a refund into a
        # deposit and quietly hide a shortfall.
        if kind in CashDrawerMovement.NEGATIVE_ONLY and amount > 0:
            raise serializers.ValidationError(
                {
                    "amount": _("A '%(kind)s' takes money out — the amount must be negative.")
                    % {"kind": kind}
                }
            )
        if kind in CashDrawerMovement.POSITIVE_ONLY and amount < 0:
            raise serializers.ValidationError(
                {
                    "amount": _("A '%(kind)s' puts money in — the amount must be positive.")
                    % {"kind": kind}
                }
            )

        shift = attrs.get("shift")
        if shift is not None:
            request = self.context.get("request")
            user = getattr(request, "user", None)
            if user is not None and not getattr(user, "is_platform_admin", False):
                if shift.company_id != getattr(user, "company_id", None):
                    raise serializers.ValidationError(
                        {"shift": _("Not your company's shift.")}
                    )
                assert_user_branch(user, shift, "shift")
            if shift.status != CashShift.OPEN:
                raise serializers.ValidationError(
                    {"shift": _("That shift is closed — cash cannot move in or out of it.")}
                )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get("request")
        if request is not None and request.user.is_authenticated:
            validated_data.setdefault("recorded_by", request.user)
        movement = super().create(validated_data)
        if movement.kind == CashDrawerMovement.PETTY:
            # Money spent from the till is a running cost like any other: the
            # movement lowers the expected cash, this row reaches the income
            # statement and cash flow (which read expenses only). Both used to
            # miss it, overstating profit by every petty payment.
            from finance.models import Expense

            Expense.objects.create(
                company_id=movement.company_id, category=Expense.CATEGORY_PETTY_CASH,
                description=movement.reason or "", amount=-movement.amount,
                method=Expense.CASH, date=timezone.localdate(movement.recorded_at),
                recorded_by=movement.recorded_by, drawer_movement=movement,
            )
        return movement


class CashShiftSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    opened_by_name = serializers.SerializerMethodField()
    closed_by_name = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()
    cash_sales = serializers.SerializerMethodField()
    drawer_movements_total = serializers.SerializerMethodField()
    expected_cash = serializers.SerializerMethodField()
    variance = serializers.SerializerMethodField()
    late_cash = serializers.SerializerMethodField()
    drawer_movements = CashDrawerMovementSerializer(many=True, read_only=True)

    class Meta:
        model = CashShift
        fields = [
            "id", "branch", "status", "status_display",
            "opening_float", "opened_by_name", "opened_at",
            "counted_cash", "closed_by_name", "closed_at",
            "cash_sales", "drawer_movements_total", "expected_cash", "variance",
            "expected_at_close", "late_cash",
            "reviewed_by_name", "reviewed_at",
            "note", "drawer_movements", "client_uuid",
        ]
        # Everything about closing and review moves through the dedicated
        # actions; a direct write could set a count without stamping who did it.
        read_only_fields = [
            "status", "opened_at", "counted_cash", "closed_at", "reviewed_at",
            "expected_at_close",
        ]

    def validate(self, attrs):
        # A till session is a financial document: its branch must be one of
        # this company's branches, and a branch-scoped cashier can only open
        # a drawer at their own branch.
        request = self.context.get("request")
        user = getattr(request, "user", None)
        branch = attrs.get("branch")
        if user is not None and branch is not None:
            if branch.company_id != getattr(user, "company_id", None):
                raise serializers.ValidationError(
                    {"branch": _("Not your company's branch.")}
                )
            role = getattr(user, "role", None)
            if role and role.scope_level == "branch" and branch.pk != user.branch_id:
                raise serializers.ValidationError(
                    {"branch": _("A branch user can only open a drawer at their own branch.")}
                )
        return attrs

    def _person(self, user):
        return (user.full_name or user.email) if user else None

    def get_opened_by_name(self, obj):
        return self._person(obj.opened_by)

    def get_late_cash(self, obj):
        """Cash from offline sales that synced after this drawer was counted."""
        if obj.expected_at_close is None:
            return None
        late = obj.expected_cash() - obj.expected_at_close
        return str(late) if late else None

    def get_closed_by_name(self, obj):
        return self._person(obj.closed_by)

    def get_reviewed_by_name(self, obj):
        return self._person(obj.reviewed_by)

    def get_cash_sales(self, obj):
        return str(_q2(obj.cash_sales()))

    def get_drawer_movements_total(self, obj):
        return str(_q2(obj.drawer_movements_total()))

    def get_expected_cash(self, obj):
        return str(_q2(obj.expected_cash()))

    def get_variance(self, obj):
        v = obj.variance()
        return None if v is None else str(_q2(v))

    def create(self, validated_data):
        # The holder of the drawer is always the caller — accepting it from the
        # body would let one person open a shift in someone else's name, which
        # is exactly the attribution this model exists to guarantee.
        request = self.context.get("request")
        if request is not None and request.user.is_authenticated:
            validated_data["opened_by"] = request.user
        return super().create(validated_data)


class POSCheckoutSerializer(serializers.Serializer):
    """
    One transactional, idempotent, offline-capable checkout. Creates the
    invoice (+lines), the sale_out stock movements, and an optional manual
    payment atomically. Re-sending the same `client_uuid` returns the already
    created invoice instead of ringing the sale up twice (Rule #2).
    """

    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(), required=False, allow_null=True
    )
    branch = serializers.IntegerField(required=False, allow_null=True)
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    currency = serializers.CharField(required=False)
    exchange_rate = serializers.DecimalField(
        max_digits=14, decimal_places=6, required=False, min_value=Decimal("0.000001")
    )
    client_uuid = serializers.UUIDField(required=False, allow_null=True)
    # The flat rate the till computed its receipt with. A till that stayed
    # offline keeps the rate it had when it last reached the server; if the
    # owner changed it meanwhile, the customer still paid the old one.
    tax_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, allow_null=True,
        min_value=Decimal("0"), max_value=Decimal("100"),
    )
    # Optional override; otherwise the customer's terms, else the company's.
    payment_terms_days = serializers.IntegerField(required=False, min_value=0)
    # Invoicing a confirmed sales order: the invoice links back to it and
    # the order is fulfilled in the same transaction.
    source_order = serializers.PrimaryKeyRelatedField(
        queryset=SalesOrder.objects.all(), required=False, allow_null=True
    )
    # The till session this sale was rung under. Sent by the client rather than
    # inferred from the clock, because an offline sale can sync long after its
    # shift closed and must still land in the drawer that actually took the cash.
    shift = serializers.PrimaryKeyRelatedField(
        queryset=CashShift.objects.all(), required=False, allow_null=True
    )
    lines = POSLineSerializer(many=True)
    payment = POSPaymentSerializer(required=False, allow_null=True)
    # A split tender: part cash, part Bankak (or two transfers). Each entry
    # is recorded as its own payment; `payment` stays for older clients and
    # queued sales. See _payments_of().
    payments = POSPaymentSerializer(many=True, required=False)
    # Store credit spent on this sale, alongside (or instead of) money.
    apply_credit = POSApplyCreditSerializer(required=False, allow_null=True)
    # A discount on the whole ticket, spread across lines in proportion to
    # their net value so per-line tax and per-line returns stay exact.
    discount_amount = serializers.DecimalField(
        max_digits=16, decimal_places=2, required=False, min_value=Decimal("0")
    )
    # When the sale actually happened at the till. Absent (older clients) it
    # is the server clock, which is only right for an online sale.
    occurred_at = serializers.DateTimeField(required=False, allow_null=True)
    local_reference = serializers.CharField(required=False, allow_blank=True, max_length=48)

    def validate_occurred_at(self, value):
        return validate_business_time(value)

    def validate_lines(self, lines):
        if not lines:
            raise serializers.ValidationError(_("At least one line is required."))
        return lines

    def _assert_company(self, obj, company_id, label):
        if obj is not None and obj.company_id != company_id:
            raise serializers.ValidationError({label: _("Not your company's record.")})

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        user = request.user
        company_id = getattr(user, "company_id", None)
        if company_id is None:
            raise serializers.ValidationError(_("A company-scoped user is required."))

        # Company checks on referenced objects.
        self._assert_company(validated_data.get("customer"), company_id, "customer")
        warehouse = validated_data["warehouse"]
        self._assert_company(warehouse, company_id, "warehouse")
        assert_user_branch(user, warehouse, "warehouse")
        branch_id = validated_data.get("branch")
        role = getattr(user, "role", None)
        user_branch_id = getattr(user, "branch_id", None)
        if role and role.scope_level == "branch" and branch_id is None:
            branch_id = user_branch_id
            validated_data["branch"] = branch_id
        if branch_id is None and warehouse.branch_id is not None:
            # An owner or GM selling from a branch's store: the sale belongs
            # to that branch, or every branch report misses it.
            branch_id = warehouse.branch_id
            validated_data["branch"] = branch_id
        if branch_id is not None:
            from org.models import Branch
            if not Branch.objects.filter(pk=branch_id, company_id=company_id).exists():
                raise serializers.ValidationError(
                    {"branch": _("Not your company's branch.")}
                )
            if role and role.scope_level == "branch" and user_branch_id != branch_id:
                raise serializers.ValidationError(
                    {"branch": _("A branch user can only sell from their own branch.")}
                )
        for ln in validated_data["lines"]:
            self._assert_company(ln["product"], company_id, "product")
            product = ln["product"]
            if not product.is_active:
                if not self.context.get("via_sync"):
                    # Archived means no longer sold: the till's catalogue was
                    # stale, and the cashier can take it off the ticket now.
                    raise serializers.ValidationError({"lines": _(
                        "%(sku)s (%(name)s) is archived and no longer sold; remove it "
                        "from the sale or restore the product."
                    ) % {"sku": product.sku, "name": product.name}})
                # Sold offline before the archive reached the till: the
                # goods left with the customer. Keep the sale; tell the
                # manager.
                log_activity(
                    action="sold_archived_product", request=self.context.get("request"),
                    entity_type="Product", entity_id=product.pk,
                    metadata={"via": "sync", "sku": product.sku},
                )

        from org.models import Company
        company = Company.objects.get(pk=company_id)
        rate = _company_tax_rate(company)
        handler = tax_handler_for(company)
        rate_override = None
        till_rate = validated_data.get("tax_rate")
        if till_rate is not None and till_rate != rate:
            if not self.context.get("via_sync"):
                # Live at the counter: the cashier can reload and charge the
                # right amount before the customer leaves.
                raise serializers.ValidationError({"tax_rate": _(
                    "The tax rate changed to %(rate)s%%. Reload the page, then ring the sale again."
                ) % {"rate": rate}})
            # Replayed from the offline queue: the sale already happened at
            # the till's rate, and that is what the customer paid. Record it
            # as it was — a refusal here lost the whole paid sale — and leave
            # an audit row so the difference is visible. But only a rate the
            # company really had while the till could have been offline: any
            # other figure is not a stale till, it is a made-up tax.
            from org.models import tax_rate_was_in_effect

            if not tax_rate_was_in_effect(company.pk, till_rate, validated_data.get("occurred_at")):
                raise serializers.ValidationError({"tax_rate": _(
                    "The till charged %(till)s%% tax, a rate this company did not have when "
                    "the sale was made (%(rate)s%% now). A manager must record this sale by "
                    "hand."
                ) % {"till": till_rate, "rate": rate}})
            log_activity(
                action="tax_rate_mismatch", request=self.context.get("request"),
                entity_type="Company", entity_id=company.pk,
                metadata={"till_rate": str(till_rate), "company_rate": str(rate)},
            )
            rate = rate_override = till_rate

        # Reports sum invoice totals per company without converting, so a
        # foreign-currency invoice would silently corrupt every figure. Until
        # multi-currency reporting exists, a sale is in the company currency.
        currency = validated_data.get("currency") or company.currency
        if currency != company.currency:
            raise serializers.ValidationError(
                {
                    "currency": (
                        _("Sales are recorded in the company currency (%(currency)s).")
                        % {"currency": company.currency}
                    )
                }
            )

        from django.utils import timezone
        occurred_at = validated_data.get("occurred_at") or timezone.now()

        source_order = validated_data.get("source_order")
        if source_order is not None:
            self._assert_company(source_order, company_id, "source_order")
            # Locked: two tills (or a till and a web-order confirmation) could
            # each invoice the same order and take its stock twice.
            source_order = SalesOrder.objects.select_for_update().get(pk=source_order.pk)
            if source_order.status != SalesOrder.CONFIRMED:
                if self.context.get("via_sync"):
                    # Sold offline against an order that was cancelled or
                    # invoiced meanwhile: the sale happened; keep it, without
                    # the order, and tell the manager.
                    log_activity(
                        action="sale_order_link_dropped", request=self.context.get("request"),
                        entity_type="SalesOrder", entity_id=source_order.pk,
                        metadata={"status": source_order.status},
                    )
                    source_order = None
                else:
                    raise serializers.ValidationError(
                        {"source_order": _("Only a confirmed sales order can be invoiced.")}
                    )
        if source_order is not None:
            sale_customer_id = getattr(validated_data.get("customer"), "pk", None)
            if source_order.customer_id != sale_customer_id:
                raise serializers.ValidationError(
                    {"source_order": _("The sale's customer must match the order's customer.")}
                )
            # The sale closes the order, so it must deliver what was ordered:
            # an order for 5 x 100 invoiced as 1 x 1.00 was marked fulfilled.
            sold = defaultdict(Decimal)
            for ln in validated_data["lines"]:
                pack = ln.get("pack")
                sold[ln["product"].pk] += ln["quantity"] * (pack.quantity if pack else 1)
            short = [
                line.product.sku for line in source_order.lines.select_related("product")
                if line.product_id and sold[line.product_id] < line.quantity
            ]
            if short:
                raise serializers.ValidationError({"source_order": _(
                    "The sale does not deliver the whole order (%(skus)s). "
                    "Sell the ordered quantities, or edit the order first."
                ) % {"skus": ", ".join(short[:5])}})

        number = allocate_invoice_number(company_id)
        terms = validated_data.get("payment_terms_days")
        if terms is None:
            sale_customer = validated_data.get("customer")
            terms = (
                sale_customer.effective_payment_terms_days()
                if sale_customer is not None
                else company.default_payment_terms_days
            )
        invoice = create_with_local_reference(
            request,
            validated_data.get("local_reference", ""),
            dict(
                company_id=company_id,
                customer=validated_data.get("customer"),
                branch_id=validated_data.get("branch"),
                warehouse=warehouse,
                number=number,
                currency=currency,
                exchange_rate=validated_data.get("exchange_rate", Decimal("1")),
                tax_rate_snapshot=rate,
                created_by=user if user.is_authenticated else None,
                client_uuid=validated_data.get("client_uuid"),
                issued_at=occurred_at,
                payment_terms_days=terms,
                source_order=source_order,
            ),
        )
        if source_order is not None:
            source_order.status = SalesOrder.FULFILLED
            source_order.save(update_fields=["status"])

        # Pass 1: gross and own-discount per line, so the ticket discount
        # can be allocated before anything is written.
        priced = []
        for ln in validated_data["lines"]:
            product = ln["product"]
            pack = ln.get("pack")
            if pack is not None:
                self._assert_company(pack, company_id, "pack")
                if pack.product_id != product.pk:
                    raise serializers.ValidationError(
                        {"pack": _("That pack belongs to a different product.")}
                    )
                if not pack.is_active:
                    raise serializers.ValidationError({"pack": _("That pack is no longer sold.")})
                packs_sold = ln["quantity"]
                pack_price = ln.get("unit_price")
                if pack_price is None:
                    pack_price = pack.effective_price()
                # Base units and an equivalent base unit price, so every
                # downstream figure (ledger, returns, reports) stays in one unit.
                qty = packs_sold * pack.quantity
                price = (pack_price / pack.quantity).quantize(Decimal("0.01"))
                ln["_pack"] = (pack, packs_sold)
                gross = _q2(packs_sold * pack_price)
            else:
                qty = ln["quantity"]
                price = ln.get("unit_price")
                if price is None:
                    price = product.sale_price
                gross = _q2(qty * price)
            if ln.get("discount_percent") is not None:
                own = _q2(gross * ln["discount_percent"] / 100)
            else:
                own = _q2(ln.get("discount_amount") or 0)
            if own > gross:
                raise serializers.ValidationError(
                    {
                        "lines": _("Discount on %(sku)s exceeds the line value.")
                        % {"sku": product.sku}
                    }
                )
            priced.append([ln, product, qty, price, gross, own])
        ticket_discount = _q2(validated_data.get("discount_amount") or 0)
        net_base = sum((row[4] - row[5] for row in priced), Decimal("0"))
        if ticket_discount > net_base:
            raise serializers.ValidationError(
                {"discount_amount": _("The ticket discount exceeds the sale value.")}
            )
        # Allocate proportionally; the last line absorbs rounding so the
        # allocated parts sum exactly to the ticket discount.
        allocated = Decimal("0")
        for index, row in enumerate(priced):
            net = row[4] - row[5]
            if index == len(priced) - 1:
                share = ticket_discount - allocated
            elif net_base > 0:
                share = _q2(ticket_discount * net / net_base)
            else:
                share = Decimal("0")
            allocated += share
            row.append(share)
        self._enforce_price_rules(priced, company, user, invoice)

        subtotal = Decimal("0")
        tax_total = Decimal("0")
        discount_total = Decimal("0")
        for ln, product, qty, price, gross, own, share in priced:
            discount = own + share
            line_subtotal = gross - discount
            line_tax = (
                handler.compute_tax(line_subtotal, product) if rate_override is None
                else (line_subtotal * rate_override / Decimal("100")).quantize(Decimal("0.01"))
            )
            pack_info = ln.get("_pack")
            InvoiceLine.objects.create(
                invoice=invoice, product=product,
                description=ln.get("description", ""),
                quantity=qty, unit_price=price, discount_amount=discount, tax_rate=rate,
                line_subtotal=line_subtotal, line_tax=line_tax,
                line_total=line_subtotal + line_tax,
                **(
                    {
                        "pack": pack_info[0], "pack_name": pack_info[0].name,
                        "pack_quantity": pack_info[0].quantity, "packs_sold": pack_info[1],
                    }
                    if pack_info else {}
                ),
            )
            subtotal += line_subtotal
            tax_total += line_tax
            discount_total += discount
            # sale_out movement (negative) — offline-first: we record the sale
            # even if it drives stock negative; reconciliation is a later step.
            # Skipped for non-stock lines (a bag, a delivery charge, the
            # miscellaneous catch-all): there is no inventory behind them, so a
            # movement would only invent a deficit.
            if product.is_stock_tracked:
                # Batch-tracked products leave lot by lot (FEFO, or the lot
                # the cashier scanned) so batch balances and the expiry
                # report stay true; everything else is one movement.
                preferred = ln.get("batch")
                if preferred is not None:
                    self._assert_company(preferred, company_id, "batch")
                    if preferred.product_id != product.pk:
                        raise serializers.ValidationError(
                            {"batch": _("That lot belongs to a different product.")}
                        )
                if product.track_batches:
                    from inventory.fefo import allocate_fefo
                    plan = allocate_fefo(
                        product, warehouse, qty, preferred_batch=preferred, as_of=occurred_at
                    )
                else:
                    plan = [(None, qty)]
                for batch, part in plan:
                    StockMovement.objects.create(
                        company_id=company_id, product=product, warehouse=warehouse,
                        batch=batch,
                        movement_type=StockMovement.SALE_OUT, quantity=-part,
                        # Snapshot the cost at the moment of sale so
                        # standard-cost COGS is reproducible; re-pricing a
                        # product later must not rewrite last quarter's margin.
                        unit_cost=product.cost_price,
                        reference_type="Invoice", reference_id=str(invoice.id),
                        created_by=user if user.is_authenticated else None,
                        created_at=occurred_at,
                    )

        invoice.subtotal = _q2(subtotal)
        invoice.discount_total = _q2(discount_total)
        invoice.tax_amount = _q2(tax_total)
        invoice.total = invoice.subtotal + invoice.tax_amount
        invoice.save(update_fields=["subtotal", "discount_total", "tax_amount", "total"])

        tenders = self._payments_of(validated_data)
        paid_now = sum((tender["amount"] for tender in tenders), Decimal("0"))
        applied = validated_data.get("apply_credit")
        credit_used = Decimal("0")
        if applied:
            from returns.models import CreditNote

            note = CreditNote.objects.select_for_update().filter(
                pk=applied["credit_note"], company_id=company_id
            ).first()
            credit_used = min(applied["amount"], invoice.total)
            assert_store_credit(note, invoice, credit_used, company_id)
            if paid_now + credit_used > invoice.total:
                raise serializers.ValidationError(
                    {"payment": _("Credit plus payment exceed the invoice total.")}
                )
            Payment.objects.create(
                company_id=company_id, invoice=invoice, method=Payment.STORE_CREDIT,
                credit_note=note, amount=credit_used,
                currency=invoice.currency, exchange_rate=invoice.exchange_rate,
                recorded_by=user if user.is_authenticated else None,
                recorded_at=occurred_at,
            )
        self._assert_credit_allowed(
            validated_data.get("customer"), invoice, invoice.total - paid_now - credit_used, user
        )
        for pay in tenders:
            payment = self._record_payment(
                invoice, pay, company_id, user, validated_data.get("shift"), occurred_at
            )
            log_activity(
                action="create", request=request, entity_type="Payment",
                entity_id=payment.pk,
                metadata={"invoice": invoice.pk, "amount": str(payment.amount)},
            )
        movement_ids = list(
            StockMovement.objects.filter(
                reference_type="Invoice", reference_id=str(invoice.pk)
            ).values_list("pk", flat=True)
        )
        if movement_ids:
            log_activity(
                action="create", request=request, entity_type="StockMovement",
                entity_id=movement_ids[0],
                metadata={"invoice": invoice.pk, "movements": movement_ids},
            )

        return invoice

    @staticmethod
    def _payments_of(validated_data):
        """The tenders of this sale: `payments` (a split) or the single
        `payment`. Nothing tendered is a credit sale, not a payment of zero:
        a 0.00 row would sit in the verification worklist, the ledger and the
        customer's statement as money that never moved. Each tender is then
        checked against what is still due as it is recorded, so a transfer
        above the balance is refused (record_payment), never capped."""
        tenders = list(validated_data.get("payments") or [])
        if validated_data.get("payment"):
            tenders.insert(0, validated_data["payment"])
        return [tender for tender in tenders if tender["amount"] > 0]

    def _enforce_price_rules(self, priced, company, user, invoice):
        """No line below cost, no discount above the company's limit — unless
        an approver rings the sale (see Company.max_discount_percent).

        The list price is always allowed, even when it sits under a cost that
        rose since: that price is the owner's decision, not the cashier's.
        At the counter a cashier is refused with the reason; an approver's
        override is written to the audit log. A sale replayed from the
        offline queue already happened, so it is kept and the audit row is
        flagged for a manager to review.

        A price typed under the list price is a discount too: what counts is
        how far the net price (after line and ticket discounts) sits below
        the list price of the product or pack. Otherwise a cashier could ring
        rice listed at 100 as 85 and give 15% where 10% is the limit. A line
        invoiced from a sales order is measured against the order's price
        when that is lower and the order's price is trusted — the price the
        customer was quoted (see _order_prices). The rule itself lives in
        sales.price_rules, shared with quotations and sales orders."""
        limit = company.max_discount_percent
        ordered = self._order_prices(invoice)
        rows = []
        for ln, product, qty, price, gross, own, share in priced:
            pack_info = ln.get("_pack")
            cost = product.cost_price or Decimal("0")
            agreed = ordered.get(product.pk)
            if pack_info:
                pack, units = pack_info
                unit_value = gross / units
                floor = _q2(cost * pack.quantity)
                listed = pack.effective_price()
                reference = listed if agreed is None else min(
                    listed, _q2(agreed * pack.quantity)
                )
            else:
                units = qty
                unit_value, floor, listed = price, cost, product.sale_price or Decimal("0")
                reference = listed if agreed is None else min(listed, agreed)
            rows.append({
                "sku": product.sku, "cost": cost, "units": units, "unit_value": unit_value,
                "floor": floor, "listed": listed, "reference": reference,
                "gross": gross, "discount": own + share,
            })
        breaches = price_breaches(rows, limit)
        if not breaches:
            return
        request = self.context.get("request")
        if can_approve_high_value(user):
            log_activity(
                action="pos_price_override", request=request,
                entity_type="Invoice", entity_id=invoice.pk,
                metadata={"breaches": breaches, "limit": str(limit)},
            )
            return
        if self.context.get("via_sync"):
            log_activity(
                action="pos_price_unapproved", request=request,
                entity_type="Invoice", entity_id=invoice.pk,
                metadata={
                    "breaches": breaches, "limit": str(limit), "via": "sync",
                    "needs_review": True,
                },
            )
            return
        refuse_price(breaches, limit)

    @staticmethod
    def _order_prices(invoice):
        """{product id: lowest unit price} on the sales order this sale
        invoices, or {} for a plain counter sale.

        Only an order whose prices are trusted counts: one an approver
        priced past the rule, or one never measured by it (created before
        the rule, or a web order at the owner's own prices). An order a
        salesperson priced within the limit is measured from the list price
        again, so a discount at the till cannot stack on the order's."""
        if not invoice.source_order_id:
            return {}
        if not invoice.source_order.prices_trusted:
            return {}
        prices = {}
        for product_id, unit_price in SalesOrderLine.objects.filter(
            sales_order_id=invoice.source_order_id
        ).values_list("product_id", "unit_price"):
            if product_id in prices:
                prices[product_id] = min(prices[product_id], unit_price)
            else:
                prices[product_id] = unit_price
        return prices

    def _assert_credit_allowed(self, customer, invoice, unpaid, user):
        """A sale that leaves a balance is a loan, and a loan needs a debtor.

        Anonymous credit produced receivables nobody owed that the debt ledger
        could not even list. A named customer on hold gets nothing on account;
        one with a limit may not pass it, unless a manager overrides — and the
        override is written to the audit trail. Runs inside the checkout
        transaction, so a refusal rolls the invoice back."""
        if unpaid <= 0:
            return
        if customer is None:
            raise serializers.ValidationError(
                {"customer": _("A sale on account needs a named customer.")}
            )
        if customer.credit_hold:
            raise serializers.ValidationError(
                {"customer": _("This customer's account is on hold; take full payment.")}
            )
        if customer.credit_limit is not None:
            # The invoice row already exists at this point (payment not yet),
            # so the customer's balance includes this sale's full total; take
            # that out and add back only what stays unpaid.
            exposure = customer.ar_balance() - invoice.total + unpaid
            if exposure > customer.credit_limit:
                if not can_approve_high_value(user):
                    raise serializers.ValidationError(
                        {
                            "customer": (
                                _("This sale would take the customer to %(exposure)s, above "
                                  "their credit limit of %(limit)s.")
                                % {"exposure": exposure, "limit": customer.credit_limit}
                            )
                        }
                    )
                log_activity(
                    action="credit_limit_override", request=self.context["request"],
                    entity_type="Customer", entity_id=customer.pk,
                    metadata={"exposure": str(exposure), "limit": str(customer.credit_limit)},
                )

    def _record_payment(self, invoice, pay, company_id, user, shift=None, occurred_at=None):
        if shift is not None:
            self._assert_company(shift, company_id, "shift")
            # The drawer is the holder's: counting a sale into someone
            # else's shift makes one count over and the other short.
            if shift.opened_by_id != getattr(user, "pk", None) and not can_approve_high_value(user):
                raise serializers.ValidationError(
                    {"shift": _("That till session belongs to another cashier.")}
                )
            if shift.status != CashShift.OPEN and not rung_while_open(shift, occurred_at):
                if not self.context.get("via_sync"):
                    raise serializers.ValidationError(
                        {"shift": _("That till session is closed — open a new one.")}
                    )
                # Replayed from a device that still believed this drawer was
                # open (it was closed elsewhere while the device was offline).
                # The sale happened and was paid; keep it, outside any drawer,
                # and leave an audit row for the manager instead of refusing
                # it for ever.
                log_activity(
                    action="sale_outside_closed_shift", request=self.context.get("request"),
                    entity_type="Invoice", entity_id=invoice.pk,
                    metadata={"shift": shift.pk, "occurred_at": str(occurred_at)},
                )
                shift = None
        if pay["amount"] > invoice.total:
            raise serializers.ValidationError(
                {
                    "payment": (
                        _("Payment exceeds the invoice total (tax included). "
                          "Give change instead of overpaying.")
                    )
                }
            )
        from sales.payments import record_payment

        ba = pay.get("company_bank_account")
        if ba is not None:
            self._assert_company(ba, company_id, "company_bank_account")
        return record_payment(
            invoice, amount=pay["amount"], method=pay["method"],
            recorded_by=user if user.is_authenticated else None,
            company_bank_account=ba, sender_bank_name=pay.get("sender_bank_name", ""),
            reference_last4=pay.get("reference_last4", ""),
            transfer_reference=pay.get("transfer_reference", ""),
            shift=shift, recorded_at=occurred_at,
        )

    def to_representation(self, instance):
        return InvoiceSerializer(instance, context=self.context).data


# ---------- Refund (money back against a Credit Note) ----------

class RefundSerializer(serializers.ModelSerializer):
    credit_note_number = serializers.CharField(
        source="credit_note.number_display", read_only=True
    )
    invoice = serializers.IntegerField(source="credit_note.invoice_id", read_only=True)
    customer_name = serializers.CharField(
        source="credit_note.customer.name", read_only=True, default=None
    )
    recorded_by_name = serializers.CharField(
        source="recorded_by.full_name", read_only=True, default=None
    )
    bank_account_name = serializers.CharField(
        source="company_bank_account.bank_name", read_only=True, default=None
    )

    class Meta:
        model = Refund
        fields = [
            "id", "company", "credit_note", "credit_note_number", "invoice",
            "customer_name", "method", "company_bank_account", "bank_account_name",
            "reference_last4", "amount", "shift", "note", "recorded_by",
            "recorded_by_name", "recorded_at", "received_at", "client_uuid",
        ]
        read_only_fields = ["company", "recorded_by", "received_at"]
        extra_kwargs = {"recorded_at": {"required": False}}

    def validate_recorded_at(self, value):
        return validate_business_time(value)

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        company_id = getattr(user, "company_id", None)
        amount = attrs.get("amount")
        if amount is None or amount <= 0:
            raise serializers.ValidationError({"amount": _("Amount must be positive.")})
        note = attrs["credit_note"]
        if note.company_id != company_id:
            raise serializers.ValidationError({"credit_note": _("Not your company's credit note.")})
        if note.is_void:
            raise serializers.ValidationError({"credit_note": _("That credit note is void.")})
        if note.invoice_id:
            assert_user_branch(user, note.invoice, "credit_note")
        method = attrs.get("method")
        ba = attrs.get("company_bank_account")
        ref = attrs.get("reference_last4", "")
        if method == Refund.BANK_TRANSFER:
            if ba is None:
                raise serializers.ValidationError(
                    {"company_bank_account": _("A bank refund needs the paying account.")}
                )
            if ba.company_id != company_id:
                raise serializers.ValidationError(
                    {"company_bank_account": _("Not your company's bank account.")}
                )
            if not ref or not ref.isdigit() or len(ref) > 4:
                raise serializers.ValidationError(
                    {"reference_last4": _("Enter up to 4 reference digits.")}
                )
        elif method == Refund.CASH and (ba or ref):
            raise serializers.ValidationError(
                _("A cash refund must not carry bank or reference details.")
            )
        shift = attrs.get("shift")
        if shift is not None:
            if shift.company_id != company_id:
                raise serializers.ValidationError({"shift": _("Not your company's till session.")})
            if shift.opened_by_id != user.pk and not can_approve_high_value(user):
                raise serializers.ValidationError(
                    {"shift": _("You can only refund cash from your own open drawer.")}
                )
            if shift.status != CashShift.OPEN and not rung_while_open(
                shift, attrs.get("recorded_at")
            ):
                if not self.context.get("via_sync"):
                    raise serializers.ValidationError(
                        {"shift": _("That till session is closed.")}
                    )
                # Handed back offline, reported after the drawer closed: the
                # cash left. Kept, like the sale it reverses would be.
                attrs["shift"] = late_money_shift(self, shift, attrs.get("recorded_at"), "Refund")
        elif method == Refund.CASH:
            raise serializers.ValidationError(
                {"shift": _("A cash refund must come out of an open till session.")}
            )
        threshold = getattr(note.company, "payment_approval_threshold", 0) or 0
        if threshold and amount >= threshold and not can_approve_high_value(user):
            raise serializers.ValidationError(
                {
                    "amount": _("Refunds of %(threshold)s or more need a manager or owner.")
                    % {"threshold": threshold}
                }
            )
        return attrs

    def create(self, validated_data):
        from returns.models import CreditNote

        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data.setdefault("recorded_by", request.user)
        with transaction.atomic():
            # The invoice first, then the note — the order record_payment
            # uses too. What may be refunded depends on the whole invoice
            # (what was paid, what other notes already handed back), so two
            # notes on one partly-paid invoice refunded at the same moment
            # each passed the check under a lock on their own note only.
            invoice_id = validated_data["credit_note"].invoice_id
            if invoice_id:
                Invoice.objects.select_for_update().get(pk=invoice_id)
            note = CreditNote.objects.select_for_update().get(
                pk=validated_data["credit_note"].pk
            )
            remaining = note.remaining_refundable()
            if validated_data["amount"] > remaining:
                if remaining <= 0 and note.invoice_id:
                    raise serializers.ValidationError(
                        {
                            "amount": _(
                                "%(note)s settled what was still owed on the invoice; "
                                "no money was paid that could be handed back."
                            ) % {"note": note.number_display}
                        }
                    )
                raise serializers.ValidationError(
                    {
                        "amount": _("Only %(remaining)s remains refundable on %(note)s.")
                        % {"remaining": remaining, "note": note.number_display}
                    }
                )
            validated_data["credit_note"] = note
            refund = super().create(validated_data)
            if refund.method == Refund.CASH and refund.shift_id:
                CashDrawerMovement.objects.create(
                    company_id=refund.company_id, shift_id=refund.shift_id,
                    kind=CashDrawerMovement.REFUND, amount=-refund.amount,
                    reason=refund.note or f"Refund {note.number_display}",
                    recorded_by=refund.recorded_by, refund=refund,
                )
            if note.invoice_id:
                Invoice.objects.filter(pk=note.invoice_id).update(updated_at=refund.recorded_at)
            if request is not None:
                log_activity(
                    action="create", request=request, entity_type="Refund",
                    entity_id=refund.pk,
                    metadata={"credit_note": note.pk, "amount": str(refund.amount)},
                )
        return refund
