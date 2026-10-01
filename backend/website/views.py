import uuid

from datetime import timedelta

from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.db.models import Q
from django.http import Http404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle
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
from website.followups import CONTACT_CHANNELS
from website.models import (
    PublicOrder,
    PushSubscription,
    FeaturedProduct, PlatformLead, RegistrationRequest, Section, Website, WebsiteImage,
)
from website.serializers import (
    PublicOrderSerializer,
    FeaturedProductSerializer,
    OwnerInvitationAcceptSerializer,
    PlatformLeadSerializer,
    PlatformRegistrationRequestSerializer,
    PublicPlanCycleSerializer,
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


def _record_contact(view, request, entity_type):
    channel = request.data.get("channel")
    if channel not in CONTACT_CHANNELS:
        return Response({"channel": "Unknown channel."}, status=status.HTTP_400_BAD_REQUEST)
    obj = view.get_object()
    obj.record_contact(channel)
    log_activity(
        action="contact", request=request, entity_type=entity_type, entity_id=obj.pk,
        metadata={"channel": channel, "label": getattr(obj, "name", None)
                  or getattr(obj, "company_name", "")},
    )
    return Response(view.get_serializer(obj).data)


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

    def perform_update(self, serializer):
        before = serializer.instance.status
        serializer.save()
        lead = serializer.instance
        log_activity(
            action="update", request=self.request, entity_type="PlatformLead",
            entity_id=lead.pk,
            metadata={
                "label": lead.name,
                "status_from": before, "status_to": lead.status,
                "fields": sorted(serializer.validated_data),
            },
        )

    def get_queryset(self):
        queryset = super().get_queryset()
        status_value = self.request.query_params.get("status")
        search = self.request.query_params.get("search", "").strip()
        if status_value:
            queryset = queryset.filter(status=status_value)
        if self.request.query_params.get("due"):
            queryset = queryset.filter(next_follow_up_at__lte=timezone.now()).exclude(
                status=PlatformLead.STATUS_CLOSED
            )
        if search:
            queryset = queryset.filter(
                models.Q(name__icontains=search)
                | models.Q(public_reference__iexact=search)
                | models.Q(email__icontains=search)
                | models.Q(phone__icontains=search)
                | models.Q(message__icontains=search)
                | models.Q(internal_note__icontains=search)
            )
        return queryset

    @action(detail=True, methods=["post"])
    def contact(self, request, pk=None):
        """A member reached out (opened the call/WhatsApp/email link)."""
        return _record_contact(self, request, "PlatformLead")


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
                # Who on the team is here right now; only for members who may
                # see the team list. Others get no key at all.
                **(
                    {"team": self._team(now)}
                    if platform_roles.user_has_platform_capability(
                        request.user, platform_roles.TEAM_VIEW
                    )
                    else {}
                ),
            }
        )

    @staticmethod
    def _team(now):
        from accounts.platform_team import platform_members
        from accounts.presence import is_online

        members = platform_members().filter(is_active=True)
        rows = [
            {
                "id": member.pk,
                "full_name": member.full_name,
                "email": member.email,
                "role_name": member.role.name if member.role_id else (
                    "Django superuser" if member.is_superuser else ""
                ),
                "online": is_online(member, now),
                "last_seen_at": member.last_seen_at,
                "last_login": member.last_login,
            }
            for member in members
        ]
        # Online first, then most recently seen.
        rows.sort(
            key=lambda r: (
                not r["online"], -(r["last_seen_at"].timestamp() if r["last_seen_at"] else 0)
            )
        )
        return rows


class PublicPlanListView(APIView):
    """Public commercial information; only explicitly published plans appear."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        plans = PlanVersion.objects.select_related("plan").filter(
            plan__is_active=True, plan__is_public=True, published_at__isnull=False
        ).order_by("plan__sort_order", "plan__name", "-version")
        latest = {}
        # plan -> cycle -> its newest published, non-legacy version: what the
        # pricing page's monthly/yearly switch offers. A plan has a cycle
        # only when such a version really exists; nothing is derived.
        by_cycle = {}
        for version in plans:
            latest.setdefault(version.plan_id, version)
            if not version.is_legacy:
                by_cycle.setdefault(version.plan_id, {}).setdefault(
                    version.billing_cycle, version
                )
        # The operator's sort_order first; plans left on the same order read
        # cheapest to dearest rather than alphabetically by working name.
        ordered = sorted(
            latest.values(),
            key=lambda version: (version.plan.sort_order, version.price, version.plan.name),
        )
        rows = PublicPlanVersionSerializer(ordered, many=True).data
        for version, row in zip(ordered, rows):
            # The row itself is the offer for its own cycle.
            cycles = {**by_cycle.get(version.plan_id, {}), version.billing_cycle: version}
            row["cycles"] = {
                cycle: PublicPlanCycleSerializer(offer).data
                for cycle, offer in sorted(cycles.items())
            }
        return Response(rows)


def _public_throttle(scope_name, rate_value):
    """A per-address throttle for one public endpoint (its own budget)."""
    from rest_framework.throttling import AnonRateThrottle

    return type(
        f"{scope_name.title().replace('_', '')}Throttle", (AnonRateThrottle,),
        {"scope": scope_name, "rate": rate_value},
    )


TrialStartThrottle = _public_throttle("trial_start", "10/hour")
TrialVerifyThrottle = _public_throttle("trial_verify", "30/hour")
TrialResendThrottle = _public_throttle("trial_resend", "10/hour")
TrackRequestThrottle = _public_throttle("track_request", "20/hour")
TrackVerifyThrottle = _public_throttle("track_verify", "30/hour")
TrackResendThrottle = _public_throttle("track_resend", "10/hour")
TrackViewThrottle = _public_throttle("track_view", "120/hour")


def _otp_error(code, http_status, **extra):
    """One shape for every refusal of the code flows: a stable ``code`` the
    page translates, a server-side ``detail`` and any numbers it needs."""
    messages = {
        "code_expired": _("This code has expired. Ask for a new one."),
        "wrong_code": _("That code is not right. Check the email and try again."),
        "too_many_attempts": _("Too many wrong codes. Ask for a new one."),
        "resend_cooldown": _("Wait a moment before asking for another code."),
        "too_many_codes": _("Too many codes were sent. Try again later."),
        "email_unavailable": _(
            "We could not send the code right now. Try again later or message us on WhatsApp."
        ),
        "view_expired": _("This view has expired. Search again to get a new code."),
    }
    body = {"code": code, "detail": messages.get(code, code), **extra}
    response = Response(body, status=http_status)
    if extra.get("retry_after"):
        response["Retry-After"] = str(extra["retry_after"])
    return response


def _registration_payload(registration):
    return {
        "reference": str(registration.request_uuid),
        # What the applicant quotes and searches on vezano.app/track/.
        "public_reference": registration.public_reference,
        "track_url": _track_url(),
        "status": registration.status,
    }


def _code_sent(pending_id, email):
    from core import otp

    return Response({
        "pending_id": pending_id,
        "email_masked": otp.mask_email(email),
        "resend_after": otp.RESEND_AFTER,
        "expires_in": otp.CODE_TTL,
    }, status=status.HTTP_202_ACCEPTED)


def _otp_failure(exc):
    """The answer for a core.otp error, or None when ``exc`` is not one."""
    from core import otp

    if isinstance(exc, (otp.Cooldown, otp.TooManySends)):
        return _otp_error(exc.code, 429, retry_after=exc.retry_after)
    if isinstance(exc, otp.WrongCode):
        return _otp_error(exc.code, 400, attempts_left=exc.attempts_left)
    if isinstance(exc, (otp.Expired, otp.TooManyAttempts)):
        return _otp_error(exc.code, 400)
    if isinstance(exc, otp.DeliveryFailed):
        from website.trial_requests import support_whatsapp

        return _otp_error(exc.code, 503, whatsapp=support_whatsapp())
    return None


class PublicRegistrationRequestView(APIView):
    """POST /api/public/registration-requests/ — the public trial form.

    Validates, refuses a duplicate of an open or provisioned request (409),
    then emails a 6-digit code and keeps the form in the cache (202); the
    request itself is created by ``…/verify/`` (website.trial_requests)."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [TrialStartThrottle]

    def post(self, request):
        from core import otp
        from website import trial_requests

        serializer = RegistrationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        data["request_uuid"] = data.get("request_uuid") or uuid.uuid4()
        # A replay of a request already created answers as it did then.
        existing = RegistrationRequest.objects.filter(request_uuid=data["request_uuid"]).first()
        if existing is not None:
            return Response(_registration_payload(existing), status=status.HTTP_200_OK)
        duplicate = trial_requests.find_duplicate(data)
        if duplicate is not None:
            trial_requests.notify_existing(duplicate)
            return Response(trial_requests.duplicate_payload(), status=status.HTTP_409_CONFLICT)
        email = data["email"].strip()
        try:
            pending_id = trial_requests.start(trial_requests.stored_form(data), email, request)
        except otp.OtpError as exc:
            return _otp_failure(exc)
        return _code_sent(pending_id, email)


class PublicRegistrationVerifyView(APIView):
    """POST …/verify/ {pending_id, code} — creates the request (201) once
    the emailed code matches; 5 tries, then the pending form is gone."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [TrialVerifyThrottle]

    def post(self, request):
        from core import otp
        from website import trial_requests

        data = request.data if isinstance(request.data, dict) else {}
        pending_id = str(data.get("pending_id") or "")
        try:
            # Kept until it expires, so a replayed verify (the first answer
            # lost on the way back) still finds its request.
            payload = otp.verify(pending_id, data.get("code"), purpose=trial_requests.PURPOSE,
                                 consume=False)
        except otp.OtpError as exc:
            return _otp_failure(exc)
        form = payload["form"]
        existing = RegistrationRequest.objects.filter(request_uuid=form["request_uuid"]).first()
        if existing is not None:
            return Response(_registration_payload(existing), status=status.HTTP_200_OK)
        serializer = RegistrationRequestSerializer(data=form)
        if not serializer.is_valid():
            otp.drop(pending_id)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        validated = serializer.validated_data
        validated["request_uuid"] = uuid.UUID(str(form["request_uuid"]))
        duplicate = trial_requests.find_duplicate(validated)
        if duplicate is not None:
            otp.drop(pending_id)
            trial_requests.notify_existing(duplicate)
            return Response(trial_requests.duplicate_payload(), status=status.HTTP_409_CONFLICT)
        registration, created = trial_requests.create(validated)
        return Response(
            _registration_payload(registration),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PublicRegistrationResendView(APIView):
    """POST …/resend/ {pending_id} — a new code after 60 s, 3 an hour."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [TrialResendThrottle]

    def post(self, request):
        from core import otp
        from website import trial_requests

        data = request.data if isinstance(request.data, dict) else {}
        pending_id = str(data.get("pending_id") or "")
        try:
            payload = trial_requests.resend(pending_id, request)
        except otp.OtpError as exc:
            return _otp_failure(exc)
        return _code_sent(pending_id, payload["email"])


def _track_url():
    from website.public_pages import site_url

    return site_url("/track/")


def _email_request_received(registration):
    """Best-effort acknowledgement so the visitor finds something in their
    inbox right away; the activation link follows once the request is
    reviewed. The mailer logs failures instead of raising."""
    from core import mailer

    return mailer.send_bilingual(
        subject_ar="استلمنا طلبك في فيزانو برو",
        subject_en="We received your Vezano Pro request",
        ar=[
            f"مرحباً {registration.contact_name}،",
            f"استلمنا طلب «{registration.company_name}» وسنراجعه قريبًا.",
            "عند الموافقة يصلك رابط تفعيل حساب المالك على هذا البريد.",
            f"رقم الطلب: {registration.public_reference}",
            "تابع حالة طلبك في أي وقت برقم الطلب أو بريدك أو هاتفك من الرابط أدناه.",
        ],
        en=[
            f"Hello {registration.contact_name},",
            f"We received the request for “{registration.company_name}” "
            "and will review it shortly.",
            "Once approved, the owner activation link arrives at this address.",
            f"Request reference: {registration.public_reference}",
            "Follow your request any time with this reference, your email or your phone "
            "at the link below.",
        ],
        link=_track_url(),
        recipient=registration.email,
    )


def _email_owner_invitation(registration, token):
    """Best-effort delivery of the activation link to the future owner.

    Returns whether an email actually went out, so the operator UI can say
    "sent" or keep instructing the operator to deliver the link by hand.
    """
    from core import mailer

    link = mailer.activation_link(token)
    if not link:
        return False
    return mailer.send_bilingual(
        subject_ar="تفعيل حساب مالك فيزانو برو",
        subject_en="Activate your Vezano Pro owner account",
        ar=[
            f"مرحباً {registration.contact_name}،",
            f"تمت الموافقة على تسجيل «{registration.company_name}» في فيزانو برو.",
            "فعّل حساب المالك من الرابط أدناه (صالح لمرة واحدة).",
            "إن لم تكن طلبت هذا التسجيل فتجاهل الرسالة.",
        ],
        en=[
            f"Hello {registration.contact_name},",
            f"Your Vezano Pro workspace for “{registration.company_name}” is ready.",
            "Activate the owner account with the one-time link below.",
            "If you did not request this, ignore this email.",
        ],
        link=link,
        recipient=registration.email,
    )


# A request in these states became (or is about to become) a company: it is
# the company's history, removed only by deleting the company.
UNDELETABLE_REGISTRATIONS = {RegistrationRequest.APPROVED, RegistrationRequest.PROVISIONED}


def registration_delete_refusal(registration):
    """Why ``registration`` may not be deleted, or None."""
    if registration.company_id or registration.status == RegistrationRequest.PROVISIONED:
        return _(
            "This request was activated into a company. Delete the company from the "
            "companies page instead."
        )
    if registration.status == RegistrationRequest.APPROVED:
        return _("This request is approved. Reject it first if it should not go ahead.")
    return None


def delete_registration(registration, request):
    """Delete one request, keeping only its reference and name in the log."""
    log_activity(
        action="delete", request=request, entity_type="RegistrationRequest",
        entity_id=registration.pk,
        metadata={
            "reference": registration.public_reference or "",
            "company_name": registration.company_name,
            "status": registration.status,
        },
    )
    registration.delete()


class PlatformRegistrationRequestViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Commercial inbox for tenant sign-up, deliberately separate from CRM."""

    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    platform_capability = platform_roles.REGISTRATIONS_REVIEW
    platform_view_capability = platform_roles.REGISTRATIONS_VIEW
    platform_action_capabilities = {
        "provision": platform_roles.REGISTRATIONS_PROVISION,
        "reissue_invitation": platform_roles.INVITATIONS_REISSUE,
        # Noting that one reached out is open to whoever may see the request.
        "contact": platform_roles.REGISTRATIONS_VIEW,
        # Spam and duplicates: the platform owner's call by default.
        "destroy": platform_roles.REGISTRATIONS_DELETE,
        "bulk_delete": platform_roles.REGISTRATIONS_DELETE,
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
        if self.request.query_params.get("due"):
            queryset = queryset.filter(next_follow_up_at__lte=timezone.now()).exclude(
                status__in=[
                    RegistrationRequest.PROVISIONED, RegistrationRequest.REJECTED,
                    RegistrationRequest.WITHDRAWN,
                ]
            )
        return queryset

    @action(detail=True, methods=["post"])
    def contact(self, request, pk=None):
        return _record_contact(self, request, "RegistrationRequest")

    def destroy(self, request, *args, **kwargs):
        registration = self.get_object()
        refusal = registration_delete_refusal(registration)
        if refusal:
            return Response(
                {"code": "registration_in_use", "detail": refusal},
                status=status.HTTP_400_BAD_REQUEST,
            )
        delete_registration(registration, request)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        """Delete several requests at once (the rejected pile, spam). Only
        rejected and withdrawn requests go this way; anything else is
        reported back as skipped."""
        ids = request.data.get("ids")
        if not isinstance(ids, list) or not ids or len(ids) > 500:
            return Response(
                {"ids": _("Send the list of requests to delete (at most 500).")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        deleted, skipped = [], []
        with transaction.atomic():
            for registration in RegistrationRequest.objects.select_for_update().filter(
                pk__in=[i for i in ids if isinstance(i, int)]
            ):
                if registration.status not in (
                    RegistrationRequest.REJECTED, RegistrationRequest.WITHDRAWN,
                ) or registration_delete_refusal(registration):
                    skipped.append(registration.pk)
                    continue
                pk = registration.pk
                delete_registration(registration, request)
                deleted.append(pk)
        return Response({"deleted": deleted, "skipped": skipped})

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
                {"detail": _("This status transition is not allowed.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        registration.status = target
        registration.internal_note = request.data.get(
            "internal_note", registration.internal_note
        )
        if target in (RegistrationRequest.REJECTED, RegistrationRequest.NEEDS_INFORMATION):
            # What the applicant reads on vezano.app/track/.
            registration.public_note = str(request.data.get("public_note") or "").strip()[:1000]
        registration.mark_reviewed(request.user)
        registration.save(
            update_fields=[
                "status", "internal_note", "public_note", "reviewed_by", "reviewed_at",
                "updated_at",
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
                {"detail": _("This request cannot be approved from its current state.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if registration.delivery_mode == RegistrationRequest.SAAS:
            if not registration.plan_version_id:
                return Response(
                    {"detail": _("Choose a published plan before approval.")},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not plan_version_is_available(registration.plan_version):
                return Response(
                    {"detail": _("The selected plan is no longer available; pick another plan.")},
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
        # The operator always receives the one-time token in this privileged
        # response and stays responsible for delivery; when SMTP is
        # configured the same link is also emailed to the owner directly.
        if invite_token:
            payload["owner_invitation_token"] = invite_token
            payload["invitation_email_sent"] = _email_owner_invitation(
                registration, invite_token
            )
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
        payload["invitation_email_sent"] = _email_owner_invitation(
            registration, invite_token
        )
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
                {"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND
            )
        site = getattr(company, "website", None)
        if site is None or not site.is_published:
            return Response(
                {"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND
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
        from website.models import PlatformLead
        from website.serializers import DemoRequestSerializer

        serializer = DemoRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            reference = str(data["request_uuid"])
            lead, _created = PlatformLead.objects.get_or_create(
                request_uuid=data["request_uuid"],
                defaults={
                    "name": data["name"],
                    "email": data["email"],
                    "phone": data.get("phone", ""),
                    "preferred_channel": data["preferred_channel"],
                    "message": data.get("message", ""),
                },
            )
            if _created:
                # Queued for after the commit; a replay of the same
                # request_uuid finds the lead and announces nothing.
                from core import team_notify

                team_notify.lead_submitted(lead)
        return Response({
            "reference": reference, "public_reference": lead.public_reference,
            "track_url": _track_url(), "status": "saved",
        }, status=201)


class PublicOrderCreateView(APIView):
    """POST /api/public/site/<slug>/orders/ — UNAUTHENTICATED. A visitor's
    order from the company's page. Throttled per address; a filled honeypot
    field (``website_url``) is silently accepted and dropped."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_order"

    def post(self, request, slug):
        from website.orders import place_order, whatsapp_number

        try:
            company = Company.objects.get(slug=slug, is_active=True)
        except Company.DoesNotExist:
            return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        site = getattr(company, "website", None)
        if site is None or not site.is_published or not site.accept_orders:
            return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        if not isinstance(request.data, dict):
            return Response(
                {"detail": _("Send the order as a form.")}, status=status.HTTP_400_BAD_REQUEST
            )
        if str(request.data.get("website_url") or "").strip():
            return Response({"reference": "W" + "0" * 6, "whatsapp": ""}, status=201)
        order = place_order(site, request.data, request)
        from website.order_payments import public_order_payload
        from website.orders import pay_url

        payload = public_order_payload(order)
        from website.tracking import tracking_url

        payload.update({
            "whatsapp": whatsapp_number(order),
            "pay_url": pay_url(order) if payload["bank_accounts"] else "",
            "track_url": tracking_url(order),
        })
        return Response(payload, status=status.HTTP_201_CREATED)


class PublicOrderStatusView(APIView):
    """GET/POST /api/public/site/<slug>/orders/<ref>/ — UNAUTHENTICATED.
    The visitor's own order by its reference (no phone, no ids), and the
    place to declare a bank transfer against it."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_order"

    def _order(self, slug, reference):
        from website.order_payments import order_for_visitor

        try:
            company = Company.objects.get(slug=slug, is_active=True)
        except Company.DoesNotExist:
            return None
        site = getattr(company, "website", None)
        if site is None or not site.is_published:
            return None
        return order_for_visitor(site, reference)

    def get(self, request, slug, reference):
        from website.order_payments import public_order_payload

        order = self._order(slug, reference)
        if order is None:
            return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        return Response(public_order_payload(order))

    def post(self, request, slug, reference):
        from website.order_payments import claim_payload, declare_payment

        order = self._order(slug, reference)
        if order is None:
            return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        if not isinstance(request.data, dict):
            return Response(
                {"detail": _("Send the transfer as a form.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        claim = declare_payment(order, request.data, request.FILES, request)
        return Response(claim_payload(claim), status=status.HTTP_201_CREATED)


class PublicOrderViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """The company's external orders: read, confirm, reject. Sales staff
    see their branch's; owners and managers see all."""

    queryset = PublicOrder.objects.select_related(
        "branch", "customer", "decided_by", "website", "company", "sales_order"
    ).prefetch_related(
        "lines", "payments__bank_account", "payments__decided_by", "events__actor"
    )
    serializer_class = PublicOrderSerializer
    rbac_module = "sales"
    branch_field = "branch"

    def get_queryset(self):
        from core.attention import branch_scope

        qs = self.queryset.filter(company_id=self.request.user.company_id)
        branch_id = branch_scope(self.request.user)
        if branch_id is not None:
            qs = qs.filter(Q(branch_id=branch_id) | Q(branch__isnull=True))
        state = self.request.query_params.get("status")
        if state:
            # One stage, or several comma-separated ("in progress" is four).
            qs = qs.filter(status__in=[s for s in state.split(",") if s])
        ref = self.request.query_params.get("ref")
        if ref:
            qs = qs.filter(reference__iexact=ref)
        return qs

    def _decide(self, request, fn, action_name):
        order = fn(self.get_object(), request.user, str(request.data.get("note") or "")[:1000])
        log_activity(
            action=action_name, request=request, entity_type="PublicOrder",
            entity_id=order.pk, metadata={"reference": order.reference},
        )
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        from website.orders import confirm

        return self._decide(request, confirm, "public_order_confirmed")

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        from website.orders import reject

        return self._decide(request, reject, "public_order_rejected")

    @action(detail=True, methods=["post"])
    def stage(self, request, pk=None):
        """Move the order along its fulfilment stages (or cancel it, with a
        reason). The same sales permission as confirm/reject."""
        from website.tracking import change_stage

        order = change_stage(
            self.get_object(), request.user, str(request.data.get("status") or ""),
            str(request.data.get("note") or "")[:1000],
        )
        return Response(self.get_serializer(self.get_queryset().get(pk=order.pk)).data)

    def _claim(self, pk, claim_pk):
        from django.shortcuts import get_object_or_404

        order = self.get_object()
        return get_object_or_404(order.payments, pk=claim_pk)

    @action(detail=True, methods=["get"], url_path=r"payments/(?P<claim_pk>\d+)/proof")
    def payment_proof(self, request, pk=None, claim_pk=None):
        from core.uploads import proof_response

        claim = self._claim(pk, claim_pk)
        if not claim.proof:
            raise Http404
        return proof_response(claim.proof)

    @action(detail=True, methods=["post"], url_path=r"payments/(?P<claim_pk>\d+)/confirm")
    def confirm_payment(self, request, pk=None, claim_pk=None):
        from inventory.models import Warehouse
        from website.order_payments import confirm_payment

        warehouse = None
        if request.data.get("warehouse"):
            warehouse = Warehouse.objects.filter(
                company_id=request.user.company_id, pk=request.data["warehouse"]
            ).first()
        confirm_payment(
            self._claim(pk, claim_pk), request.user, request, warehouse=warehouse,
            note=str(request.data.get("note") or "")[:1000],
            surplus_returned=str(request.data.get("surplus_returned", "")).lower()
            in ("1", "true", "yes"),
        )
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["post"], url_path=r"payments/(?P<claim_pk>\d+)/reject")
    def reject_payment(self, request, pk=None, claim_pk=None):
        from website.order_payments import reject_payment

        reject_payment(
            self._claim(pk, claim_pk), request.user, request,
            note=str(request.data.get("note") or "")[:1000],
        )
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["post"], url_path=r"payments/(?P<claim_pk>\d+)/fraud")
    def fraud_payment(self, request, pk=None, claim_pk=None):
        from website.order_payments import flag_fraud

        flag_fraud(
            self._claim(pk, claim_pk), request.user, request,
            note=str(request.data.get("note") or "")[:1000],
        )
        return Response(self.get_serializer(self.get_object()).data)


class PushSubscriptionView(APIView):
    """The signed-in person's browser registering (or dropping) itself for
    push. GET hands out the public VAPID key so the browser can subscribe."""

    permission_classes = [IsAuthenticated]
    entitlement_exempt = True

    def get(self, request):
        from core.push import push_is_enabled
        from django.conf import settings

        return Response({
            "enabled": push_is_enabled(),
            "public_key": settings.VAPID_PUBLIC_KEY if push_is_enabled() else "",
            "subscriptions": PushSubscription.objects.filter(user=request.user).count(),
        })

    def post(self, request):
        from core.push import is_push_endpoint, push_is_enabled

        if not push_is_enabled():
            return Response({"detail": _("Push is not configured.")}, status=503)
        if not isinstance(request.data, dict):
            return Response({"detail": _("A push subscription is required.")}, status=400)
        endpoint = str(request.data.get("endpoint") or "")[:1000]
        keys = request.data.get("keys") or {}
        if not isinstance(keys, dict) or not keys.get("p256dh") or not keys.get("auth"):
            return Response({"detail": _("A push subscription is required.")}, status=400)
        if not is_push_endpoint(endpoint):
            return Response(
                {"detail": _("This browser's push service is not supported.")}, status=400
            )
        sub, _created = PushSubscription.objects.update_or_create(
            endpoint=endpoint,
            defaults={
                "user": request.user, "company_id": request.user.company_id,
                "p256dh": str(keys["p256dh"])[:255], "auth": str(keys["auth"])[:255],
                "user_agent": str(request.META.get("HTTP_USER_AGENT", ""))[:255],
                "failures": 0,
            },
        )
        return Response({"id": sub.pk}, status=201)

    def delete(self, request):
        endpoint = str(request.data.get("endpoint") or "")
        PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
        return Response(status=204)


class PlatformTrackView(APIView):
    """POST /api/public/track/ — UNAUTHENTICATED. The search behind
    vezano.app/track/: web orders from any published store, and the
    visitor's registration / demo requests and subscription payments with
    Vezano (website.platform_tracking says what is found and shown).

    A POST so the query never lands in a URL or an access log; nothing here
    changes state, so no CSRF token is needed (no session auth either). The
    per-address budget is the store tracking page's, shared."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @staticmethod
    def _private(response):
        response["Cache-Control"] = "no-store"
        response["X-Robots-Tag"] = "noindex"
        return response

    def post(self, request):
        from website import platform_tracking, tracking

        if not isinstance(request.data, dict):
            return self._private(Response(
                {"detail": _("Enter a reference, a phone number, an email or a name.")},
                status=status.HTTP_400_BAD_REQUEST,
            ))
        query = str(request.data.get("q") or "").strip()[:254]
        language = "en" if str(request.data.get("language") or "").startswith("en") else "ar"
        if not query:
            return self._private(Response(
                {"detail": _("Enter a reference, a phone number, an email or a name.")},
                status=status.HTTP_400_BAD_REQUEST,
            ))
        if tracking.rate_limited(request):
            return self._private(Response(
                {"limited": True, "results": []}, status=status.HTTP_429_TOO_MANY_REQUESTS,
            ))
        kind, items = platform_tracking.lookup(query, language)
        platform_tracking.log_lookup(kind, items)
        return self._private(Response({
            "limited": False, "results": items, "lookup_days": tracking.LOOKUP_DAYS,
        }))


def _track_language(data):
    return "en" if str(data.get("language") or "").startswith("en") else "ar"


class _TrackRequestBase(APIView):
    """Shared by the code-gated trial/demo tracking endpoints: public, no
    session, never cached or indexed (website.request_tracking)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        return PlatformTrackView._private(response)


class TrackRequestStartView(_TrackRequestBase):
    """POST /api/public/track/requests/ {q, language} — always 202 with a
    fresh challenge, whether or not a request matched (see the module)."""

    throttle_classes = [TrackRequestThrottle]

    def post(self, request):
        from core import otp
        from website import request_tracking

        data = request.data if isinstance(request.data, dict) else None
        query = str((data or {}).get("q") or "").strip()[:254]
        if not query:
            return Response(
                {"detail": _("Enter a reference, a phone number, an email or a name.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            _search, body = request_tracking.start(query, _track_language(data), request)
        except otp.OtpError as exc:
            return _otp_failure(exc)
        return Response(body, status=status.HTTP_202_ACCEPTED)


class TrackRequestResendView(_TrackRequestBase):
    """POST /api/public/track/requests/resend/ {challenge_id}."""

    throttle_classes = [TrackResendThrottle]

    def post(self, request):
        from core import otp
        from website import request_tracking

        data = request.data if isinstance(request.data, dict) else {}
        try:
            body = request_tracking.resend(str(data.get("challenge_id") or ""), request)
        except otp.OtpError as exc:
            return _otp_failure(exc)
        return Response(body, status=status.HTTP_202_ACCEPTED)


class TrackRequestVerifyView(_TrackRequestBase):
    """POST /api/public/track/requests/verify/ {challenge_id, code} — the
    requests stored with the email the code went to, and a 30-minute view
    token. 5 tries per search."""

    throttle_classes = [TrackVerifyThrottle]

    def post(self, request):
        from core import otp
        from website import request_tracking

        data = request.data if isinstance(request.data, dict) else {}
        try:
            email = request_tracking.verify(str(data.get("challenge_id") or ""),
                                            data.get("code"))
        except otp.OtpError as exc:
            return _otp_failure(exc)
        return Response({
            "token": request_tracking.view_token(email),
            "expires_in": request_tracking.VIEW_TTL,
            "email_masked": otp.mask_email(email),
            "results": request_tracking.results(email, _track_language(data)),
        })


class TrackRequestView(_TrackRequestBase):
    """POST /api/public/track/requests/view/ {token, language} — the same
    results again while the view token lasts (a reload, a language switch)."""

    throttle_classes = [TrackViewThrottle]

    def post(self, request):
        from core import otp
        from website import request_tracking

        data = request.data if isinstance(request.data, dict) else {}
        token = str(data.get("token") or "")
        email = request_tracking.email_from_token(token)
        if email is None:
            return _otp_error("view_expired", 403)
        return Response({
            "token": token,
            "expires_in": request_tracking.token_expires_in(token),
            "email_masked": otp.mask_email(email),
            "results": request_tracking.results(email, _track_language(data)),
        })
