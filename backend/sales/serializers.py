from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from inventory.models import Product, StockMovement, Warehouse
from sales.models import (
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

TWO_PLACES = Decimal("0.01")


def _q2(value):
    return Decimal(value).quantize(TWO_PLACES)


def _company_tax_rate(company):
    """Flat rate from the company's TaxProfile (Rule #7) — never hardcoded."""
    profile = getattr(company, "tax_profile", None)
    return profile.flat_tax_rate if profile else Decimal("0")


class CustomerSerializer(serializers.ModelSerializer):
    ar_balance = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            "id", "company", "name", "phone", "email", "address",
            "is_active", "ar_balance",
        ]
        read_only_fields = ["company"]

    def get_ar_balance(self, obj):
        return obj.ar_balance()


class CompanyBankAccountSerializer(serializers.ModelSerializer):
    # Derived, never stored — see CompanyBankAccount.balance().
    balance = serializers.SerializerMethodField()
    received_total = serializers.SerializerMethodField()
    paid_total = serializers.SerializerMethodField()

    class Meta:
        model = CompanyBankAccount
        fields = [
            "id", "company", "bank_name", "account_name",
            "account_number", "opening_balance", "is_active",
            "balance", "received_total", "paid_total",
        ]
        read_only_fields = ["company"]

    def get_balance(self, obj):
        return str(obj.balance())

    def get_received_total(self, obj):
        return str(obj.received_total())

    def get_paid_total(self, obj):
        return str(obj.paid_total())


# ---------- Quotation ----------

class QuotationLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuotationLine
        fields = ["id", "product", "description", "quantity", "unit_price", "line_total"]
        read_only_fields = ["line_total"]


class QuotationSerializer(serializers.ModelSerializer):
    lines = QuotationLineSerializer(many=True)

    class Meta:
        model = Quotation
        fields = [
            "id", "company", "customer", "branch", "status", "valid_until",
            "note", "subtotal", "tax_amount", "total", "lines", "created_at",
        ]
        read_only_fields = ["company", "subtotal", "tax_amount", "total", "created_at"]

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines")
        company_id = validated_data.get("company_id")
        rate = _company_tax_rate_by_id(company_id)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        quotation = Quotation.objects.create(**validated_data)
        subtotal = Decimal("0")
        for line in lines:
            lt = _q2(line["quantity"] * line["unit_price"])
            QuotationLine.objects.create(quotation=quotation, line_total=lt, **line)
            subtotal += lt
        quotation.subtotal = _q2(subtotal)
        quotation.tax_amount = _q2(subtotal * rate / 100)
        quotation.total = quotation.subtotal + quotation.tax_amount
        quotation.save(update_fields=["subtotal", "tax_amount", "total"])
        return quotation


def _company_tax_rate_by_id(company_id):
    from org.models import Company
    try:
        return _company_tax_rate(Company.objects.get(pk=company_id))
    except Company.DoesNotExist:
        return Decimal("0")


# ---------- Sales Order ----------

class SalesOrderLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesOrderLine
        fields = ["id", "product", "description", "quantity", "unit_price", "line_total"]
        read_only_fields = ["line_total"]


class SalesOrderSerializer(serializers.ModelSerializer):
    lines = SalesOrderLineSerializer(many=True)

    class Meta:
        model = SalesOrder
        fields = [
            "id", "company", "customer", "branch", "source_quotation", "status",
            "subtotal", "tax_amount", "total", "lines", "created_at",
        ]
        read_only_fields = ["company", "subtotal", "tax_amount", "total", "created_at"]

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines")
        company_id = validated_data.get("company_id")
        rate = _company_tax_rate_by_id(company_id)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        order = SalesOrder.objects.create(**validated_data)
        subtotal = Decimal("0")
        for line in lines:
            lt = _q2(line["quantity"] * line["unit_price"])
            SalesOrderLine.objects.create(sales_order=order, line_total=lt, **line)
            subtotal += lt
        order.subtotal = _q2(subtotal)
        order.tax_amount = _q2(subtotal * rate / 100)
        order.total = order.subtotal + order.tax_amount
        order.save(update_fields=["subtotal", "tax_amount", "total"])
        return order


# ---------- Invoice (read) ----------

class InvoiceLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLine
        fields = [
            "id", "product", "description", "quantity", "unit_price",
            "tax_rate", "line_subtotal", "line_tax", "line_total",
        ]


class InvoiceSerializer(serializers.ModelSerializer):
    lines = InvoiceLineSerializer(many=True, read_only=True)
    number_display = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    amount_paid = serializers.SerializerMethodField()
    amount_due = serializers.SerializerMethodField()
    days_overdue = serializers.IntegerField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id", "company", "customer", "branch", "warehouse", "number",
            "number_display", "currency", "exchange_rate", "tax_rate_snapshot",
            "subtotal", "tax_amount", "total", "is_void", "status",
            "amount_paid", "amount_due", "lines", "client_uuid", "issued_at",
            "payment_terms_days", "due_date", "days_overdue", "is_overdue",
        ]
        read_only_fields = ["due_date"]

    def get_amount_paid(self, obj):
        return obj.amount_paid()

    def get_amount_due(self, obj):
        return obj.amount_due()


# ---------- Payment (Rule #3) ----------

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id", "company", "invoice", "method", "company_bank_account",
            "sender_bank_name", "reference_last4", "amount", "recorded_by",
            "recorded_at", "verified_at", "verified_by", "client_uuid",
        ]
        read_only_fields = [
            "company", "recorded_by", "recorded_at", "verified_at", "verified_by",
        ]

    def validate(self, attrs):
        method = attrs.get("method")
        amount = attrs.get("amount")
        if amount is None or amount <= 0:
            raise serializers.ValidationError("Amount must be positive.")

        bank_account = attrs.get("company_bank_account")
        sender = attrs.get("sender_bank_name", "")
        ref = attrs.get("reference_last4", "")

        if method == Payment.BANK_TRANSFER:
            if bank_account is None:
                raise serializers.ValidationError(
                    "Bank transfer requires the receiving company bank account."
                )
            if not sender:
                raise serializers.ValidationError(
                    "Bank transfer requires the sender's bank name."
                )
            if not ref or not ref.isdigit() or len(ref) > 4:
                raise serializers.ValidationError(
                    "reference_last4 must be up to 4 digits."
                )
        elif method == Payment.CASH:
            if bank_account or sender or ref:
                raise serializers.ValidationError(
                    "Cash payments must not carry bank/reference details."
                )

        self._check_company(attrs)
        return attrs

    def _check_company(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None or getattr(user, "is_platform_admin", False):
            return
        company_id = getattr(user, "company_id", None)
        invoice = attrs.get("invoice")
        if invoice is not None and invoice.company_id != company_id:
            raise serializers.ValidationError({"invoice": "Not your company's invoice."})
        ba = attrs.get("company_bank_account")
        if ba is not None and ba.company_id != company_id:
            raise serializers.ValidationError(
                {"company_bank_account": "Not your company's bank account."}
            )

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data.setdefault("recorded_by", request.user)
        return super().create(validated_data)


# ---------- POS checkout ----------

class POSLineSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.DecimalField(max_digits=16, decimal_places=3, min_value=Decimal("0.001"))
    unit_price = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False
    )
    description = serializers.CharField(required=False, allow_blank=True)


class POSPaymentSerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=Payment.METHOD_CHOICES)
    company_bank_account = serializers.PrimaryKeyRelatedField(
        queryset=CompanyBankAccount.objects.all(), required=False, allow_null=True
    )
    sender_bank_name = serializers.CharField(required=False, allow_blank=True)
    reference_last4 = serializers.CharField(required=False, allow_blank=True)
    amount = serializers.DecimalField(max_digits=16, decimal_places=2)


class CashDrawerMovementSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    recorded_by_name = serializers.CharField(
        source="recorded_by.full_name", read_only=True, default=None
    )

    class Meta:
        model = CashDrawerMovement
        fields = [
            "id", "shift", "kind", "kind_display", "amount", "reason",
            "recorded_by_name", "recorded_at", "client_uuid",
        ]
        read_only_fields = ["recorded_at"]

    def validate(self, attrs):
        kind = attrs.get("kind")
        amount = attrs.get("amount")
        if amount is None or amount == 0:
            raise serializers.ValidationError("Amount must not be zero.")
        # The sign carries the meaning, so a typo must not turn a refund into a
        # deposit and quietly hide a shortfall.
        if kind in CashDrawerMovement.NEGATIVE_ONLY and amount > 0:
            raise serializers.ValidationError(
                {"amount": f"A '{kind}' takes money out — the amount must be negative."}
            )
        if kind in CashDrawerMovement.POSITIVE_ONLY and amount < 0:
            raise serializers.ValidationError(
                {"amount": f"A '{kind}' puts money in — the amount must be positive."}
            )

        shift = attrs.get("shift")
        if shift is not None:
            request = self.context.get("request")
            user = getattr(request, "user", None)
            if user is not None and not getattr(user, "is_platform_admin", False):
                if shift.company_id != getattr(user, "company_id", None):
                    raise serializers.ValidationError(
                        {"shift": "Not your company's shift."}
                    )
            if shift.status != CashShift.OPEN:
                raise serializers.ValidationError(
                    {"shift": "That shift is closed — cash cannot move in or out of it."}
                )
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        if request is not None and request.user.is_authenticated:
            validated_data.setdefault("recorded_by", request.user)
        return super().create(validated_data)


class CashShiftSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    opened_by_name = serializers.SerializerMethodField()
    closed_by_name = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()
    cash_sales = serializers.SerializerMethodField()
    drawer_movements_total = serializers.SerializerMethodField()
    expected_cash = serializers.SerializerMethodField()
    variance = serializers.SerializerMethodField()
    drawer_movements = CashDrawerMovementSerializer(many=True, read_only=True)

    class Meta:
        model = CashShift
        fields = [
            "id", "branch", "status", "status_display",
            "opening_float", "opened_by_name", "opened_at",
            "counted_cash", "closed_by_name", "closed_at",
            "cash_sales", "drawer_movements_total", "expected_cash", "variance",
            "reviewed_by_name", "reviewed_at",
            "note", "drawer_movements", "client_uuid",
        ]
        # Everything about closing and review moves through the dedicated
        # actions; a direct write could set a count without stamping who did it.
        read_only_fields = [
            "status", "opened_at", "counted_cash", "closed_at", "reviewed_at",
        ]

    def _person(self, user):
        return (user.full_name or user.email) if user else None

    def get_opened_by_name(self, obj):
        return self._person(obj.opened_by)

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
        max_digits=14, decimal_places=6, required=False
    )
    client_uuid = serializers.UUIDField(required=False, allow_null=True)
    # The till session this sale was rung under. Sent by the client rather than
    # inferred from the clock, because an offline sale can sync long after its
    # shift closed and must still land in the drawer that actually took the cash.
    shift = serializers.PrimaryKeyRelatedField(
        queryset=CashShift.objects.all(), required=False, allow_null=True
    )
    lines = POSLineSerializer(many=True)
    payment = POSPaymentSerializer(required=False, allow_null=True)

    def validate_lines(self, lines):
        if not lines:
            raise serializers.ValidationError("At least one line is required.")
        return lines

    def _assert_company(self, obj, company_id, label):
        if obj is not None and obj.company_id != company_id:
            raise serializers.ValidationError({label: "Not your company's record."})

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        user = request.user
        company_id = getattr(user, "company_id", None)
        if company_id is None:
            raise serializers.ValidationError("A company-scoped user is required.")

        # Company checks on referenced objects.
        self._assert_company(validated_data.get("customer"), company_id, "customer")
        warehouse = validated_data["warehouse"]
        self._assert_company(warehouse, company_id, "warehouse")
        for ln in validated_data["lines"]:
            self._assert_company(ln["product"], company_id, "product")

        from org.models import Company
        company = Company.objects.get(pk=company_id)
        rate = _company_tax_rate(company)

        number = allocate_invoice_number(company_id)
        invoice = Invoice.objects.create(
            company_id=company_id,
            customer=validated_data.get("customer"),
            branch_id=validated_data.get("branch"),
            warehouse=warehouse,
            number=number,
            currency=validated_data.get("currency", company.currency),
            exchange_rate=validated_data.get("exchange_rate", Decimal("1")),
            tax_rate_snapshot=rate,
            created_by=user if user.is_authenticated else None,
            client_uuid=validated_data.get("client_uuid"),
        )

        subtotal = Decimal("0")
        tax_total = Decimal("0")
        for ln in validated_data["lines"]:
            product = ln["product"]
            qty = ln["quantity"]
            price = ln.get("unit_price")
            if price is None:
                price = product.sale_price
            line_subtotal = _q2(qty * price)
            line_tax = _q2(line_subtotal * rate / 100)
            InvoiceLine.objects.create(
                invoice=invoice, product=product,
                description=ln.get("description", ""),
                quantity=qty, unit_price=price, tax_rate=rate,
                line_subtotal=line_subtotal, line_tax=line_tax,
                line_total=line_subtotal + line_tax,
            )
            subtotal += line_subtotal
            tax_total += line_tax
            # sale_out movement (negative) — offline-first: we record the sale
            # even if it drives stock negative; reconciliation is a later step.
            # Skipped for non-stock lines (a bag, a delivery charge, the
            # miscellaneous catch-all): there is no inventory behind them, so a
            # movement would only invent a deficit.
            if product.is_stock_tracked:
                StockMovement.objects.create(
                    company_id=company_id, product=product, warehouse=warehouse,
                    movement_type=StockMovement.SALE_OUT, quantity=-qty,
                    reference_type="Invoice", reference_id=str(invoice.id),
                    created_by=user if user.is_authenticated else None,
                )

        invoice.subtotal = _q2(subtotal)
        invoice.tax_amount = _q2(tax_total)
        invoice.total = invoice.subtotal + invoice.tax_amount
        invoice.save(update_fields=["subtotal", "tax_amount", "total"])

        pay = validated_data.get("payment")
        if pay:
            self._record_payment(
                invoice, pay, company_id, user, validated_data.get("shift")
            )

        return invoice

    def _record_payment(self, invoice, pay, company_id, user, shift=None):
        if shift is not None:
            self._assert_company(shift, company_id, "shift")
            if shift.status != CashShift.OPEN:
                raise serializers.ValidationError(
                    {"shift": "That till session is closed — open a new one."}
                )
        method = pay["method"]
        ba = pay.get("company_bank_account")
        sender = pay.get("sender_bank_name", "")
        ref = pay.get("reference_last4", "")
        if method == Payment.BANK_TRANSFER:
            if ba is None or not sender or not ref or not ref.isdigit() or len(ref) > 4:
                raise serializers.ValidationError(
                    "Bank transfer needs receiving account, sender bank, and "
                    "up-to-4-digit reference."
                )
            self._assert_company(ba, company_id, "company_bank_account")
        elif method == Payment.CASH and (ba or sender or ref):
            raise serializers.ValidationError(
                "Cash payment must not carry bank/reference details."
            )
        Payment.objects.create(
            company_id=company_id, invoice=invoice, method=method,
            company_bank_account=ba, sender_bank_name=sender,
            reference_last4=ref, amount=pay["amount"],
            shift=shift,
            recorded_by=user if user.is_authenticated else None,
        )

    def to_representation(self, instance):
        return InvoiceSerializer(instance, context=self.context).data
