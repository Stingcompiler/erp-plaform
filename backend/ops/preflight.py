"""
Pre-install / pre-upgrade checks for a standalone installation.

These run before an operator changes anything. The point is to turn the failure
modes that would otherwise surface mid-migration — wrong database, unbuilt
frontend, unapplied migrations, a default secret key — into a readable list
before a maintenance window opens.

Every check returns a Finding; none of them mutate state or raise for an
ordinary misconfiguration. The command decides the exit code.
"""

from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

OK = "ok"
WARN = "warn"
FAIL = "fail"

INSECURE_SECRET = "dev-insecure-secret-key-change-me"


@dataclass(frozen=True)
class Finding:
    code: str
    level: str
    detail: str

    @property
    def is_blocking(self):
        return self.level == FAIL

    def as_dict(self):
        return {"code": self.code, "level": self.level, "detail": self.detail}


def check_deployment_profile():
    from config.deployment import get_deployment_config

    try:
        config = get_deployment_config()
    except Exception as exc:  # noqa: BLE001 - surfaced as a finding, not a crash
        return Finding(
            "deployment_profile", FAIL, f"Invalid deployment settings: {exc}"
        )
    if config.is_standalone and settings.DEBUG:
        return Finding(
            "deployment_profile",
            FAIL,
            "A standalone installation must not run with DEBUG enabled.",
        )
    if config.entitlement_policy == "disabled" and config.is_standalone:
        return Finding(
            "deployment_profile",
            WARN,
            "SUBSCRIPTION_POLICY is disabled in a standalone install; the licence "
            "is not being enforced.",
        )
    return Finding(
        "deployment_profile",
        OK,
        f"mode={config.mode} policy={config.entitlement_policy}",
    )


def check_secret_key():
    secret = settings.SECRET_KEY or ""
    if not secret or secret == INSECURE_SECRET or len(secret) < 32:
        return Finding(
            "secret_key",
            FAIL,
            "DJANGO_SECRET_KEY is missing, default, or shorter than 32 characters.",
        )
    return Finding("secret_key", OK, "A custom secret key is configured.")


def check_https_consistency():
    hosts = [host for host in settings.ALLOWED_HOSTS if host]
    if settings.FORCE_HTTPS and not hosts:
        return Finding(
            "https_consistency",
            FAIL,
            "FORCE_HTTPS is on but DJANGO_ALLOWED_HOSTS is empty; TLS redirects "
            "would be unverifiable.",
        )
    if any(host in {"localhost", "127.0.0.1"} for host in hosts) and not settings.DEBUG:
        return Finding(
            "https_consistency",
            WARN,
            "ALLOWED_HOSTS still contains a development host in a non-debug run.",
        )
    return Finding(
        "https_consistency",
        OK,
        f"FORCE_HTTPS={settings.FORCE_HTTPS} hosts={','.join(hosts) or 'none'}",
    )


def check_database():
    from django.db import connection

    try:
        connection.ensure_connection()
    except Exception as exc:  # noqa: BLE001
        return Finding("database", FAIL, f"Cannot reach the database: {exc}")
    vendor = connection.vendor
    if vendor == "sqlite":
        return Finding(
            "database",
            WARN,
            "Connected to SQLite. Production and standalone installs require PostgreSQL.",
        )
    return Finding("database", OK, f"Connected to {vendor}.")


def pending_migrations():
    """Names of migrations that the loader would apply, in plan order."""
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes()
    plan = executor.migration_plan(targets)
    return [
        f"{migration.app_label}.{migration.name}"
        for migration, backwards in plan
        if not backwards
    ]


def check_pending_migrations():
    try:
        plan = pending_migrations()
    except Exception as exc:  # noqa: BLE001
        return Finding("migrations", FAIL, f"Could not build the migration plan: {exc}")
    if plan:
        preview = ", ".join(plan[:5])
        more = "" if len(plan) <= 5 else f" (+{len(plan) - 5} more)"
        return Finding(
            "migrations",
            WARN,
            f"{len(plan)} migration(s) pending: {preview}{more}",
        )
    return Finding("migrations", OK, "The database schema is up to date.")


def check_media_writable():
    root = Path(settings.MEDIA_ROOT)
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".preflight-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return Finding("media", FAIL, f"Media directory is not writable: {exc}")
    return Finding("media", OK, f"Media directory is writable ({root}).")


def check_static_files():
    root = Path(settings.STATIC_ROOT)
    if not root.is_dir() or not any(root.iterdir()):
        return Finding(
            "static_files",
            WARN,
            "STATIC_ROOT is empty; run collectstatic before serving.",
        )
    return Finding("static_files", OK, f"Static files are collected ({root}).")


def check_frontend_build():
    from ops.release import frontend_inventory

    inventory = frontend_inventory()
    if not inventory["present"]:
        return Finding(
            "frontend_build",
            FAIL,
            "The built frontend export is missing; run `npm run build` in frontend/.",
        )
    if not inventory["index_sha256"]:
        return Finding(
            "frontend_build",
            FAIL,
            "The frontend export has no index.html.",
        )
    return Finding(
        "frontend_build",
        OK,
        f"{inventory['files']} file(s), {inventory['bytes']} bytes.",
    )


def check_licence_keys():
    """Without a trusted public key every licence import is refused as untrusted."""
    from config.deployment import get_deployment_config

    if not get_deployment_config().is_standalone:
        return Finding("licence_keys", OK, "Not applicable outside standalone deployments.")
    keys = settings.VEZANO_LICENSE_PUBLIC_KEYS or {}
    bad = [key_id for key_id, pem in keys.items() if "BEGIN PUBLIC KEY" not in str(pem)]
    if bad:
        return Finding(
            "licence_keys",
            FAIL,
            f"Licence key(s) {', '.join(bad)} are not PEM public keys; check the "
            "file(s) in VEZANO_LICENSE_PUBLIC_KEYS_DIR or the JSON value.",
        )
    if not keys:
        return Finding(
            "licence_keys",
            FAIL,
            "No licence public key is configured (VEZANO_LICENSE_PUBLIC_KEYS_DIR "
            "or VEZANO_LICENSE_PUBLIC_KEYS); no licence can be imported.",
        )
    return Finding("licence_keys", OK, f"Trusted key id(s): {', '.join(sorted(keys))}.")


def check_licence():
    from config.deployment import get_deployment_config

    if not get_deployment_config().is_standalone:
        return Finding("licence", OK, "Not applicable outside standalone deployments.")
    from licensing.services import active_license

    activation = active_license()
    if not activation:
        return Finding(
            "licence",
            FAIL,
            "No standalone licence is installed; the company opens read-only.",
        )
    if activation.kind == activation.TERM and activation.usable_until:
        from django.utils import timezone

        if timezone.now() > activation.usable_until:
            return Finding(
                "licence",
                FAIL,
                f"The fixed-term licence ended on {activation.usable_until:%Y-%m-%d}.",
            )
    from licensing.services import application_version, version_exceeds_licence

    if version_exceeds_licence(activation):
        return Finding(
            "licence",
            FAIL,
            f"Release {application_version()} exceeds the licence ceiling "
            f"{activation.max_application_version}; writes will be blocked. "
            "Renew maintenance before upgrading, or roll back.",
        )
    if activation.maintenance_until:
        from django.utils import timezone

        if timezone.now().date() > activation.maintenance_until:
            return Finding(
                "licence",
                WARN,
                f"Maintenance ended on {activation.maintenance_until:%Y-%m-%d}; "
                "this release keeps running but newer releases are not covered.",
            )
    return Finding(
        "licence",
        OK,
        f"{activation.kind} licence for {activation.organisation_name}.",
    )


def run_preflight():
    """Every check, in a stable order. Import-time safe: never touches the network."""
    return [
        check_deployment_profile(),
        check_secret_key(),
        check_https_consistency(),
        check_database(),
        check_pending_migrations(),
        check_media_writable(),
        check_static_files(),
        check_frontend_build(),
        check_licence_keys(),
        check_licence(),
    ]
