from django.urls import include, path
from rest_framework.routers import DefaultRouter

from website.views import (
    FeaturedProductViewSet,
    DemoRequestView,
    OwnerInvitationAcceptView,
    PlatformLeadViewSet,
    PlatformOverviewView,
    PlatformRegistrationRequestViewSet,
    PublicPlanListView,
    PublicRegistrationRequestView,
    PublicSiteView,
    SectionViewSet,
    WebsitePublishView,
    WebsiteView, WebsiteImageUploadView, WebsiteImageViewSet,
)

router = DefaultRouter()
router.register("website/sections", SectionViewSet, basename="section")
router.register("website/gallery", WebsiteImageViewSet, basename="website-image")
router.register(
    "website/featured-products", FeaturedProductViewSet, basename="featuredproduct"
)
router.register("platform/leads", PlatformLeadViewSet, basename="platform-lead")
router.register(
    "platform/registration-requests", PlatformRegistrationRequestViewSet,
    basename="platform-registration-request",
)

urlpatterns = [
    path("platform/overview/", PlatformOverviewView.as_view(), name="platform-overview"),
    path("public/demo-requests/", DemoRequestView.as_view(), name="demo-request"),
    path("public/plans/", PublicPlanListView.as_view(), name="public-plan-list"),
    path(
        "public/registration-requests/", PublicRegistrationRequestView.as_view(),
        name="registration-request",
    ),
    path(
        "public/owner-invitations/accept/", OwnerInvitationAcceptView.as_view(),
        name="owner-invitation-accept",
    ),
    path("website/page/", WebsiteView.as_view(), name="website-page"),
    path("website/page/publish/", WebsitePublishView.as_view(), name="website-publish"),
    path(
        "website/page/image/<str:kind>/", WebsiteImageUploadView.as_view(),
        name="website-image",
    ),
    # Public, unauthenticated read-only site by company slug.
    path("public/site/<slug:slug>/", PublicSiteView.as_view(), name="public-site"),
    path("", include(router.urls)),
]
