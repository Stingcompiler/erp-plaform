from django.db.models import Prefetch, Q
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from accounts.models import PlatformInvitation, User
from accounts.presence import is_online
from core.models import ActivityLog
from accounts.platform_team import (
    accept_platform_invitation,
    delete_platform_member,
    invite_platform_member,
    platform_members,
    reissue_platform_invitation,
    set_platform_member_active,
    set_platform_member_profile,
    set_platform_member_role,
)
from core import platform_roles
from core.permissions import IsPlatformAdmin


class PlatformMemberSerializer(serializers.ModelSerializer):
    role_name = serializers.SerializerMethodField()
    activated = serializers.SerializerMethodField()
    invitation_expires_at = serializers.SerializerMethodField()
    online = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "full_name", "role_name", "is_active", "is_superuser",
            "activated", "invitation_expires_at", "last_login", "last_seen_at", "online",
            "created_at",
        ]
        read_only_fields = fields

    def get_role_name(self, obj):
        return obj.role.name if obj.role_id else ("Django superuser" if obj.is_superuser else "")

    def get_online(self, obj):
        return is_online(obj)

    def get_activated(self, obj):
        return obj.has_usable_password()

    def get_invitation_expires_at(self, obj):
        # Prefetched in the viewset; only the live invitation matters.
        live = [
            invite for invite in getattr(obj, "_live_invitations", [])
            if invite.accepted_at is None and invite.revoked_at is None
        ]
        return live[0].expires_at if live else None


def _person(user):
    if user is None:
        return None
    return {"id": user.pk, "full_name": user.full_name, "email": user.email}


class PlatformMemberDetailSerializer(PlatformMemberSerializer):
    """One member in full: what the role lets them do, how they got here, and
    what they have done. Read by the member information page."""

    capabilities = serializers.SerializerMethodField()
    invited_by = serializers.SerializerMethodField()
    invitations = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()
    activity = serializers.SerializerMethodField()

    class Meta(PlatformMemberSerializer.Meta):
        fields = PlatformMemberSerializer.Meta.fields + [
            "capabilities", "invited_by", "invitations", "history", "activity",
        ]
        read_only_fields = fields

    def get_capabilities(self, obj):
        return sorted(platform_roles.platform_capabilities_for(obj))

    def _invitations(self, obj):
        return list(
            PlatformInvitation.objects.filter(user=obj)
            .select_related("invited_by")
            .order_by("-created_at")
        )

    def get_invited_by(self, obj):
        invitations = self._invitations(obj)
        return _person(invitations[-1].invited_by) if invitations else None

    def get_invitations(self, obj):
        return [
            {
                "created_at": invite.created_at,
                "expires_at": invite.expires_at,
                "accepted_at": invite.accepted_at,
                "revoked_at": invite.revoked_at,
                "invited_by": _person(invite.invited_by),
            }
            for invite in self._invitations(obj)
        ]

    @staticmethod
    def _entry(row):
        return {
            "id": row.pk,
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "metadata": row.metadata,
            "ip_address": row.ip_address,
            "created_at": row.created_at,
            "user": _person(row.user),
        }

    def get_history(self, obj):
        """Changes made *to* this member: who invited, re-roled or disabled them."""
        rows = (
            ActivityLog.objects.filter(
                entity_type__in=("PlatformMember", "PlatformInvitation"),
                entity_id=str(obj.pk),
            )
            .select_related("user")
            .order_by("-created_at")[:50]
        )
        return [self._entry(row) for row in rows]

    def get_activity(self, obj):
        """The member's own recent actions across the platform console."""
        rows = (
            ActivityLog.objects.filter(user=obj)
            .select_related("user")
            .order_by("-created_at")[:50]
        )
        return [self._entry(row) for row in rows]


class PlatformMemberInviteSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=255)
    role = serializers.ChoiceField(choices=[(name, name) for name in platform_roles.PLATFORM_ROLES])


class PlatformMemberRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=[(name, name) for name in platform_roles.PLATFORM_ROLES])


class PlatformMemberProfileSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255, required=False)
    email = serializers.EmailField(required=False)


class PlatformTeamViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """The people who run the Vezano platform, managed from the platform page."""

    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    platform_capability = platform_roles.TEAM_MANAGE
    platform_view_capability = platform_roles.TEAM_VIEW
    entitlement_exempt = True
    serializer_class = PlatformMemberSerializer

    def get_queryset(self):
        return platform_members().prefetch_related(
            Prefetch(
                "platform_invitations",
                queryset=PlatformInvitation.objects.order_by("-created_at"),
                to_attr="_live_invitations",
            )
        )

    def get_serializer_class(self):
        if self.action == "retrieve":
            return PlatformMemberDetailSerializer
        return PlatformMemberSerializer

    def _payload(self, user, token=None, email_sent=None):
        user = self.get_queryset().get(pk=user.pk)
        data = self.get_serializer(user).data
        if token:
            data["invitation_token"] = token
            data["invitation_email_sent"] = bool(email_sent)
        return data

    @staticmethod
    def _email_invitation(user, token):
        """Best-effort: the inviting admin always gets the link to deliver
        by hand; with SMTP configured it is also emailed to the member."""
        from core import mailer

        link = mailer.activation_link(token, kind="platform")
        if not link:
            return False
        name = user.full_name or user.email
        return mailer.send_bilingual(
            subject_ar="دعوة فريق منصة فيزانو برو",
            subject_en="Vezano Pro platform team invitation",
            ar=[
                f"مرحباً {name}،",
                "تمت دعوتك للانضمام إلى فريق منصة فيزانو برو.",
                "فعّل حسابك من الرابط أدناه (صالح لمرة واحدة).",
            ],
            en=[
                f"Hello {name},",
                "You have been invited to the Vezano Pro platform team.",
                "Activate your account with the one-time link below.",
            ],
            link=link,
            recipient=user.email,
        )

    def create(self, request):
        serializer = PlatformMemberInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, token = invite_platform_member(
            serializer.validated_data["email"], serializer.validated_data["full_name"],
            serializer.validated_data["role"], request.user, request,
        )
        return Response(
            self._payload(user, token, email_sent=self._email_invitation(user, token)),
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, pk=None):
        serializer = PlatformMemberProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = set_platform_member_profile(
            pk, serializer.validated_data.get("full_name"),
            serializer.validated_data.get("email"), request.user, request,
        )
        return Response(self._payload(user))

    def destroy(self, request, pk=None):
        delete_platform_member(pk, request.user, request)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"])
    def roles(self, request):
        return Response(
            [
                {"name": name, "description": description, "capabilities": capabilities}
                for name, description, capabilities in platform_roles.platform_role_choices()
            ]
        )

    @action(detail=True, methods=["post"], url_path="set-role")
    def set_role(self, request, pk=None):
        serializer = PlatformMemberRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = set_platform_member_role(
            pk, serializer.validated_data["role"], request.user, request
        )
        return Response(self._payload(user))

    @action(detail=True, methods=["post"], url_path="reissue-invitation")
    def reissue_invitation(self, request, pk=None):
        user, token = reissue_platform_invitation(pk, request.user, request)
        return Response(
            self._payload(user, token, email_sent=self._email_invitation(user, token)),
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        user = set_platform_member_active(pk, False, request.user, request)
        return Response(self._payload(user))

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        user = set_platform_member_active(pk, True, request.user, request)
        return Response(self._payload(user))


# Everything the platform team does is recorded under one of these entity
# types (or by a platform member on anything at all).
PLATFORM_ENTITY_TYPES = (
    "PlatformMember", "PlatformInvitation", "PlatformLead",
    "RegistrationRequest", "RegistrationProvision", "OwnerInvitation",
    "Subscription", "SubscriptionInvoice", "SubscriptionPayment",
    "Plan", "PlanVersion", "SeoSettings", "SeoPageOverride",
)


class PlatformActivitySerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()

    class Meta:
        model = ActivityLog
        fields = ["id", "action", "entity_type", "entity_id", "metadata", "ip_address",
                  "created_at", "user"]
        read_only_fields = fields

    def get_user(self, obj):
        if obj.user is None:
            return None
        role = obj.user.role.name if obj.user.role_id else (
            "Django superuser" if obj.user.is_superuser else ""
        )
        return {"id": obj.user.pk, "full_name": obj.user.full_name,
                "email": obj.user.email, "role_name": role}


class PlatformActivityViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """The platform team's audit trail: every row written by a platform
    member, plus every row about a platform object (an owner accepting an
    invitation, for instance, is written by the owner). Tenant business
    activity never appears here. Read by whoever may see the team."""

    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    platform_view_capability = platform_roles.TEAM_VIEW
    entitlement_exempt = True
    serializer_class = PlatformActivitySerializer

    def get_queryset(self):
        members = platform_members().values("pk")
        qs = (
            ActivityLog.objects.filter(
                Q(user__in=members) | Q(entity_type__in=PLATFORM_ENTITY_TYPES)
            )
            .select_related("user", "user__role")
            .order_by("-created_at", "-pk")
        )
        params = self.request.query_params
        if params.get("user"):
            qs = qs.filter(user_id=params["user"])
        if params.get("action"):
            qs = qs.filter(action=params["action"])
        if params.get("entity_type"):
            qs = qs.filter(entity_type__iexact=params["entity_type"])
        if params.get("start"):
            qs = qs.filter(created_at__date__gte=params["start"])
        if params.get("end"):
            qs = qs.filter(created_at__date__lte=params["end"])
        search = params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(user__email__icontains=search)
                | Q(user__full_name__icontains=search)
                | Q(entity_type__icontains=search)
                | Q(entity_id__icontains=search)
                | Q(metadata__icontains=search)
            )
        return qs

    @action(detail=False, methods=["get"])
    def facets(self, request):
        """Distinct actions and entity types present, for the filter controls."""
        qs = self.get_queryset()
        return Response({
            "actions": sorted(set(qs.values_list("action", flat=True))),
            "entity_types": sorted(set(qs.values_list("entity_type", flat=True))),
        })


class PlatformInvitationAcceptSerializer(serializers.Serializer):
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


class PlatformInvitationAcceptView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get_throttles(self):
        class InvitationThrottle(AnonRateThrottle):
            scope = "platform_invitation_accept"
            rate = "10/hour"

        return [InvitationThrottle()]

    def post(self, request):
        serializer = PlatformInvitationAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = accept_platform_invitation(
                serializer.validated_data["token"], serializer.validated_data["password"],
                request,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"email": user.email, "status": "activated"})
