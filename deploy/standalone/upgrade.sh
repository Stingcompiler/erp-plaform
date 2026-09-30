#!/usr/bin/env bash
# Apply a prepared Vezano release in SaaS or standalone mode on a systemd host.
# Verify the archive's trusted checksum/signature before invoking this script.
# Keep every external writer (cron, beat, other hosts) out of the maintenance
# window. Installed Vezano timers and an already active worker are handled here.
#
# Usage: upgrade.sh --release DIR [options]
#   --link PATH             current symlink (default /opt/vezano/current)
#   --env-file FILE         protected settings (default /etc/vezano/vezano.env)
#   --backup-dir DIR        backup root (default /var/backups/vezano)
#   --web-service UNIT      required active web unit (default vezano-web.service)
#   --worker-service UNIT   auto (default), none, or an installed service name
#   --health-url URL        local health endpoint (default http://127.0.0.1:8000/api/health/)
#   --health-host HOST      HTTP Host header, e.g. pro.vezano.app
#   --require-no-migrations refuse any pending migration; enable code-only recovery
#   --prepare-only          prepare/check candidate without entering maintenance
#   --python3 PATH          venv creation interpreter (default python3)
#   --skip-backup           proceed without a new backup (not recommended)
#   --yes                   accept the maintenance window without prompting
#
# Failures before database writes restore the old link and active services.
# After any migration/bootstrap attempt, failures leave writers stopped for
# operator recovery: a symlink change cannot undo database changes.

set -euo pipefail
umask 077

RELEASE=""
LINK="/opt/vezano/current"
ENV_FILE="/etc/vezano/vezano.env"
BACKUP_DIR="/var/backups/vezano"
WEB_SERVICE="vezano-web.service"
WORKER_SERVICE="auto"
HEALTH_URL="http://127.0.0.1:8000/api/health/"
HEALTH_HOST=""
REQUIRE_NO_MIGRATIONS=0
PREPARE_ONLY=0
SKIP_BACKUP=0
ASSUME_YES=0
PYTHON3="python3"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { printf '[upgrade] %s\n' "$*"; }
fail() { printf '[upgrade] ERROR: %s\n' "$*" >&2; exit 1; }
value_required() { [ "$#" -ge 2 ] && [ -n "$2" ] || fail "$1 requires a value"; }

while [ "$#" -gt 0 ]; do
    case "$1" in
        --release|--link|--env-file|--backup-dir|--web-service|--worker-service|--health-url|--health-host|--python3)
            value_required "$@"
            case "$1" in
                --release) RELEASE="$2" ;;
                --link) LINK="$2" ;;
                --env-file) ENV_FILE="$2" ;;
                --backup-dir) BACKUP_DIR="$2" ;;
                --web-service) WEB_SERVICE="$2" ;;
                --worker-service) WORKER_SERVICE="$2" ;;
                --health-url) HEALTH_URL="$2" ;;
                --health-host) HEALTH_HOST="$2" ;;
                --python3) PYTHON3="$2" ;;
            esac
            shift 2 ;;
        --require-no-migrations) REQUIRE_NO_MIGRATIONS=1; shift ;;
        --prepare-only) PREPARE_ONLY=1; shift ;;
        --skip-backup) SKIP_BACKUP=1; shift ;;
        --yes) ASSUME_YES=1; shift ;;
        -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
        *) fail "unknown option: $1" ;;
    esac
done

[ -n "$RELEASE" ] || fail "--release DIR is required"
[ -L "$LINK" ] && [ -d "$LINK" ] || fail "current must be a valid symlink"
[ -d "$RELEASE" ] || fail "release directory not found"
RELEASE="$(cd "$RELEASE" && pwd -P)"
LINK="$(cd "$(dirname "$LINK")" && pwd -P)/$(basename "$LINK")"
OLD_RELEASE="$(cd "$LINK" && pwd -P)"
[ "$RELEASE" != "$OLD_RELEASE" ] || fail "candidate is already current"
[ -f "$RELEASE/backend/manage.py" ] || fail "candidate lacks backend/manage.py"
[ -f "$RELEASE/release-manifest.json" ] || fail "candidate lacks release-manifest.json"
[ -f "$ENV_FILE" ] || fail "protected environment file not found"
ENV_FILE="$(cd "$(dirname "$ENV_FILE")" && pwd -P)/$(basename "$ENV_FILE")"
for command in systemctl flock runuser curl; do
    command -v "$command" >/dev/null 2>&1 || fail "$command is required on the deployment host"
done
# The lock is outside both releases and survives an atomic symlink replacement.
exec 9>"${LINK}.upgrade.lock"
flock -n 9 || fail "another upgrade holds the current-link lock"

unit_property() { systemctl show "$1" --property="$2" --value; }
unit_state() { unit_property "$1" ActiveState; }
require_service_layout() {
    local unit="$1" executable="$2" start environment
    [ "$(unit_property "$unit" WorkingDirectory)" = "$LINK/backend" ] \
        || fail "$unit WorkingDirectory must follow the current link"
    start="$(unit_property "$unit" ExecStart)"
    [[ "$start" == *"path=$LINK/venv/bin/$executable ;"* ]] \
        || fail "$unit ExecStart must use current/venv/bin/$executable"
    environment="$(unit_property "$unit" Environment)"
    [ "$environment" = "VEZANO_ENV_FILE=$ENV_FILE" ] \
        || fail "$unit must use only the selected VEZANO_ENV_FILE; review other overrides"
    [ -z "$(unit_property "$unit" EnvironmentFiles)" ] \
        || fail "$unit has additional environment files; align settings before upgrading"
}
[ "$(unit_property "$WEB_SERVICE" LoadState)" = loaded ] || fail "web unit is missing or unusable"
[ "$(unit_state "$WEB_SERVICE")" = active ] || fail "web unit must be active before upgrading"
require_service_layout "$WEB_SERVICE" gunicorn
APP_USER="$(unit_property "$WEB_SERVICE" User)"
APP_GROUP="$(unit_property "$WEB_SERVICE" Group)"
[ -n "$APP_USER" ] && [ "$APP_USER" != root ] || fail "web unit must specify a non-root User"
[ -n "$APP_GROUP" ] || APP_GROUP="$APP_USER"

# Do not inherit operator environment overrides that could select another DB.
# Settings are read by Django, never sourced or printed by the shell.
as_app() {
    runuser -u "$APP_USER" -g "$APP_GROUP" -- env -i PATH="$PATH" \
        VEZANO_ENV_FILE="$ENV_FILE" VEZANO_BACKUP_DIR="$BACKUP_DIR" "$@"
}
NEW_PYTHON="$RELEASE/venv/bin/python"
manage() { (cd "$RELEASE/backend" && as_app "$NEW_PYTHON" manage.py "$@"); }

ACTIVE_WORKER=""
worker_unit="$WORKER_SERVICE"
if [ "$worker_unit" = auto ] || [ "$worker_unit" = none ]; then
    worker_unit=vezano-worker.service
fi
case "$(unit_property "$worker_unit" LoadState)" in
    not-found)
        case "$WORKER_SERVICE" in auto|none) ;; *) fail "requested worker unit is missing" ;; esac ;;
    loaded)
        case "$(unit_state "$worker_unit")" in
            active)
                [ "$WORKER_SERVICE" != none ] || fail "worker is active; do not exclude a writer"
                require_service_layout "$worker_unit" celery
                [ "$(unit_property "$worker_unit" User)" = "$APP_USER" ] \
                    || fail "worker and web must use the same application user"
                ACTIVE_WORKER="$worker_unit" ;;
            inactive) log "installed worker is inactive; preserving its state" ;;
            *) fail "worker is failed or transitioning; resolve before upgrading" ;;
        esac ;;
    *) fail "worker unit is masked or cannot be loaded" ;;
esac

ACTIVE_TIMERS=()
for timer in vezano-daily-scans.timer vezano-backup.timer; do
    case "$(unit_property "$timer" LoadState)" in
        not-found) ;;
        loaded)
            case "$(unit_state "$timer")" in
                active) ACTIVE_TIMERS+=("$timer") ;;
                inactive) ;;
                *) fail "$timer is failed or transitioning" ;;
            esac ;;
        *) fail "$timer is masked or cannot be loaded" ;;
    esac
done

MAINTENANCE=0
DB_MAY_HAVE_CHANGED=0
TEMP_LINK=""
atomic_link() {
    # Same-directory rename is atomic on this Linux deployment profile.
    TEMP_LINK="${LINK}.next.$$"
    ln -s "$1" "$TEMP_LINK" || return 1
    mv -Tf "$TEMP_LINK" "$LINK" || return 1
    TEMP_LINK=""
}
resume_timers() {
    local timer result=0
    [ "${#ACTIVE_TIMERS[@]}" -gt 0 ] || return 0
    for timer in "${ACTIVE_TIMERS[@]}"; do systemctl start "$timer" || result=1; done
    return "$result"
}
stop_writers() {
    local timer result=0
    if [ "${#ACTIVE_TIMERS[@]}" -gt 0 ]; then
        for timer in "${ACTIVE_TIMERS[@]}"; do systemctl stop "$timer" || result=1; done
    fi
    if [ -n "$ACTIVE_WORKER" ]; then systemctl stop "$ACTIVE_WORKER" || result=1; fi
    systemctl stop "$WEB_SERVICE" || result=1
    return "$result"
}
recover_on_exit() {
    local result="$?" recovery_failed=0
    trap - EXIT INT TERM
    set +e
    [ -z "$TEMP_LINK" ] || rm -f "$TEMP_LINK"
    if [ "$result" -ne 0 ] && [ "$MAINTENANCE" -eq 1 ]; then
        if [ "$DB_MAY_HAVE_CHANGED" -eq 0 ]; then
            log "failure before database writes: restoring $OLD_RELEASE"
            if ! atomic_link "$OLD_RELEASE"; then
                stop_writers
                log "ERROR: could not restore the previous link; operator recovery required"
                exit "$result"
            fi
            systemctl restart "$WEB_SERVICE" || recovery_failed=1
            if [ -n "$ACTIVE_WORKER" ]; then systemctl start "$ACTIVE_WORKER" || recovery_failed=1; fi
            resume_timers || recovery_failed=1
            if [ "$recovery_failed" -eq 0 ] && systemctl is-active --quiet "$WEB_SERVICE" && health_check; then
                log "previous release is serving healthy responses"
            else
                log "ERROR: previous release recovery needs operator attention"
            fi
        else
            if stop_writers; then
                log "ERROR: database writes were attempted; managed writers remain stopped"
            else
                log "ERROR: database writes were attempted and some writers could not be stopped"
            fi
            log "use the pre-upgrade backup and the documented restore procedure"
            log "do not reverse the link or database automatically"
        fi
    fi
    exit "$result"
}
trap recover_on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [ ! -x "$NEW_PYTHON" ]; then
    log "creating candidate environment as the web service user"
    as_app "$PYTHON3" -m venv "$RELEASE/venv"
    as_app "$RELEASE/venv/bin/pip" install --quiet -r "$RELEASE/backend/requirements.lock"
fi
log "verifying the prepared release"
manage verify_release --manifest "$RELEASE/release-manifest.json"
MODE="$(manage shell --verbosity 0 -c 'from config.deployment import get_deployment_config, assert_mode_matches_installation; assert_mode_matches_installation(); print(get_deployment_config().mode)')"
case "$MODE" in saas|standalone) ;; *) fail "could not determine the effective deployment mode" ;; esac
log "deployment mode: $MODE"
log "running deployment checks before maintenance"
manage check --deploy
manage migrate --plan
PENDING_MIGRATIONS=0
if ! manage migrate --check; then PENDING_MIGRATIONS=1; fi
if [ "$REQUIRE_NO_MIGRATIONS" -eq 1 ] && [ "$PENDING_MIGRATIONS" -eq 1 ]; then
    fail "pending migrations; refusing code-only promotion"
fi
# STATIC_ROOT is release-local in this project's settings. Running as the
# application user catches permissions errors before stopping production.
manage collectstatic --noinput
manage preflight

health_check() {
    local response
    local headers=(-H 'X-Forwarded-Proto: https')
    [ -z "$HEALTH_HOST" ] || headers+=(-H "Host: $HEALTH_HOST")
    response="$(curl --silent --fail --max-time 5 "${headers[@]}" "$HEALTH_URL" 2>/dev/null)" || return 1
    # Only report success/failure; never print the health payload or exceptions.
    # The candidate venv is app-owned. Never execute its interpreter as root.
    printf '%s' "$response" | /usr/bin/python3 -I -c \
        'import json,sys
try:
    data=json.load(sys.stdin)
    ok=data.get("status")=="ok" and data.get("database")=="ok" and data.get("deployment_mode")==sys.argv[1]
except Exception:
    ok=False
sys.exit(0 if ok else 1)' "$MODE"
}
health_check || fail "current web endpoint is not healthy with the selected Host and URL"
if [ "$PREPARE_ONLY" -eq 1 ]; then
    log "candidate preparation complete; promotion requires a subsequent invocation"
    exit 0
fi
if [ "$ASSUME_YES" -ne 1 ]; then
    printf '[upgrade] Begin backup, maintenance and promotion? [y/N] '
    read -r reply
    case "$reply" in y|Y|yes|YES) ;; *) fail "aborted before maintenance" ;; esac
fi

MAINTENANCE=1
log "pausing timers and waiting for in-flight scheduled jobs"
if [ "${#ACTIVE_TIMERS[@]}" -gt 0 ]; then
    for timer in "${ACTIVE_TIMERS[@]}"; do systemctl stop "$timer"; done
fi
for job in vezano-daily-scans.service vezano-backup.service; do
    for ((attempt=0; attempt<60; attempt++)); do
        state="$(unit_state "$job")"
        case "$state" in active|activating|deactivating) sleep 1 ;; *) break ;; esac
    done
    case "$state" in inactive|"") ;; *) fail "$job has not completed successfully" ;; esac
done
log "stopping active application writers"
stop_writers

# The snapshot/media archive are consistent because writers are now quiescent.
if [ "$SKIP_BACKUP" -eq 1 ]; then
    log "WARNING: no fresh pre-upgrade backup requested"
else
    log "taking a protected pre-upgrade backup"
    VEZANO_HOME="$OLD_RELEASE" VEZANO_ENV_FILE="$ENV_FILE" VEZANO_BACKUP_DIR="$BACKUP_DIR" \
        VEZANO_PYTHON="${VEZANO_PYTHON:-$OLD_RELEASE/venv/bin/python}" \
        VEZANO_BACKUP_APP_USER="$APP_USER" \
        bash "$SCRIPT_DIR/backup.sh" --label pre-upgrade
fi
# Recheck under the writer pause rather than relying on an earlier plan.
if ! manage migrate --check; then
    [ "$REQUIRE_NO_MIGRATIONS" -eq 0 ] || fail "migration state changed; promotion refused"
    DB_MAY_HAVE_CHANGED=1
    log "applying migrations; any failure now requires database-aware recovery"
    manage migrate --noinput
fi
manage check --deploy
if [ "$MODE" = standalone ]; then
    NEW_VERSION="$(tr -d '[:space:]' < "$RELEASE/VERSION")"
    [ -n "$NEW_VERSION" ] || fail "standalone candidate needs VERSION"
    DB_MAY_HAVE_CHANGED=1
    manage bootstrap_standalone --app-version "$NEW_VERSION"
else
    log "SaaS: standalone bootstrap is not applicable"
fi

log "atomically promoting $RELEASE"
atomic_link "$RELEASE"
systemctl restart "$WEB_SERVICE"
healthy=0
for ((attempt=0; attempt<30; attempt++)); do
    if systemctl is-active --quiet "$WEB_SERVICE" && health_check; then healthy=1; break; fi
    sleep 1
done
[ "$healthy" -eq 1 ] || fail "web failed its post-promotion health check"
if [ -n "$ACTIVE_WORKER" ]; then
    systemctl start "$ACTIVE_WORKER"
    systemctl is-active --quiet "$ACTIVE_WORKER" || fail "worker failed to start"
fi
resume_timers
manage preflight
MAINTENANCE=0
log "upgrade complete; previous release retained at $OLD_RELEASE"
log "database recovery after incompatible migrations requires the matching backup"
