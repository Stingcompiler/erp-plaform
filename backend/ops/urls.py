from django.urls import path

from ops.views import (
    BackupDownloadView, BackupView, LanguagesView, PreferenceView, RestoreView,
)

urlpatterns = [
    path("ops/backups/", BackupView.as_view(), name="ops-backups"),
    path("ops/backups/restore/", RestoreView.as_view(), name="ops-restore"),
    path(
        "ops/backups/<int:pk>/download/", BackupDownloadView.as_view(),
        name="ops-backup-download",
    ),
    path("ops/preferences/", PreferenceView.as_view(), name="ops-preferences"),
    path("ops/languages/", LanguagesView.as_view(), name="ops-languages"),
]
