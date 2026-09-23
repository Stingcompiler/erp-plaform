"""The platform team's SEO control page: site-wide settings and per-page
overrides (website.models.SeoSettings / SeoPageOverride).

Reads need `platform.seo.view`, writes `platform.seo.manage` (core.
platform_roles). Every change is written to the activity log under the
model's name, so the platform activity page shows who changed what.
"""
from rest_framework import serializers, viewsets
from django.utils.translation import gettext as _
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core import platform_roles
from core.activity import log_activity
from core.permissions import IsPlatformAdmin
from core.public_media import stored_public_url
from core.seo_inject import ANALYTICS_ID
from website.images import clear_image, prepare_image, replace_image
from website.models import SeoPageOverride, SeoSettings, normalize_seo_path
from website.seo import site_seo

# A share image is 1200×630 by convention; the longest side is bounded here
# and the file re-encoded like every other public image.
OG_IMAGE_SIDE = 1200


class SeoSettingsSerializer(serializers.ModelSerializer):
    default_og_image_url = serializers.SerializerMethodField()

    class Meta:
        model = SeoSettings
        fields = [
            "google_site_verification", "bing_site_verification", "analytics_id",
            "default_og_image_url", "robots_extra",
            "support_whatsapp", "support_phone", "support_email", "updated_at",
        ]
        read_only_fields = ["default_og_image_url", "updated_at"]

    def get_default_og_image_url(self, obj):
        return stored_public_url(obj.default_og_image)

    def validate_analytics_id(self, value):
        value = (value or "").strip()
        if value and not ANALYTICS_ID.match(value):
            raise serializers.ValidationError(
                _("Use the measurement id as Google shows it, such as G-XXXXXXXXXX.")
            )
        return value

    def _token(self, value):
        value = (value or "").strip()
        if any(ch in value for ch in "<>\"'"):
            raise serializers.ValidationError(_("Paste only the content value of the tag."))
        return value

    def validate_google_site_verification(self, value):
        return self._token(value)

    def _phone(self, value):
        value = " ".join((value or "").split())
        digits = sum(ch.isdigit() for ch in value)
        if value and (digits < 7 or digits > 15):
            raise serializers.ValidationError(_("Enter a number in international form."))
        return value

    def validate_support_whatsapp(self, value):
        return self._phone(value)

    def validate_support_phone(self, value):
        return self._phone(value)

    def validate_bing_site_verification(self, value):
        return self._token(value)


class SeoPageOverrideSerializer(serializers.ModelSerializer):
    class Meta:
        model = SeoPageOverride
        fields = [
            "id", "path", "language", "title", "description", "noindex", "canonical",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        # Uniqueness is checked below on the normalised path.
        validators = []

    def validate_path(self, value):
        value = normalize_seo_path(value)
        if any(ch in value for ch in " <>\"'?#"):
            raise serializers.ValidationError(_("Enter a path such as /pricing or /s/shop."))
        return value

    def validate(self, attrs):
        path = attrs.get("path", getattr(self.instance, "path", None))
        language = attrs.get("language", getattr(self.instance, "language", None))
        clash = SeoPageOverride.objects.filter(path=path, language=language)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError(
                {"path": _("There is already an override for this path and language.")}
            )
        return attrs


class SeoSettingsView(APIView):
    """GET the site-wide settings; PATCH any of the text fields."""

    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    platform_view_capability = platform_roles.SEO_VIEW
    platform_capability = platform_roles.SEO_MANAGE
    entitlement_exempt = True

    def get(self, request):
        return Response(SeoSettingsSerializer(SeoSettings.load()).data)

    def patch(self, request):
        settings_row = SeoSettings.load()
        serializer = SeoSettingsSerializer(settings_row, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log_activity(
            action="update", request=request, entity_type="SeoSettings",
            entity_id=settings_row.pk, metadata={"fields": sorted(serializer.validated_data)},
        )
        return Response(serializer.data)


class PublicSiteContactView(APIView):
    """What the marketing site shows as the platform's own contact: read by
    every visitor, cached briefly, empty fields when nothing is set."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        site = site_seo()
        response = Response({
            "whatsapp": site.support_whatsapp,
            "phone": site.support_phone,
            "email": site.support_email,
        })
        response["Cache-Control"] = "public, max-age=300"
        return response


class SeoOgImageView(APIView):
    """POST a multipart `image` to set the default share image; DELETE to
    remove it. Same pipeline as the company pages' images (website.images)."""

    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    platform_view_capability = platform_roles.SEO_VIEW
    platform_capability = platform_roles.SEO_MANAGE
    entitlement_exempt = True
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        settings_row = SeoSettings.load()
        content = prepare_image(request.FILES.get("image"), OG_IMAGE_SIDE)
        replace_image(settings_row, "default_og_image", content)
        log_activity(
            action="update", request=request, entity_type="SeoSettings",
            entity_id=settings_row.pk, metadata={"image": "default_og_image"},
        )
        return Response(SeoSettingsSerializer(settings_row).data)

    def delete(self, request):
        settings_row = SeoSettings.load()
        clear_image(settings_row, "default_og_image")
        log_activity(
            action="update", request=request, entity_type="SeoSettings",
            entity_id=settings_row.pk, metadata={"image": "default_og_image", "removed": True},
        )
        return Response(SeoSettingsSerializer(settings_row).data)


class SeoPageOverrideViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    platform_view_capability = platform_roles.SEO_VIEW
    platform_capability = platform_roles.SEO_MANAGE
    entitlement_exempt = True
    serializer_class = SeoPageOverrideSerializer
    queryset = SeoPageOverride.objects.all()
    pagination_class = None

    def _log(self, action, override, fields=None):
        metadata = {"label": override.path, "path": override.path, "language": override.language}
        if fields:
            metadata["fields"] = sorted(fields)
        log_activity(
            action=action, request=self.request, entity_type="SeoPageOverride",
            entity_id=override.pk, metadata=metadata,
        )

    def perform_create(self, serializer):
        serializer.save()
        self._log("create", serializer.instance)

    def perform_update(self, serializer):
        serializer.save()
        self._log("update", serializer.instance, serializer.validated_data)

    def perform_destroy(self, instance):
        self._log("delete", instance)
        instance.delete()
