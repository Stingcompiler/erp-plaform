from django.urls import include, path
from rest_framework.routers import DefaultRouter

from website.views import (
    FeaturedProductViewSet,
    PublicSiteView,
    SectionViewSet,
    WebsitePublishView,
    WebsiteView,
)

router = DefaultRouter()
router.register("website/sections", SectionViewSet, basename="section")
router.register(
    "website/featured-products", FeaturedProductViewSet, basename="featuredproduct"
)

urlpatterns = [
    path("website/page/", WebsiteView.as_view(), name="website-page"),
    path("website/page/publish/", WebsitePublishView.as_view(), name="website-publish"),
    # Public, unauthenticated read-only site by company slug.
    path("public/site/<slug:slug>/", PublicSiteView.as_view(), name="public-site"),
    path("", include(router.urls)),
]
