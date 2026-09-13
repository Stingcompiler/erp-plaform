from django.http import FileResponse, Http404
from django.db import IntegrityError
from django.utils import timezone
from uuid import uuid4
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from config.deployment import get_deployment_config
from core.activity import log_activity
from core.entitlements import resolve_entitlements
from core.permissions import IsPlatformAdmin
from subscriptions.models import (
    Plan,
    PlanVersion,
    Subscription,
    SubscriptionEvent,
    SubscriptionInvoice,
    SubscriptionPayment,
)
from subscriptions.permissions import IsBusinessOwner
from subscriptions.serializers import (
    PlanSerializer,
    PlanVersionSerializer,
    SubscriptionEventSerializer,
    SubscriptionInvoiceSerializer,
    SubscriptionPaymentSerializer,
    SubscriptionSerializer,
    PaymentVerificationSerializer,
)
from subscriptions.services import (
    configure_subscription,
    transition_subscription,
    verify_and_allocate_payment,
)


class CompanySubscriptionView(APIView):
    permission_classes = [IsAuthenticated, IsBusinessOwner]
    entitlement_exempt = True

    def get(self, request):
        company = request.user.company
        subscription = (
            Subscription.objects.select_related("plan_version__plan")
            .filter(company=company)
            .first()
        )
        decision = resolve_entitlements(company)
        return Response(
            {
                "deployment_mode": get_deployment_config().mode,
                "entitlements": decision.as_dict(),
                "subscription": (
                    SubscriptionSerializer(subscription).data if subscription else None
                ),
                "invoices": SubscriptionInvoiceSerializer(
                    SubscriptionInvoice.objects.filter(
                        company=company
                    ).prefetch_related("allocations__payment")[:20],
                    many=True,
                ).data,
                "events": (
                    SubscriptionEventSerializer(
                        subscription.events.all()[:20], many=True
                    ).data
                    if subscription
                    else []
                ),
                "payments": SubscriptionPaymentSerializer(
                    SubscriptionPayment.objects.filter(company=company).select_related(
                        "recorded_by"
                    )[:20],
                    many=True,
                ).data,
            }
        )


class CompanySubscriptionPaymentViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsAuthenticated, IsBusinessOwner]
    entitlement_exempt = True
    serializer_class = SubscriptionPaymentSerializer

    def get_queryset(self):
        return SubscriptionPayment.objects.filter(company=self.request.user.company)

    def create(self, request, *args, **kwargs):
        client_uuid = request.data.get("client_uuid")
        if client_uuid:
            existing = self.get_queryset().filter(client_uuid=client_uuid).first()
            if existing:
                return Response(self.get_serializer(existing).data)
        try:
            return super().create(request, *args, **kwargs)
        except IntegrityError:
            if client_uuid:
                existing = self.get_queryset().filter(client_uuid=client_uuid).first()
                if existing:
                    return Response(self.get_serializer(existing).data)
            raise

    def perform_create(self, serializer):
        payment = serializer.save(
            company=self.request.user.company, recorded_by=self.request.user
        )
        log_activity(
            action="create",
            request=self.request,
            entity_type="SubscriptionPayment",
            entity_id=payment.pk,
        )

    @action(detail=True, methods=["get"])
    def proof(self, request, pk=None):
        payment = self.get_object()
        if not payment.proof:
            raise Http404
        return FileResponse(payment.proof.open("rb"), as_attachment=True)


class PlatformPlanViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    entitlement_exempt = True
    queryset = Plan.objects.prefetch_related("versions")
    serializer_class = PlanSerializer


class PlatformPlanVersionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    entitlement_exempt = True
    queryset = PlanVersion.objects.select_related("plan")
    serializer_class = PlanVersionSerializer

    def perform_update(self, serializer):
        if (
            serializer.instance.published_at
            or serializer.instance.subscriptions.exists()
        ):
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                "A plan version in use is immutable; create a new version."
            )
        serializer.save()

    def perform_destroy(self, instance):
        if instance.subscriptions.exists():
            from rest_framework.exceptions import ValidationError

            raise ValidationError("A plan version in use cannot be deleted.")
        instance.delete()


class PlatformSubscriptionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    entitlement_exempt = True
    queryset = Subscription.objects.select_related("company", "plan_version__plan")
    serializer_class = SubscriptionSerializer
    http_method_names = ["get", "post", "head", "options"]

    def perform_create(self, serializer):
        subscription = serializer.save()
        SubscriptionEvent.objects.create(
            subscription=subscription,
            event_type="provisioned",
            to_status=subscription.status,
            actor=self.request.user,
        )
        log_activity(
            action="create",
            request=self.request,
            company=subscription.company,
            entity_type="Subscription",
            entity_id=subscription.pk,
        )

    @action(detail=True, methods=["post"])
    def configure(self, request, pk=None):
        current = self.get_object()
        allowed = {
            "plan_version",
            "status",
            "starts_at",
            "period_ends_at",
            "trial_ends_at",
            "grace_ends_at",
            "cancel_at_period_end",
            "suspended_reason",
        }
        changes = {key: value for key, value in request.data.items() if key in allowed}
        serializer = self.get_serializer(current, data=changes, partial=True)
        serializer.is_valid(raise_exception=True)
        subscription = configure_subscription(
            current.pk,
            serializer.validated_data,
            request.user,
            request.data.get("reason", ""),
        )
        log_activity(
            action="update",
            request=request,
            company=subscription.company,
            entity_type="Subscription",
            entity_id=subscription.pk,
            metadata={"configuration_changed": sorted(serializer.validated_data)},
        )
        return Response(self.get_serializer(subscription).data)

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        target = request.data.get("status")
        allowed = {choice[0] for choice in Subscription.STATES} - {Subscription.LEGACY}
        if target not in allowed:
            return Response(
                {"status": ["Invalid target state."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        required_end = {
            Subscription.TRIALING: "trial_ends_at",
            Subscription.ACTIVE: "period_ends_at",
            Subscription.GRACE: "grace_ends_at",
        }.get(target)
        current = self.get_object()
        if required_end and not getattr(current, required_end):
            return Response(
                {required_end: [f"Set {required_end} before this transition."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        subscription, previous = transition_subscription(
            current.pk, target, request.user, request.data.get("reason", "")
        )
        log_activity(
            action="update",
            request=request,
            company=subscription.company,
            entity_type="Subscription",
            entity_id=subscription.pk,
            metadata={"from": previous, "to": target},
        )
        return Response(self.get_serializer(subscription).data)


class PlatformSubscriptionInvoiceViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    entitlement_exempt = True
    queryset = SubscriptionInvoice.objects.select_related(
        "company", "subscription"
    ).prefetch_related("allocations__payment")
    serializer_class = SubscriptionInvoiceSerializer
    http_method_names = ["get", "post", "head", "options"]

    def perform_create(self, serializer):
        invoice = serializer.save(
            number=f"PENDING-{uuid4().hex}",
            status=SubscriptionInvoice.ISSUED,
            issued_at=timezone.now(),
        )
        invoice.number = f"VSUB-{invoice.pk:06d}"
        invoice.save(update_fields=["number"])
        log_activity(
            action="create",
            request=self.request,
            company=invoice.company,
            entity_type="SubscriptionInvoice",
            entity_id=invoice.pk,
        )


class PlatformSubscriptionPaymentViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    entitlement_exempt = True
    queryset = SubscriptionPayment.objects.select_related(
        "company", "recorded_by", "verified_by"
    )
    serializer_class = SubscriptionPaymentSerializer

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        serializer = PaymentVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = verify_and_allocate_payment(
            self.get_object().pk, request.user, serializer.validated_data["allocations"]
        )
        log_activity(
            action="approve",
            request=request,
            company=payment.company,
            entity_type="SubscriptionPayment",
            entity_id=payment.pk,
        )
        return Response(self.get_serializer(payment).data)

    @action(detail=True, methods=["get"])
    def proof(self, request, pk=None):
        payment = self.get_object()
        if not payment.proof:
            raise Http404
        return FileResponse(payment.proof.open("rb"), as_attachment=True)


class DeploymentInfoView(APIView):
    permission_classes = [IsAuthenticated]
    entitlement_exempt = True

    def get(self, request):
        config = get_deployment_config()
        return Response({"mode": config.mode, "policy": config.entitlement_policy})
