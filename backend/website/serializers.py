from rest_framework import serializers
from django.utils.translation import gettext as _

from subscriptions.models import PlanVersion
from core.public_media import stored_public_url
from website.models import (
    PublicOrder,
    PublicOrderLine,
    PublicOrderPayment,
    FeaturedProduct, PlatformLead, RegistrationRequest, Section, Website, WebsiteImage,
    service_lines,
)
from website.services import plan_version_is_available


# What a landing page needs before it is worth publishing. The editor shows
# the missing items; the platform's marketing sections only pick complete
# sites (see website.public_pages.is_complete).
def completeness(site):
    missing = []
    if not stored_public_url(site.cover_image):
        missing.append("cover_image")
    if not (stored_public_url(site.logo_image) or site.logo_url):
        missing.append("logo")
    if not site.about_text.strip():
        missing.append("about_text")
    if not site.tagline.strip():
        missing.append("tagline")
    if not (site.contact_phone.strip() or site.contact_email.strip()):
        missing.append("contact")
    if not site.category:
        missing.append("category")
    if not service_lines(site.services):
        missing.append("services")
    if not site.featured_products.filter(product__image__isnull=False).exclude(
        product__image=""
    ).exists():
        missing.append("product_with_image")
    return missing


class WebsiteSerializer(serializers.ModelSerializer):
    # Where the page is (or will be) served as HTML; see website.public_pages.
    public_url = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    logo_image_url = serializers.SerializerMethodField()
    missing = serializers.SerializerMethodField()

    class Meta:
        model = Website
        fields = [
            "id", "company", "business_name", "tagline", "about_text",
            "logo_url", "primary_color", "contact_email", "contact_phone",
            "address", "social_links", "is_published", "published_at",
            "updated_at", "public_url",
            "category", "city", "opening_hours", "map_url", "services", "list_in_directory",
            "cover_image_url", "logo_image_url", "missing", "accept_orders", "order_instructions",
            "order_notify_owners", "order_notify_emails",
        ]
        read_only_fields = ["company", "is_published", "published_at", "updated_at"]

    def get_public_url(self, obj):
        from website.public_pages import public_site_path, site_url

        return site_url(public_site_path(obj.company.slug))

    def get_cover_image_url(self, obj):
        return stored_public_url(obj.cover_image)

    def get_logo_image_url(self, obj):
        return stored_public_url(obj.logo_image)

    def get_missing(self, obj):
        return completeness(obj)

    def validate_services(self, value):
        lines = service_lines(value)
        if any(len(line) > 60 for line in lines):
            raise serializers.ValidationError(_("Keep each service under 60 characters."))
        return "\n".join(lines)


class WebsiteImageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = WebsiteImage
        fields = ["id", "company", "website", "url", "caption", "order", "created_at"]
        read_only_fields = ["company", "website", "url", "created_at"]

    def get_url(self, obj):
        return stored_public_url(obj.image)


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
                raise serializers.ValidationError(_("Not your company's website."))
        return website


class FeaturedProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeaturedProduct
        fields = [
            "id", "company", "website", "product", "caption", "order",
            "show_price", "allow_order",
        ]
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
                        {key: _("Not your company's record.")}
                    )
        return attrs


# ---------- Public (unauthenticated) read-only serializers ----------

class PublicSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ["type", "title", "order", "content"]


class PublicFeaturedProductSerializer(serializers.Serializer):
    product = serializers.IntegerField(source="product_id")
    name = serializers.CharField(source="product.name")
    sku = serializers.CharField(source="product.sku")
    price = serializers.SerializerMethodField()
    orderable = serializers.BooleanField(source="allow_order")
    in_stock = serializers.SerializerMethodField()
    caption = serializers.CharField()
    order = serializers.IntegerField()
    image_url = serializers.SerializerMethodField()

    def get_price(self, obj):
        return str(obj.product.sale_price) if obj.show_price else None

    def get_in_stock(self, obj):
        from website.orders import in_stock

        return in_stock(obj.product)

    def get_image_url(self, obj):
        image = obj.product.image
        return stored_public_url(image)


class PublicSiteSerializer(serializers.ModelSerializer):
    """Only public-safe fields; only visible sections; no internal IDs.
    The original fields are unchanged; the landing-page fields are appended."""

    sections = serializers.SerializerMethodField()
    featured_products = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    logo_image_url = serializers.SerializerMethodField()
    gallery = serializers.SerializerMethodField()
    services = serializers.SerializerMethodField()

    class Meta:
        model = Website
        fields = [
            "business_name", "tagline", "about_text", "logo_url",
            "primary_color", "contact_email", "contact_phone", "address",
            "social_links", "published_at", "sections", "featured_products",
            "category", "city", "opening_hours", "map_url", "services",
            "cover_image_url", "logo_image_url", "gallery", "accept_orders", "order_instructions",
        ]

    def get_services(self, obj):
        return service_lines(obj.services)

    def get_cover_image_url(self, obj):
        return stored_public_url(obj.cover_image)

    def get_logo_image_url(self, obj):
        return stored_public_url(obj.logo_image)

    def get_gallery(self, obj):
        return [
            {"url": url, "caption": image.caption}
            for image in obj.images.order_by("order", "id")
            if (url := stored_public_url(image.image))
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
    email = serializers.EmailField(max_length=254, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=64, required=False, allow_blank=True)
    preferred_channel = serializers.ChoiceField(
        choices=PlatformLead.CHANNEL_CHOICES, required=False,
        default=PlatformLead.CHANNEL_WHATSAPP,
    )
    message = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    website = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate_website(self, value):
        if value:
            raise serializers.ValidationError(_("Leave this field empty."))
        return value

    def validate_phone(self, value):
        value = " ".join((value or "").split())
        digits = sum(ch.isdigit() for ch in value)
        if value and (digits < 7 or digits > 15 or len(value) > 32):
            raise serializers.ValidationError(_("Enter a phone number we can call."))
        return value

    def validate(self, attrs):
        attrs["email"] = (attrs.get("email") or "").strip()
        if not attrs.get("phone") and not attrs["email"]:
            raise serializers.ValidationError(
                {"phone": _("Leave a phone number or an email so we can reach you.")}
            )
        # A channel we cannot use falls back to one we can.
        channel = attrs.get("preferred_channel") or PlatformLead.CHANNEL_WHATSAPP
        if channel == PlatformLead.CHANNEL_EMAIL and not attrs["email"]:
            channel = PlatformLead.CHANNEL_WHATSAPP
        if channel != PlatformLead.CHANNEL_EMAIL and not attrs.get("phone"):
            channel = PlatformLead.CHANNEL_EMAIL
        attrs["preferred_channel"] = channel
        return attrs


class PlatformLeadSerializer(serializers.ModelSerializer):
    follow_up_due = serializers.BooleanField(read_only=True)

    class Meta:
        model = PlatformLead
        fields = [
            "id", "request_uuid", "name", "email", "phone", "preferred_channel", "message",
            "status", "internal_note", "last_contacted_at", "last_contact_channel",
            "next_follow_up_at", "follow_up_due", "source", "created_at",
        ]
        read_only_fields = [
            "id", "request_uuid", "name", "email", "phone", "preferred_channel", "message",
            "last_contacted_at", "last_contact_channel", "follow_up_due", "source", "created_at",
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
                _("This plan is not available for registration.")
            )
        return value

    def validate_country(self, value):
        value = value.upper()
        if len(value) != 2 or not value.isalpha():
            raise serializers.ValidationError(_("Use a two-letter country code."))
        return value

    def validate(self, attrs):
        if (
            attrs.get("delivery_mode") == RegistrationRequest.SAAS
            and not attrs.get("plan_version")
        ):
            raise serializers.ValidationError(
                {"plan_version": _("Choose a plan for a SaaS trial.")}
            )
        return attrs


class PlatformRegistrationRequestSerializer(serializers.ModelSerializer):
    company_id = serializers.IntegerField(source="company.id", read_only=True)
    plan_name = serializers.CharField(source="plan_version.plan.name", read_only=True)
    follow_up_due = serializers.BooleanField(read_only=True)

    class Meta:
        model = RegistrationRequest
        fields = [
            "id", "request_uuid", "company_name", "contact_name", "email", "phone", "country",
            "timezone_name", "estimated_users", "estimated_branches", "delivery_mode",
            "plan_version", "plan_name", "message", "privacy_version", "status", "internal_note",
            "last_contacted_at", "last_contact_channel", "next_follow_up_at", "follow_up_due",
            "reviewed_by", "reviewed_at", "company_id", "created_at", "updated_at",
        ]
        read_only_fields = [
            "request_uuid", "company_name", "contact_name", "email", "phone", "country",
            "timezone_name", "estimated_users", "estimated_branches",
            "delivery_mode", "message", "privacy_version",
            "status", "last_contacted_at", "last_contact_channel", "follow_up_due",
            "reviewed_by", "reviewed_at", "company_id",
            "created_at", "updated_at",
        ]

    # The applicant's plan choice can go stale (unpublished, retired) between
    # submission and approval. The platform may swap it for a live plan while
    # the request is still open; once provisioned the subscription owns it.
    def validate_plan_version(self, value):
        if value is None:
            raise serializers.ValidationError(_("A SaaS request needs a plan."))
        if not plan_version_is_available(value):
            raise serializers.ValidationError(_("This plan is not available for registration."))
        if self.instance and self.instance.status in {
            RegistrationRequest.PROVISIONED,
            RegistrationRequest.REJECTED,
            RegistrationRequest.WITHDRAWN,
        }:
            raise serializers.ValidationError(_("The plan of a closed request cannot change."))
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


class PublicOrderLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = PublicOrderLine
        fields = ["id", "product", "name", "quantity", "unit_price"]


class PublicOrderPaymentSerializer(serializers.ModelSerializer):
    bank_name = serializers.CharField(source="bank_account.bank_name", read_only=True, default=None)
    decided_by_name = serializers.SerializerMethodField()
    proof_available = serializers.SerializerMethodField()
    invoice_number = serializers.IntegerField(source="invoice.number", read_only=True, default=None)

    class Meta:
        model = PublicOrderPayment
        fields = [
            "id", "status", "bank_account", "bank_name", "sender_bank_name", "reference_last4",
            "amount", "proof_available", "decided_by_name", "decided_at", "decision_note",
            "payment", "invoice", "invoice_number", "created_at",
        ]
        read_only_fields = fields

    def get_decided_by_name(self, obj):
        user = obj.decided_by
        return (user.full_name or user.email) if user else None

    def get_proof_available(self, obj):
        return bool(obj.proof)


class PublicOrderSerializer(serializers.ModelSerializer):
    lines = PublicOrderLineSerializer(many=True, read_only=True)
    payments = PublicOrderPaymentSerializer(many=True, read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    customer_name = serializers.CharField(source="customer.name", read_only=True, default=None)
    decided_by_name = serializers.SerializerMethodField()
    whatsapp = serializers.SerializerMethodField()

    class Meta:
        model = PublicOrder
        fields = [
            "id", "reference", "status", "contact_name", "phone", "delivery_mode", "address",
            "note", "language", "currency", "total", "tax_amount", "branch", "branch_name",
            "customer",
            "customer_name", "sales_order", "decided_by_name", "decided_at", "decision_note",
            "whatsapp", "created_at", "lines", "payments", "email",
        ]
        read_only_fields = fields

    def get_decided_by_name(self, obj):
        user = obj.decided_by
        return (user.full_name or user.email) if user else None

    def get_whatsapp(self, obj):
        import re

        digits = re.sub(r"\D", "", obj.phone or "")
        return digits if len(digits) >= 8 else ""
