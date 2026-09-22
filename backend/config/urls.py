from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path

from core.frontend import FRONTEND_DIST, serve_frontend

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
    path("api/", include("subscriptions.urls")),
    path("api/", include("licensing.urls")),
]

# The Next.js app is built as a static export (frontend/out) and served by
# Django, so the frontend and API are one origin / one deployable service.
# Production always serves it through this catch-all; development serves it too
# whenever the export has been built (run `npm run build` in frontend/ after UI
# changes), so `runserver` on :8000 shows the real pages — `next dev` on :3000
# still works via CORS for hot-reload.
#
# The catch-all is listed last and excludes the /api/, /admin/, /static/,
# /media/ and /s/ prefixes, so it can never shadow the API, the admin, Django's
# static/media handlers or the public company pages (unknown /api/ paths keep
# Django/DRF behaviour and JSON 404s). Frontend routes (dashboard, login, ...)
# don't collide with those prefixes, so nothing the export serves is lost.
# Public company pages (/s/<slug>/), their directory and sitemap are rendered
# by Django (website.public_pages), so they sit outside the export too.
from website.public_pages import (  # noqa: E402
    public_site_directory,
    public_pay_page,
    public_site_page,
    public_sites_sitemap,
)

from core.public_media import serve_public_media  # noqa: E402

urlpatterns += [
    # Only MEDIA_ROOT/public/ (site and product images) is served anonymously.
    path("media/public/<path:path>", serve_public_media, name="public-media"),
    path("s/", public_site_directory, name="public-site-directory"),
    path("s/<slug:slug>/", public_site_page, name="public-site-page"),
    path("s/<slug:slug>/pay/", public_pay_page, name="public-pay-page"),
    path("sitemap-sites.xml", public_sites_sitemap, name="public-sites-sitemap"),
]

_FRONTEND_CATCH_ALL = re_path(
    r"^(?!api/|admin/|static/|media/|s/|sitemap-sites\.xml$)(?P<path>.*)$",
    serve_frontend,
)

if not settings.DEBUG or FRONTEND_DIST.is_dir():
    urlpatterns += [_FRONTEND_CATCH_ALL]
else:
    # Dev with no export built yet: answer "/" with a small pointer instead of a
    # bare Django 404.
    from core.views import api_index

    urlpatterns += [path("", api_index, name="api-index")]
