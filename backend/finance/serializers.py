from django.utils.translation import gettext as _
from rest_framework import serializers

from finance.models import Budget, BudgetLine, Expense


class ExpenseSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        # The same tier every other money-moving record has: at or above the
        # company's payment threshold an expense needs an approver role.
        # Expenses were the one outflow anyone with finance write could post
        # unbounded.
        from core.rbac import can_approve_high_value

        request = self.context.get("request")
        user = getattr(request, "user", None)
        company = getattr(user, "company", None)
        threshold = getattr(company, "payment_approval_threshold", 0) or 0
        amount = attrs.get("amount")
        if threshold and amount is not None and amount >= threshold:
            if not can_approve_high_value(user):
                raise serializers.ValidationError(
                    {"amount": _("Expenses of %(threshold)s or more need a manager or owner.")
                     % {"threshold": threshold}}
                )
        return attrs

    method_display = serializers.CharField(source="get_method_display", read_only=True)
    recorded_by_name = serializers.CharField(
        source="recorded_by.full_name", read_only=True, default=None
    )

    class Meta:
        model = Expense
        fields = [
            "id", "category", "description", "amount", "method",
            "method_display", "date", "recorded_by_name", "created_at",
            "payroll_run", "salary_advance",
        ]
        # The HR links are set by the approval flows only.
        read_only_fields = ["created_at", "payroll_run", "salary_advance"]

    def create(self, validated_data):
        request = self.context.get("request")
        if request is not None:
            validated_data["recorded_by"] = request.user
        return super().create(validated_data)


class BudgetLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = BudgetLine
        fields = ["id", "kind", "category", "planned_amount"]


class BudgetSerializer(serializers.ModelSerializer):
    lines = BudgetLineSerializer(many=True, required=False)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    approved_by_name = serializers.SerializerMethodField()
    planned_total = serializers.SerializerMethodField()

    class Meta:
        model = Budget
        fields = [
            "id", "name", "period_start", "period_end",
            "status", "status_display", "note",
            "approved_by_name", "approved_at", "planned_total",
            "lines", "created_at",
        ]
        # Status moves only through the approve/reopen actions, never by a
        # direct write — otherwise a draft could be self-activated.
        read_only_fields = ["status", "approved_at", "created_at"]

    def get_planned_total(self, obj):
        return str(obj.planned_total())

    def get_approved_by_name(self, obj):
        """Full name when set, otherwise the email — an approver must always be
        identifiable on an approved budget."""
        if not obj.approved_by:
            return None
        return obj.approved_by.full_name or obj.approved_by.email

    def validate(self, attrs):
        start = attrs.get("period_start", getattr(self.instance, "period_start", None))
        end = attrs.get("period_end", getattr(self.instance, "period_end", None))
        if start and end and end < start:
            raise serializers.ValidationError("period_end cannot be before period_start.")
        return attrs

    def create(self, validated_data):
        lines = validated_data.pop("lines", [])
        request = self.context.get("request")
        if request is not None:
            validated_data["created_by"] = request.user
        budget = super().create(validated_data)
        for line in lines:
            BudgetLine.objects.create(budget=budget, **line)
        return budget

    def update(self, instance, validated_data):
        if instance.status == Budget.APPROVED:
            raise serializers.ValidationError(
                "An approved budget is locked. Reopen it before making changes."
            )
        lines = validated_data.pop("lines", None)
        from django.db import transaction
        with transaction.atomic():
            budget = super().update(instance, validated_data)
            if lines is not None:
                # Lines are replaced wholesale — a budget is edited as one document.
                budget.lines.all().delete()
                for line in lines:
                    BudgetLine.objects.create(budget=budget, **line)
            return budget
