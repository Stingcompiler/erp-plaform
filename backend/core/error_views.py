"""The platform console's error feed: open production errors, newest first.

Read and resolved by whoever may see the team (the same people who read
the activity log). Resolving is bookkeeping, not deletion — a resolved
error that recurs reopens itself with its count intact.
"""

from django.utils import timezone
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core import platform_roles
from core.models import ErrorEvent
from core.permissions import IsPlatformAdmin


class ErrorEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ErrorEvent
        fields = [
            "id", "exc_type", "message", "path", "method", "traceback",
            "user_id", "company_id", "count", "first_seen", "last_seen", "resolved_at",
        ]


class ErrorEventViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    platform_view_capability = platform_roles.TEAM_VIEW
    platform_capability = platform_roles.TEAM_VIEW
    entitlement_exempt = True
    serializer_class = ErrorEventSerializer

    def get_queryset(self):
        qs = ErrorEvent.objects.all()
        if self.request.query_params.get("all") != "1":
            qs = qs.filter(resolved_at__isnull=True)
        return qs

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        event = self.get_object()
        event.resolved_at = timezone.now()
        event.save(update_fields=["resolved_at"])
        return Response(self.get_serializer(event).data)
