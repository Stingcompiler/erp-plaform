from django.db.models import Prefetch
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from accounts.models import PlatformInvitation, User
from core.models import ActivityLog
from accounts.platform_team import (
    accept_platform_invitation,
    invite_platform_member,
    platform_members,
    reissue_platform_invitation,
    set_platform_member_active,
    set_platform_member_role,
)
from core import platform_roles
from core.permissions import IsPlatformAdmin


class PlatformMemberSerializer(serializers.ModelSerializer):
    role_name = serializers.SerializerMethodField()
    activated = serializers.SerializerMethodField()
    invitation_expires_at = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "full_name", "role_name", "is_active", "is_superuser",
            "activated", "invitation_expires_at", "last_login", "created_at",
        ]
        read_only_fields = fields

    def get_role_name(self, obj):
        return obj.role.name if obj.role_id else ("Django superuser" if obj.is_superuser else "")

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

    def _payload(self, user, token=None):
        user = self.get_queryset().get(pk=user.pk)
        data = self.get_serializer(user).data
        if token:
            data["invitation_token"] = token
        return data

    def create(self, request):
        serializer = PlatformMemberInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, token = invite_platform_member(
            serializer.validated_data["email"], serializer.validated_data["full_name"],
            serializer.validated_data["role"], request.user, request,
        )
        return Response(self._payload(user, token), status=status.HTTP_201_CREATED)

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
        return Response(self._payload(user, token), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        user = set_platform_member_active(pk, False, request.user, request)
        return Response(self._payload(user))

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        user = set_platform_member_active(pk, True, request.user, request)
        return Response(self._payload(user))


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
