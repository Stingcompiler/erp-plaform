#!/usr/bin/env bash
# Install the reviewed OVH deployment gateway; does not restart or promote web.
# Usage: sudo bash install.sh PUBLIC_KEY_FILE [PYTHON3.12_PATH]
set -euo pipefail
umask 077

[ "$(id -u)" -eq 0 ] || { printf 'Run with sudo\n' >&2; exit 1; }
[ "$#" -ge 1 ] && [ "$#" -le 2 ] || { printf 'Public key file required\n' >&2; exit 1; }
PUBLIC_KEY_FILE="$1"
PYTHON="${2:-/usr/bin/python3.12}"
SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -x "$PYTHON" ] || { printf 'Python 3.12 executable not found\n' >&2; exit 1; }
"$PYTHON" -c 'import sys; assert sys.version_info[:2] == (3, 12)'
ssh-keygen -lf "$PUBLIC_KEY_FILE" >/dev/null
PUBLIC_KEY="$(cat "$PUBLIC_KEY_FILE")"
[[ "$PUBLIC_KEY" == ssh-ed25519\ * ]] && [[ "$PUBLIC_KEY" != *$'\n'* ]] \
    || { printf 'A single Ed25519 public key is required\n' >&2; exit 1; }
id vezano >/dev/null
if ! id vezano-deploy >/dev/null 2>&1; then
    useradd --system --user-group --home-dir /var/lib/vezano-deploy --shell /bin/sh vezano-deploy
    usermod --password '*' vezano-deploy
fi
install -d -o root -g root -m 0755 /usr/local/libexec/vezano /var/lib/vezano-deploy /var/lib/vezano-deploy/.ssh
install -d -o root -g vezano-deploy -m 0770 /srv/vezano-deploy/incoming
install -d -o root -g root -m 0700 /srv/vezano-deploy/private /var/log/vezano-deploy /var/lib/vezano-deploy-state
install -m 0755 "$SOURCE/gateway.py" /usr/local/libexec/vezano/gateway.py
install -m 0755 "$SOURCE/deploy_release.py" /usr/local/libexec/vezano/deploy_release.py
install -m 0755 "$SOURCE/../standalone/upgrade.sh" /usr/local/libexec/vezano/upgrade.sh
install -m 0755 "$SOURCE/../standalone/backup.sh" /usr/local/libexec/vezano/backup.sh

printf 'command="/usr/local/libexec/vezano/gateway.py",restrict %s\n' "$PUBLIC_KEY" \
    > /var/lib/vezano-deploy/.ssh/authorized_keys
chmod 0644 /var/lib/vezano-deploy/.ssh/authorized_keys
cat > /etc/vezano-deploy.json <<JSON
{
  "repository": "Stingcompiler/erp-plaform",
  "incoming": "/srv/vezano-deploy/incoming",
  "private_stage": "/srv/vezano-deploy/private",
  "releases": "/opt/vezano/releases",
  "link": "/opt/vezano/current",
  "env_file": "/etc/vezano/vezano.env",
  "backups": "/var/backups/vezano",
  "health_host": "pro.vezano.app",
  "app_user": "vezano",
  "python": "$PYTHON",
  "logs": "/var/log/vezano-deploy",
  "state": "/var/lib/vezano-deploy-state",
  "lock": "/run/lock/vezano-autodeploy.lock"
}
JSON
chmod 0644 /etc/vezano-deploy.json
SUDOERS="$(mktemp)"
trap 'rm -f "$SUDOERS"' EXIT
printf 'Defaults:vezano-deploy env_reset\nvezano-deploy ALL=(root) NOPASSWD:NOSETENV: /usr/local/libexec/vezano/deploy_release.py *\n' > "$SUDOERS"
visudo -cf "$SUDOERS" >/dev/null
install -o root -g root -m 0440 "$SUDOERS" /etc/sudoers.d/vezano-deploy
printf '[deploy] gateway installed; production service and current link retained\n'
