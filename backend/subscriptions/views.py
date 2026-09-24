from django.http import Http404

from core.uploads import proof_response
from django.db import IntegrityError
from decimal import Decimal
from django.utils import timezone
from django.utils.translation import gettext as _
from uuid import uuid4
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from config.deployment import get_deployment_config
from core.activity import log_activity
from core.entitlements import resolve_entitlements
from core import platform_roles
from core.permissions import IsPlatformAdmin
from subscriptions.models import (
    PlanChangeRequest,
    Plan,
    PlanVersion,
    Subscription,
    SubscriptionEvent,
    SubscriptionInvoice,
    SubscriptionPayment,
)
from subscriptions.permissions import IsBusinessOwner
from subscriptions.serializers import (
    PlanChangeRequestSerializer,
    PlanSerializer,
    PlanVersionSerializer,
    SubscriptionEventSerializer,
    SubscriptionInvoiceSerializer,
    SubscriptionPaymentSerializer,
    SubscriptionSerializer,
    PaymentVerificationSerializer,
    PlatformSubscriptionPaymentSerializer,
)
from subscriptions.services import (
    configure_subscription,
    normalise_currency,
    reject_payment,
    transition_subscription,
    usage_for,
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
                "usage": usage_for(company, decision.limits),
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
        company = self.request.user.company
        # Money in the wrong currency can never be applied to an invoice
        # (verify_and_allocate_payment refuses it), so refuse it here where
        # the owner can still fix it, instead of parking it for review.
        subscription = Subscription.objects.select_related("plan_version").filter(
            company=company
        ).first()
        currency = serializer.validated_data.get("currency")
        # A plan change into another currency is invoiced in that currency;
        # paying it must be possible while the old plan is still current.
        accepted = set()
        if subscription is not None:
            accepted.add(normalise_currency(subscription.plan_version.currency))
            accepted.update(
                normalise_currency(value)
                for value in SubscriptionInvoice.objects.filter(
                    company=company, status=SubscriptionInvoice.ISSUED,
                ).values_list("currency", flat=True)
            )
        if subscription is not None and normalise_currency(currency) not in accepted:
            raise ValidationError({
                "currency": _("Your subscription is billed in %(currency)s; pay in that currency.")
                % {"currency": subscription.plan_version.currency},
            })
        payment = serializer.save(company=company, recorded_by=self.request.user)
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
        return proof_response(payment.proof)


class _PlatformAuditMixin:
    """create/update/delete on a platform catalogue object are audited, so
    the price list has a history like everything else the team touches."""

    audit_entity_type = None

    def _audit(self, action, instance, **metadata):
        log_activity(
            action=action, request=self.request, entity_type=self.audit_entity_type,
            entity_id=instance.pk, metadata={"label": str(instance), **metadata},
        )

    def perform_create(self, serializer):
        serializer.save()
        self._audit("create", serializer.instance)

    def perform_update(self, serializer):
        changed = sorted(serializer.validated_data)
        serializer.save()
        self._audit("update", serializer.instance, fields=changed)

    def perform_destroy(self, instance):
        self._audit("delete", instance)
        instance.delete()


class PlatformPlanViewSet(_PlatformAuditMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    platform_capability = platform_roles.PLANS_MANAGE
    platform_view_capability = platform_roles.PLANS_VIEW
    entitlement_exempt = True
    queryset = Plan.objects.prefetch_related("versions")
    serializer_class = PlanSerializer
    audit_entity_type = "Plan"


class PlatformPlanVersionViewSet(_PlatformAuditMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    platform_capability = platform_roles.PLANS_MANAGE
    platform_view_capability = platform_roles.PLANS_VIEW
    entitlement_exempt = True
    queryset = PlanVersion.objects.select_related("plan")
    serializer_class = PlanVersionSerializer
    audit_entity_type = "PlanVersion"

    def perform_update(self, serializer):
        if (
            serializer.instance.published_at
            or serializer.instance.subscriptions.exists()
        ):
            raise ValidationError(
                _("A plan version in use is immutable; create a new version.")
            )
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        if instance.subscriptions.exists():
            from rest_framework.exceptions import ValidationError

            raise ValidationError(_("A plan version in use cannot be deleted."))
        super().perform_destroy(instance)


class PlatformSubscriptionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    platform_capability = platform_roles.SUBSCRIPTIONS_MANAGE
    platform_view_capability = platform_roles.SUBSCRIPTIONS_VIEW
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
                {"status": [_("Invalid target state.")]},
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
                {
                    required_end: [
                        _("Set %(field)s before this transition.") % {"field": required_end}
                    ]
                },
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
    platform_capability = platform_roles.BILLING_REVIEW
    platform_view_capability = platform_roles.BILLING_VIEW
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
    platform_capability = platform_roles.BILLING_REVIEW
    platform_view_capability = platform_roles.BILLING_VIEW
    entitlement_exempt = True
    queryset = SubscriptionPayment.objects.select_related(
        "company", "recorded_by", "verified_by"
    )
    serializer_class = PlatformSubscriptionPaymentSerializer

    @action(detail=True, methods=["get"])
    def renewal(self, request, pk=None):
        """The renewal approving this payment would perform (dry run)."""
        from subscriptions.renewals import plan_renewal, renewal_as_json

        return Response(renewal_as_json(plan_renewal(self.get_object())))

    @action(detail=True, methods=["post"])
    def renew(self, request, pk=None):
        """Approve and renew: issue the renewal invoice(s) this payment pays
        for, allocate it and grant the periods — no invoice needed first.
        ``expected`` is the preview's key; a changed plan is refused."""
        from subscriptions.renewals import renew_with_payment

        expected = request.data.get("expected")
        payment, issued = renew_with_payment(
            self.get_object().pk, request.user,
            expected_key=str(expected) if expected is not None else None,
        )
        log_activity(
            action="approve",
            request=request,
            company=payment.company,
            entity_type="SubscriptionPayment",
            entity_id=payment.pk,
            metadata={"renewal": True, "invoices_issued": issued},
        )
        return Response(self.get_serializer(payment).data)

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

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        payment = reject_payment(
            self.get_object().pk, request.user, str(request.data.get("reason", ""))
        )
        log_activity(
            action="reject",
            request=request,
            company=payment.company,
            entity_type="SubscriptionPayment",
            entity_id=payment.pk,
            metadata={"reason": payment.rejection_reason},
        )
        return Response(self.get_serializer(payment).data)

    @action(detail=True, methods=["get"])
    def proof(self, request, pk=None):
        payment = self.get_object()
        if not payment.proof:
            raise Http404
        return proof_response(payment.proof)


class DeploymentInfoView(APIView):
    permission_classes = [IsAuthenticated]
    entitlement_exempt = True

    def get(self, request):
        config = get_deployment_config()
        return Response({"mode": config.mode, "policy": config.entitlement_policy})


class CompanyPlanChangeViewSet(viewsets.GenericViewSet):
    """The owner's side of a plan change: what can be moved to, what it
    would cost for the rest of this period, asking, and withdrawing."""

    permission_classes = [IsAuthenticated, IsBusinessOwner]
    entitlement_exempt = True
    serializer_class = PlanChangeRequestSerializer

    def get_queryset(self):
        return PlanChangeRequest.objects.filter(
            company_id=self.request.user.company_id
        ).select_related("from_version__plan", "to_version__plan", "invoice", "requested_by")

    def list(self, request):
        from subscriptions.plan_changes import (
            classify, open_request, proration, same_currency, usage_over_limits,
        )

        company = request.user.company
        subscription = Subscription.objects.select_related("plan_version").filter(
            company=company
        ).first()
        options = []
        if subscription is not None:
            current = subscription.plan_version
            latest = {}
            # Plans in another currency are offered too: a company billed in
            # a currency no public plan uses any more would otherwise see
            # nothing. Same currency first, then the rest.
            for version in PlanVersion.objects.select_related("plan").filter(
                plan__is_active=True, plan__is_public=True, published_at__isnull=False,
            ).order_by("plan__sort_order", "plan__name", "-version"):
                latest.setdefault(version.plan_id, version)
            for version in sorted(
                latest.values(), key=lambda v: not same_currency(v.currency, current.currency)
            ):
                if version.pk == current.pk:
                    continue
                kind = classify(current, version)
                if kind == PlanChangeRequest.SWITCH:
                    amount = Decimal(version.price)
                elif kind == PlanChangeRequest.UPGRADE:
                    amount, _ = proration(subscription, current, version)
                else:
                    amount = Decimal("0")
                options.append({
                    "version": version.pk, "plan": version.plan.name, "code": version.plan.code,
                    "price": str(version.price), "currency": version.currency,
                    "billing_cycle": version.billing_cycle, "limits": version.limits,
                    "modules": version.modules, "kind": kind,
                    "currency_change": kind == PlanChangeRequest.SWITCH,
                    "due_now": str(amount),
                    "blocked_by": (
                        usage_over_limits(company, version)
                        if kind in (PlanChangeRequest.DOWNGRADE, PlanChangeRequest.SWITCH)
                        else {}
                    ),
                })
        addons = []
        if subscription is not None:
            from subscriptions.plan_changes import period_fraction_left

            version = subscription.plan_version
            fraction = period_fraction_left(subscription, version)
            for resource, unit_price in (version.addon_prices or {}).items():
                if resource not in (version.limits or {}):
                    continue
                addons.append({
                    "resource": resource,
                    "unit_price": str(unit_price),
                    "currency": version.currency,
                    "billing_cycle": version.billing_cycle,
                    "owned": int((subscription.extra_limits or {}).get(resource, 0)),
                    "plan_limit": int(version.limits[resource]),
                    # What one more unit costs for the rest of this period.
                    "unit_due_now": str(
                        (Decimal(str(unit_price)) * fraction).quantize(Decimal("0.01"))
                    ),
                })
        current = open_request(company)
        return Response({
            "current": self.get_serializer(current).data if current else None,
            "options": options,
            "addons": addons,
            "history": self.get_serializer(self.get_queryset()[:20], many=True).data,
        })

    def create(self, request):
        from subscriptions.plan_changes import (
            UsageExceedsTarget, request_addon, request_change,
        )

        note = str(request.data.get("note") or "")[:1000]
        try:
            if request.data.get("extra_delta"):
                change = request_addon(
                    request.user.company, request.data.get("extra_delta"), request.user, note
                )
            else:
                try:
                    version = PlanVersion.objects.select_related("plan").get(
                        pk=request.data.get("to_version")
                    )
                except (PlanVersion.DoesNotExist, ValueError, TypeError):
                    return Response(
                        {"to_version": _("Choose a plan.")}, status=status.HTTP_400_BAD_REQUEST
                    )
                change = request_change(request.user.company, version, request.user, note)
        except UsageExceedsTarget as exc:
            return Response(
                {
                    "code": "usage_exceeds_target",
                    "detail": _("Reduce usage to fit the new plan first."),
                    "over": exc.over,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        log_activity(
            action="plan_change_requested", request=request,
            entity_type="PlanChangeRequest", entity_id=change.pk,
            metadata={
                "kind": change.kind, "to_plan": change.to_version.plan.name,
                "extra_delta": change.extra_delta,
            },
        )
        return Response(self.get_serializer(change).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        from subscriptions.plan_changes import cancel_request

        change = cancel_request(self.get_object(), request.user)
        log_activity(
            action="plan_change_cancelled", request=request,
            entity_type="PlanChangeRequest", entity_id=change.pk,
        )
        return Response(self.get_serializer(change).data)


class PlatformPlanChangeViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    platform_capability = platform_roles.SUBSCRIPTIONS_MANAGE
    platform_view_capability = platform_roles.SUBSCRIPTIONS_VIEW
    entitlement_exempt = True
    serializer_class = PlanChangeRequestSerializer
    queryset = PlanChangeRequest.objects.select_related(
        "company", "from_version__plan", "to_version__plan", "invoice", "requested_by"
    )

    def get_queryset(self):
        qs = super().get_queryset()
        state = self.request.query_params.get("status")
        return qs.filter(status=state) if state else qs

    def _decide(self, request, fn, action_name):
        change = fn(self.get_object(), request.user, str(request.data.get("note") or "")[:1000])
        log_activity(
            action=action_name, request=request, company=change.company,
            entity_type="PlanChangeRequest", entity_id=change.pk,
            metadata={"kind": change.kind, "status": change.status},
        )
        return Response(self.get_serializer(change).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        from subscriptions.plan_changes import approve_request

        return self._decide(request, approve_request, "plan_change_approved")

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        from subscriptions.plan_changes import reject_request

        return self._decide(request, reject_request, "plan_change_rejected")
