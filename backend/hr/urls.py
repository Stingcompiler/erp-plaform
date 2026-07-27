from django.urls import include, path
from rest_framework.routers import DefaultRouter

from hr.views import (
    AttendanceViewSet,
    DeductionViewSet,
    EmployeeDocumentViewSet,
    EmployeeViewSet,
    LeaveRequestViewSet,
    PerformanceRecordViewSet,
    PositionViewSet,
    SalaryAdvanceViewSet,
    WorkPolicyViewSet,
)

router = DefaultRouter()
router.register("positions", PositionViewSet, basename="position")
router.register("employees", EmployeeViewSet, basename="employee")
router.register("attendance", AttendanceViewSet, basename="attendance")
router.register("leave-requests", LeaveRequestViewSet, basename="leaverequest")
router.register("performance-records", PerformanceRecordViewSet, basename="performancerecord")
router.register("employee-documents", EmployeeDocumentViewSet, basename="employeedocument")
router.register("salary-advances", SalaryAdvanceViewSet, basename="salaryadvance")
router.register("work-policies", WorkPolicyViewSet, basename="workpolicy")
router.register("deductions", DeductionViewSet, basename="deduction")

urlpatterns = [
    path("", include(router.urls)),
]
