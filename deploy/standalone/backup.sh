#!/usr/bin/env bash
#
# Vezano standalone — full installation backup.
#
# Produces one dated directory containing:
#   database.dump      pg_dump custom-format dump of the whole database
#   media.tar.gz       the entire media directory
#   fingerprint.json   live row counts (and optional media hash) captured first
#   environment.env    a copy of the protected environment file
#   backup-manifest.json  SHA-256 of every artefact above
#
# This is the full-recovery backup the operations guide requires. It is NOT the
# same as the in-app backup screen, which exports selected business rows for a
# single company and cannot restore an installation.
#
# Usage:
#   backup.sh [--out DIR] [--label LABEL] [--env-file FILE] [--no-media-hash]
#
# Environment (all optional):
#   VEZANO_HOME       install root                 (default /opt/vezano/current)
#   VEZANO_ENV_FILE   protected env file           (default /etc/vezano/vezano.env)
#   VEZANO_BACKUP_DIR destination root             (default /var/backups/vezano)
#   VEZANO_PYTHON     python interpreter to use    (default $VEZANO_HOME/venv/bin/python)
#   VEZANO_MEDIA_ROOT media directory              (default: MEDIA_ROOT from the env file)
#   VEZANO_BACKUP_APP_USER non-root app account    (default: vezano when run as root)
#
# Exit codes: 0 success, non-zero on any failure. Nothing is left half-written:
# the staging directory is removed on failure and only renamed into place on
# success.

set -euo pipefail
umask 077

VEZANO_HOME="${VEZANO_HOME:-/opt/vezano/current}"
VEZANO_ENV_FILE="${VEZANO_ENV_FILE:-/etc/vezano/vezano.env}"
VEZANO_BACKUP_DIR="${VEZANO_BACKUP_DIR:-/var/backups/vezano}"
VEZANO_PYTHON="${VEZANO_PYTHON:-${VEZANO_HOME}/venv/bin/python}"

LABEL=""
OUT_DIR=""
MEDIA_HASH=1

while [ $# -gt 0 ]; do
    case "$1" in
        --out) OUT_DIR="$2"; shift 2 ;;
        --label) LABEL="$2"; shift 2 ;;
        --env-file) VEZANO_ENV_FILE="$2"; shift 2 ;;
        --no-media-hash) MEDIA_HASH=0; shift ;;
        -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

log() { printf '[backup] %s\n' "$*"; }
fail() { printf '[backup] ERROR: %s\n' "$*" >&2; exit 1; }

[ -f "$VEZANO_ENV_FILE" ] || fail "environment file not found: $VEZANO_ENV_FILE"
[ -d "$VEZANO_HOME/backend" ] || fail "installation not found at: $VEZANO_HOME"
command -v pg_dump >/dev/null 2>&1 || fail "pg_dump is not on PATH"

# Root owns the backup output, but application interpreters/modules and all
# database/media readers run without root privileges. Non-root scheduled
# backups keep running as their existing service account.
BACKUP_APP_USER="${VEZANO_BACKUP_APP_USER:-}"
if [ "$(id -u)" -eq 0 ]; then
    BACKUP_APP_USER="${BACKUP_APP_USER:-vezano}"
    [ "$(id -u "$BACKUP_APP_USER")" -ne 0 ] || fail "backup application user must not be root"
    as_app() {
        runuser -u "$BACKUP_APP_USER" -- env -i PATH="$PATH" \
            VEZANO_ENV_FILE="$VEZANO_ENV_FILE" "$@"
    }
else
    [ -z "$BACKUP_APP_USER" ] || [ "$(id -u "$BACKUP_APP_USER")" -eq "$(id -u)" ] \
        || fail "non-root backup cannot select another account"
    as_app() { "$@"; }
fi

# The protected file is read by Django's own parser (django-environ), not
# sourced by this shell: a JSON value or a quoted string survives that parser
# and does not survive `. file`. Exporting VEZANO_ENV_FILE makes every
# manage.py call below see the same settings the services run with.
export VEZANO_ENV_FILE
env_value() {
    as_app "$VEZANO_PYTHON" - "$1" <<'PY'
import os
import sys

import environ

environ.Env.read_env(os.environ["VEZANO_ENV_FILE"])
print(os.environ.get(sys.argv[1], ""))
PY
}
DATABASE_URL="$(env_value DATABASE_URL)"
[ -n "$DATABASE_URL" ] || fail "DATABASE_URL is not set in $VEZANO_ENV_FILE"
if [ -z "${VEZANO_MEDIA_ROOT:-}" ]; then
    VEZANO_MEDIA_ROOT="$(env_value MEDIA_ROOT)"
    VEZANO_MEDIA_ROOT="${VEZANO_MEDIA_ROOT:-${VEZANO_HOME}/backend/media}"
fi

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="${TIMESTAMP}${LABEL:+-$LABEL}"
DEST_ROOT="${OUT_DIR:-$VEZANO_BACKUP_DIR}"
DEST="${DEST_ROOT}/${NAME}"
STAGE="${DEST}.partial"

[ -e "$DEST" ] && fail "destination already exists: $DEST"
rm -rf "$STAGE"
mkdir -p "$STAGE"

cleanup() { if [ -d "$STAGE" ]; then rm -rf "$STAGE"; fi; }
trap cleanup EXIT

log "capturing data fingerprint"
# The fingerprint must describe the same media tree that gets archived below,
# so the app is told where media lives explicitly. Redirect through a root-opened
# descriptor rather than granting the app access to the protected backup tree.
(
    cd "$VEZANO_HOME/backend"
    as_app env MEDIA_ROOT="$VEZANO_MEDIA_ROOT" "$VEZANO_PYTHON" -c '
import json, os, sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from ops.restore_check import data_fingerprint
json.dump(data_fingerprint(with_media_hash=sys.argv[1] == "1"), sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
' "$MEDIA_HASH"
) > "$STAGE/fingerprint.json"

log "dumping database"
as_app pg_dump --dbname="$DATABASE_URL" --format=custom --no-owner --no-privileges \
    > "$STAGE/database.dump"

if [ -d "$VEZANO_MEDIA_ROOT" ]; then
    log "archiving media"
    as_app tar -czf - -C "$VEZANO_MEDIA_ROOT" . > "$STAGE/media.tar.gz"
else
    log "media directory absent; writing an empty archive"
    as_app tar -czf - -T /dev/null > "$STAGE/media.tar.gz"
fi

log "protecting a copy of the environment file"
install -m 0600 "$VEZANO_ENV_FILE" "$STAGE/environment.env"

log "hashing artefacts"
# Only the root-owned isolated system interpreter touches protected files.
/usr/bin/python3 -I - "$STAGE" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

stage = Path(sys.argv[1])
fingerprint = json.loads((stage / "fingerprint.json").read_text(encoding="utf-8"))
if not isinstance(fingerprint, dict) or not isinstance(fingerprint.get("counts"), dict):
    raise ValueError("backup fingerprint must contain table counts")


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


artefacts = {}
for name in ("database.dump", "media.tar.gz", "fingerprint.json", "environment.env"):
    path = stage / name
    if path.is_file():
        artefacts[name] = {"sha256": sha256(path), "bytes": path.stat().st_size}

manifest = {"version": 1, "artefacts": artefacts}
(stage / "backup-manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
print(json.dumps(artefacts, indent=2, sort_keys=True))
PY

mv "$STAGE" "$DEST"
trap - EXIT

log "backup complete: $DEST"
du -sh "$DEST" 2>/dev/null || true
