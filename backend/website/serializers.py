from rest_framework import serializers

from subscriptions.models import PlanVersion
from website.models import (
    FeaturedProduct, PlatformLead, RegistrationRequest, Section, Website,
)
from website.services import plan_version_is_available


class WebsiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Website
        fields = [
            "id", "company", "business_name", "tagline", "about_text",
            "logo_url", "primary_color", "contact_email", "contact_phone",
            "address", "social_links", "is_published", "published_at",
            "updated_at",
        ]
        read_only_fields = ["company", "is_published", "published_at", "updated_at"]


class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = [
            "id", "company", "website", "type", "title", "order",
            "content", "is_visible",
        ]
        read_only_fields = ["company"]

    def validate_website(self, website):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is not None and not getattr(user, "is_platform_admin", False):
            if website.company_id != getattr(user, "company_id", None):
                raise serializers.ValidationError("Not your company's website.")
        return website


class FeaturedProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeaturedProduct
        fields = ["id", "company", "website", "product", "caption", "order"]
        read_only_fields = ["company"]

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is not None and not getattr(user, "is_platform_admin", False):
            cid = getattr(user, "company_id", None)
            for key in ("website", "product"):
                obj = attrs.get(key)
                if obj is not None and obj.company_id != cid:
                    raise serializers.ValidationError(
                        {key: "Not your company's record."}
                    )
        return attrs


# ---------- Public (unauthenticated) read-only serializers ----------

class PublicSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ["type", "title", "order", "content"]


class PublicFeaturedProductSerializer(serializers.Serializer):
    name = serializers.CharField(source="product.name")
    sku = serializers.CharField(source="product.sku")
    price = serializers.DecimalField(
        source="product.sale_price", max_digits=14, decimal_places=2
    )
    caption = serializers.CharField()
    order = serializers.IntegerField()


class PublicSiteSerializer(serializers.ModelSerializer):
    """Only public-safe fields; only visible sections; no internal IDs."""

    sections = serializers.SerializerMethodField()
    featured_products = serializers.SerializerMethodField()

    class Meta:
        model = Website
        fields = [
            "business_name", "tagline", "about_text", "logo_url",
            "primary_color", "contact_email", "contact_phone", "address",
            "social_links", "published_at", "sections", "featured_products",
        ]

    def get_sections(self, obj):
        visible = obj.sections.filter(is_visible=True).order_by("order", "id")
        return PublicSectionSerializer(visible, many=True).data

    def get_featured_products(self, obj):
        featured = obj.featured_products.select_related("product").order_by(
            "order", "id"
        )
        return PublicFeaturedProductSerializer(featured, many=True).data


class DemoRequestSerializer(serializers.Serializer):
    request_uuid = serializers.UUIDField()
    name = serializers.CharField(max_length=255)
    email = serializers.EmailField(max_length=254)
    message = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    website = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate_website(self, value):
        if value:
            raise serializers.ValidationError("Leave this field empty.")
        return value


class PlatformLeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformLead
        fields = [
            "id", "request_uuid", "name", "email", "message", "status",
            "source", "created_at",
        ]
        read_only_fields = [
            "id", "request_uuid", "name", "email", "message", "source",
            "created_at",
        ]


class PublicPlanVersionSerializer(serializers.ModelSerializer):
    plan_code = serializers.CharField(source="plan.code", read_only=True)
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    # Marketing copy lives on the plan; the pricing page picks the language.
    display = serializers.SerializerMethodField()
    # Every SaaS sign-up starts with the same platform-wide trial; the landing
    # page shows the length so applicants know what they are requesting.
    trial_days = serializers.SerializerMethodField()

    class Meta:
        model = PlanVersion
        fields = [
            "id", "plan_code", "plan_name", "display", "currency", "price",
            "billing_cycle", "modules", "limits", "trial_days",
        ]

    def get_display(self, obj):
        plan = obj.plan

        def lines(text):
            return [line.strip() for line in (text or "").splitlines() if line.strip()]

        return {
            "name": {"en": plan.name, "ar": plan.name_ar or plan.name},
            "tagline": {"en": plan.tagline_en, "ar": plan.tagline_ar or plan.tagline_en},
            "features": {"en": lines(plan.features_en), "ar": lines(plan.features_ar)},
            "is_highlighted": plan.is_highlighted,
            "sort_order": plan.sort_order,
        }

    def get_trial_days(self, obj):
        from django.conf import settings

        return getattr(settings, "VEZANO_TRIAL_DAYS", 14)


class RegistrationRequestSerializer(serializers.ModelSerializer):
    request_uuid = serializers.UUIDField(required=False, validators=[])
    estimated_users = serializers.IntegerField(required=False, min_value=1)
    estimated_branches = serializers.IntegerField(required=False, min_value=1)

    class Meta:
        model = RegistrationRequest
        fields = [
            "request_uuid", "company_name", "contact_name", "email", "phone", "country",
            "timezone_name", "estimated_users", "estimated_branches", "delivery_mode",
            "plan_version", "message", "privacy_version", "status", "created_at",
        ]
        read_only_fields = ["status", "created_at"]

    def validate_plan_version(self, value):
        if value is not None and not plan_version_is_available(value):
            raise serializers.ValidationError(
                "This plan is not available for registration."
            )
        return value

    def validate_country(self, value):
        value = value.upper()
        if len(value) != 2 or not value.isalpha():
            raise serializers.ValidationError("Use a two-letter country code.")
        return value

    def validate(self, attrs):
        if (
            attrs.get("delivery_mode") == RegistrationRequest.SAAS
            and not attrs.get("plan_version")
        ):
            raise serializers.ValidationError(
                {"plan_version": "Choose a plan for a SaaS trial."}
            )
        return attrs


class PlatformRegistrationRequestSerializer(serializers.ModelSerializer):
    company_id = serializers.IntegerField(source="company.id", read_only=True)
    plan_name = serializers.CharField(source="plan_version.plan.name", read_only=True)

    class Meta:
        model = RegistrationRequest
        fields = [
            "id", "request_uuid", "company_name", "contact_name", "email", "phone", "country",
            "timezone_name", "estimated_users", "estimated_branches", "delivery_mode",
            "plan_version", "plan_name", "message", "privacy_version", "status", "internal_note",
            "reviewed_by", "reviewed_at", "company_id", "created_at", "updated_at",
        ]
        read_only_fields = [
            "request_uuid", "company_name", "contact_name", "email", "phone", "country",
            "timezone_name", "estimated_users", "estimated_branches",
            "delivery_mode", "message", "privacy_version",
            "status", "reviewed_by", "reviewed_at", "company_id",
            "created_at", "updated_at",
        ]

    # The applicant's plan choice can go stale (unpublished, retired) between
    # submission and approval. The platform may swap it for a live plan while
    # the request is still open; once provisioned the subscription owns it.
    def validate_plan_version(self, value):
        if value is None:
            raise serializers.ValidationError("A SaaS request needs a plan.")
        if not plan_version_is_available(value):
            raise serializers.ValidationError("This plan is not available for registration.")
        if self.instance and self.instance.status in {
            RegistrationRequest.PROVISIONED,
            RegistrationRequest.REJECTED,
            RegistrationRequest.WITHDRAWN,
        }:
            raise serializers.ValidationError("The plan of a closed request cannot change.")
        return value


class OwnerInvitationAcceptSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=256)
    password = serializers.CharField(write_only=True, min_length=10)

    def validate_password(self, value):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value
