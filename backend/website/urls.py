from django.urls import include, path
from rest_framework.routers import DefaultRouter

from website.public_pages import public_showcase
from website.analytics_views import CompanyVisitsView, PlatformAnalyticsOverview, PlatformFunnelView
from website.seo_views import (
    PublicSiteContactView, SeoOgImageView, SeoPageOverrideViewSet, SeoSettingsView,
)
from website.views import (
    FeaturedProductViewSet,
    DemoRequestView,
    OwnerInvitationAcceptView,
    PlatformLeadViewSet,
    PlatformOverviewView,
    PlatformRegistrationRequestViewSet,
    PublicPlanListView,
    PublicRegistrationRequestView,
    PublicOrderCreateView,
    PublicOrderViewSet,
    PublicSiteView,
    SectionViewSet,
    WebsitePublishView,
    WebsiteView, WebsiteImageUploadView, WebsiteImageViewSet, WebsitePreviewView,
)

router = DefaultRouter()
router.register("website/sections", SectionViewSet, basename="section")
router.register("website/gallery", WebsiteImageViewSet, basename="website-image")
router.register(
    "website/featured-products", FeaturedProductViewSet, basename="featuredproduct"
)
router.register("platform/leads", PlatformLeadViewSet, basename="platform-lead")
router.register("web-orders", PublicOrderViewSet, basename="web-order")
router.register(
    "platform/registration-requests", PlatformRegistrationRequestViewSet,
    basename="platform-registration-request",
)
router.register(
    "platform/seo/overrides", SeoPageOverrideViewSet, basename="platform-seo-override"
)

urlpatterns = [
    path("platform/overview/", PlatformOverviewView.as_view(), name="platform-overview"),
    path(
        "platform/analytics/overview/", PlatformAnalyticsOverview.as_view(),
        name="platform-analytics-overview",
    ),
    path(
        "platform/analytics/funnel/", PlatformFunnelView.as_view(),
        name="platform-analytics-funnel",
    ),
    path("platform/seo/settings/", SeoSettingsView.as_view(), name="platform-seo-settings"),
    path(
        "platform/seo/settings/image/", SeoOgImageView.as_view(),
        name="platform-seo-settings-image",
    ),
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
    path("website/visits/", CompanyVisitsView.as_view(), name="website-visits"),
    path("website/page/publish/", WebsitePublishView.as_view(), name="website-publish"),
    path("website/page/preview/", WebsitePreviewView.as_view(), name="website-preview"),
    path("public/showcase/", public_showcase, name="public-showcase"),
    path("public/site-contact/", PublicSiteContactView.as_view(), name="public-site-contact"),
    path(
        "website/page/image/<str:kind>/", WebsiteImageUploadView.as_view(),
        name="website-image",
    ),
    # Public, unauthenticated read-only site by company slug.
    path("public/site/<slug:slug>/", PublicSiteView.as_view(), name="public-site"),
    path(
        "public/site/<slug:slug>/orders/", PublicOrderCreateView.as_view(),
        name="public-site-order",
    ),
    path("", include(router.urls)),
]
