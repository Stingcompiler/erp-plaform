#!/usr/bin/env bash
#
# Vezano standalone — roll back to the previous release after a failed upgrade.
#
# Code alone cannot be rolled back once a migration has run, so this script
# restores the pre-upgrade backup into a FRESH database and a FRESH media
# directory prepared for it, proves the restore reproduces the backup, and
# only then repoints the protected environment file, moves the `current`
# symlink to the previous release and restarts the services. The database and
# media the upgraded release was using are left untouched for forensics.
#
# Everything written after the pre-upgrade backup was taken is lost by design:
# that is what a rollback means. Say so to the customer before running it.
#
# Usage:
#   rollback.sh --to /opt/vezano/releases/1.0.0 \
#               --from /var/backups/vezano/<stamp>-pre-upgrade \
#               --database-url postgres://vezano:...@127.0.0.1/vezano_rb1 \
#               [--media-root /var/lib/vezano/media-rb1] [--yes]
#
# Options:
#   --to DIR            the previous release directory (must hold backend/manage.py)
#   --from DIR          the backup to restore (normally the pre-upgrade one)
#   --database-url URL  an EMPTY database created for the rollback (createdb -O vezano)
#   --media-root DIR    where media is restored (default: <MEDIA_ROOT>.rollback-<stamp>)
#   --link PATH         the 'current' symlink (default /opt/vezano/current)
#   --env-file FILE     protected environment file (default /etc/vezano/vezano.env)
#   --yes               do not prompt before repointing the installation
#
# Exit codes: 0 rolled back and preflight passed; non-zero with nothing
# repointed on any failure before the promotion step.

set -euo pipefail

TO=""
FROM=""
TARGET_URL=""
MEDIA_ROOT=""
LINK="/opt/vezano/current"
ENV_FILE="/etc/vezano/vezano.env"
ASSUME_YES=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

while [ $# -gt 0 ]; do
    case "$1" in
        --to) TO="$2"; shift 2 ;;
        --from) FROM="$2"; shift 2 ;;
        --database-url) TARGET_URL="$2"; shift 2 ;;
        --media-root) MEDIA_ROOT="$2"; shift 2 ;;
        --link) LINK="$2"; shift 2 ;;
        --env-file) ENV_FILE="$2"; shift 2 ;;
        --yes) ASSUME_YES=1; shift ;;
        -h|--help) sed -n '2,31p' "$0"; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

log() { printf '[rollback] %s\n' "$*"; }
fail() { printf '[rollback] ERROR: %s\n' "$*" >&2; exit 1; }

[ -n "$TO" ] || fail "--to RELEASE_DIR is required"
[ -n "$FROM" ] || fail "--from BACKUP_DIR is required"
[ -n "$TARGET_URL" ] || fail "--database-url URL of an empty database is required"
[ -f "$TO/backend/manage.py" ] || fail "$TO does not look like a Vezano release"
[ -x "$TO/venv/bin/python" ] || fail "$TO has no venv; the previous release must be intact"
[ -d "$FROM" ] || fail "backup directory not found: $FROM"
[ -f "$ENV_FILE" ] || fail "environment file not found: $ENV_FILE"

export VEZANO_ENV_FILE="$ENV_FILE"
PREV_PYTHON="$TO/venv/bin/python"

env_value() {
    "$PREV_PYTHON" - "$1" <<'PY'
import os
import sys

import environ

environ.Env.read_env(os.environ["VEZANO_ENV_FILE"])
print(os.environ.get(sys.argv[1], ""))
PY
}

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
# The URL carries the database password; never echo it into a log.
SAFE_URL="$(printf '%s' "$TARGET_URL" | sed -E 's#(//[^:/@]+):[^@]*@#\1:***@#')"
LIVE_MEDIA="$(env_value MEDIA_ROOT)"
LIVE_MEDIA="${LIVE_MEDIA:-$LINK/backend/media}"
[ -n "$MEDIA_ROOT" ] || MEDIA_ROOT="${LIVE_MEDIA%/}.rollback-${STAMP}"
[ -e "$MEDIA_ROOT" ] && [ -n "$(ls -A "$MEDIA_ROOT" 2>/dev/null)" ] \
    && fail "media directory is not empty: $MEDIA_ROOT"

# 1. Restore into the fresh database and media directory, and prove it.
log "restoring $FROM into the rollback database"
VEZANO_HOME="$TO" VEZANO_PYTHON="$PREV_PYTHON" VEZANO_ENV_FILE="$ENV_FILE" \
    bash "$SCRIPT_DIR/restore.sh" --from "$FROM" --database-url "$TARGET_URL" \
        --media-root "$MEDIA_ROOT" \
    || fail "the restore did not verify; nothing has been repointed"

# 2. Confirm before the installation is repointed.
log "the verified copy is ready:"
log "  release   $TO"
log "  database  $SAFE_URL"
log "  media     $MEDIA_ROOT"
log "everything written after the backup was taken will no longer be visible."
if [ "$ASSUME_YES" -ne 1 ]; then
    printf '[rollback] Repoint the installation now? [y/N] '
    read -r reply
    case "$reply" in
        y|Y|yes|YES) ;;
        *) fail "aborted by the operator; the restored copy remains for inspection" ;;
    esac
fi

# 3. Stop the writers.
if command -v systemctl >/dev/null 2>&1; then
    log "stopping services"
    systemctl stop vezano-worker.service || log "worker was not running"
    systemctl stop vezano-web.service || log "web service was not running"
fi

# 4. Repoint the environment file (keeping a copy of the one being replaced).
install -m 0600 "$ENV_FILE" "${ENV_FILE}.before-rollback-${STAMP}"
log "previous environment file kept at ${ENV_FILE}.before-rollback-${STAMP}"
"$PREV_PYTHON" - "$ENV_FILE" "$TARGET_URL" "$MEDIA_ROOT" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
updates = {"DATABASE_URL": sys.argv[2], "MEDIA_ROOT": sys.argv[3]}
lines = path.read_text(encoding="utf-8").splitlines()
seen = set()
for i, line in enumerate(lines):
    key = line.split("=", 1)[0].strip()
    if "=" in line and not line.lstrip().startswith("#") and key in updates:
        lines[i] = f"{key}={updates[key]}"
        seen.add(key)
for key, value in updates.items():
    if key not in seen:
        lines.append(f"{key}={value}")
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

# 5. Move the symlink and record the version change.
log "switching $LINK -> $TO"
ln -sfn "$TO" "$LINK"
PREV_VERSION="$(tr -d '[:space:]' < "$TO/VERSION" 2>/dev/null || true)"
if [ -n "$PREV_VERSION" ]; then
    (cd "$TO/backend" && "$PREV_PYTHON" manage.py bootstrap_standalone --app-version "$PREV_VERSION") \
        || log "WARNING: could not record version $PREV_VERSION on the installation"
fi

# 6. Restart and confirm.
if command -v systemctl >/dev/null 2>&1; then
    log "restarting services"
    systemctl restart vezano-web.service
    systemctl start vezano-worker.service || log "worker not started (optional)"
fi

log "running preflight on the rolled-back installation"
(cd "$TO/backend" && "$PREV_PYTHON" manage.py preflight) \
    || fail "preflight failed after the rollback; review before use"

log "rollback complete: $LINK -> $TO, database $SAFE_URL, media $MEDIA_ROOT"
log "the upgraded release's database and media were not modified."
