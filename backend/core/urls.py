from django.urls import include, path
from rest_framework.routers import DefaultRouter

from core.views import (
    ActivityLogViewSet,
    attention,
    attention_seen,
    dashboard,
    health_check,
    rbac_access,
)

router = DefaultRouter()
router.register("activity-logs", ActivityLogViewSet, basename="activitylog")

urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("dashboard/", dashboard, name="dashboard"),
    path("rbac/access/", rbac_access, name="rbac-access"),
    path("attention/", attention, name="attention"),
    path("attention/seen/", attention_seen, name="attention-seen"),
    path("", include(router.urls)),
]
