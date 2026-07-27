from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from core.activity import log_activity
from core.deletion import ArchiveOnDeleteMixin
from core.scoping import CompanyScopedModelViewSet
from crm.models import CustomerGroup, FollowUp, Lead, Note
from sales.models import Customer
from crm.serializers import (
    CustomerGroupSerializer,
    FollowUpSerializer,
    LeadSerializer,
    NoteSerializer,
)


class CustomerGroupViewSet(ArchiveOnDeleteMixin, CompanyScopedModelViewSet):
    queryset = CustomerGroup.objects.select_related("company").all()
    serializer_class = CustomerGroupSerializer
    activity_entity_type = "CustomerGroup"


class LeadViewSet(CompanyScopedModelViewSet):
    queryset = Lead.objects.select_related(
        "company", "branch", "customer_group", "assigned_to"
    ).all()
    serializer_class = LeadSerializer
    activity_entity_type = "Lead"
    branch_field = "branch"
    # A lead is a prospect, not a financial record — the CRM officer who owns
    # the pipeline clears their own duplicates. Note that deleting one cascades
    # its notes and follow-ups, so the usual advice is to mark it Lost instead.
    manager_only_delete = False

    def get_queryset(self):
        qs = super().get_queryset()
        stage = self.request.query_params.get("stage")
        if stage:
            qs = qs.filter(stage=stage)
        # ?open=1 hides won/lost so the pipeline stays focused on live deals.
        if self.request.query_params.get("open") in ("1", "true"):
            qs = qs.exclude(stage__in=Lead.CLOSED_STAGES)
        return qs

    @action(detail=False, methods=["get"])
    def pipeline(self, request):
        """Lead counts and estimated value grouped by stage — drives the
        pipeline board and the CRM dashboard tiles."""
        qs = self.filter_queryset(self.get_queryset())
        # One grouped query rather than two per stage, and no rows pulled into
        # Python just to be summed.
        rows = {
            r["stage"]: r
            for r in qs.values("stage").annotate(
                count=Count("id"),
                value=Coalesce(Sum("estimated_value"), Decimal("0")),
            )
        }
        cents = Decimal("0.01")
        return Response(
            {
                stage: {
                    "label": label,
                    "count": rows.get(stage, {}).get("count", 0),
                    # Always a 2-decimal string: an empty stage returning "0"
                    # beside "1500.00" reads as a bug in the dashboard.
                    "value": str(
                        Decimal(
                            rows.get(stage, {}).get("value", 0) or 0
                        ).quantize(cents)
                    ),
                }
                for stage, label in Lead.STAGE_CHOICES
            }
        )

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        """
        Turn a won lead into a customer — the handoff from CRM to Sales that
        was missing, leaving 'won' as a dead end you had to re-key by hand.

        Idempotent: converting twice returns the existing customer rather than
        creating a duplicate, because this is exactly the kind of button people
        press again when a response is slow.
        """
        lead = self.get_object()
        if lead.stage != Lead.STAGE_WON:
            return Response(
                {
                    "detail": (
                        "Only a won lead can be converted. Move it to Won first."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing = Customer.objects.filter(
            company_id=lead.company_id, name=lead.name
        ).first()
        if existing:
            return Response(
                {"customer": existing.id, "name": existing.name, "created": False}
            )

        customer = Customer.objects.create(
            company_id=lead.company_id,
            name=lead.name,
            phone=lead.phone,
            email=lead.email,
        )
        log_activity(
            action="create", request=request, entity_type="Customer",
            entity_id=customer.id, metadata={"converted_from_lead": lead.id},
        )
        return Response(
            {"customer": customer.id, "name": customer.name, "created": True},
            status=status.HTTP_201_CREATED,
        )


class FollowUpViewSet(CompanyScopedModelViewSet):
    queryset = FollowUp.objects.select_related("company", "lead").all()
    serializer_class = FollowUpSerializer
    activity_entity_type = "FollowUp"
    # Working notes on a lead — the CRM officer who wrote one may clear it.
    manager_only_delete = False

    def get_queryset(self):
        qs = super().get_queryset()
        lead = self.request.query_params.get("lead")
        if lead:
            qs = qs.filter(lead_id=lead)
        if self.request.query_params.get("open") in ("1", "true"):
            qs = qs.filter(done=False)
        return qs


class NoteViewSet(CompanyScopedModelViewSet):
    queryset = Note.objects.select_related("company", "lead", "created_by").all()
    serializer_class = NoteSerializer
    activity_entity_type = "Note"
    manager_only_delete = False

    def get_queryset(self):
        qs = super().get_queryset()
        lead = self.request.query_params.get("lead")
        if lead:
            qs = qs.filter(lead_id=lead)
        return qs
