"""The platform team's view of every company: what the plan allows, what the
company actually uses (people, branches, warehouses, devices), who owns it
and when it was last alive. One row per tenant, computed from the same
counters the sign-in and create paths enforce, so "over the plan" here
means the next attempt is refused there.
"""

from datetime import timedelta

from django.db.models import Count, Max
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from config.deployment import get_deployment_config
from core import platform_roles
from core.entitlements import resolve_entitlements
from core.permissions import IsPlatformAdmin
from org.devices import reactivate_device, revoke_device
from org.models import Company, Device
from org.serializers import DeviceSerializer
from sales.models import Invoice
from subscriptions.models import Subscription
from subscriptions.services import usage_for


def company_row(company, subscription, owner, invoices_30d, last_active_at):
    decision = resolve_entitlements(company, apply_policy=False)
    usage = usage_for(company, decision.limits)
    over = [
        key for key, cell in usage.items()
        if cell["limit"] is not None and cell["used"] > cell["limit"]
    ]
    plan = None
    if subscription is not None:
        version = subscription.plan_version
        plan = {
            "name": version.plan.name if version else None,
            "code": version.plan.code if version else None,
            "status": subscription.status,
            "period_ends_at": subscription.period_ends_at,
            "trial_ends_at": subscription.trial_ends_at,
        }
    return {
        "id": company.pk,
        "name": company.name,
        "slug": company.slug,
        "business_type": company.business_type,
        "currency": company.currency,
        "created_at": company.created_at,
        "owner": (
            {"name": owner.full_name, "email": owner.email, "phone": company.phone}
            if owner else None
        ),
        "plan": plan,
        "usage": usage,
        "over_limit": over,
        "invoices_30d": invoices_30d,
        "last_active_at": last_active_at,
    }


class PlatformCompanyViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    platform_capability = platform_roles.SUBSCRIPTIONS_MANAGE
    platform_view_capability = platform_roles.SUBSCRIPTIONS_VIEW
    entitlement_exempt = True

    def _companies(self):
        return Company.objects.order_by("name")

    def list(self, request):
        since = timezone.now() - timedelta(days=30)
        companies = list(self._companies())
        ids = [c.pk for c in companies]
        subscriptions = {
            s.company_id: s
            for s in Subscription.objects.filter(company_id__in=ids).select_related(
                "plan_version__plan"
            )
        }
        owners = {}
        from accounts.models import User

        for user in (
            User.objects.filter(
                company_id__in=ids, role__name="Business Owner", is_active=True
            ).order_by("pk")
        ):
            owners.setdefault(user.company_id, user)
        invoices = dict(
            Invoice.objects.filter(company_id__in=ids, received_at__gte=since, is_void=False)
            .values_list("company_id").annotate(n=Count("id")).values_list("company_id", "n")
        )
        activity = dict(
            User.objects.filter(company_id__in=ids)
            .values_list("company_id").annotate(t=Max("last_seen_at"))
            .values_list("company_id", "t")
        )
        rows = [
            company_row(
                c, subscriptions.get(c.pk), owners.get(c.pk),
                invoices.get(c.pk, 0), activity.get(c.pk),
            )
            for c in companies
        ]
        return Response(
            {
                "companies": rows,
                "generated_at": timezone.now(),
                # "disabled" or "observe" means every limit above is advisory:
                # the page must say so, or the team reads room where there is none.
                "policy": get_deployment_config().entitlement_policy,
            }
        )

    @action(detail=True, methods=["get"])
    def devices(self, request, pk=None):
        devices = Device.objects.filter(company_id=pk).select_related("branch", "last_user")
        return Response({"devices": DeviceSerializer(devices, many=True).data})

    def _device(self, pk, device_pk):
        return Device.objects.select_related("company").get(company_id=pk, pk=device_pk)

    @action(detail=True, methods=["post"], url_path=r"devices/(?P<device_pk>\d+)/revoke")
    def revoke_device(self, request, pk=None, device_pk=None):
        device = revoke_device(self._device(pk, device_pk), request.user, request)
        return Response(DeviceSerializer(device).data)

    @action(detail=True, methods=["post"], url_path=r"devices/(?P<device_pk>\d+)/reactivate")
    def reactivate_device(self, request, pk=None, device_pk=None):
        device = reactivate_device(self._device(pk, device_pk), request.user, request)
        return Response(DeviceSerializer(device).data)
