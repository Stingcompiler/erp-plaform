from django.urls import include, path
from rest_framework.routers import DefaultRouter

from subscriptions.platform_companies import PlatformCompanyViewSet
from subscriptions.views import (
    CompanySubscriptionPaymentViewSet,
    CompanySubscriptionView,
    DeploymentInfoView,
    PlatformPlanVersionViewSet,
    PlatformPlanViewSet,
    PlatformSubscriptionViewSet,
    PlatformSubscriptionInvoiceViewSet,
    PlatformSubscriptionPaymentViewSet,
)

router = DefaultRouter()
router.register(
    "subscription/payments",
    CompanySubscriptionPaymentViewSet,
    basename="subscription-payment",
)
router.register("platform/plans", PlatformPlanViewSet, basename="platform-plan")
router.register("platform/companies", PlatformCompanyViewSet, basename="platform-company")
router.register(
    "platform/plan-versions",
    PlatformPlanVersionViewSet,
    basename="platform-plan-version",
)
router.register(
    "platform/subscriptions",
    PlatformSubscriptionViewSet,
    basename="platform-subscription",
)
router.register(
    "platform/subscription-invoices",
    PlatformSubscriptionInvoiceViewSet,
    basename="platform-subscription-invoice",
)
router.register(
    "platform/subscription-payments",
    PlatformSubscriptionPaymentViewSet,
    basename="platform-subscription-payment",
)

urlpatterns = [
    path(
        "subscription/", CompanySubscriptionView.as_view(), name="company-subscription"
    ),
    path("deployment/", DeploymentInfoView.as_view(), name="deployment-info"),
    path("", include(router.urls)),
]
