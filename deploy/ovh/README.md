# Automatic OVH deployment

The existing CI workflow now has an optional `deploy-ovh` job. It runs only for
pushes to `main`, after backend tests on SQLite and PostgreSQL, frontend checks,
offline E2E tests and deployment orchestration tests all pass. Pull requests and
other branches cannot run this job. It is gated by the repository variable
`OVH_AUTO_DEPLOY_ENABLED=true` and serializes deployment without cancelling an
upgrade already in progress.

Backend and E2E dependency installation is constrained by `requirements.lock`,
so their runtime versions match the packaged release and the VPS installation.

The deployment uses the frontend export produced by the successful frontend
job in the same workflow run. It checks out the exact tested commit, installs
the runtime pins, creates the existing release manifest/archive, and uploads
over SSH with strict pinned host verification. GitHub and the server both
reject stale commits that are no longer the head of `main`.

## Access boundary

Use a dedicated Ed25519 deployment key; never put an operator's personal SSH
private key in GitHub Actions. Store its private half in the repository's
encrypted Actions secret `OVH_DEPLOY_SSH_KEY`. The public half is installed on
the VPS for the separate `vezano-deploy` account. This account:

- Has a root-owned home and authorized_keys file, so it cannot edit key policy.
- Uses an SSH forced command with `restrict`, disabling interactive shell,
  forwarding, PTY and user startup scripts for this key.
- Can only send `ready`, `upload <commit> <sha256>`, or `deploy <commit> <sha256>`.
- Can write incoming archives, but cannot read `/etc/vezano/vezano.env` or
  protected deployment logs.
- Has passwordless sudo only for the fixed, root-owned controller. The
  controller validates exactly two full hexadecimal identifiers; it does not
  accept shell commands or arbitrary script paths. `NOSETENV` prevents adding
  a user-controlled privileged environment.

The controller copies incoming data without following symlinks, verifies its
checksum, and rejects archive traversal, duplicate paths, links, device files
and oversized payloads. It installs code as the existing `vezano` application
user. It always uses the reviewed root-owned upgrade and backup scripts in
`/usr/local/libexec/vezano`, never uploaded root scripts.

Application Python (including backup fingerprinting), database dumps and media
reads run as the application account. Root opens the protected backup output
files and copies the fixed environment file; it uses only the isolated system
interpreter for health JSON and backup hashes. An app-owned venv is never
executed as root by this deployment path.

The deployment key grants permission to replace application code through this
controller. Protect access to Actions secrets and `main` accordingly. Checksum
verification prevents corruption; origin trust comes from the authenticated
SSH channel and the approved CI workflow, not a detached vendor signature.

## One-time server installation

Review the changes before running the installer. Obtain the code from the
reviewed, pinned commit and supply the dedicated public key as a file:

```bash
sudo bash deploy/ovh/install.sh /tmp/vezano-deploy.pub /usr/bin/python3.12
```

The installer creates the restricted account, fixed controller, configuration,
sudo rule, incoming directory and protected logs. It does not switch current,
restart web, install Redis/Celery or change application/database settings. It
replaces the dedicated account's authorized_keys on reinstallation, providing
an explicit key-rotation path.

The installer explicitly sets `/srv/vezano-deploy` to root-owned mode `0710`
with group `vezano-deploy`. This permits the deployment account to traverse
the parent to its writable `incoming` directory, without listing or writing
the parent. The `private` staging directory remains root-only mode `0700`.
On an existing installation with a root-only parent, repair only that directory:

```bash
sudo install -d -o root -g vezano-deploy -m 0710 /srv/vezano-deploy
sudo -u vezano-deploy test -w /srv/vezano-deploy/incoming
```

`/etc/vezano-deploy.json` contains only paths and public deployment settings; it
does not contain application secrets. Its location is outside the protected
application configuration directory, so the gateway needs no broader access
to that directory.

The default Python path is Ubuntu 24.04's `/usr/bin/python3.12`. If the host uses
a different Python 3.12 executable, supply its absolute path to the installer.
The existing web unit must match the current-link layout and protected env file
validated by `upgrade.sh`.

## GitHub configuration

Repository variables:

| Name | Value |
|---|---|
| `OVH_AUTO_DEPLOY_ENABLED` | `false` until gateway installation/authentication succeeds; then `true` |
| `OVH_DEPLOY_HOST` | The VPS hostname or IP |
| `OVH_DEPLOY_PORT` | `22` for this host |
| `OVH_DEPLOY_USER` | `vezano-deploy` |

Repository Actions secrets:

| Name | Contents |
|---|---|
| `OVH_DEPLOY_SSH_KEY` | Dedicated private deployment key |
| `OVH_KNOWN_HOSTS` | Existing trusted known_hosts entry for the VPS, verified by the operator |

Do not collect a new host key blindly during each deployment, disable strict
host checking, print secret values or enable shell tracing. The workflow writes
credentials only to protected temporary runner files and removes them on exit.
Deployment subprocess output stays in root-only logs on the host; public Actions
logs receive short deployment results and file paths, not Django/database traces.

Authenticate with the dedicated key using `ready` before enabling the variable:

```bash
ssh -T -i /path/to/dedicated/key \
  -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
  vezano-deploy@VPS_HOST ready
```

The `ovh-production` GitHub environment records deployments and their commit.
Environment approval rules can be added if the team later wants a manual
production gate. No approval rule is required for the requested fully automatic
no-migration path.

## Production behavior and recovery

New releases live at `/opt/vezano/releases/<version>-<commit-prefix>-auto` with a
`DEPLOYMENT.json` recording the full commit and archive checksum. Dependencies
are prepared as `vezano` before maintenance. Repeating the same commit/checksum
reuses its prepared release; a conflicting artifact is rejected.

Only SaaS mode is accepted. `upgrade.sh` is always invoked with
`--require-no-migrations --worker-service none --yes`, with the normal backup
enabled. Pending migrations stop before the maintenance window, leaving the
live release in place. Use the documented manual migration workflow to review
and apply schema changes; rerun CI only after the database is ready.

The upgrade pauses/drains Vezano scheduled jobs, stops web, captures its full
backup, rechecks migration state, atomically promotes and verifies the actual
web endpoint. A failure before database writes restores the previous release.
The workflow then checks public HTTPS health. This uses a maintenance window
including backup time; it is not a zero-downtime deployment.

Other writers (cron, beat, test candidate processes or workers on other hosts)
must follow the same maintenance policy. The controller does not enumerate or
stop arbitrary services. Existing code-only rollback assumptions and backup
restore acceptance limits remain in `deploy/standalone/UPGRADE_REVIEW.md`.

Protected logs: `/var/log/vezano-deploy/`

Last successful deployment: `/var/lib/vezano-deploy-state/last-success.json`

There is no automatic deletion of old releases or backups. Plan retention and
test restores separately. A failed public reverse-proxy check after a locally
healthy promotion reports failure and requires investigation; it does not
silently claim the public site is healthy.

To stop future automatic deployments, set `OVH_AUTO_DEPLOY_ENABLED=false`.
An upgrade already running is allowed to finish rather than being cancelled
during its writer pause.

## Verification

```bash
python3 -m unittest discover -s deploy/tests -v
bash -n deploy/ovh/install.sh
bash -n deploy/standalone/upgrade.sh
actionlint .github/workflows/ci.yml
```

First acceptance requires a real successful CI run on main, a successful
restricted-key connection, a protected backup, promotion to the matching
commit's release, local/public health success, and no worker or schema change.
