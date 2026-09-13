"""
Django settings for the ERP platform backend.

M0 scope: scaffolding only. Auth, company-scoping middleware, and the full
app list land in M1+ per erp_ai_agent_build_plan.md. Do not add business
logic here — this file should only ever grow INSTALLED_APPS / middleware /
infra config as later milestones land their own Django apps.
"""

from datetime import timedelta
from pathlib import Path
import sys

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
# .env is optional locally; on Render, env vars are injected directly.
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-insecure-secret-key-change-me")
DEBUG = env("DEBUG")

# Whether this process is actually reachable over HTTPS. Defaults to `not
# DEBUG` (real prod always wants this), but is independently overridable so
# DEBUG=False can be used locally to test the monolithic static-serving path
# (core/frontend.py) over plain HTTP without a TLS terminator in front.
FORCE_HTTPS = env.bool("FORCE_HTTPS", default=not DEBUG)

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# Render sets RENDER_EXTERNAL_HOSTNAME on every deployed service.
RENDER_EXTERNAL_HOSTNAME = env("RENDER_EXTERNAL_HOSTNAME", default=None)
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",  # enables logout invalidation
    "corsheaders",
    # local
    "core",       # shared: health check, ActivityLog, company-scoping base
    "accounts",   # custom User, Role, Permission, cookie-JWT auth (M1)
    "org",        # Company, Branch, Department, TaxProfile (M1)
    "inventory",  # Product, stock ledger, batches, adjustments, transfers (M2)
    "sales",      # Customer, quotation/order/invoice, POS, payments (M3)
    "purchasing",  # Supplier, PO, receiving, bills, supplier payments (M4)
    "returns",    # Sales/purchase returns, disposition, credit/debit notes (M5)
    "crm",        # CustomerGroup, Lead, FollowUp, Note (M6)
    "finance",    # Expense tracking + company funds (Finance Dept)
    "hr",         # Employee, Position, Attendance, Leave, Performance, Docs (M6)
    "sync",       # Offline batch push + delta pull (M7)
    "website",    # Public landing page generator (M8)
    "reports",    # Read-only reporting endpoints (M9)
    "ops",        # Backup/restore + user preferences (M10)
    "tax",        # Pluggable tax / e-invoicing handlers (M11)
    "subscriptions",  # SaaS plans, commercial subscriptions and manual billing
    "licensing",      # Standalone installation identity and signed licences
]

# M1: email-login custom user with company/branch/role scoping. Introduced
# now (before any real migrate/deploy) because swapping AUTH_USER_MODEL after
# initial migration is destructive — M0 shipped no models, so this is additive.
AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",  # M10: i18n (en / ar)
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Note (M1): Rule #1 company-scoping is enforced in the shared DRF base
    # viewset (core/scoping.py), NOT in middleware — DRF resolves the
    # authenticated user inside the view, so request.user isn't available at
    # Django-middleware time. Rule #1 explicitly permits a base mixin as the
    # alternative to middleware. ActivityLog is written from views via
    # core.activity.log_activity for the same reason.
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Database ---
# Dev default: SQLite. Prod: DATABASE_URL provided by Render's managed
# PostgreSQL (erp-db), wired automatically via render.yaml.
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},  # M10 security hardening
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
# M10: supported UI languages. Arabic drives RTL on the frontend.
LANGUAGES = [("en", "English"), ("ar", "Arabic")]
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Commercial defaults are configuration, not hard-coded workflow rules. The
# hosted registration service uses this only when it creates a new trial.
VEZANO_TRIAL_DAYS = env.int("VEZANO_TRIAL_DAYS", default=14)

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    # Default backend for user-uploaded media (FileField). Filesystem-backed;
    # swap for an S3/R2 backend in production for durability (Render's disk is
    # ephemeral). Explicitly declared because a custom STORAGES dict otherwise
    # drops Django's built-in "default" entry.
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# User-uploaded files (e.g. sick-leave medical reports). Stored on disk by
# default; on Render's ephemeral filesystem these don't persist across deploys,
# so wire a durable S3/R2 backend for production (mirrors the backup storage
# approach). Sensitive uploads are never served via MEDIA_URL directly — they
# go through company-scoped viewset actions that enforce tenancy.
#
# MEDIA_ROOT is env-overridable because a standalone customer may keep media on
# a separate mounted volume from the application code — and because the
# backup/restore scripts address the media tree by path, not by guesswork.
MEDIA_URL = env("MEDIA_URL", default="media/")
MEDIA_ROOT = env("MEDIA_ROOT", default=str(BASE_DIR / "media"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- DRF ---
# JWT-via-HttpOnly-cookie auth (custom class reads the cookie, not the
# Authorization header). Company-scoping is enforced by the shared base
# viewset in core/scoping.py (PROJECT_RULES Rule #1), which every
# company-owned viewset inherits.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "accounts.authentication.CookieJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
        # M6: role-based module access, enforced globally. Endpoints that set
        # their own permission_classes (auth, POS checkout, receiving) opt in
        # explicitly where needed.
        "core.rbac.RoleModuleAccess",
        "core.permissions.EntitlementAccess",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    # Turns a PROTECT-blocked delete into a 409 that names what is holding the
    # row, instead of DRF's default 500. See core/exceptions.py.
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
    # M10: throttle login attempts to slow credential-stuffing (applied on the
    # login view via a scoped throttle).
    # Test cases share one process/cache and one loopback IP; a generous test
    # rate prevents unrelated login tests from throttling each other. The
    # production limit remains unchanged, and per-view throttle tests that set
    # their own rate still exercise the real cache.
    "DEFAULT_THROTTLE_RATES": {
        "login": "10000/min" if "test" in sys.argv else "10/min"
    },
    # Reports export CSV via `?format=csv`, handled manually in the report views
    # (ReportView.wants_csv). Disable DRF's built-in `format` query-param
    # override so it doesn't intercept `format=csv` and 404 before the view runs
    # (no CSV renderer is registered — the views build the CSV themselves).
    "URL_FORMAT_OVERRIDE": None,
}

# --- SimpleJWT + cookie transport ---
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,  # M10: rotate + blacklist old refresh tokens
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    # Cookie transport config consumed by accounts/authentication.py + cookies.py
    "AUTH_COOKIE": "access_token",
    "AUTH_COOKIE_REFRESH": "refresh_token",
    "AUTH_COOKIE_DOMAIN": env("AUTH_COOKIE_DOMAIN", default=None),
    "AUTH_COOKIE_PATH": "/",
    # Secure cookies whenever actually served over HTTPS; SameSite=Lax works
    # for the same-site frontend/api pairing on *.onrender.com.
    "AUTH_COOKIE_SECURE": FORCE_HTTPS,
    "AUTH_COOKIE_SAMESITE": env("AUTH_COOKIE_SAMESITE", default="Lax"),
}

# --- CORS ---
# Only the Next.js frontend origin(s) may call the API with credentials
# (needed for HttpOnly cookie auth landing in M1).
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS", default=["http://localhost:3000"]
)
CORS_ALLOW_CREDENTIALS = True

# --- Celery (erp-worker) ---
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# --- Delivery profile and commercial entitlement rollout ---
# Existing installations remain unaffected until the operator deliberately
# progresses disabled -> observe -> enforce after reviewing observe logs.
VEZANO_DEPLOYMENT_MODE = env("VEZANO_DEPLOYMENT_MODE", default="saas")
SUBSCRIPTION_POLICY = env("SUBSCRIPTION_POLICY", default="disabled")
VEZANO_LICENSE_PUBLIC_KEYS = env.json("VEZANO_LICENSE_PUBLIC_KEYS", default={})

# --- M10 security hardening ---
# Applied always:
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
# Render terminates TLS at its edge and forwards the original scheme here.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# --- Backup object storage (optional; S3/R2-compatible) ---
# When BACKUP_S3_BUCKET is set, backup payloads are pushed off-box so they
# survive Render's ephemeral filesystem. Leave unset for metadata-only backups.
BACKUP_S3_BUCKET = env("BACKUP_S3_BUCKET", default="")
BACKUP_S3_ENDPOINT_URL = env("BACKUP_S3_ENDPOINT_URL", default="")
BACKUP_S3_REGION = env("BACKUP_S3_REGION", default="")
BACKUP_S3_ACCESS_KEY_ID = env("BACKUP_S3_ACCESS_KEY_ID", default="")
BACKUP_S3_SECRET_ACCESS_KEY = env("BACKUP_S3_SECRET_ACCESS_KEY", default="")

# --- Logging (M12) ---
# Log to stdout so Render captures it; level configurable via LOG_LEVEL.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

# HTTPS-only hardening in production (kept off in local dev so http works;
# see FORCE_HTTPS above for the DEBUG=False-but-plain-HTTP local test case).
if FORCE_HTTPS:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
