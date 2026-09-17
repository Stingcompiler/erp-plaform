from django.urls import path

from sync.views import (
    DiscardedOperationListView,
    DiscardedOperationResolveView,
    SyncDiscardView,
    SyncPullView,
    SyncPushView,
)

urlpatterns = [
    path("sync/push/", SyncPushView.as_view(), name="sync-push"),
    path("sync/pull/", SyncPullView.as_view(), name="sync-pull"),
    path("sync/discard/", SyncDiscardView.as_view(), name="sync-discard"),
    path("sync/discarded/", DiscardedOperationListView.as_view(), name="sync-discarded"),
    path(
        "sync/discarded/<int:pk>/resolve/",
        DiscardedOperationResolveView.as_view(),
        name="sync-discarded-resolve",
    ),
]
