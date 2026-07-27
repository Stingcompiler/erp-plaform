from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("core.urls")),
    path("api/", include("accounts.urls")),
    path("api/", include("org.urls")),
    path("api/", include("inventory.urls")),
    path("api/", include("sales.urls")),
    path("api/", include("purchasing.urls")),
    path("api/", include("returns.urls")),
    path("api/", include("crm.urls")),
    path("api/", include("hr.urls")),
    path("api/", include("finance.urls")),
    path("api/", include("sync.urls")),
    path("api/", include("website.urls")),
    path("api/", include("reports.urls")),
    path("api/", include("ops.urls")),
    path("api/", include("tax.urls")),
]

if not settings.DEBUG:
    # Production serves the Next.js static export (frontend/out) directly —
    # one deployable service. Local dev keeps using `next dev` on :3000
    # against this API via CORS, so this stays out of the DEBUG=True path.
    from core.frontend import serve_frontend

    urlpatterns += [re_path(r"^(?P<path>.*)$", serve_frontend)]
