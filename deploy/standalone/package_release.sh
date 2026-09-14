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
# files, uploaded media, the developer's .env, editor/agent settings, test
# caches and the git history. Shipping any of those would either bloat the
# release or leak one installation's data (or the vendor's secrets) into
# another's. The archive is listed against a deny-pattern after it is written,
# so a new kind of stray file fails the build instead of shipping quietly.
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
    --exclude='.github' \
    --exclude='.claude' \
    --exclude='.venv' \
    --exclude='.venv*' \
    --exclude='venv' \
    --exclude='node_modules' \
    --exclude='.next' \
    --exclude='__pycache__' \
    --exclude='.pytest_cache' \
    --exclude='*.pyc' \
    --exclude='*.sqlite3' \
    --exclude='*.sqlite3.*' \
    --exclude='.env' \
    --exclude='.env.*' \
    --exclude='backend/staticfiles' \
    --exclude='backend/media' \
    --exclude='.DS_Store' \
    --exclude='*.log' \
    -C "$REPO_ROOT" .

# Belt and braces: refuse to ship if anything secret-shaped or host-specific
# still made it in. The patterns are the things that have leaked in practice.
log "auditing archive contents"
STRAY="$(tar -tzf "$ARCHIVE" | grep -Ei \
    '(^|/)(\.env|\.env\.[^/]*|\.git|\.github|\.claude|\.pytest_cache|node_modules|\.next|\.venv[^/]*|venv|__pycache__|\.DS_Store)(/|$)|\.(sqlite3|pem|key|log)(\.|$)|^\./backend/(staticfiles|media)/' \
    | grep -Ev '(^|/)\.env\.example$' || true)"
if [ -n "$STRAY" ]; then
    printf '%s\n' "$STRAY" | head -20 >&2
    rm -f "$ARCHIVE"
    fail "the archive contains files that must never ship (listed above); fix the exclusions"
fi
log "$(tar -tzf "$ARCHIVE" | grep -vc '/$') file(s) in the archive"

# `<hash>  <basename>` is the format `sha256sum -c` / `shasum -c` expect, so
# the operator can verify with the command in OPERATIONS.md from inside the
# download directory.
log "hashing archive"
(
    cd "$OUTPUT"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$(basename "$ARCHIVE")" > "${ARCHIVE}.sha256"
    else
        shasum -a 256 "$(basename "$ARCHIVE")" > "${ARCHIVE}.sha256"
    fi
)

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
