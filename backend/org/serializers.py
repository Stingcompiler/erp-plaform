from django.utils.translation import gettext as _
from rest_framework import serializers

from org.models import Branch, Company, Department, Device, ExchangeRate, TaxProfile


class TaxProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxProfile
        fields = [
            "country",
            "invoice_format",
            "flat_tax_rate",
            "e_invoicing_enabled",
            "invoice_xml_format",
        ]
        read_only_fields = ["invoice_xml_format"]


class CompanySerializer(serializers.ModelSerializer):
    tax_profile = TaxProfileSerializer(read_only=True)

    class Meta:
        model = Company
        fields = [
            "id",
            "name",
            "legal_name",
            "slug",
            "currency",
            "timezone",
            "business_type",
            "address",
            "phone",
            "email",
            "tax_number",
            "registration_number",
            "is_active",
            "tax_profile",
            "created_at",
        ]
        read_only_fields = ["slug", "created_at"]

    def validate_timezone(self, value):
        from core.timezone import is_valid_timezone

        if not is_valid_timezone(value):
            raise serializers.ValidationError(
                _("Unknown time zone; use an IANA name such as Africa/Khartoum.")
            )
        return value


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = [
            "id",
            "company",
            "name",
            "code",
            "address",
            "phone",
            "is_active",
        ]
        read_only_fields = ["company"]


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "company", "branch", "name", "is_active"]
        read_only_fields = ["company"]

    def validate_branch(self, branch):
        # A department's branch must belong to the same company as the
        # requesting user — never let a payload cross the tenant boundary.
        if branch is None:
            return branch
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is not None and not getattr(user, "is_platform_admin", False):
            if branch.company_id != getattr(user, "company_id", None):
                raise serializers.ValidationError(
                    _("Branch does not belong to your company.")
                )
        return branch


class DeviceSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    last_user_name = serializers.SerializerMethodField()

    class Meta:
        model = Device
        fields = [
            "id", "device_id", "label", "user_agent", "branch", "branch_name",
            "last_user", "last_user_name", "first_seen_at", "last_seen_at",
            "is_active", "revoked_at",
        ]
        read_only_fields = [f for f in fields if f != "label"]

    def get_last_user_name(self, obj):
        user = obj.last_user
        return (user.full_name or user.email) if user else None


class ExchangeRateSerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.CharField(
        source="recorded_by.full_name", read_only=True, default=""
    )

    class Meta:
        model = ExchangeRate
        fields = ["id", "currency", "rate", "note", "recorded_at", "recorded_by_name"]
        read_only_fields = ["id", "currency", "recorded_at", "recorded_by_name"]

    def validate_rate(self, value):
        if value <= 0:
            raise serializers.ValidationError(_("The rate must be greater than zero."))
        return value
