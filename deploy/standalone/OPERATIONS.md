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
| `/opt/vezano/current` | symlink to the release in service |
| `/opt/vezano/venv` | the Python environment for the release in service |
| `/etc/vezano/vezano.env` | protected environment file, mode `0600` |
| `/var/backups/vezano` | backup directories, one per run |
| `<MEDIA_ROOT>` | uploaded files; pointed at by `MEDIA_ROOT` in the env file |

## First installation

1. Verify the release archive against the checksum and signature shipped beside it:

   ```bash
   sha256sum -c vezano-1.0.0.tar.gz.sha256
   openssl dgst -sha256 -verify vezano-release.pub.pem \
       -signature vezano-1.0.0.tar.gz.sig vezano-1.0.0.tar.gz
   ```

2. Unpack into `/opt/vezano/releases/1.0.0` and create the symlink
   `/opt/vezano/current`.

3. Create the virtual environment and install the pinned dependencies:

   ```bash
   python3 -m venv /opt/vezano/venv
   /opt/vezano/venv/bin/pip install -r backend/requirements.txt
   ```

4. Build the frontend once, on a machine with Node.js 20:

   ```bash
   cd frontend && npm ci && npm run build
   ```

   The export lands in `frontend/out` and is served by Django. Given the export
   is committed, a build machine is not required if the archive already carries
   a current `frontend/out`.

5. Write `/etc/vezano/vezano.env` from `vezano.env.example`: unique
   `DJANGO_SECRET_KEY`, `VEZANO_DEPLOYMENT_MODE=standalone`,
   `SUBSCRIPTION_POLICY=enforce`, the database URL, and the trusted licence
   public keys. Set `MEDIA_ROOT` if media lives on a separate volume. `chmod 600`.

6. Apply the schema and collect static files:

   ```bash
   cd /opt/vezano/current/backend
   /opt/vezano/venv/bin/python manage.py migrate
   /opt/vezano/venv/bin/python manage.py collectstatic --noinput
   ```

7. Record the installation identity and check readiness:

   ```bash
   /opt/vezano/venv/bin/python manage.py bootstrap_standalone \
       --organisation "Customer legal name" --app-version 1.0.0
   /opt/vezano/venv/bin/python manage.py preflight
   ```

8. Create the first owner with an interactive, unique password — never a shared
   default. Then install the signed licence from **Subscription & licence**, and
   start the services.

`preflight` exits non-zero while any check *fails* (as opposed to warns). In
standalone enforce mode, a missing licence is a blocking failure; import the
signed licence before accepting the installation. Empty static files produce a
warning until `collectstatic` has run.

## Backup

```bash
VEZANO_HOME=/opt/vezano/current \
VEZANO_ENV_FILE=/etc/vezano/vezano.env \
VEZANO_MEDIA_ROOT=/var/lib/vezano/media \
    deploy/standalone/backup.sh --label nightly
```

Produces one dated directory holding `database.dump`, `media.tar.gz`,
`fingerprint.json`, a protected copy of the environment file, and
`backup-manifest.json` with a SHA-256 for each. The directory is written to a
`.partial` staging name and renamed only on success, so a failed run never looks
like a usable backup.

**A backup is not accepted until a restore into an isolated database succeeds.**

## Restore (and prove it)

```bash
createdb -h 127.0.0.1 -U postgres vezano_verify

VEZANO_HOME=/opt/vezano/current \
VEZANO_PYTHON=/opt/vezano/venv/bin/python \
    deploy/standalone/restore.sh \
    --from /var/backups/vezano/20260913T055205Z \
    --database-url "postgres://vezano@127.0.0.1/vezano_verify" \
    --media-root /var/lib/vezano/media-verify
```

The script refuses to write into a database that is not empty (use `--force`
deliberately), verifies every artefact checksum, restores, extracts media, and
then runs `verify_restore`, which compares the restored database and media
against the fingerprint. A non-zero exit means the restore did **not** reproduce
the backup and the instance must not go live.

Promotion is a deliberate act: stop the web service, point the environment file
at the verified database, move media into place, and restart.

## Upgrade

```bash
deploy/standalone/upgrade.sh --release /opt/vezano/releases/1.1.0
```

The order is fixed and matters:

1. `verify_release` proves the new tree matches its own manifest.
2. A pre-upgrade backup is taken — a backup after migrating cannot undo it.
3. `migrate --plan` is printed and confirmed.
4. The worker is paused; migrations and `collectstatic` run against the new code.
5. `check --deploy` runs before the tree can serve.
6. The `current` symlink moves.
7. Services restart and `preflight` runs again.

**Rollback.** Reverting application files alone is not a rollback once an
incompatible migration has run. Restore the matching pre-upgrade database and
media backup using the procedure above, then point `current` at the previous
release.

## Building a release

```bash
deploy/standalone/package_release.sh --output /tmp/releases \
    --signing-key /secure/vezano-release.key
```

This writes `release-manifest.json` and `SHA256SUMS` into the tree, then creates
`vezano-<version>.tar.gz`, its `.sha256`, and — when a key is given — a detached
`.sig`. The archive excludes the virtual environment, `node_modules`, the local
database, collected static files, uploaded media, and the git history.

**Distribution of an unsigned archive is not supported.** Without a signature an
operator cannot tell a genuine release from a tampered one.

## What is verified vs. what is not

Verified in the repository test environment: the Django migration graph is
complete, transfer and fingerprint comparisons detect mismatches, release
manifests detect an edited migration or manifest, and `preflight` reports
blocking configurations. The current automated suite uses SQLite.

Required before a standalone release is approved: a clean PostgreSQL 16 install,
a real `pg_dump`/`pg_restore` round trip including media, a signed package
verification, service startup under the target Linux distribution, and TLS at
the reverse proxy. Restoring a production-scale database remains a separate
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
