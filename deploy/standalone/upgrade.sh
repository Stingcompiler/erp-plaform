#!/usr/bin/env bash
#
# Vezano standalone — apply a prepared release.
#
# This is the controlled half of an upgrade: the operator has already unpacked
# the new release beside the old one and verified its checksum and signature.
# This script builds the release's own Python environment if it is missing,
# takes a backup, proves the new tree matches its manifest, applies
# migrations, and only then switches the `current` symlink. Each release owns
# its venv (<release>/venv), so moving the symlink moves code and dependencies
# together and the previous release stays runnable as it was.
#
# The order matters. A backup taken *after* migrating cannot undo the migration,
# and switching the symlink before `check --deploy` runs can serve a tree whose
# settings are wrong.
#
# Usage:
#   upgrade.sh --release /opt/vezano/releases/1.2.0 [options]
#
# Options:
#   --link PATH       the 'current' symlink to move (default /opt/vezano/current)
#   --env-file FILE   protected environment file (default /etc/vezano/vezano.env)
#   --backup-dir DIR  where to write the pre-upgrade backup (default /var/backups/vezano)
#   --skip-backup     DANGEROUS: proceed without a fresh backup
#   --yes             do not prompt before applying migrations
#   --python3 PATH    interpreter used to create the release venv (default python3)
#
# Exit codes: 0 upgraded, non-zero with the old release left in place on failure.

set -euo pipefail

RELEASE=""
LINK="/opt/vezano/current"
ENV_FILE="/etc/vezano/vezano.env"
BACKUP_DIR="/var/backups/vezano"
SKIP_BACKUP=0
ASSUME_YES=0
PYTHON3="python3"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

while [ $# -gt 0 ]; do
    case "$1" in
        --release) RELEASE="$2"; shift 2 ;;
        --link) LINK="$2"; shift 2 ;;
        --env-file) ENV_FILE="$2"; shift 2 ;;
        --backup-dir) BACKUP_DIR="$2"; shift 2 ;;
        --skip-backup) SKIP_BACKUP=1; shift ;;
        --yes) ASSUME_YES=1; shift ;;
        --python3) PYTHON3="$2"; shift 2 ;;
        -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

log() { printf '[upgrade] %s\n' "$*"; }
fail() { printf '[upgrade] ERROR: %s\n' "$*" >&2; exit 1; }

[ -n "$RELEASE" ] || fail "--release DIR is required"
[ -d "$RELEASE" ] || fail "release directory not found: $RELEASE"
[ -f "$RELEASE/backend/manage.py" ] || fail "$RELEASE does not look like a Vezano release"
[ -f "$ENV_FILE" ] || fail "environment file not found: $ENV_FILE"
[ -d "$LINK" ] || fail "current installation not found at $LINK"

# Django reads the protected file itself (see backup.sh for why it is not
# sourced here). Everything below inherits this.
export VEZANO_ENV_FILE="$ENV_FILE"

# 0. The new release's own environment, with its own pinned dependencies.
NEW_PYTHON="${RELEASE}/venv/bin/python"
if [ ! -x "$NEW_PYTHON" ]; then
    log "creating the release environment at ${RELEASE}/venv"
    "$PYTHON3" -m venv "${RELEASE}/venv" || fail "could not create the venv"
    "${RELEASE}/venv/bin/pip" install --quiet --upgrade pip \
        || fail "could not upgrade pip in the new venv"
    "${RELEASE}/venv/bin/pip" install --quiet -r "${RELEASE}/backend/requirements.txt" \
        || fail "dependency installation failed; the old release is untouched"
fi

# 1. Prove the new tree matches the manifest the vendor signed.
log "verifying the new release"
"$NEW_PYTHON" "$RELEASE/backend/manage.py" verify_release \
    --manifest "$RELEASE/release-manifest.json" \
    || fail "the new release does not match its manifest; refusing to upgrade"

# 2. Back up the current installation before anything changes.
if [ "$SKIP_BACKUP" -eq 1 ]; then
    log "WARNING: --skip-backup given; there will be no pre-upgrade restore point"
else
    log "taking a pre-upgrade backup"
    VEZANO_HOME="$LINK" VEZANO_ENV_FILE="$ENV_FILE" VEZANO_BACKUP_DIR="$BACKUP_DIR" \
    VEZANO_PYTHON="${VEZANO_PYTHON:-$LINK/venv/bin/python}" \
        bash "$SCRIPT_DIR/backup.sh" --label "pre-upgrade" \
        || fail "backup failed; refusing to upgrade without a restore point"
fi

# 3. Show what the database migration would do, then confirm.
log "planned migrations:"
(cd "$RELEASE/backend" && "$NEW_PYTHON" manage.py migrate --plan)

if [ "$ASSUME_YES" -ne 1 ]; then
    printf '[upgrade] Apply these migrations now? [y/N] '
    read -r reply
    case "$reply" in
        y|Y|yes|YES) ;;
        *) fail "aborted by the operator; nothing was changed" ;;
    esac
fi

# 4. Stop every writer before migration. The maintenance window begins here.
if command -v systemctl >/dev/null 2>&1; then
    log "entering the maintenance window"
    systemctl stop vezano-worker.service || log "worker was not running"
    systemctl stop vezano-web.service || log "web service was not running"
fi

# 5. Apply migrations and collect static files against the NEW code.
log "applying migrations"
(cd "$RELEASE/backend" && "$NEW_PYTHON" manage.py migrate)

log "collecting static files"
(cd "$RELEASE/backend" && "$NEW_PYTHON" manage.py collectstatic --noinput)

# 6. Deployment check before the new tree can serve traffic.
log "running Django's deployment check"
(cd "$RELEASE/backend" && "$NEW_PYTHON" manage.py check --deploy) \
    || fail "check --deploy failed; the old release link remains in place"

# 7. Move the symlink only now, and record the version change in the
#    installation record (the licence page and support read it from there).
log "switching $LINK -> $RELEASE"
ln -sfn "$RELEASE" "$LINK"
NEW_VERSION="$(tr -d '[:space:]' < "$RELEASE/VERSION" 2>/dev/null || true)"
if [ -n "$NEW_VERSION" ]; then
    (cd "$RELEASE/backend" && "$NEW_PYTHON" manage.py bootstrap_standalone --app-version "$NEW_VERSION") \
        || log "WARNING: could not record version $NEW_VERSION on the installation"
fi

# 8. Restart services and confirm health.
if command -v systemctl >/dev/null 2>&1; then
    log "restarting services"
    systemctl restart vezano-web.service
    systemctl start vezano-worker.service
fi

log "running preflight after the upgrade"
(cd "$RELEASE/backend" && "$NEW_PYTHON" manage.py preflight) \
    || fail "preflight failed after the upgrade; review before use"

log "upgrade complete"
log "rollback: the pre-upgrade backup is in $BACKUP_DIR; reverting code alone is"
log "not a rollback once an incompatible migration has run."
