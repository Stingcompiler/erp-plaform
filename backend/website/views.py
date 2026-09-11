from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.activity import log_activity
from core.rbac import RoleModuleAccess
from core.scoping import CompanyScopedModelViewSet
from org.models import Company
from website.models import FeaturedProduct, Section, Website
from website.serializers import (
    FeaturedProductSerializer,
    PublicSiteSerializer,
    SectionSerializer,
    WebsiteSerializer,
)


class WebsiteView(APIView):
    """
    Singleton per company: GET returns (creating if needed) the company's
    Website; PATCH updates content; publish/unpublish flip visibility.
    """

    permission_classes = [IsAuthenticated, RoleModuleAccess]
    rbac_module = "website"

    def _get_site(self, request):
        company_id = getattr(request.user, "company_id", None)
        name = self._company_name(company_id)
        site, created = Website.objects.get_or_create(
            company_id=company_id,
            defaults={"business_name": name},
        )
        if created:
            # Auto-generate a starter site so there's something to edit/publish.
            Section.objects.bulk_create([
                Section(
                    company_id=company_id, website=site, type=Section.HERO,
                    title=name, order=0,
                    content={"headline": name, "subtitle": "Welcome"},
                ),
                Section(
                    company_id=company_id, website=site, type=Section.ABOUT,
                    title="About us", order=1, content={"text": ""},
                ),
                Section(
                    company_id=company_id, website=site, type=Section.CONTACT,
                    title="Contact", order=2, content={},
                ),
            ])
        return site

    def _company_name(self, company_id):
        if company_id is None:
            return ""
        try:
            return Company.objects.get(pk=company_id).name
        except Company.DoesNotExist:
            return ""

    def get(self, request):
        site = self._get_site(request)
        return Response(WebsiteSerializer(site, context={"request": request}).data)

    def patch(self, request):
        site = self._get_site(request)
        serializer = WebsiteSerializer(
            site, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log_activity(
            action="update", request=request, entity_type="Website",
            entity_id=site.id,
        )
        return Response(serializer.data)


class WebsitePublishView(APIView):
    permission_classes = [IsAuthenticated, RoleModuleAccess]
    rbac_module = "website"

    def post(self, request):
        company_id = getattr(request.user, "company_id", None)
        site, _ = Website.objects.get_or_create(company_id=company_id)
        publish = request.data.get("publish", True)
        site.is_published = bool(publish)
        site.published_at = timezone.now() if publish else None
        site.save(update_fields=["is_published", "published_at"])
        log_activity(
            action="update", request=request, entity_type="Website",
            entity_id=site.id, metadata={"is_published": site.is_published},
        )
        return Response(WebsiteSerializer(site, context={"request": request}).data)


# Landing-page content, not records: building a page means adding and removing
# blocks, and the Website Manager who owns that work is not a manager-level role
# in the RBAC sense. Deletions here are still audited.
class SectionViewSet(CompanyScopedModelViewSet):
    queryset = Section.objects.select_related("website").all()
    serializer_class = SectionSerializer
    activity_entity_type = "Section"
    manager_only_delete = False


class FeaturedProductViewSet(CompanyScopedModelViewSet):
    queryset = FeaturedProduct.objects.select_related("product", "website").all()
    serializer_class = FeaturedProductSerializer
    activity_entity_type = "FeaturedProduct"
    manager_only_delete = False


class PublicSiteView(APIView):
    """
    GET /api/public/site/<slug>/ — UNAUTHENTICATED. Serves a company's public
    landing page by slug, but only if published, and only public-safe fields.
    No auth, no RBAC; resolves exactly one company by slug.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, slug):
        try:
            company = Company.objects.get(slug=slug, is_active=True)
        except Company.DoesNotExist:
            return Response(
                {"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND
            )
        site = getattr(company, "website", None)
        if site is None or not site.is_published:
            return Response(
                {"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(PublicSiteSerializer(site).data)


class DemoRequestView(APIView):
    """Save platform enquiries to the explicitly configured owner's CRM.

    No tenant ID is accepted from visitors. Retries reuse the request UUID;
    nothing is returned other than that public reference.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get_throttles(self):
        from rest_framework.throttling import AnonRateThrottle

        class DemoThrottle(AnonRateThrottle):
            scope = "demo_request"
            rate = "5/hour"

        return [DemoThrottle()]

    def post(self, request):
        from django.conf import settings
        from django.db import transaction
        from crm.models import Lead, Note
        from website.serializers import DemoRequestSerializer

        serializer = DemoRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        owner_slug = getattr(settings, "DEMO_REQUEST_COMPANY_SLUG", "")
        if not owner_slug:
            return Response({"detail": "Demo requests are not configured."}, status=503)
        with transaction.atomic():
            owner = Company.objects.select_for_update().filter(
                slug=owner_slug, is_active=True,
            ).first()
            if owner is None:
                return Response({"detail": "Demo requests are not configured."}, status=503)
            reference = str(data["request_uuid"])
            source = f"platform-demo:{reference}"
            lead = Lead.objects.filter(company=owner, source=source).first()
            if lead is None:
                lead = Lead.objects.create(
                    company=owner,
                    source=source,
                    name=data["name"],
                    contact_name=data["name"],
                    email=data["email"])
                log_activity(action="create", company=owner, request=request,
                             entity_type="Lead", entity_id=lead.pk)
                if data.get("message"):
                    note = Note.objects.create(company=owner, lead=lead, body=data["message"])
                    log_activity(action="create", company=owner, request=request,
                                 entity_type="Note", entity_id=note.pk)
        return Response({"reference": reference, "status": "saved"}, status=201)
