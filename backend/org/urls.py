from django.urls import include, path
from rest_framework.routers import DefaultRouter

from org.views import (
    BranchViewSet,
    CompanyProfileView,
    CompanyViewSet,
    DepartmentViewSet,
    StoreModeSettingsView,
)

router = DefaultRouter()
router.register("companies", CompanyViewSet, basename="company")
router.register("branches", BranchViewSet, basename="branch")
router.register("departments", DepartmentViewSet, basename="department")

urlpatterns = [
    path(
        "company/profile/", CompanyProfileView.as_view(), name="company-profile"
    ),
    path("company/store-mode/", StoreModeSettingsView.as_view(), name="store-mode-settings"),
    path("", include(router.urls)),
]
