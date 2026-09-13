#!/usr/bin/env bash
#
# Vezano standalone — restore a full backup into a target database.
#
# The safe procedure is to restore into an ISOLATED database first, verify it,
# and only then promote it. This script does exactly that shape: it restores
# into whatever database you point it at, extracts media, and runs the
# fingerprint comparison — refusing to declare success unless every counted
# table and the media totals come back unchanged.
#
# Usage:
#   restore.sh --from BACKUP_DIR --database-url URL [options]
#
# Options:
#   --media-root DIR   where to extract media (default: a temporary directory)
#   --skip-verify      restore only; do not compare fingerprints (not advised)
#   --force            proceed even if the target database is not empty
#
# Environment:
#   VEZANO_HOME     install root        (default /opt/vezano/current)
#   VEZANO_PYTHON   python interpreter  (default /opt/vezano/venv/bin/python)
#
# Exit codes: 0 verified, non-zero on any failure.

set -euo pipefail

VEZANO_HOME="${VEZANO_HOME:-/opt/vezano/current}"
VEZANO_PYTHON="${VEZANO_PYTHON:-/opt/vezano/venv/bin/python}"

FROM=""
TARGET_URL=""
MEDIA_ROOT=""
SKIP_VERIFY=0
FORCE=0

while [ $# -gt 0 ]; do
    case "$1" in
        --from) FROM="$2"; shift 2 ;;
        --database-url) TARGET_URL="$2"; shift 2 ;;
        --media-root) MEDIA_ROOT="$2"; shift 2 ;;
        --skip-verify) SKIP_VERIFY=1; shift ;;
        --force) FORCE=1; shift ;;
        -h|--help) sed -n '2,28p' "$0"; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

log() { printf '[restore] %s\n' "$*"; }
fail() { printf '[restore] ERROR: %s\n' "$*" >&2; exit 1; }

[ -n "$FROM" ] || fail "--from BACKUP_DIR is required"
[ -n "$TARGET_URL" ] || fail "--database-url URL is required"
[ -d "$FROM" ] || fail "backup directory not found: $FROM"
[ -f "$FROM/database.dump" ] || fail "missing database.dump in $FROM"
[ -f "$FROM/fingerprint.json" ] || fail "missing fingerprint.json in $FROM"
command -v pg_restore >/dev/null 2>&1 || fail "pg_restore is not on PATH"
command -v psql >/dev/null 2>&1 || fail "psql is not on PATH"
[ -f "$FROM/backup-manifest.json" ] || fail "missing backup-manifest.json in $FROM"

TEMP_MEDIA=""
cleanup() { [ -n "$TEMP_MEDIA" ] && rm -rf "$TEMP_MEDIA"; }
trap cleanup EXIT

# 1. Verify the archive against its own manifest before touching anything.
log "verifying artefact checksums"
    "$VEZANO_PYTHON" - "$FROM" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
manifest = json.loads((root / "backup-manifest.json").read_text(encoding="utf-8"))


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


problems = []
for name, meta in manifest.get("artefacts", {}).items():
    path = root / name
    if not path.is_file():
        problems.append(f"missing: {name}")
        continue
    if sha256(path) != meta.get("sha256"):
        problems.append(f"checksum mismatch: {name}")
if problems:
    print("\n".join(problems))
    raise SystemExit(1)
print(f"{len(manifest.get('artefacts', {}))} artefact(s) verified")
PY

# 2. Refuse to write into a database that already holds data.
TABLE_COUNT="$(psql "$TARGET_URL" -tAc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")"
if [ "${TABLE_COUNT:-0}" != "0" ] && [ "$FORCE" -ne 1 ]; then
    fail "target database is not empty ($TABLE_COUNT table(s)); restore into a fresh database or pass --force"
fi
if [ "${TABLE_COUNT:-0}" != "0" ]; then
    log "WARNING: target is not empty and --force was given; existing objects may conflict"
fi

# 3. Restore the database.
log "restoring database"
pg_restore --dbname="$TARGET_URL" --no-owner --no-privileges --exit-on-error \
    "$FROM/database.dump"

# 4. Extract media.
if [ -z "$MEDIA_ROOT" ]; then
    TEMP_MEDIA="$(mktemp -d)"
    MEDIA_ROOT="$TEMP_MEDIA"
fi
mkdir -p "$MEDIA_ROOT"
if [ -f "$FROM/media.tar.gz" ]; then
    log "extracting media into $MEDIA_ROOT"
    "$VEZANO_PYTHON" - "$FROM/media.tar.gz" <<'PY'
import sys
import tarfile
from pathlib import PurePosixPath

with tarfile.open(sys.argv[1], "r:gz") as archive:
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
            raise SystemExit(f"unsafe media archive member: {member.name}")
PY
    tar -xzf "$FROM/media.tar.gz" -C "$MEDIA_ROOT"
fi

# 5. Prove the restore reproduces the backup.
if [ "$SKIP_VERIFY" -eq 1 ]; then
    log "WARNING: --skip-verify given; the restore was not proven"
    exit 0
fi

log "verifying the restored data against the fingerprint"
(
    cd "$VEZANO_HOME/backend"
    DATABASE_URL="$TARGET_URL" MEDIA_ROOT="$MEDIA_ROOT" "$VEZANO_PYTHON" manage.py \
        verify_restore --expected "$FROM/fingerprint.json"
)

log "restore verified successfully"
[ -n "$TEMP_MEDIA" ] && log "media was extracted to a temporary directory and will now be removed"
