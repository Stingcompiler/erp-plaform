from rest_framework import serializers

from subscriptions.models import (
    LIMIT_KEYS,
    Plan,
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
                f"Unknown modules: {', '.join(sorted(unknown))}"
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
                        f"{module} also requires {', '.join(sorted(missing))}."
                    )
        return value

    def validate_limits(self, value):
        allowed = set(LIMIT_KEYS)
        if set(value) - allowed:
            raise serializers.ValidationError("One or more usage limits are unknown.")
        if any(
            not isinstance(item, int) or isinstance(item, bool) or item < 0
            for item in value.values()
        ):
            raise serializers.ValidationError(
                "Usage limits must be non-negative integers."
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
            "revision",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["revision", "created_at", "updated_at"]

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
                {required_end: f"Required for {status_value}."}
            )
        for field in ("period_ends_at", "trial_ends_at", "grace_ends_at"):
            value = attrs.get(field, getattr(self.instance, field, None))
            if value and starts_at and value <= starts_at:
                raise serializers.ValidationError(
                    {field: "Must be after the subscription start."}
                )
        return attrs

    def validate_plan_version(self, value):
        if value.published_at is None:
            raise serializers.ValidationError(
                "Publish the plan version before assigning it to a company."
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
                "Invoice and subscription must belong to the same company."
            )
        period_start = attrs.get(
            "period_start", getattr(self.instance, "period_start", None)
        )
        period_end = attrs.get(
            "period_end", getattr(self.instance, "period_end", None)
        )
        if period_start and period_end and period_end < period_start:
            raise serializers.ValidationError(
                {"period_end": "The invoice period cannot end before it starts."}
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

    class Meta:
        model = SubscriptionPayment
        fields = [
            "id",
            "company",
            "company_name",
            "amount",
            "currency",
            "method",
            "sender_bank_name",
            "reference_last4",
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
        ]

    def get_proof_available(self, obj):
        return bool(obj.proof)

    def get_recorded_by_name(self, obj):
        return obj.recorded_by.full_name or obj.recorded_by.email

    def validate(self, attrs):
        if (
            attrs.get("method") == "bank_transfer"
            and len(attrs.get("reference_last4", "")) != 4
        ):
            raise serializers.ValidationError(
                {"reference_last4": "Enter the last four reference characters."}
            )
        return attrs

    def validate_proof(self, value):
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("Payment proof must be 10 MB or smaller.")
        allowed = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
        if getattr(value, "content_type", "") not in allowed:
            raise serializers.ValidationError(
                "Use a PDF, JPEG, PNG or WebP proof file."
            )
        return value


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
                    "Each allocation needs invoice_id and amount."
                )
            if amount <= 0:
                raise serializers.ValidationError(
                    "Allocation amounts must be positive."
                )
            if invoice_id in invoice_ids:
                raise serializers.ValidationError("Each invoice may appear only once.")
            invoice_ids.add(invoice_id)
            cleaned.append({"invoice_id": invoice_id, "amount": amount})
        return cleaned
