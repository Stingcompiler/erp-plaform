from django.urls import include, path
from rest_framework.routers import DefaultRouter

from accounts.platform_team_views import (
    PlatformActivityViewSet,
    PlatformInvitationAcceptView,
    PlatformTeamViewSet,
)
from accounts.password_reset import PasswordResetConfirmView, PasswordResetRequestView
from core.error_views import ErrorEventViewSet
from accounts.views import (
    LoginView,
    LogoutView,
    MeView,
    PermissionViewSet,
    RefreshView,
    RoleViewSet,
    UserViewSet,
)

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("roles", RoleViewSet, basename="role")
router.register("permissions", PermissionViewSet, basename="permission")
router.register("platform/team", PlatformTeamViewSet, basename="platform-team")
router.register("platform/errors", ErrorEventViewSet, basename="platform-errors")
router.register("platform/activity", PlatformActivityViewSet, basename="platform-activity")

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path(
        "auth/password-reset/",
        PasswordResetRequestView.as_view(), name="auth-password-reset",
    ),
    path(
        "auth/password-reset/confirm/",
        PasswordResetConfirmView.as_view(), name="auth-password-reset-confirm",
    ),
    path(
        "public/platform-invitations/accept/", PlatformInvitationAcceptView.as_view(),
        name="platform-invitation-accept",
    ),
    path("", include(router.urls)),
]
