from django.urls import include, path
from rest_framework.routers import DefaultRouter

from crm.views import (
    CustomerGroupViewSet,
    FollowUpViewSet,
    LeadViewSet,
    NoteViewSet,
)

router = DefaultRouter()
router.register("customer-groups", CustomerGroupViewSet, basename="customergroup")
router.register("leads", LeadViewSet, basename="lead")
router.register("followups", FollowUpViewSet, basename="followup")
router.register("crm-notes", NoteViewSet, basename="crmnote")

urlpatterns = [
    path("", include(router.urls)),
]
