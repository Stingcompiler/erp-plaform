from rest_framework import serializers

from finance.models import Budget, BudgetLine, Expense


class ExpenseSerializer(serializers.ModelSerializer):
    method_display = serializers.CharField(source="get_method_display", read_only=True)
    recorded_by_name = serializers.CharField(
        source="recorded_by.full_name", read_only=True, default=None
    )

    class Meta:
        model = Expense
        fields = [
            "id", "category", "description", "amount", "method",
            "method_display", "date", "recorded_by_name", "created_at",
        ]
        read_only_fields = ["created_at"]

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
        lines = validated_data.pop("lines", None)
        budget = super().update(instance, validated_data)
        if lines is not None:
            # Lines are replaced wholesale — a budget is edited as one document.
            budget.lines.all().delete()
            for line in lines:
                BudgetLine.objects.create(budget=budget, **line)
        return budget
