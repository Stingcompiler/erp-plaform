from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from config.deployment import get_deployment_config
from core.activity import log_activity
from core.entitlements import resolve_entitlements
from licensing.models import Installation
from licensing.serializers import (
    InstallationSerializer,
    LicenseActivationSerializer,
    LicenseImportSerializer,
)
from licensing.services import activate_license, active_license
from subscriptions.permissions import IsBusinessOwner


class LicenseView(APIView):
    permission_classes = [IsAuthenticated, IsBusinessOwner]
    entitlement_exempt = True

    def get(self, request):
        config = get_deployment_config()
        installation = Installation.current() if config.is_standalone else None
        activation = active_license() if installation else None
        return Response(
            {
                "deployment_mode": config.mode,
                "installation": (
                    InstallationSerializer(installation).data if installation else None
                ),
                "license": (
                    LicenseActivationSerializer(activation).data if activation else None
                ),
                "entitlements": resolve_entitlements(
                    getattr(request.user, "company", None)
                ).as_dict(),
            }
        )

    def post(self, request):
        if not get_deployment_config().is_standalone:
            return Response(
                {
                    "detail": "Licence import is available only in standalone deployments."
                },
                status=409,
            )
        serializer = LicenseImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        activation, created = activate_license(
            serializer.validated_data, actor=request.user
        )
        log_activity(
            action="create" if created else "update",
            request=request,
            entity_type="LicenseActivation",
            entity_id=activation.license_id,
            metadata={"key_id": activation.key_id, "kind": activation.kind},
        )
        return Response(
            LicenseActivationSerializer(activation).data, status=201 if created else 200
        )
