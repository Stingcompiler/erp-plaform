# Vezano standalone deployment

This profile installs the same Django monolith used by SaaS for one customer.
It uses native Linux services and PostgreSQL; it does not use containers and
does not depend on Render.

## Supported shape

- Ubuntu LTS or an equivalent maintained Linux distribution.
- PostgreSQL with a dedicated database and least-privilege login.
- Python 3.12 virtual environment **inside each release** (`<release>/venv`), Node.js 20 or newer on the build machine, and TLS at the reverse proxy (Caddy: see `Caddyfile.example`).
- One Gunicorn web service and optional Celery worker (the worker needs Redis; the web service does not). The frontend is built once and served by Django.
- `VEZANO_DEPLOYMENT_MODE=standalone`; this value is fixed for the life of the database.

Copy `vezano.env.example` to `/etc/vezano/vezano.env`, fill it with unique
secrets, set mode `0600`. Django reads that file itself (`VEZANO_ENV_FILE`, set
by the service units and exported by the scripts); it is never sourced by a
shell. `package_release.sh` refuses to build an archive that contains a real
environment file, a database, media, a key, or a developer virtual environment.

## First installation

The step-by-step commands are in `OPERATIONS.md`. In outline:

1. Verify the signed release checksum and signature; unpack into `/opt/vezano/releases/<version>`; link `/opt/vezano/current`.
2. Create `<release>/venv` and install `backend/requirements.txt`.
3. Write `/etc/vezano/vezano.env`; drop the vendor's public key into `/etc/vezano/license-keys/`.
4. `migrate`, `collectstatic --noinput`, `bootstrap_standalone --organisation "Customer legal name" --app-version <version>`.
5. `create_owner --email <owner>` — prompts for a unique password and creates the company, its main branch, the role set and the Business Owner. No default password exists anywhere.
6. Start the services, sign in, import the signed licence from **Subscription & licence**, then `preflight` must pass.

The frontend export ships inside the archive (`frontend/out`), so the customer
host does not need Node.js; `npm ci && npm run build` is a build-machine step.

## Upgrade

Put the application in a documented maintenance window, verify a fresh database
and media backup, unpack the signed new release beside the old one, install its
locked dependencies, build the frontend, run `migrate --plan`, then `migrate`
and `check --deploy`. Change the `/opt/vezano/current` link only after those
checks pass. A rollback after an incompatible database migration requires the
matching pre-upgrade database and media backup; changing application files
alone is not a safe rollback.

## Backup and recovery

Back up the complete PostgreSQL database with `pg_dump --format=custom`, the
entire media directory, and the protected environment file. Store encrypted
copies away from the application host. A backup is accepted only after a test
restore into an isolated PostgreSQL database, verification of row counts and
files, and a successful login/health check. The installation identity lives in
the database, so restoring it preserves licence binding.

The existing in-app backup screen exports selected business rows and is not a
replacement for this full recovery procedure.


## Issuing a licence (vendor side, never on the customer server)

1. Once: create the signing key pair, outside any repository, and back the
   private key up in your secrets manager.

   ```bash
   python backend/manage.py license_keygen --key-id vezano-2026 --out-dir ~/vezano-keys
   ```

   Ship `vezano-2026.public.pem` with every release: the customer copies it
   into `/etc/vezano/license-keys/` (`VEZANO_LICENSE_PUBLIC_KEYS_DIR`).
   Rotating keys later = a new `--key-id`, its public key copied beside the
   old one, new licences signed with the new key; existing licences keep
   verifying. (The single-line `VEZANO_LICENSE_PUBLIC_KEYS` JSON form still
   works for environments without a file drop.)

2. Per customer, after they ran `bootstrap_standalone` and sent you the
   installation ID shown on their Subscription & licence page:

   ```bash
   # perpetual licence, maintenance (upgrades) for one year, up to release 1.x
   python backend/manage.py issue_license \
     --private-key ~/vezano-keys/vezano-2026.private.pem --key-id vezano-2026 \
     --installation-id <uuid from the customer> --organisation "Customer legal name" \
     --kind perpetual --maintenance-until 2027-09-14 --max-version 1.99.99 \
     --modules "*" --limit users=25 --limit branches=3 \
     --out customer-2026-09.json

   # fixed-term licence: last usable day, 14 days grace, then read-only
   python backend/manage.py issue_license ... --kind term --usable-until 2027-09-14 --grace-days 14
   ```

3. Send the JSON file to the customer; they import it on **Subscription &
   licence**. A licence is bound to one installation ID and one signing key;
   a file for another installation or from an untrusted key is refused.

What each field does at runtime:

| Field | Effect |
|---|---|
| `kind=term`, `usable_until`, `grace_until` | active → grace (writes still allowed, banner warns) → read-only |
| `maintenance_until` | informational; `preflight` warns once it has passed |
| `max_application_version` | a release above it puts the installation in read-only until renewed or rolled back; `preflight` fails before the upgrade goes live |
| `modules`, `limits` | same entitlement engine as SaaS plans |

`SUBSCRIPTION_POLICY` is ignored in standalone: the licence always enforces.
