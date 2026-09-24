import re

from django.utils.translation import gettext as _
from rest_framework import serializers

from subscriptions.models import (
    LIMIT_KEYS,
    Plan,
    PlanChangeRequest,
    PlanVersion,
    Subscription,
    SubscriptionEvent,
    SubscriptionInvoice,
    SubscriptionPayment,
)


class PlanVersionSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True)

    class Meta:
        model = PlanVersion
        fields = [
            "id",
            "plan",
            "plan_name",
            "version",
            "currency",
            "price",
            "billing_cycle",
            "modules",
            "limits",
            "addon_prices",
            "is_legacy",
            "published_at",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def validate_modules(self, value):
        allowed = {
            "*",
            "users",
            "org",
            "inventory",
            "sales",
            "purchasing",
            "sales_returns",
            "purchase_returns",
            "reports",
            "hr",
            "crm",
            "finance",
            "website",
            "settings",
        }
        unknown = set(value) - allowed
        if unknown:
            raise serializers.ValidationError(
                _("Unknown modules: %(modules)s")
                % {"modules": ", ".join(sorted(unknown))}
            )
        dependencies = {
            "sales_returns": {"sales", "inventory"},
            "purchase_returns": {"purchasing", "inventory"},
        }
        if "*" not in value:
            for module, required in dependencies.items():
                missing = required - set(value) if module in value else set()
                if missing:
                    raise serializers.ValidationError(
                        _("%(module)s also requires %(required)s.")
                        % {"module": module, "required": ", ".join(sorted(missing))}
                    )
        return value

    def validate_addon_prices(self, value):
        from decimal import Decimal, InvalidOperation

        allowed = set(LIMIT_KEYS) - {"storage_mb"}
        if set(value) - allowed:
            raise serializers.ValidationError(_("One or more add-ons are unknown."))
        for item in value.values():
            try:
                if Decimal(str(item)) < 0:
                    raise ValueError
            except (InvalidOperation, ValueError):
                raise serializers.ValidationError(_("Add-on prices must be non-negative amounts."))
        return {key: str(Decimal(str(item))) for key, item in value.items()}

    def validate_limits(self, value):
        allowed = set(LIMIT_KEYS)
        if set(value) - allowed:
            raise serializers.ValidationError(_("One or more usage limits are unknown."))
        if any(
            not isinstance(item, int) or isinstance(item, bool) or item < 0
            for item in value.values()
        ):
            raise serializers.ValidationError(
                _("Usage limits must be non-negative integers.")
            )
        return value


class PlanSerializer(serializers.ModelSerializer):
    versions = PlanVersionSerializer(many=True, read_only=True)

    class Meta:
        model = Plan
        fields = [
            "id",
            "code",
            "name",
            "description",
            "name_ar",
            "tagline_en",
            "tagline_ar",
            "features_en",
            "features_ar",
            "is_highlighted",
            "sort_order",
            "is_public",
            "is_active",
            "versions",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class SubscriptionSerializer(serializers.ModelSerializer):
    addon_lines = serializers.SerializerMethodField()
    recurring_amount = serializers.SerializerMethodField()
    next_renewal = serializers.SerializerMethodField()
    company_name = serializers.CharField(source="company.name", read_only=True)
    # The company's own contact number, so the platform team can call or
    # WhatsApp a customer from the subscription row.
    company_phone = serializers.CharField(source="company.phone", read_only=True)
    plan = PlanVersionSerializer(source="plan_version", read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "company",
            "company_name",
            "company_phone",
            "plan_version",
            "plan",
            "status",
            "starts_at",
            "period_ends_at",
            "trial_ends_at",
            "grace_ends_at",
            "cancel_at_period_end",
            "suspended_reason",
            "extra_limits",
            "addon_lines",
            "recurring_amount",
            "next_renewal",
            "revision",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "revision", "created_at", "updated_at", "addon_lines", "recurring_amount",
            "next_renewal",
        ]

    def get_addon_lines(self, obj):
        from subscriptions.services import addon_lines

        return addon_lines(obj)

    def get_recurring_amount(self, obj):
        from subscriptions.services import recurring_price

        return str(recurring_price(obj))

    def get_next_renewal(self, obj):
        from subscriptions.renewals import next_renewal

        return next_renewal(obj)

    def validate(self, attrs):
        status_value = attrs.get("status", getattr(self.instance, "status", None))
        starts_at = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        required_end = {
            Subscription.TRIALING: "trial_ends_at",
            Subscription.ACTIVE: "period_ends_at",
            Subscription.GRACE: "grace_ends_at",
        }.get(status_value)
        if required_end and not attrs.get(
            required_end, getattr(self.instance, required_end, None)
        ):
            raise serializers.ValidationError(
                {required_end: _("Required for %(status)s.") % {"status": status_value}}
            )
        for field in ("period_ends_at", "trial_ends_at", "grace_ends_at"):
            value = attrs.get(field, getattr(self.instance, field, None))
            if value and starts_at and value <= starts_at:
                raise serializers.ValidationError(
                    {field: _("Must be after the subscription start.")}
                )
        return attrs

    def validate_plan_version(self, value):
        if value.published_at is None:
            raise serializers.ValidationError(
                _("Publish the plan version before assigning it to a company.")
            )
        return value


class SubscriptionEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.full_name", read_only=True)

    class Meta:
        model = SubscriptionEvent
        fields = [
            "id",
            "event_type",
            "from_status",
            "to_status",
            "reason",
            "actor_name",
            "metadata",
            "created_at",
        ]


class SubscriptionInvoiceSerializer(serializers.ModelSerializer):
    allocated_amount = serializers.SerializerMethodField()
    number = serializers.CharField(required=False)

    class Meta:
        model = SubscriptionInvoice
        fields = [
            "id",
            "company",
            "subscription",
            "number",
            "status",
            "period_start",
            "period_end",
            "currency",
            "amount",
            "allocated_amount",
            "due_at",
            "line_snapshot",
            "issued_at",
            "entitlement_granted_at",
            "created_at",
        ]
        read_only_fields = [
            "number",
            "allocated_amount",
            "issued_at",
            "entitlement_granted_at",
            "created_at",
        ]

    def validate(self, attrs):
        company = attrs.get("company", getattr(self.instance, "company", None))
        subscription = attrs.get(
            "subscription", getattr(self.instance, "subscription", None)
        )
        if company and subscription and subscription.company_id != company.pk:
            raise serializers.ValidationError(
                _("Invoice and subscription must belong to the same company.")
            )
        period_start = attrs.get(
            "period_start", getattr(self.instance, "period_start", None)
        )
        period_end = attrs.get(
            "period_end", getattr(self.instance, "period_end", None)
        )
        if period_start and period_end and period_end < period_start:
            raise serializers.ValidationError(
                {"period_end": _("The invoice period cannot end before it starts.")}
            )
        return attrs

    def get_allocated_amount(self, obj):
        return sum(
            (row.amount for row in obj.allocations.filter(payment__status="verified")),
            0,
        )


class SubscriptionPaymentSerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.SerializerMethodField()
    company_name = serializers.CharField(source="company.name", read_only=True)
    proof_available = serializers.SerializerMethodField()
    allocations = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionPayment
        fields = [
            "id",
            "company",
            "company_name",
            "amount",
            "currency",
            "allocations",
            "method",
            "sender_bank_name",
            "reference_last4",
            "transfer_reference",
            "proof",
            "proof_available",
            "status",
            "recorded_by_name",
            "verified_at",
            "rejection_reason",
            "client_uuid",
            "created_at",
        ]
        read_only_fields = [
            "company",
            "company_name",
            "status",
            "recorded_by_name",
            "verified_at",
            "rejection_reason",
            "created_at",
            "proof_available",
            "allocations",
        ]

    def get_allocations(self, obj):
        """What a verified payment paid for: invoice, period and whether the
        invoice is settled — so a partial payment is visible to both sides."""
        if obj.status != SubscriptionPayment.VERIFIED:
            return []
        return [
            {
                "invoice": row.invoice_id,
                "invoice_number": row.invoice.number,
                "amount": str(row.amount),
                "invoice_amount": str(row.invoice.amount),
                "invoice_status": row.invoice.status,
                "period_start": row.invoice.period_start.isoformat(),
                "period_end": row.invoice.period_end.isoformat(),
            }
            for row in obj.allocations.select_related("invoice").order_by("invoice__period_start")
        ]

    def get_proof_available(self, obj):
        return bool(obj.proof)

    def get_recorded_by_name(self, obj):
        return obj.recorded_by.full_name or obj.recorded_by.email

    def validate(self, attrs):
        from sales.serializers import normalise_reference
        from subscriptions.services import normalise_currency

        if "currency" in attrs:
            attrs["currency"] = normalise_currency(attrs["currency"])
        full = normalise_reference(attrs.get("transfer_reference"))
        attrs["transfer_reference"] = full
        last4 = str(attrs.get("reference_last4") or "").strip()
        if full and not last4:
            digits = re.sub(r"\D", "", full)
            last4 = (digits or full)[-4:]
            attrs["reference_last4"] = last4
        if attrs.get("method") == "bank_transfer":
            if len(last4) != 4:
                raise serializers.ValidationError(
                    {"transfer_reference": _("Enter the transfer reference from the app.")}
                )
            company = self.context["request"].user.company
            if full and SubscriptionPayment.objects.filter(
                company=company, transfer_reference=full,
            ).exclude(status=SubscriptionPayment.REJECTED).exists():
                raise serializers.ValidationError(
                    {"transfer_reference": _("This transfer reference was already submitted.")}
                )
        return attrs

    def validate_proof(self, value):
        from rest_framework.exceptions import ValidationError as DRFValidationError

        from core.uploads import validate_proof

        try:
            validate_proof(value, max_bytes=10 * 1024 * 1024, allow_pdf=True)
        except DRFValidationError as exc:
            raise serializers.ValidationError(exc.detail.get("proof", exc.detail))
        return value


class PlatformSubscriptionPaymentSerializer(SubscriptionPaymentSerializer):
    """The platform's view of a payment: a pending one carries the renewal
    its approval would perform (subscriptions.renewals.plan_renewal)."""

    renewal = serializers.SerializerMethodField()

    class Meta(SubscriptionPaymentSerializer.Meta):
        fields = SubscriptionPaymentSerializer.Meta.fields + ["renewal"]
        read_only_fields = SubscriptionPaymentSerializer.Meta.read_only_fields + ["renewal"]

    def get_renewal(self, obj):
        if obj.status != SubscriptionPayment.PENDING:
            return None
        from subscriptions.renewals import plan_renewal, renewal_as_json

        return renewal_as_json(plan_renewal(obj))


class PaymentVerificationSerializer(serializers.Serializer):
    allocations = serializers.ListField(
        child=serializers.DictField(), allow_empty=False
    )

    def validate_allocations(self, rows):
        cleaned = []
        invoice_ids = set()
        for row in rows:
            try:
                invoice_id = int(row["invoice_id"])
                amount = serializers.DecimalField(
                    max_digits=14, decimal_places=2
                ).to_internal_value(row["amount"])
            except (KeyError, TypeError, ValueError):
                raise serializers.ValidationError(
                    _("Each allocation needs invoice_id and amount.")
                )
            if amount <= 0:
                raise serializers.ValidationError(
                    _("Allocation amounts must be positive.")
                )
            if invoice_id in invoice_ids:
                raise serializers.ValidationError(_("Each invoice may appear only once."))
            invoice_ids.add(invoice_id)
            cleaned.append({"invoice_id": invoice_id, "amount": amount})
        return cleaned


class PlanChangeRequestSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)
    from_plan = serializers.CharField(source="from_version.plan.name", read_only=True)
    to_plan = serializers.CharField(source="to_version.plan.name", read_only=True)
    from_price = serializers.DecimalField(
        source="from_version.price", max_digits=14, decimal_places=2, read_only=True
    )
    to_price = serializers.DecimalField(
        source="to_version.price", max_digits=14, decimal_places=2, read_only=True
    )
    to_cycle = serializers.CharField(source="to_version.billing_cycle", read_only=True)
    to_limits = serializers.JSONField(source="to_version.limits", read_only=True)
    currency = serializers.CharField(source="to_version.currency", read_only=True)
    from_currency = serializers.CharField(source="from_version.currency", read_only=True)
    requested_by_name = serializers.SerializerMethodField()
    invoice_number = serializers.CharField(source="invoice.number", read_only=True, default=None)
    invoice_amount = serializers.DecimalField(
        source="invoice.amount", max_digits=14, decimal_places=2, read_only=True, default=None
    )
    invoice_status = serializers.CharField(source="invoice.status", read_only=True, default=None)

    class Meta:
        model = PlanChangeRequest
        fields = [
            "id", "company", "company_name", "kind", "status", "extra_delta", "note",
            "decision_note",
            "from_version", "from_plan", "from_price", "from_currency",
            "to_version", "to_plan", "to_price",
            "to_cycle", "to_limits", "currency", "requested_by_name", "invoice_number",
            "invoice_amount", "invoice_status", "apply_at", "applied_at", "decided_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_requested_by_name(self, obj):
        user = obj.requested_by
        return user.full_name or user.email
