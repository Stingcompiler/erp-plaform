# Vezano standalone — operations runbook

This is the procedure intended for a release candidate. The Python services,
commands, migration graph, and shell syntax are covered by the repository test
suite. A release is not approved for sale until this exact procedure also passes
against a clean PostgreSQL 16 host and the signed acceptance record is retained.

Nothing here needs a connection to Vezano.

## Layout

| Path | Purpose |
|---|---|
| `/opt/vezano/releases/<version>` | one unpacked release per version |
| `/opt/vezano/releases/<version>/venv` | that release's Python environment (built on the host, never shipped) |
| `/opt/vezano/current` | symlink to the release in service — code **and** venv move together |
| `/etc/vezano/vezano.env` | protected environment file, mode `0600`, read by Django via `VEZANO_ENV_FILE` |
| `/etc/vezano/license-keys/` | the vendor's licence public key(s), `<key-id>.public.pem` |
| `/var/backups/vezano` | backup directories, one per run |
| `<MEDIA_ROOT>` | uploaded files; pointed at by `MEDIA_ROOT` in the env file |

## First installation

Run as the `vezano` user unless stated. Every command below was executed in
this order on 2026-09-14 (see *Acceptance record*).

1. Verify the release archive against the checksum and signature shipped beside it,
   from inside the download directory:

   ```bash
   sha256sum -c vezano-1.0.0.tar.gz.sha256
   openssl dgst -sha256 -verify vezano-release.pub.pem \
       -signature vezano-1.0.0.tar.gz.sig vezano-1.0.0.tar.gz
   ```

2. Unpack and link:

   ```bash
   mkdir -p /opt/vezano/releases/1.0.0
   tar -xzf vezano-1.0.0.tar.gz -C /opt/vezano/releases/1.0.0
   ln -sfn /opt/vezano/releases/1.0.0 /opt/vezano/current
   ```

3. Create the release's own environment (Ubuntu 24.04: `apt install python3.12-venv`):

   ```bash
   python3.12 -m venv /opt/vezano/current/venv
   /opt/vezano/current/venv/bin/pip install --upgrade pip
   /opt/vezano/current/venv/bin/pip install -r /opt/vezano/current/backend/requirements.txt
   ```

   The frontend export is inside the archive (`frontend/out`); Node.js is only
   needed on the machine that runs `package_release.sh`.

4. PostgreSQL: a dedicated role and database (as the `postgres` superuser):

   ```sql
   CREATE ROLE vezano LOGIN PASSWORD '<unique>';
   CREATE DATABASE vezano OWNER vezano;
   ```

5. Write `/etc/vezano/vezano.env` from `vezano.env.example` — unique
   `DJANGO_SECRET_KEY` (`openssl rand -hex 32`), `DJANGO_ALLOWED_HOSTS`,
   `DATABASE_URL`, `MEDIA_ROOT`, `VEZANO_LICENSE_PUBLIC_KEYS_DIR` — then
   `chmod 600`. Copy the vendor's `<key-id>.public.pem` into
   `/etc/vezano/license-keys/`. Keep `FORCE_HTTPS=True` behind the TLS proxy.

   For the rest of this shell:

   ```bash
   export VEZANO_ENV_FILE=/etc/vezano/vezano.env
   cd /opt/vezano/current/backend
   ```

6. Prove the tree, apply the schema, collect static files:

   ```bash
   ../venv/bin/python manage.py verify_release --manifest ../release-manifest.json
   ../venv/bin/python manage.py migrate
   ../venv/bin/python manage.py collectstatic --noinput
   ```

7. Record the installation identity, create the first owner, check readiness:

   ```bash
   ../venv/bin/python manage.py bootstrap_standalone \
       --organisation "Customer legal name" --app-version 1.0.0
   ../venv/bin/python manage.py create_owner --email owner@customer.example --full-name "Name"
   ../venv/bin/python manage.py preflight
   ```

   `bootstrap_standalone` prints the **installation ID**; the customer sends it
   to Vezano to receive their licence file. `create_owner` prompts twice for a
   password, runs the project's validators, and creates the company (named
   after the organisation), a `MAIN` branch, the role set and the Business
   Owner. There is no default account.

   `preflight` exits non-zero while any check *fails*. At this point exactly
   one failure is expected — `licence: No standalone licence is installed` —
   and it clears in the next step. `licence_keys` must already be `ok`;
   if it is not, the public key file is missing or not a PEM public key.

8. Install the services and TLS, then import the licence:

   ```bash
   sudo cp deploy/standalone/vezano-web.service /etc/systemd/system/
   sudo systemctl daemon-reload && sudo systemctl enable --now vezano-web
   sudo cp deploy/standalone/Caddyfile.example /etc/caddy/Caddyfile   # edit the host name
   sudo systemctl reload caddy
   curl -s https://<host>/api/health/
   ```

   `/api/health/` reports `deployment_mode`, `version`, `installation_id` and
   the licence state (`unlicensed` until the import). Sign in as the owner,
   open **Subscription & licence**, upload the JSON file from Vezano. The
   state becomes `active`, and `manage.py preflight` now passes.

   The worker unit (`vezano-worker.service`) is optional and needs Redis.

   **HTTPS is required even on a private LAN.** The offline mode of the POS
   is a service worker plus IndexedDB, and browsers only run a service
   worker on a secure origin (`https://…` or `localhost`). A till opened at
   `http://192.168.1.10/` has no offline shell at all — the sale queue still
   works, but the page will not open after a reboot with the server down.
   With no public DNS name, let Caddy issue its own certificate and install
   its root on every till:

   ```caddyfile
   vezano.lan {
       tls internal
       encode gzip
       reverse_proxy 127.0.0.1:8000
   }
   ```

   ```bash
   # on the server, once:
   sudo caddy trust                                   # trusts the local CA on the server
   sudo cp /var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt /srv/vezano-root.crt
   # on each till: import /srv/vezano-root.crt as a trusted root
   # (Windows: certmgr → Trusted Root Certification Authorities; macOS: Keychain → System;
   #  Android: Settings → Security → Install certificate → CA certificate),
   # and resolve vezano.lan to the server in the router's DNS or the hosts file.
   ```

   `DJANGO_ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS` in `vezano.env` must
   name the same host. After the first visit while online, the sync drawer on
   the till should say *installed as an app* and *local storage is protected*
   — that is the state the acceptance row below expects.

## Backup

```bash
VEZANO_HOME=/opt/vezano/current \
VEZANO_ENV_FILE=/etc/vezano/vezano.env \
    deploy/standalone/backup.sh --label nightly
```

The media directory is taken from `MEDIA_ROOT` in the env file (override with
`VEZANO_MEDIA_ROOT` only for a deliberate reason). Produces one dated
directory holding `database.dump`, `media.tar.gz`, `fingerprint.json`, a
protected copy of the environment file, and `backup-manifest.json` with a
SHA-256 for each. The directory is written to a `.partial` staging name and
renamed only on success, so a failed run never looks like a usable backup.

**A backup is not accepted until a restore into an isolated database succeeds.**

## Restore (and prove it)

```bash
createdb -h 127.0.0.1 -U postgres -O vezano vezano_verify

VEZANO_HOME=/opt/vezano/current \
VEZANO_ENV_FILE=/etc/vezano/vezano.env \
    deploy/standalone/restore.sh \
    --from /var/backups/vezano/20260914T210202Z-nightly \
    --database-url "postgres://vezano:<password>@127.0.0.1/vezano_verify" \
    --media-root /var/lib/vezano/media-verify
```

The script refuses to write into a database that is not empty (use `--force`
deliberately), verifies every artefact checksum, restores, extracts media, and
then runs `verify_restore`, which compares the restored database and media
against the fingerprint. A non-zero exit means the restore did **not** reproduce
the backup and the instance must not go live.

To also prove login and health on the restored copy without touching the
live service, start a throwaway Gunicorn on another port against it:

```bash
DATABASE_URL="postgres://vezano:<password>@127.0.0.1/vezano_verify" \
MEDIA_ROOT=/var/lib/vezano/media-verify \
    /opt/vezano/current/venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8001
```

Promotion is a deliberate act: stop the web service, point the environment file
at the verified database, move media into place, and restart. The installation
identity lives in the database, so a restored copy keeps its licence binding.

## Upgrade

```bash
mkdir -p /opt/vezano/releases/1.1.0 && tar -xzf vezano-1.1.0.tar.gz -C /opt/vezano/releases/1.1.0
deploy/standalone/upgrade.sh --release /opt/vezano/releases/1.1.0 --python3 python3.12
```

The order is fixed and matters:

1. The release's own `venv` is created and its dependencies installed if missing.
2. `verify_release` proves the new tree matches its own manifest.
3. A pre-upgrade backup is taken — a backup after migrating cannot undo it.
4. `migrate --plan` is printed and confirmed.
5. The services are stopped; migrations and `collectstatic` run against the new code.
6. `check --deploy` runs before the tree can serve. With `FORCE_HTTPS=True`
   it reports no issues; the four `security.W0xx` warnings seen with
   `FORCE_HTTPS=False` are that setting, not a fault. Warnings do not block,
   errors do.
7. The `current` symlink moves — code and venv together — and the new
   version is recorded on the installation (`previous_version`,
   `upgraded_at`; visible on Subscription & licence and in `/api/license/`).
8. Services restart and `preflight` runs again.

## Rollback

If no migration ran, `ln -sfn /opt/vezano/releases/<previous> /opt/vezano/current`
and restart the services. Once a migration has run, reverting application
files alone is not a rollback. Use the script, which restores the
pre-upgrade backup into a **fresh** database and media directory, proves the
restore, and only then repoints the installation:

```bash
createdb -h 127.0.0.1 -U postgres -O vezano vezano_rb1
deploy/standalone/rollback.sh \
    --to /opt/vezano/releases/1.0.0 \
    --from /var/backups/vezano/<stamp>-pre-upgrade \
    --database-url "postgres://vezano:<password>@127.0.0.1/vezano_rb1"
```

It writes `DATABASE_URL` and `MEDIA_ROOT` into `/etc/vezano/vezano.env`
(keeping the old file beside it as `vezano.env.before-rollback-<stamp>`),
moves `current`, restarts the services and runs `preflight`. The database and
media the upgraded release was using are not touched — keep them until the
cause is understood. **Everything written after the pre-upgrade backup is no
longer visible after a rollback**; tell the customer before running it.
Rolling back to a release older than 1.1.0 prints a harmless warning that the
version could not be recorded (its `bootstrap_standalone` needed
`--organisation`).

## Building a release

```bash
deploy/standalone/package_release.sh --output /tmp/releases \
    --signing-key /secure/vezano-release.key
```

This writes `release-manifest.json` and `SHA256SUMS` into the tree, then creates
`vezano-<version>.tar.gz`, its `.sha256` (in `sha256sum -c` format) and — when a
key is given — a detached `.sig`. The archive excludes the virtual environments,
`node_modules`, databases, collected static files, uploaded media, `.env`
files, editor/agent settings, test caches and the git history, and the script
**fails the build** if any such file is still found in the archive.

**Distribution of an unsigned archive is not supported.** Without a signature an
operator cannot tell a genuine release from a tampered one.

## What is verified vs. what is not

Verified in the repository test environment: the Django migration graph is
complete, transfer and fingerprint comparisons detect mismatches, release
manifests detect an edited migration or manifest, `preflight` reports blocking
configurations, and `create_owner` refuses weak passwords and hosted mode.

### Acceptance record — 2026-09-14, local dry run against PostgreSQL 16.15

Run literally, in the order above, on macOS with the release tree under a
scratch root (paths substituted; no systemd, no TLS proxy, `FORCE_HTTPS=False`):

| Step | Result |
|---|---|
| `package_release.sh` + `sha256sum -c` + `openssl dgst -verify` | 652 files, `OK`, `Verified OK` |
| unpack, per-release venv, `verify_release` | 85 migrations, frontend hash matches |
| `migrate`, `collectstatic` | 91 tables, 162 static files |
| `bootstrap_standalone`, `create_owner`, `preflight` | installation ID issued; only `licence` failing |
| Gunicorn from the unit's `ExecStart`, `/api/health/` | `unlicensed`, root → login, SaaS routes 404 |
| `issue_license` (vendor) → import on Subscription & licence | HTTP 201, state `active`, `preflight` passes |
| POS: +10 stock, sale of 3 (cash), offline batch of 2 replayed twice | invoices 3, on hand 12, replay applied once |
| Browser: login through the Django-served export, licence page | dashboard and licence details render |
| `backup.sh --label nightly` | 4 artefacts, media 20 KB from `MEDIA_ROOT` |
| `restore.sh` into empty `vezano_verify` | 91 tables and media match; login + invoices on port 8001 |
| `restore.sh` again into the same database | refused: not empty |
| `upgrade.sh` 1.0.0 → 1.0.1 (`--yes`) | venv built, pre-upgrade backup, no migrations, link moved, `preflight` passes |

#### Phase D addendum — same day, same host: upgrade with a real migration, then rollback

| Step | Result |
|---|---|
| cut 1.1.0 (adds `licensing.0003_installation_upgrade_trail`), verify checksum + signature | 654 files, `OK`, `Verified OK` |
| `upgrade.sh --release …/1.1.0 --yes` | venv built, pre-upgrade backup, plan = 1 migration, applied, `check --deploy`, link moved, version recorded `1.1.0 (previously 1.0.0)`, `preflight` passes |
| restart on 1.1.0; `/api/health/`, `/api/license/` | version 1.1.0, licence active, `previous_version` 1.0.0, `upgraded_at` set |
| POS sale on 1.1.0 | invoice 4, on hand 11 |
| `rollback.sh --to …/1.0.0 --from <pre-upgrade> --database-url …/vezano_rb1 --yes` | restore verified (91 tables + media), env repointed, link → 1.0.0, `preflight` passes |
| restart on 1.0.0 | version 1.0.0, licence active, 3 invoices (invoice 4 gone by design); the upgraded database still holds 4 |

Break found by this run: `restore.sh` exited 1 after a *successful* restore
whenever `--media-root` was given (a false `[ … ] &&` as the last command of
its EXIT trap under `set -e`), which made `rollback.sh` refuse to promote.
Fixed in `restore.sh` and the same pattern in `backup.sh`.

Breaks found by the phase C run and fixed in the scripts: the developer `.env`,
`.claude/`, `.pytest_cache/` and a SQLite backup were being shipped; the
`.sha256` file was not `sha256sum -c` readable; the JSON public-key line could
not survive `. vezano.env` (so `backup.sh` crashed); `upgrade.sh` looked for a
venv that the layout never created; and there was no command to create the
first owner.

Still required before a standalone release is approved: the same run on a
clean Ubuntu 24.04 host with systemd units, Caddy TLS in front (`tls
internal` when there is no public name — see step 8), PostgreSQL from the
distribution packages, and on a till: install the app from the browser,
confirm the sync drawer reports *local storage is protected*, unplug the
network, take two sales, reboot the till, confirm the POS opens and still
lists the two queued sales, reconnect, confirm both upload once. The same
sequence runs in CI against the export on every push (`E2E (offline POS in
Chromium)`); what CI cannot do is the install prompt and the TLS trust on a
real device. Restoring a production-scale database remains a separate
capacity test.

## Moving one SaaS company to a standalone installation

On the SaaS source, freeze writes for the selected company after its offline
queues are synchronized, then create the archive:

```bash
python backend/manage.py export_company --company 42 --output /secure/acme.vezano.zip
```

Copy the archive through an approved secure channel. On the fresh standalone
database, seed the standard roles and import it:

```bash
python backend/manage.py import_company --archive /secure/acme.vezano.zip
```

The importer creates the company, remaps internal foreign keys, resolves global
roles by name, rejects unexpected models or inconsistent counts, and disables
all imported passwords. Users must reset passwords locally. Use `--slug` if the
source slug already exists. Keep the source read-only until balances, stock,
payroll totals, user counts, and representative files are accepted by the
customer.
