import uuid

from datetime import timedelta

from django.db import models
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.renderers import StaticHTMLRenderer
from rest_framework.response import Response
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.views import APIView

from core.activity import log_activity
from core import platform_roles
from core.permissions import IsPlatformAdmin
from core.rbac import RoleModuleAccess
from core.scoping import CompanyScopedModelViewSet
from org.models import Company
from subscriptions.models import PlanVersion, Subscription, SubscriptionPayment
from website.images import (
    COVER_SIDE, LOGO_SIDE, PHOTO_SIDE, clear_image, prepare_image, replace_image,
)
from website.models import (
    FeaturedProduct, PlatformLead, RegistrationRequest, Section, Website, WebsiteImage,
)
from website.serializers import (
    FeaturedProductSerializer,
    OwnerInvitationAcceptSerializer,
    PlatformLeadSerializer,
    PlatformRegistrationRequestSerializer,
    PublicPlanVersionSerializer,
    PublicSiteSerializer,
    RegistrationRequestSerializer,
    SectionSerializer,
    WebsiteSerializer, WebsiteImageSerializer,
)
from website.services import (
    accept_owner_invitation,
    plan_version_is_available,
    provision_registration_request,
    reissue_owner_invitation,
)


class PlatformLeadViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Platform sales inbox, kept separate from every tenant CRM."""

    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    platform_capability = platform_roles.LEADS_MANAGE
    platform_view_capability = platform_roles.LEADS_VIEW
    serializer_class = PlatformLeadSerializer
    queryset = PlatformLead.objects.all()

    def get_queryset(self):
        queryset = super().get_queryset()
        status_value = self.request.query_params.get("status")
        search = self.request.query_params.get("search", "").strip()
        if status_value:
            queryset = queryset.filter(status=status_value)
        if search:
            queryset = queryset.filter(
                models.Q(name__icontains=search)
                | models.Q(email__icontains=search)
                | models.Q(message__icontains=search)
            )
        return queryset


class PlatformOverviewView(APIView):
    """Commercial SaaS operating summary, never tenant operational data."""

    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    entitlement_exempt = True

    def get(self, request):
        now = timezone.now()
        soon = now + timedelta(days=7)
        registrations = RegistrationRequest.objects.select_related("plan_version__plan")
        subscriptions = Subscription.objects.select_related("company", "plan_version__plan")
        payment_count = SubscriptionPayment.objects.filter(
            status=SubscriptionPayment.PENDING
        ).count()
        trial_expiring = subscriptions.filter(
            status=Subscription.TRIALING,
            trial_ends_at__gte=now,
            trial_ends_at__lte=soon,
        )
        period_expiring = subscriptions.filter(
            status__in=[Subscription.ACTIVE, Subscription.GRACE],
            period_ends_at__gte=now,
            period_ends_at__lte=soon,
        )
        attention = registrations.filter(
            status__in=[
                RegistrationRequest.SUBMITTED,
                RegistrationRequest.UNDER_REVIEW,
                RegistrationRequest.NEEDS_INFORMATION,
                RegistrationRequest.APPROVED,
            ]
        )
        return Response(
            {
                "counts": {
                    "registration_attention": attention.count(),
                    "provisioned_companies": subscriptions.count(),
                    "trialing": subscriptions.filter(status=Subscription.TRIALING).count(),
                    "active": subscriptions.filter(status=Subscription.ACTIVE).count(),
                    "pending_payments": payment_count,
                    "expiring_within_7_days": trial_expiring.count() + period_expiring.count(),
                },
                "registration_attention": PlatformRegistrationRequestSerializer(
                    attention.order_by("created_at")[:6], many=True
                ).data,
                "expiring_subscriptions": [
                    {
                        "id": item.id,
                        "company_name": item.company.name,
                        "status": item.status,
                        "ends_at": item.trial_ends_at or item.period_ends_at,
                    }
                    for item in list(trial_expiring) + list(period_expiring)
                ][:6],
            }
        )


class PublicPlanListView(APIView):
    """Public commercial information; only explicitly published plans appear."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        plans = PlanVersion.objects.select_related("plan").filter(
            plan__is_active=True, plan__is_public=True, published_at__isnull=False
        ).order_by("plan__sort_order", "plan__name", "-version")
        latest = {}
        for version in plans:
            latest.setdefault(version.plan_id, version)
        return Response(PublicPlanVersionSerializer(latest.values(), many=True).data)


class PublicRegistrationRequestView(APIView):
    """Accept a SaaS or standalone enquiry without exposing tenant accounts."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get_throttles(self):
        from rest_framework.throttling import AnonRateThrottle

        class RegistrationThrottle(AnonRateThrottle):
            scope = "registration_request"
            rate = "3/hour"

        return [RegistrationThrottle()]

    def post(self, request):
        serializer = RegistrationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        request_uuid = data.get("request_uuid") or uuid.uuid4()
        data["request_uuid"] = request_uuid
        registration, created = RegistrationRequest.objects.get_or_create(
            request_uuid=request_uuid, defaults=data
        )
        return Response(
            {"reference": str(registration.request_uuid), "status": registration.status},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PlatformRegistrationRequestViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Commercial inbox for tenant sign-up, deliberately separate from CRM."""

    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    platform_capability = platform_roles.REGISTRATIONS_REVIEW
    platform_view_capability = platform_roles.REGISTRATIONS_VIEW
    platform_action_capabilities = {
        "provision": platform_roles.REGISTRATIONS_PROVISION,
        "reissue_invitation": platform_roles.INVITATIONS_REISSUE,
    }
    entitlement_exempt = True
    serializer_class = PlatformRegistrationRequestSerializer
    queryset = RegistrationRequest.objects.select_related(
        "plan_version__plan", "company", "reviewed_by"
    )

    def get_queryset(self):
        queryset = super().get_queryset()
        status_value = self.request.query_params.get("status")
        if status_value:
            queryset = queryset.filter(status=status_value)
        return queryset

    def perform_update(self, serializer):
        registration = serializer.save()
        log_activity(
            action="update", request=self.request, entity_type="RegistrationRequest",
            entity_id=registration.pk, metadata={"fields": sorted(serializer.validated_data)},
        )

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        registration = self.get_object()
        target = request.data.get("status")
        allowed = {
            RegistrationRequest.UNDER_REVIEW,
            RegistrationRequest.NEEDS_INFORMATION,
            RegistrationRequest.REJECTED,
        }
        if target not in allowed or registration.status in {
            RegistrationRequest.PROVISIONED,
            RegistrationRequest.WITHDRAWN,
            RegistrationRequest.REJECTED,
        }:
            return Response(
                {"detail": "This status transition is not allowed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        registration.status = target
        registration.internal_note = request.data.get(
            "internal_note", registration.internal_note
        )
        registration.mark_reviewed(request.user)
        registration.save(
            update_fields=[
                "status", "internal_note", "reviewed_by", "reviewed_at", "updated_at"
            ]
        )
        log_activity(
            action="update", request=request, entity_type="RegistrationRequest",
            entity_id=registration.pk, metadata={"status": target},
        )
        return Response(self.get_serializer(registration).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        registration = self.get_object()
        if registration.status not in {
            RegistrationRequest.SUBMITTED,
            RegistrationRequest.UNDER_REVIEW,
            RegistrationRequest.NEEDS_INFORMATION,
        }:
            return Response(
                {"detail": "This request cannot be approved from its current state."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if registration.delivery_mode == RegistrationRequest.SAAS:
            if not registration.plan_version_id:
                return Response(
                    {"detail": "Choose a published plan before approval."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not plan_version_is_available(registration.plan_version):
                return Response(
                    {"detail": "The selected plan is no longer available; pick another plan."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        registration.status = RegistrationRequest.APPROVED
        registration.internal_note = request.data.get(
            "internal_note", registration.internal_note
        )
        registration.mark_reviewed(request.user)
        registration.save(
            update_fields=[
                "status", "internal_note", "reviewed_by", "reviewed_at", "updated_at"
            ]
        )
        log_activity(
            action="approve", request=request, entity_type="RegistrationRequest",
            entity_id=registration.pk,
        )
        return Response(self.get_serializer(registration).data)

    @action(detail=True, methods=["post"])
    def provision(self, request, pk=None):
        try:
            registration, invite_token = provision_registration_request(
                pk, request.user, request
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        payload = self.get_serializer(registration).data
        # Delivery is intentionally not implemented here. The platform operator
        # receives the one-time token only in this privileged response.
        if invite_token:
            payload["owner_invitation_token"] = invite_token
        return Response(
            payload,
            status=status.HTTP_201_CREATED if invite_token else status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="reissue-invitation")
    def reissue_invitation(self, request, pk=None):
        try:
            registration, invite_token = reissue_owner_invitation(pk, request.user, request)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        payload = self.get_serializer(registration).data
        payload["owner_invitation_token"] = invite_token
        return Response(payload, status=status.HTTP_201_CREATED)


class OwnerInvitationAcceptView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get_throttles(self):
        from rest_framework.throttling import AnonRateThrottle

        class InvitationThrottle(AnonRateThrottle):
            scope = "owner_invitation_accept"
            rate = "10/hour"

        return [InvitationThrottle()]

    def post(self, request):
        serializer = OwnerInvitationAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            owner = accept_owner_invitation(
                serializer.validated_data["token"],
                serializer.validated_data["password"],
                request,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"email": owner.email, "company": owner.company_id, "status": "activated"}
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


class WebsitePreviewView(APIView):
    """GET the caller's own landing page as HTML, published or not, for the
    editor's preview pane. Never indexed, never cached. The editor shows it
    in an iframe on the same origin, so the clickjacking header allows that
    one origin instead of the site-wide DENY."""

    permission_classes = [IsAuthenticated, RoleModuleAccess]
    rbac_module = "website"
    renderer_classes = [StaticHTMLRenderer]

    def get(self, request):
        from website.public_pages import render_site

        site = WebsiteView()._get_site(request)
        response = render_site(request, site, preview=True)
        response["X-Frame-Options"] = "SAMEORIGIN"
        response["Content-Security-Policy"] = "frame-ancestors 'self'"
        return response


class WebsiteImageUploadView(APIView):
    """POST an `image` (multipart) to set the site's cover or logo; DELETE to
    remove it. The file is validated, resized and stored as WebP under the
    public media subtree (website.images)."""

    permission_classes = [IsAuthenticated, RoleModuleAccess]
    rbac_module = "website"
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    FIELDS = {"cover": ("cover_image", COVER_SIDE, False), "logo": ("logo_image", LOGO_SIDE, True)}

    def _site(self, request):
        return WebsiteView()._get_site(request)

    def post(self, request, kind):
        field, side, square = self.FIELDS[kind]
        site = self._site(request)
        content = prepare_image(request.FILES.get("image"), side, square=square)
        replace_image(site, field, content)
        log_activity(
            action="update", request=request, entity_type="Website", entity_id=site.id,
            metadata={"image": kind},
        )
        return Response(WebsiteSerializer(site, context={"request": request}).data)

    def delete(self, request, kind):
        field, _, _ = self.FIELDS[kind]
        site = self._site(request)
        clear_image(site, field)
        log_activity(
            action="update", request=request, entity_type="Website", entity_id=site.id,
            metadata={"image": kind, "removed": True},
        )
        return Response(WebsiteSerializer(site, context={"request": request}).data)


class WebsiteImageViewSet(CompanyScopedModelViewSet):
    """Gallery photos. Create with a multipart `image`; PATCH caption/order."""

    queryset = WebsiteImage.objects.select_related("website").all()
    serializer_class = WebsiteImageSerializer
    activity_entity_type = "WebsiteImage"
    manager_only_delete = False
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    rbac_module = "website"

    def perform_create(self, serializer):
        content = prepare_image(self.request.FILES.get("image"), PHOTO_SIDE)
        site = WebsiteView()._get_site(self.request)
        # The scoped base stamps company_id and the logging mixin records the
        # create; only the processed image and the site are added here.
        serializer.validated_data["website"] = site
        serializer.validated_data["image"] = content
        super().perform_create(serializer)

    def perform_destroy(self, instance):
        if instance.image:
            instance.image.delete(save=False)
        super().perform_destroy(instance)


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
    """Save platform enquiries in the platform lead inbox.

    These leads are intentionally not tenant CRM records. Retries reuse the
    request UUID; nothing is returned other than that public reference.
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
        from django.db import transaction
        from website.models import PlatformLead
        from website.serializers import DemoRequestSerializer

        serializer = DemoRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            reference = str(data["request_uuid"])
            PlatformLead.objects.get_or_create(
                request_uuid=data["request_uuid"],
                defaults={
                    "name": data["name"],
                    "email": data["email"],
                    "message": data.get("message", ""),
                },
            )
        return Response({"reference": reference, "status": "saved"}, status=201)
