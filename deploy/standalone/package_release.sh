#!/usr/bin/env bash
#
# Vezano standalone — build a signed release archive.
#
# Produces, in the output directory:
#   vezano-<version>.tar.gz        the release tree
#   vezano-<version>.tar.gz.sha256 its SHA-256
#   vezano-<version>.tar.gz.sig    a detached signature (when --signing-key is given)
# plus release-manifest.json and SHA256SUMS captured from inside the tree.
#
# The archive deliberately excludes everything that is not application code:
# the virtual environment, node_modules, the local database, collected static
# files, uploaded media and the git history. Shipping any of those would either
# bloat the release or leak one installation's data into another's.
#
# Usage:
#   package_release.sh --output DIR [--signing-key PRIVATE_KEY.pem] [--version VERSION]
#
# Exit codes: 0 success, non-zero on any failure.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VEZANO_PYTHON="${VEZANO_PYTHON:-${REPO_ROOT}/backend/.venv312/bin/python}"

OUTPUT=""
SIGNING_KEY=""
VERSION=""

while [ $# -gt 0 ]; do
    case "$1" in
        --output) OUTPUT="$2"; shift 2 ;;
        --signing-key) SIGNING_KEY="$2"; shift 2 ;;
        --version) VERSION="$2"; shift 2 ;;
        -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

log() { printf '[package] %s\n' "$*"; }
fail() { printf '[package] ERROR: %s\n' "$*" >&2; exit 1; }

[ -n "$OUTPUT" ] || fail "--output DIR is required"
[ -d "$REPO_ROOT/frontend/out" ] || fail "frontend/out is missing; run 'npm run build' in frontend/ first"
[ -f "$REPO_ROOT/frontend/out/index.html" ] || fail "frontend/out has no index.html"

if [ -z "$VERSION" ]; then
    VERSION="$(tr -d '[:space:]' < "$REPO_ROOT/VERSION" 2>/dev/null || echo 0.0.0-unknown)"
fi

mkdir -p "$OUTPUT"
OUTPUT="$(cd "$OUTPUT" && pwd)"
ARCHIVE="$OUTPUT/vezano-${VERSION}.tar.gz"

log "building release manifest (version $VERSION)"
"$VEZANO_PYTHON" "$REPO_ROOT/backend/manage.py" release_manifest --output-dir "$REPO_ROOT" \
    || fail "manifest generation failed"

log "creating archive"
tar -czf "$ARCHIVE" \
    --exclude='.git' \
    --exclude='.venv' \
    --exclude='.venv312' \
    --exclude='venv' \
    --exclude='node_modules' \
    --exclude='.next' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.sqlite3' \
    --exclude='backend/staticfiles' \
    --exclude='backend/media' \
    --exclude='*.log' \
    -C "$REPO_ROOT" .

log "hashing archive"
if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$ARCHIVE" | awk '{print $1}' > "${ARCHIVE}.sha256"
else
    sha256sum "$ARCHIVE" | awk '{print $1}' > "${ARCHIVE}.sha256"
fi

if [ -n "$SIGNING_KEY" ]; then
    [ -f "$SIGNING_KEY" ] || fail "signing key not found: $SIGNING_KEY"
    command -v openssl >/dev/null 2>&1 || fail "openssl is required to sign"
    log "signing archive with $SIGNING_KEY"
    openssl dgst -sha256 -sign "$SIGNING_KEY" -out "${ARCHIVE}.sig" "$ARCHIVE"
    log "signature: ${ARCHIVE}.sig"
else
    log "no --signing-key given; the archive is unsigned and an operator cannot"
    log "verify it came from Vezano. Sign before distributing to a customer."
fi

log "release ready:"
log "  archive   $ARCHIVE"
log "  checksum  ${ARCHIVE}.sha256"
log "  version   $VERSION"
