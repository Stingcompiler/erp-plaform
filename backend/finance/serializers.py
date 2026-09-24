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
        if amount is None or amount == 0:
            raise serializers.ValidationError({"amount": _("Enter an amount other than zero.")})
        # abs(): a -50,000 "expense" raised profit by 50,000 with no approval.
        if threshold and abs(amount) >= threshold and not can_approve_high_value(user):
            raise serializers.ValidationError(
                {"amount": _("Expenses of %(threshold)s or more need a manager or owner.")
                 % {"threshold": threshold}}
            )
        reverses = attrs.get("reverses")
        if amount < 0:
            # A negative amount only undoes a real expense, and never more
            # than what is left of it.
            if reverses is None:
                raise serializers.ValidationError({"reverses": _(
                    "A negative amount corrects an earlier expense: choose which one."
                )})
            if reverses.company_id != getattr(company, "pk", None):
                raise serializers.ValidationError({"reverses": _("Not your company's expense.")})
            left = reverses.amount + sum(c.amount for c in reverses.corrections.all())
            if -amount > left:
                raise serializers.ValidationError({"amount": _(
                    "The correction (%(amount)s) is more than what is left of that expense "
                    "(%(left)s)."
                ) % {"amount": -amount, "left": left}})
        elif reverses is not None:
            raise serializers.ValidationError({"reverses": _(
                "Only a negative amount can correct an earlier expense."
            )})
        account = attrs.get("company_bank_account")
        if attrs.get("method") == Expense.BANK_TRANSFER and account is None:
            raise serializers.ValidationError({"company_bank_account": _(
                "Choose the bank account this expense was paid from."
            )})
        if account is not None and account.company_id != getattr(company, "pk", None):
            raise serializers.ValidationError(
                {"company_bank_account": _("Not your company's bank account.")}
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
            "payroll_run", "salary_advance", "reverses", "company_bank_account",
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
            raise serializers.ValidationError(_("period_end cannot be before period_start."))
        # Revenue is one company figure; two revenue lines both received it.
        lines = attrs.get("lines") or []
        if sum(1 for line in lines if line.get("kind") == BudgetLine.REVENUE) > 1:
            raise serializers.ValidationError({"lines": _("A budget has one revenue line.")})
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
                _("An approved budget is locked. Reopen it before making changes.")
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
