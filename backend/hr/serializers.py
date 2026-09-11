"""
HR serializers.

Company scoping is enforced by the viewset (CompanyScopedModelViewSet forces
`company` from the request user and filters every queryset). Relational fields
that point at other company-owned rows (employee, branch, department, position)
are narrowed to the request user's company in `__init__` so a client can't
attach another tenant's row by id. Reviewer/approver identities come from the
request user, never the request body.
"""
from django.utils import timezone
from rest_framework import serializers

from hr.models import (
    Attendance,
    Deduction,
    Employee,
    EmployeeDocument,
    LeaveRequest,
    PerformanceRecord,
    Position,
    SalaryAdvance,
    PayrollRun,
    PayrollEntry,
    WorkPolicy,
)


class _CompanyScopedFKMixin:
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


class PositionSerializer(serializers.ModelSerializer):
    employee_count = serializers.SerializerMethodField()

    class Meta:
        model = Position
        fields = [
            "id", "title", "description", "base_salary", "is_active",
            "employee_count", "created_at",
        ]
        read_only_fields = ["created_at"]

    def get_employee_count(self, obj):
        return obj.employees.count()


class EmployeeSerializer(_CompanyScopedFKMixin, serializers.ModelSerializer):
    scoped_fk_fields = ("branch", "department", "position")

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    position_title = serializers.CharField(source="position.title", read_only=True, default=None)
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)

    class Meta:
        model = Employee
        fields = [
            "id", "employee_code", "full_name", "email", "phone",
            "branch", "department", "department_name",
            "position", "position_title",
            "hire_date", "status", "status_display",
            "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class AttendanceSerializer(_CompanyScopedFKMixin, serializers.ModelSerializer):
    scoped_fk_fields = ("employee",)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)

    class Meta:
        model = Attendance
        fields = [
            "id", "employee", "employee_name", "date", "status",
            "check_in", "check_out", "note", "created_at",
        ]
        read_only_fields = ["created_at"]


class LeaveRequestSerializer(_CompanyScopedFKMixin, serializers.ModelSerializer):
    scoped_fk_fields = ("employee",)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    leave_type_display = serializers.CharField(
        source="get_leave_type_display", read_only=True
    )
    # Uploaded on write (multipart); on read we only expose whether one exists —
    # the file itself is downloaded through the scoped `report` viewset action,
    # never a public media URL (medical reports are sensitive).
    medical_report = serializers.FileField(
        required=False, allow_null=True, write_only=True
    )
    has_report = serializers.SerializerMethodField()

    class Meta:
        model = LeaveRequest
        fields = [
            "id", "employee", "employee_name", "start_date", "end_date",
            "leave_type", "leave_type_display", "reason", "medical_report",
            "has_report", "status", "status_display", "reviewed_at", "created_at",
        ]
        read_only_fields = ["reviewed_at", "created_at"]

    def get_has_report(self, obj):
        return bool(obj.medical_report)

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError("end_date cannot be before start_date.")
        return attrs

    def update(self, instance, validated_data):
        # Stamp the reviewer/time when a request transitions out of pending.
        request = self.context.get("request")
        new_status = validated_data.get("status")
        if new_status and new_status != instance.status and new_status != LeaveRequest.PENDING:
            validated_data["reviewed_at"] = timezone.now()
            if request is not None:
                validated_data["reviewed_by"] = request.user
        return super().update(instance, validated_data)


class PerformanceRecordSerializer(_CompanyScopedFKMixin, serializers.ModelSerializer):
    scoped_fk_fields = ("employee",)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    reviewer_name = serializers.CharField(
        source="reviewer.full_name", read_only=True, default=None
    )

    class Meta:
        model = PerformanceRecord
        fields = [
            "id", "employee", "employee_name", "review_date", "rating",
            "summary", "reviewer_name", "created_at",
        ]
        read_only_fields = ["created_at"]

    def validate_rating(self, value):
        if not 1 <= value <= 5:
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value

    def create(self, validated_data):
        request = self.context.get("request")
        if request is not None:
            validated_data["reviewer"] = request.user
        return super().create(validated_data)


class EmployeeDocumentSerializer(_CompanyScopedFKMixin, serializers.ModelSerializer):
    scoped_fk_fields = ("employee",)

    class Meta:
        model = EmployeeDocument
        fields = [
            "id", "employee", "title", "doc_type", "file_url", "note", "created_at",
        ]
        read_only_fields = ["created_at"]

    def create(self, validated_data):
        request = self.context.get("request")
        if request is not None:
            validated_data["uploaded_by"] = request.user
        return super().create(validated_data)


class SalaryAdvanceSerializer(_CompanyScopedFKMixin, serializers.ModelSerializer):
    scoped_fk_fields = ("employee",)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = SalaryAdvance
        fields = [
            "id", "employee", "employee_name", "amount", "reason",
            "status", "status_display", "reviewed_at", "created_at",
        ]
        read_only_fields = ["reviewed_at", "created_at"]

    def update(self, instance, validated_data):
        request = self.context.get("request")
        new_status = validated_data.get("status")
        if new_status and new_status != instance.status and new_status != SalaryAdvance.PENDING:
            validated_data["reviewed_at"] = timezone.now()
            if request is not None:
                validated_data["reviewed_by"] = request.user
        return super().update(instance, validated_data)


class PayrollEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollEntry
        fields = ["id", "employee", "employee_name", "department_name", "position_title", "base_salary", "deductions_total", "advances_total", "net_salary"]
        read_only_fields = fields


class PayrollRunSerializer(serializers.ModelSerializer):
    entries = PayrollEntrySerializer(many=True, read_only=True)
    employee_count = serializers.IntegerField(source="entries.count", read_only=True)

    class Meta:
        model = PayrollRun
        fields = ["id", "period", "status", "employee_count", "created_at", "approved_at", "entries"]
        read_only_fields = fields


class WorkPolicySerializer(serializers.ModelSerializer):
    violation_type_display = serializers.CharField(
        source="get_violation_type_display", read_only=True
    )

    class Meta:
        model = WorkPolicy
        fields = [
            "id", "name", "description", "violation_type",
            "violation_type_display", "is_active", "created_at",
        ]
        read_only_fields = ["created_at"]


class DeductionSerializer(_CompanyScopedFKMixin, serializers.ModelSerializer):
    scoped_fk_fields = ("employee", "policy")
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    policy_name = serializers.CharField(source="policy.name", read_only=True, default=None)
    recorded_by_name = serializers.CharField(
        source="recorded_by.full_name", read_only=True, default=None
    )

    class Meta:
        model = Deduction
        fields = [
            "id", "employee", "employee_name", "policy", "policy_name",
            "amount", "note", "date", "recorded_by_name", "created_at",
        ]
        read_only_fields = ["created_at"]

    def create(self, validated_data):
        request = self.context.get("request")
        if request is not None:
            validated_data["recorded_by"] = request.user
        return super().create(validated_data)
