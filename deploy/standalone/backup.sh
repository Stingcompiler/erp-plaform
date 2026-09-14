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
#
# Exit codes: 0 success, non-zero on any failure. Nothing is left half-written:
# the staging directory is removed on failure and only renamed into place on
# success.

set -euo pipefail

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

# The protected file is read by Django's own parser (django-environ), not
# sourced by this shell: a JSON value or a quoted string survives that parser
# and does not survive `. file`. Exporting VEZANO_ENV_FILE makes every
# manage.py call below see the same settings the services run with.
export VEZANO_ENV_FILE
env_value() {
    "$VEZANO_PYTHON" - "$1" <<'PY'
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

cleanup() { [ -d "$STAGE" ] && rm -rf "$STAGE"; }
trap cleanup EXIT

log "capturing data fingerprint"
FINGERPRINT_ARGS=(--output "$STAGE/fingerprint.json")
[ "$MEDIA_HASH" -eq 1 ] && FINGERPRINT_ARGS+=(--media-hash)
# The fingerprint must describe the same media tree that gets archived below,
# so the app is told where media lives explicitly (settings reads MEDIA_ROOT).
(
    cd "$VEZANO_HOME/backend"
    MEDIA_ROOT="$VEZANO_MEDIA_ROOT" "$VEZANO_PYTHON" manage.py \
        backup_snapshot "${FINGERPRINT_ARGS[@]}"
)

log "dumping database"
pg_dump --dbname="$DATABASE_URL" --format=custom --no-owner --no-privileges \
    --file="$STAGE/database.dump"

if [ -d "$VEZANO_MEDIA_ROOT" ]; then
    log "archiving media"
    tar -czf "$STAGE/media.tar.gz" -C "$VEZANO_MEDIA_ROOT" .
else
    log "media directory absent; writing an empty archive"
    tar -czf "$STAGE/media.tar.gz" -T /dev/null
fi

log "protecting a copy of the environment file"
install -m 0600 "$VEZANO_ENV_FILE" "$STAGE/environment.env"

log "hashing artefacts"
"$VEZANO_PYTHON" - "$STAGE" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

stage = Path(sys.argv[1])


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
