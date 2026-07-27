from django.urls import path

from sync.views import SyncPullView, SyncPushView

urlpatterns = [
    path("sync/push/", SyncPushView.as_view(), name="sync-push"),
    path("sync/pull/", SyncPullView.as_view(), name="sync-pull"),
]
