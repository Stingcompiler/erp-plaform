from django.contrib import admin

from hr.models import (
    Attendance,
    Employee,
    EmployeeDocument,
    LeaveRequest,
    PerformanceRecord,
    Position,
)


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "is_active")
    list_filter = ("company", "is_active")
    search_fields = ("title",)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("full_name", "company", "position", "department", "status")
    list_filter = ("company", "status", "department")
    search_fields = ("full_name", "employee_code", "email")


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("employee", "date", "status", "company")
    list_filter = ("company", "status")


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ("employee", "start_date", "end_date", "status", "company")
    list_filter = ("company", "status")


@admin.register(PerformanceRecord)
class PerformanceRecordAdmin(admin.ModelAdmin):
    list_display = ("employee", "review_date", "rating", "company")
    list_filter = ("company",)


@admin.register(EmployeeDocument)
class EmployeeDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "employee", "doc_type", "company")
    list_filter = ("company",)
