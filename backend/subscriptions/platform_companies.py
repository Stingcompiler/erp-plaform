"""The platform team's view of every company: what the plan allows, what the
company actually uses (people, branches, warehouses, devices), who owns it
and when it was last alive. One row per tenant, computed from the same
counters the sign-in and create paths enforce, so "over the plan" here
means the next attempt is refused there.
"""

from datetime import timedelta

from django.db.models import Count, Max
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from config.deployment import get_deployment_config
from core import platform_roles
from core.activity import log_activity
from core.entitlements import resolve_entitlements
from core.permissions import IsPlatformAdmin
from org.devices import reactivate_device, revoke_device
from org.models import Company, Device
from org.serializers import DeviceSerializer
from sales.models import Invoice
from subscriptions import company_deletion, tenant_controls
from subscriptions.models import CompanyDeletion, Subscription, SubscriptionPayment
from subscriptions.services import usage_for


def _deletion_row(deletion):
    if deletion is None:
        return None
    return {
        "id": deletion.pk,
        "requested_at": deletion.requested_at,
        "purge_after": deletion.purge_after,
        "reason": deletion.reason,
        "requested_by": (
            deletion.requested_by.full_name or deletion.requested_by.email
            if deletion.requested_by_id else None
        ),
        "backup_id": deletion.backup_id,
        "backup_rows": deletion.backup_rows,
    }


def company_row(
    company, subscription, owner, invoices_30d, last_active_at, deletion=None,
    pending_payments=0,
):
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
    suspension = None
    if subscription is not None and subscription.status == Subscription.SUSPENDED:
        suspension = {
            # Blank on rows suspended before the kind existed: manual.
            "kind": subscription.suspension_kind or Subscription.SUSPENSION_MANUAL,
            "reason": subscription.suspended_reason,
            "since": subscription.suspended_at,
        }
    return {
        "id": company.pk,
        "name": company.name,
        "slug": company.slug,
        "business_type": company.business_type,
        "is_demo": company.is_demo,
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
        "is_active": company.is_active,
        "suspension": suspension,
        "deletion": _deletion_row(deletion),
        # Shown as a warning next to "Delete": money the company recorded
        # that nobody has reviewed yet.
        "pending_payments": pending_payments,
    }


class PlatformCompanyViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    platform_capability = platform_roles.SUBSCRIPTIONS_MANAGE
    platform_view_capability = platform_roles.SUBSCRIPTIONS_VIEW
    platform_action_capabilities = {
        "suspend": platform_roles.COMPANIES_SUSPEND,
        "lift_suspension": platform_roles.COMPANIES_SUSPEND,
        "delete_company": platform_roles.COMPANIES_DELETE,
        "restore": platform_roles.COMPANIES_DELETE,
        "purge": platform_roles.COMPANIES_DELETE,
    }
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
        deletions = {
            d.company_id: d
            for d in CompanyDeletion.objects.filter(
                company_id__in=ids, status=CompanyDeletion.SCHEDULED
            ).select_related("requested_by")
        }
        pending = dict(
            SubscriptionPayment.objects.filter(
                company_id__in=ids, status=SubscriptionPayment.PENDING
            ).values_list("company_id").annotate(n=Count("id")).values_list("company_id", "n")
        )
        rows = [
            company_row(
                c, subscriptions.get(c.pk), owners.get(c.pk),
                invoices.get(c.pk, 0), activity.get(c.pk),
                deletion=deletions.get(c.pk), pending_payments=pending.get(c.pk, 0),
            )
            for c in companies
        ]
        purged = [
            {
                "id": d.company_ref, "name": d.name, "slug": d.slug,
                "purged_at": d.purged_at, "backup_id": d.backup_id,
            }
            for d in CompanyDeletion.objects.filter(
                status=CompanyDeletion.PURGED
            ).order_by("-purged_at")[:50]
        ]
        return Response(
            {
                "companies": rows,
                # Tombstones of companies already purged, newest first.
                "purged": purged,
                "generated_at": timezone.now(),
                # "disabled" or "observe" means every limit above is advisory:
                # the page must say so, or the team reads room where there is none.
                "policy": get_deployment_config().entitlement_policy,
            }
        )

    @action(detail=True, methods=["post"])
    def demo(self, request, pk=None):
        """Mark a company as a demo tenant, or clear the mark. The public page
        and the showcase card then carry the "demo company" label."""
        value = request.data.get("is_demo")
        if not isinstance(value, bool):
            raise serializers.ValidationError({"is_demo": _("Send true or false.")})
        company = get_object_or_404(Company, pk=pk)
        if company.is_demo != value:
            company.is_demo = value
            company.save(update_fields=["is_demo", "updated_at"])
            log_activity(
                action="company_demo_marked" if value else "company_demo_cleared",
                request=request, user=request.user, company=company,
                entity_type="Company", entity_id=company.pk,
                metadata={"is_demo": value},
            )
        return Response({"id": company.pk, "is_demo": company.is_demo})

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

    # ------------------------------------------------------------ owner controls

    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        """Suspend until payment: only the owner signs in, only to pay."""
        company = get_object_or_404(Company, pk=pk)
        tenant_controls.suspend_until_payment(
            company, request.user, str(request.data.get("reason") or ""), request=request
        )
        return Response({"id": company.pk, "suspended": True})

    @action(detail=True, methods=["post"], url_path="lift-suspension")
    def lift_suspension(self, request, pk=None):
        company = get_object_or_404(Company, pk=pk)
        subscription = tenant_controls.lift_suspension(
            company, request.user, request=request, note=str(request.data.get("note") or ""),
        )
        return Response({"id": company.pk, "suspended": False, "status": subscription.status})

    @action(detail=True, methods=["post"], url_path="delete")
    def delete_company(self, request, pk=None):
        """Deactivate now, back up, purge after 30 days. ``confirm`` must be
        the company's name or slug, typed."""
        company = get_object_or_404(Company, pk=pk)
        deletion = company_deletion.schedule_deletion(
            company, request.user, request.data.get("confirm"),
            reason=str(request.data.get("reason") or ""), request=request,
        )
        return Response(_deletion_row(deletion))

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        company = get_object_or_404(Company, pk=pk)
        company_deletion.restore_company(company, request.user, request=request)
        return Response({"id": company.pk, "is_active": True})

    @action(detail=True, methods=["post"])
    def purge(self, request, pk=None):
        """Delete permanently now, without waiting for the 30 days."""
        company = get_object_or_404(Company, pk=pk)
        deletion = company_deletion.open_deletion(company)
        if deletion is None:
            raise serializers.ValidationError(
                {"detail": _("Schedule the deletion first; it takes the backup.")}
            )
        company_deletion.require_confirmation(company, request.data.get("confirm"))
        deletion = company_deletion.purge_company(deletion, request.user, request=request)
        return Response({"id": deletion.company_ref, "purged_at": deletion.purged_at})

    @action(detail=True, methods=["get"])
    def backup(self, request, pk=None):
        """The deletion backup of a company (scheduled or purged) as a
        company transfer archive. Whole-company data: deleters only."""
        if not platform_roles.user_has_platform_capability(
            request.user, platform_roles.COMPANIES_DELETE
        ):
            return Response(
                {"detail": _("Your platform role does not include this action.")}, status=403
            )
        deletion = (
            CompanyDeletion.objects.select_related("backup")
            .filter(company_ref=pk).exclude(status=CompanyDeletion.RESTORED)
            .order_by("-requested_at").first()
        )
        archive = company_deletion.backup_archive(deletion) if deletion else None
        if archive is None:
            return Response({"detail": _("No backup is available for this company.")}, status=404)
        log_activity(
            action="company_backup_downloaded", request=request, user=request.user,
            entity_type="CompanyLifecycle", entity_id=deletion.company_ref,
            metadata={"company": deletion.name, "backup_id": deletion.backup_id},
        )
        stamp = deletion.requested_at.strftime("%Y-%m-%d")
        response = HttpResponse(archive, content_type="application/zip")
        response["Content-Disposition"] = (
            f'attachment; filename="vezano-company-{deletion.slug}-{stamp}.zip"'
        )
        response["Cache-Control"] = "no-store"
        return response
