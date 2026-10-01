"""The platform team's SEO control page: site-wide settings and per-page
overrides (website.models.SeoSettings / SeoPageOverride).

Reads need `platform.seo.view`, writes `platform.seo.manage` (core.
platform_roles). Every change is written to the activity log under the
model's name, so the platform activity page shows who changed what.
"""
import csv
import io

from django.db import transaction
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
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
from website import redirects
from website.models import (
    PRICING_CYCLES, PRICING_TEMPLATES, SeoPageOverride, SeoRedirect, SeoSettings,
    normalize_seo_path,
)
from website.seo import pricing_display, pricing_display_of, site_seo
from website.seo_health import health_report

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


class PricingDisplaySerializer(serializers.ModelSerializer):
    """How /pricing lays out the plans: a template name and three switches.
    Choices are validated against the model's; nothing here touches a
    price, which stays with the plan versions."""

    template = serializers.ChoiceField(
        source="pricing_template", choices=[value for value, _label in PRICING_TEMPLATES],
        required=False,
    )
    show_compare = serializers.BooleanField(source="pricing_show_compare", required=False)
    show_self_hosted = serializers.BooleanField(
        source="pricing_show_self_hosted", required=False
    )
    default_cycle = serializers.ChoiceField(
        source="pricing_default_cycle", choices=[value for value, _label in PRICING_CYCLES],
        required=False,
    )

    class Meta:
        model = SeoSettings
        fields = ["template", "show_compare", "show_self_hosted", "default_cycle", "updated_at"]
        read_only_fields = ["updated_at"]


class PricingDisplayView(APIView):
    """GET/PATCH the pricing page layout. It lives beside the price list, so
    it takes the plans capabilities (`platform.plans.view` to read,
    `platform.plans.manage` to change), not the SEO ones."""

    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    platform_view_capability = platform_roles.PLANS_VIEW
    platform_capability = platform_roles.PLANS_MANAGE
    entitlement_exempt = True

    def get(self, request):
        return Response(PricingDisplaySerializer(SeoSettings.load()).data)

    def patch(self, request):
        settings_row = SeoSettings.load()
        serializer = PricingDisplaySerializer(settings_row, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log_activity(
            action="update", request=request, entity_type="PricingDisplay",
            entity_id=settings_row.pk,
            metadata={
                "fields": sorted(serializer.validated_data),
                **pricing_display_of(settings_row),
            },
        )
        return Response(serializer.data)


class PublicPricingDisplayView(APIView):
    """The pricing page layout for every visitor (cached like the contact
    details). Under public/plans/, so a standalone install gates it with the
    rest of the plan catalogue (core.deployment_gate)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        response = Response(pricing_display())
        response["Cache-Control"] = "public, max-age=60"
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


class SeoHealthView(APIView):
    """GET the SEO health report (website.seo_health): the exported pages,
    the sitemap, the company pages and the site-wide settings, checked.
    Read with `platform.seo.view`; cached for five minutes, and `?refresh=1`
    recomputes it for those who may change things (`platform.seo.manage`)."""

    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    platform_view_capability = platform_roles.SEO_VIEW
    platform_capability = platform_roles.SEO_MANAGE
    entitlement_exempt = True

    def get(self, request):
        refresh = request.query_params.get("refresh") in {"1", "true"}
        if refresh and not platform_roles.user_has_platform_capability(
            request.user, platform_roles.SEO_MANAGE
        ):
            raise PermissionDenied(
                _("Only the team members who manage SEO can refresh the check.")
            )
        return Response(health_report(refresh=refresh))


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


# --- Redirects (phase C) ---------------------------------------------------

# A CSV import is a migration list, not a dump: a few hundred lines at most.
IMPORT_MAX_ROWS = 1000
IMPORT_MAX_BYTES = 512 * 1024


def export_app_page(key):
    """Whether the export serves `key` as a page kept out of search (the
    signed-in app, a private page): those are never redirected."""
    from core.frontend import _candidates
    from website.seo_health import _NOINDEX, parse_page

    for candidate in _candidates(key.strip("/")):
        if candidate.suffix == ".html" and candidate.is_file():
            facts = parse_page(candidate.read_text(encoding="utf-8"))
            return bool(_NOINDEX.search(facts.metas.get("robots", "")))
    return False


def redirect_errors(source, target, *, allow_external, status_code, is_active, exclude_pk=None):
    """check_redirect against what is stored, plus the unique source."""
    errors = redirects.check_redirect(
        source, target, allow_external=allow_external, status_code=status_code,
        is_active=is_active, others=redirects.active_pairs(exclude_pk),
        prefixes=redirects.protected_prefixes(), app_page=export_app_page,
    )
    clash = SeoRedirect.objects.filter(source_path=source)
    if exclude_pk is not None:
        clash = clash.exclude(pk=exclude_pk)
    if "source_path" not in errors and clash.exists():
        errors["source_path"] = _("There is already a redirect for this path.")
    return errors


class SeoRedirectSerializer(serializers.ModelSerializer):
    # Declared, so the unique check runs on the normalised path below rather
    # than on what was typed.
    source_path = serializers.CharField(max_length=500)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = SeoRedirect
        fields = [
            "id", "source_path", "target", "allow_external", "status_code", "is_active",
            "note", "hits", "last_hit_at", "created_by_name", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "hits", "last_hit_at", "created_by_name", "created_at", "updated_at",
        ]

    def get_created_by_name(self, obj):
        user = obj.created_by
        return (user.full_name or user.email) if user else ""

    def validate_source_path(self, value):
        try:
            return redirects.normalize_source(value)
        except redirects.RedirectPathError as error:
            raise serializers.ValidationError(str(error)) from None

    def validate_target(self, value):
        return (value or "").strip()

    def validate(self, attrs):
        def current(name, default):
            return attrs.get(name, getattr(self.instance, name, default))

        errors = redirect_errors(
            current("source_path", ""), current("target", ""),
            allow_external=current("allow_external", False),
            status_code=current("status_code", SeoRedirect.STATUS_PERMANENT),
            is_active=current("is_active", True),
            exclude_pk=self.instance.pk if self.instance is not None else None,
        )
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


def _truthy(value):
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def parse_redirect_csv(text):
    """[(line, source, target, status text)] from `source,target,status`
    lines; a first line naming the columns is skipped."""
    rows = []
    for number, cells in enumerate(csv.reader(io.StringIO(text)), start=1):
        cells = [cell.strip() for cell in cells]
        if not any(cells):
            continue
        if number == 1 and cells[0].lower() in {"source", "source_path", "from"}:
            continue
        cells += [""] * (3 - len(cells))
        rows.append((number, cells[0], cells[1], cells[2]))
    return rows


def import_report(text):
    """Every CSV row checked against the stored redirects and the rest of
    the file: what would be created, and each row's errors."""
    parsed = parse_redirect_csv(text)
    if len(parsed) > IMPORT_MAX_ROWS:
        raise ValidationError({"file": _("Import at most %(count)s redirects at a time.") % {
            "count": IMPORT_MAX_ROWS,
        }})
    stored = redirects.active_pairs()
    existing = set(SeoRedirect.objects.values_list("source_path", flat=True))
    rows, first_line = [], {}
    for line, source, target, status_text in parsed:
        row = {
            "line": line, "source": source, "source_path": "", "target": target,
            "status_code": None, "errors": {},
        }
        try:
            row["source_path"] = redirects.normalize_source(source)
        except redirects.RedirectPathError as error:
            row["errors"]["source_path"] = str(error)
        status_text = status_text or "301"
        row["status_code"] = int(status_text) if status_text.isdigit() else status_text
        rows.append(row)
        if row["source_path"]:
            first_line.setdefault(row["source_path"], row)
    prefixes = redirects.protected_prefixes()
    for row in rows:
        if row["errors"]:
            continue
        source = row["source_path"]
        if source in existing:
            row["errors"]["source_path"] = _("There is already a redirect for this path.")
            continue
        if first_line[source] is not row:
            row["errors"]["source_path"] = _(
                "This path is already earlier in the file (line %(line)s)."
            ) % {"line": first_line[source]["line"]}
            continue
        # Against what is stored and the rows above it: a chain inside the
        # file is reported once, on its later line.
        others = stored + [
            (other["source_path"], redirects.target_key(other["target"], allow_external=True)[0])
            for other in rows[: rows.index(row)]
            if other["source_path"] and "source_path" not in other["errors"]
        ]
        row["errors"].update(redirects.check_redirect(
            source, row["target"], status_code=row["status_code"], others=others,
            prefixes=prefixes, app_page=export_app_page,
        ))
    valid = sum(1 for row in rows if not row["errors"])
    return {"rows": rows, "total": len(rows), "valid": valid, "invalid": len(rows) - valid}


class SeoRedirectViewSet(viewsets.ModelViewSet):
    """CRUD for the redirects, unpaginated like the overrides; plus `test`
    (what a URL would get), `check` (the form's live validation) and
    `import` (a CSV, with a dry run). Read with `platform.seo.view`, write
    with `platform.seo.manage`."""

    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    platform_view_capability = platform_roles.SEO_VIEW
    platform_capability = platform_roles.SEO_MANAGE
    entitlement_exempt = True
    serializer_class = SeoRedirectSerializer
    queryset = SeoRedirect.objects.select_related("created_by")
    pagination_class = None
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def _log(self, action_name, redirect, fields=None):
        metadata = {
            "label": redirect.source_path, "source_path": redirect.source_path,
            "target": redirect.target, "status_code": redirect.status_code,
            "is_active": redirect.is_active,
        }
        if fields:
            metadata["fields"] = sorted(fields)
        log_activity(
            action=action_name, request=self.request, entity_type="SeoRedirect",
            entity_id=redirect.pk, metadata=metadata,
        )

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
        self._log("create", serializer.instance)

    def perform_update(self, serializer):
        serializer.save()
        self._log("update", serializer.instance, serializer.validated_data)

    def perform_destroy(self, instance):
        self._log("delete", instance)
        instance.delete()

    @action(detail=False, methods=["get"], url_path="test", url_name="test")
    def test_url(self, request):
        """GET ?path=/old-page?x=1 — what a visitor of that address gets."""
        path = request.query_params.get("path", "")
        if not path.strip():
            raise ValidationError({"path": _("Enter a path or an address on this site.")})
        return Response(redirects.describe(path))

    @action(detail=False, methods=["post"], url_path="check")
    def check(self, request):
        """The form's live validation: the rules of a save, nothing written.
        Pass `id` when editing."""
        data = request.data
        pk = data.get("id")
        instance = SeoRedirect.objects.filter(pk=pk).first() if str(pk or "").isdigit() else None
        serializer = SeoRedirectSerializer(instance, data=data, partial=instance is not None)
        valid = serializer.is_valid()
        try:
            normalized = redirects.normalize_source(
                data.get("source_path", getattr(instance, "source_path", ""))
            )
        except redirects.RedirectPathError:
            normalized = ""
        return Response({"valid": valid, "source_path": normalized, "errors": serializer.errors})

    @action(detail=False, methods=["post"], url_path="import", url_name="import")
    def import_csv(self, request):
        """POST a CSV (`file`, or `csv` text) of source,target,status lines.
        `dry_run` reports each row and writes nothing; otherwise every row
        is created, or none when any row has an error."""
        upload = request.FILES.get("file")
        if upload is not None:
            if upload.size > IMPORT_MAX_BYTES:
                raise ValidationError({"file": _("The file is too large.")})
            try:
                text = upload.read().decode("utf-8-sig")
            except UnicodeDecodeError:
                raise ValidationError({"file": _("Save the file as UTF-8 CSV.")}) from None
        else:
            text = str(request.data.get("csv") or "")
            if len(text.encode("utf-8")) > IMPORT_MAX_BYTES:
                raise ValidationError({"file": _("The file is too large.")})
            text = text.lstrip("﻿")
        report = import_report(text)
        if not report["total"]:
            raise ValidationError({"file": _("The file has no redirect lines.")})
        dry_run = _truthy(request.data.get("dry_run", ""))
        report.update(dry_run=dry_run, created=0)
        if dry_run:
            return Response(report)
        if report["invalid"]:
            return Response(report, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            for row in report["rows"]:
                SeoRedirect.objects.create(
                    source_path=row["source_path"], target=row["target"].strip(),
                    status_code=row["status_code"], created_by=request.user,
                    note=_("Imported from CSV"),
                )
        report["created"] = report["total"]
        log_activity(
            action="import", request=request, entity_type="SeoRedirect", entity_id="",
            metadata={"label": "CSV", "created": report["created"]},
        )
        return Response(report, status=status.HTTP_201_CREATED)
