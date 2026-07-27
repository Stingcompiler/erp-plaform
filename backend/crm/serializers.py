"""
CRM serializers.

Company scoping is enforced two ways that reinforce each other:
  * the viewset forces `company` from the request user on create and filters
    every queryset by it (CompanyScopedModelViewSet), and
  * relational fields here (lead, customer_group, branch, assigned_to) have
    their querysets narrowed to the request user's company in `__init__`, so a
    client can't attach another tenant's row by guessing its id.
`created_by` is always taken from the request user, never the request body.
"""
from django.utils import timezone
from rest_framework import serializers

from crm.models import CustomerGroup, FollowUp, Lead, Note


class _CompanyScopedFKMixin:
    """Narrows the given relational fields to the request user's company.

    Platform admins (no company) are left unrestricted — they already bypass
    company scoping everywhere else.
    """

    # {field_name: (queryset_or_None uses field default)}
    scoped_fk_fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        company_id = getattr(getattr(request, "user", None), "company_id", None)
        if company_id is None:
            return
        for name in self.scoped_fk_fields:
            field = self.fields.get(name)
            if field is not None and getattr(field, "queryset", None) is not None:
                field.queryset = field.queryset.filter(company_id=company_id)


class CustomerGroupSerializer(serializers.ModelSerializer):
    lead_count = serializers.SerializerMethodField()

    class Meta:
        model = CustomerGroup
        fields = [
            "id", "name", "description", "color", "is_active",
            "lead_count", "created_at",
        ]
        read_only_fields = ["created_at"]

    def get_lead_count(self, obj):
        return obj.leads.count()


class LeadSerializer(_CompanyScopedFKMixin, serializers.ModelSerializer):
    scoped_fk_fields = ("customer_group", "branch")

    stage_display = serializers.CharField(source="get_stage_display", read_only=True)
    customer_group_name = serializers.CharField(
        source="customer_group.name", read_only=True, default=None
    )
    assigned_to_name = serializers.CharField(
        source="assigned_to.full_name", read_only=True, default=None
    )
    open_followups = serializers.SerializerMethodField()
    is_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = Lead
        fields = [
            "id", "name", "contact_name", "email", "phone", "source",
            "stage", "stage_display", "estimated_value",
            "customer_group", "customer_group_name",
            "branch", "assigned_to", "assigned_to_name",
            "is_open", "open_followups", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_open_followups(self, obj):
        return obj.followups.filter(done=False).count()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # assigned_to is scoped to company users, not the generic user table.
        request = self.context.get("request")
        company_id = getattr(getattr(request, "user", None), "company_id", None)
        field = self.fields.get("assigned_to")
        if company_id is not None and field is not None:
            field.queryset = field.queryset.filter(company_id=company_id)

    def create(self, validated_data):
        request = self.context.get("request")
        if request is not None:
            validated_data["created_by"] = request.user
        return super().create(validated_data)


class FollowUpSerializer(_CompanyScopedFKMixin, serializers.ModelSerializer):
    scoped_fk_fields = ("lead",)
    lead_name = serializers.CharField(source="lead.name", read_only=True)

    class Meta:
        model = FollowUp
        fields = [
            "id", "lead", "lead_name", "due_date", "summary",
            "done", "done_at", "created_at",
        ]
        read_only_fields = ["done_at", "created_at"]

    def create(self, validated_data):
        request = self.context.get("request")
        if request is not None:
            validated_data["created_by"] = request.user
        if validated_data.get("done") and not validated_data.get("done_at"):
            validated_data["done_at"] = timezone.now()
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Stamp/clear done_at when the done flag flips, so the timeline is honest.
        if "done" in validated_data:
            if validated_data["done"] and not instance.done:
                validated_data["done_at"] = timezone.now()
            elif not validated_data["done"]:
                validated_data["done_at"] = None
        return super().update(instance, validated_data)


class NoteSerializer(_CompanyScopedFKMixin, serializers.ModelSerializer):
    scoped_fk_fields = ("lead",)
    created_by_name = serializers.CharField(
        source="created_by.full_name", read_only=True, default=None
    )

    class Meta:
        model = Note
        fields = ["id", "lead", "body", "created_by_name", "created_at"]
        read_only_fields = ["created_at"]

    def create(self, validated_data):
        request = self.context.get("request")
        if request is not None:
            validated_data["created_by"] = request.user
        return super().create(validated_data)
