"""
Django settings for the ERP platform backend.

M0 scope: scaffolding only. Auth, company-scoping middleware, and the full
app list land in M1+ per erp_ai_agent_build_plan.md. Do not add business
logic here — this file should only ever grow INSTALLED_APPS / middleware /
infra config as later milestones land their own Django apps.
"""

import decimal
from datetime import timedelta
import os
from pathlib import Path
import sys

import environ

# Money rounds half-up everywhere (0.125 -> 0.13). Python's default is
# banker's rounding (half-even), which tax authorities in the target markets
# do not use; a per-line VAT that rounds 0.125 down fails invoice matching.
# Set on DefaultContext so every new thread's context inherits it, and on the
# current context for the thread importing settings.
decimal.DefaultContext.rounding = decimal.ROUND_HALF_UP
decimal.getcontext().rounding = decimal.ROUND_HALF_UP

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
# .env is optional locally; on Render, env vars are injected directly. A
# standalone installation keeps its protected file outside the release tree
# and names it in VEZANO_ENV_FILE, so every process (service units, the
# backup/upgrade scripts, an operator's shell) reads it with this one parser
# instead of each shell quoting it differently.
environ.Env.read_env(os.environ.get("VEZANO_ENV_FILE") or BASE_DIR / ".env")

_INSECURE_DEFAULT_SECRET = "dev-insecure-secret-key-change-me"
SECRET_KEY = env("DJANGO_SECRET_KEY", default=_INSECURE_DEFAULT_SECRET)
DEBUG = env("DEBUG")
# The secret signs every JWT, session and sync cursor. A production process
# that silently fell back to the public default would accept forged tokens,
# so refuse to start instead. Dev (DEBUG=True) keeps the convenience default.
if not DEBUG and SECRET_KEY == _INSECURE_DEFAULT_SECRET:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set when DEBUG is False."
    )

# Whether this process is actually reachable over HTTPS. Defaults to `not
# DEBUG` (real prod always wants this), but is independently overridable so
# DEBUG=False can be used locally to test the monolithic static-serving path
# (core/frontend.py) over plain HTTP without a TLS terminator in front.
FORCE_HTTPS = env.bool("FORCE_HTTPS", default=not DEBUG)

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# The hosted SaaS answers on the apex domain (the canonical one: what the
# marketing pages, sitemap and Open Graph tags advertise), the www alias, and
# the older enterprise.* subdomain that existing customers, their installed
# PWAs and their cookies still live on. All three stay in the effective
# allow-list even while an existing Render service still carries an older
# DJANGO_ALLOWED_HOSTS value; otherwise Django rejects the custom domain with
# a 400 before it can serve either the app or the admin panel.
VEZANO_CANONICAL_HOST = "vezano.app"
VEZANO_PUBLIC_HOSTS = [VEZANO_CANONICAL_HOST, "www.vezano.app", "enterprise.vezano.app"]
# The hosted SaaS hostnames belong to the hosted SaaS only. A customer's own
# server must not answer for vezano.app, nor trust it as a CSRF origin.
_IS_SAAS = env("VEZANO_DEPLOYMENT_MODE", default="saas").strip().lower() != "standalone"
if _IS_SAAS:
    for _host in VEZANO_PUBLIC_HOSTS:
        if _host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(_host)

# The admin panel and any session-authenticated POST check the Origin header
# against this list; the JWT cookie API is same-origin on every host anyway.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
if _IS_SAAS:
    for _host in VEZANO_PUBLIC_HOSTS:
        if f"https://{_host}" not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(f"https://{_host}")

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
    # Answers 404 for platform/registration routes on standalone installs.
    "core.deployment_gate.StandaloneSurfaceGate",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # M10: i18n (en / ar). Cookie or site default only — never Accept-Language.
    "core.locale_middleware.CookieOnlyLocaleMiddleware",
    # Clears the active time zone per request; the company's zone is
    # activated by accounts.authentication once the user is known.
    "core.timezone.CompanyTimezoneMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # /admin/ is superuser-only (and optionally IP-restricted); see below.
    "core.admin_gate.AdminAccessGate",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Last in the list = first to see an unhandled view exception. Records
    # it for the platform console (core.models.ErrorEvent) and steps aside.
    "core.error_monitor.ErrorMonitorMiddleware",
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
# An empty DATABASE_URL (a CI matrix leg, a blank dashboard field) means
# "not configured", not "connect to nothing"; treat it like an unset variable.
_SQLITE_URL = f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
DATABASES = {
    "default": env.db_url_config(env("DATABASE_URL", default="") or _SQLITE_URL)
}
# Reuse a connection across requests instead of opening one per request —
# Render's small PostgreSQL plans have a low connection ceiling and a
# per-request handshake is the first thing to fall over under load. The
# health check makes a stale connection reconnect instead of erroring once.
if not DATABASES["default"]["ENGINE"].endswith("sqlite3"):
    DATABASES["default"]["CONN_MAX_AGE"] = int(env("CONN_MAX_AGE", default="60"))
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

# --- Cache ---
# Shared across gunicorn workers without Redis. Without a shared cache each
# worker kept its own LocMemCache, so the login throttle was "10/min" PER
# WORKER and an attention "seen" mark on one worker was invisible to the
# others for the whole cache window. The table is created by
# `manage.py createcachetable` (in the pre-deploy command and the standalone
# runbook). Tests keep the in-memory cache: faster, and isolated per process.
CACHES = {
    "default": {
        "BACKEND": (
            "django.core.cache.backends.locmem.LocMemCache"
            if "test" in sys.argv or "pytest" in sys.modules
            else "django.core.cache.backends.db.DatabaseCache"
        ),
        "LOCATION": "vezano_cache",
        "TIMEOUT": 300,
        "OPTIONS": {"MAX_ENTRIES": 5000},
    }
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

LANGUAGE_CODE = "ar"
# M10: supported UI languages. Arabic drives RTL on the frontend.
LANGUAGES = [("ar", "العربية"), ("en", "English")]
TIME_ZONE = "UTC"
USE_I18N = True
# The frontend persists the user's UI language in this cookie (see
# I18nProvider); LocaleMiddleware reads it so validation messages come back
# in the language the person is actually reading.
LANGUAGE_COOKIE_NAME = "erp_language"
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_TZ = True

# Commercial defaults are configuration, not hard-coded workflow rules. The
# hosted registration service uses this only when it creates a new trial.
VEZANO_TRIAL_DAYS = env.int("VEZANO_TRIAL_DAYS", default=14)
# How far back an offline client may date a sale or payment it queued. Long
# enough for a multi-week outage, short enough that a forgotten device cannot
# rewrite a closed period.
VEZANO_MAX_BACKDATE_DAYS = env.int("VEZANO_MAX_BACKDATE_DAYS", default=31)

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    # Default backend for user-uploaded media (FileField). Filesystem-backed;
    # the hosted service points MEDIA_ROOT at its Render persistent disk.
    # Explicitly declared because a custom STORAGES dict otherwise drops
    # Django's built-in "default" entry.
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        # Django admin must remain renderable even when an operator-created
        # service missed collectstatic. Next.js fingerprints its own assets;
        # Django's comparatively small static set only needs compression here.
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

# Keep Django's admin and other server-rendered pages usable when an
# operator-created Render service omitted collectstatic from its build command.
# The normal Render build still runs collectstatic and produces compressed
# production assets.
WHITENOISE_USE_FINDERS = True

# User-uploaded files (e.g. sick-leave medical reports). The hosted SaaS sets
# this to /var/data/media/, the mounted Render persistent disk. Sensitive
# uploads are never served via MEDIA_URL directly — they go through
# company-scoped viewset actions that enforce tenancy.
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
    "DEFAULT_PAGINATION_CLASS": "core.pagination.CappedPageNumberPagination",
    "PAGE_SIZE": 50,
    # Exactly one trusted proxy (Render's edge, or the standalone reverse
    # proxy) sits in front and appends the peer address to X-Forwarded-For.
    # Without this DRF keys the login throttle on the FIRST forwarded entry,
    # which the client itself controls, and rotating that header defeats the
    # rate limit entirely.
    "NUM_PROXIES": 1,
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
        "login": "10000/min" if "test" in sys.argv else "10/min",
        "password_reset": "10000/min" if "test" in sys.argv else "5/hour",
        "public_order": "10000/min" if "test" in sys.argv else "20/hour",
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
    # for the same-origin frontend/API pairing on every public host.
    "AUTH_COOKIE_SECURE": FORCE_HTTPS,
    "AUTH_COOKIE_SAMESITE": env("AUTH_COOKIE_SAMESITE", default="Lax"),
}

# --- CORS ---
# Only the Next.js frontend origin(s) may call the API with credentials
# (needed for HttpOnly cookie auth landing in M1). Production serves the
# frontend from the same origin, so it needs no CORS origin at all; the dev
# default must not leak into a deployment that forgot to set the variable.
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS", default=["http://localhost:3000"] if DEBUG else []
)
CORS_ALLOW_CREDENTIALS = True

# --- Login lockout ---
# Failed sign-ins per account before the account is refused for the window.
# Complements the per-IP throttle, which alone cannot stop a distributed guess
# against one mailbox.
LOGIN_LOCKOUT_ATTEMPTS = env.int("LOGIN_LOCKOUT_ATTEMPTS", default=10)
LOGIN_LOCKOUT_SECONDS = env.int("LOGIN_LOCKOUT_SECONDS", default=15 * 60)

# --- Django admin ---
# Comma-separated client addresses allowed to reach /admin/. Empty = no IP
# restriction (the superuser requirement in core.admin_gate still applies).
ADMIN_ALLOWED_IPS = env.list("ADMIN_ALLOWED_IPS", default=[])

# --- Transactional email ---
# Email is optional infrastructure: nothing in the product *requires* it
# (activation links are always shown to the operator to deliver by hand),
# but when EMAIL_HOST is set, invitations are also emailed automatically.
# SMTP when configured; the console backend in DEBUG so developers see the
# messages; a dummy backend otherwise so an unconfigured production install
# never queues mail into the void. ops.preflight warns when email is off in
# production. core.mailer is the one place that sends.
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_ENABLED = bool(EMAIL_HOST)
if EMAIL_ENABLED:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
elif DEBUG:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"
EMAIL_PORT = int(env("EMAIL_PORT", default="587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = str(env("EMAIL_USE_TLS", default="true")).strip().lower() == "true"
EMAIL_USE_SSL = str(env("EMAIL_USE_SSL", default="false")).strip().lower() == "true"
EMAIL_TIMEOUT = int(env("EMAIL_TIMEOUT", default="10"))
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default=f"Vezano <no-reply@{VEZANO_CANONICAL_HOST}>")
# Absolute origin used in links inside emails. The hosted SaaS default is the
# canonical host; a standalone install sets its own.
PUBLIC_APP_ORIGIN = env(
    "PUBLIC_APP_ORIGIN",
    default=f"https://{VEZANO_CANONICAL_HOST}" if _IS_SAAS else "",
)

# --- Celery (erp-worker) ---
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
# Periodic work. The worker runs with embedded beat (`celery worker -B`, see
# render.yaml) so a single process both schedules and executes; enough for
# one worker, and beat has no state worth a separate service yet.
CELERY_BEAT_SCHEDULE = {
    "scan-due-receivables": {
        "task": "sales.tasks.scan_due_receivables",
        "schedule": 60 * 60 * 24,
    },
    "scan-stock-alerts": {
        "task": "inventory.tasks.scan_stock_alerts",
        "schedule": 60 * 60 * 24,
    },
    "scan-subscription-expiries": {
        "task": "subscriptions.tasks.scan_subscription_expiries",
        "schedule": 60 * 60 * 24,
    },
    "archive-activity-logs": {
        "task": "core.tasks.archive_activity_logs",
        "schedule": 60 * 60 * 24,
    },
    "rollup-page-visits": {
        "task": "website.tasks.rollup_page_visits",
        "schedule": 60 * 60 * 24,
    },
}

# Audit rows older than this move from the hot ActivityLog table to
# ActivityLogArchive on the nightly run (floor of 30 days enforced in
# core.tasks so a typo cannot sweep recent rows out of the live views).
ACTIVITY_LOG_RETENTION_DAYS = int(env("ACTIVITY_LOG_RETENTION_DAYS", default="365"))

# --- Delivery profile and commercial entitlement rollout ---
# Existing installations remain unaffected until the operator deliberately
# progresses disabled -> observe -> enforce after reviewing observe logs.
VEZANO_DEPLOYMENT_MODE = env("VEZANO_DEPLOYMENT_MODE", default="saas")
SUBSCRIPTION_POLICY = env("SUBSCRIPTION_POLICY", default="disabled")
VEZANO_LICENSE_PUBLIC_KEYS = env.json("VEZANO_LICENSE_PUBLIC_KEYS", default={})
# A directory of PEM files is the operator-friendly form: one file per key,
# named <key-id>.pem or <key-id>.public.pem. Rotating a key is a file copy,
# and nothing has to fit a multi-line PEM into one environment line.
VEZANO_LICENSE_PUBLIC_KEYS_DIR = env("VEZANO_LICENSE_PUBLIC_KEYS_DIR", default="")
if VEZANO_LICENSE_PUBLIC_KEYS_DIR:
    for _pem in sorted(Path(VEZANO_LICENSE_PUBLIC_KEYS_DIR).glob("*.pem")):
        _key_id = _pem.name[: -len(".pem")]
        if _key_id.endswith(".public"):
            _key_id = _key_id[: -len(".public")]
        VEZANO_LICENSE_PUBLIC_KEYS.setdefault(_key_id, _pem.read_text(encoding="utf-8"))

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
# Without object storage, snapshots live gzip-compressed in the database
# (ops.BackupRecord.payload_gz). Rows older than this are pruned nightly;
# each company's most recent successful snapshot is always kept.
BACKUP_RETENTION_DAYS = int(env("BACKUP_RETENTION_DAYS", default="30"))

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
    # Preload submits the domain to browser vendors' hard-coded HTTPS lists,
    # a decision for the domain owner. That is us for vezano.app; on a
    # customer's domain it would be theirs, so only the SaaS opts in.
    SECURE_HSTS_PRELOAD = _IS_SAAS
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# Web Push (VAPID). Generate once with `python -m py_vapid --gen` (or
# `manage.py vapid_keys`), keep the private key secret; the public key is
# handed to browsers. Without a private key push is simply off.
VAPID_PRIVATE_KEY = env("VAPID_PRIVATE_KEY", default="")
VAPID_PUBLIC_KEY = env("VAPID_PUBLIC_KEY", default="")
VAPID_CLAIMS_EMAIL = env("VAPID_CLAIMS_EMAIL", default="mailto:musab@vezano.app")
WEB_PUSH_ENABLED = bool(VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY)
