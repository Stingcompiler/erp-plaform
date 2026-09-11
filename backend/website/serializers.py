from rest_framework import serializers

from website.models import FeaturedProduct, Section, Website


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
