# Vezano standalone deployment

This profile installs the same Django monolith used by SaaS for one customer.
It uses native Linux services and PostgreSQL; it does not use containers and
does not depend on Render.

## Supported shape

- Ubuntu LTS or an equivalent maintained Linux distribution.
- PostgreSQL with a dedicated database and least-privilege login.
- Python 3.12 virtual environment, Node.js 20 for release builds, and TLS at the reverse proxy.
- One Gunicorn web service and optional Celery worker. The frontend is built once and served by Django.
- `VEZANO_DEPLOYMENT_MODE=standalone`; this value is fixed for the life of the database.

Copy `vezano.env.example` outside the repository, fill it with unique secrets,
set mode `0600`, and reference it from the service units. Never package a real
environment file, database, uploaded media, signing private key, or developer
virtual environment in a customer release.

## First installation

1. Verify the signed release checksum and unpack it into `/opt/vezano/releases/<version>`.
2. Create the Python environment and install `backend/requirements.txt`.
3. Run `npm ci && npm run build` inside `frontend`.
4. Run `python backend/manage.py migrate` and `python backend/manage.py collectstatic --noinput`.
5. Run `python backend/manage.py bootstrap_standalone --organisation "Customer legal name"`.
6. Create the first owner with an interactive, unique password. Do not ship a common password.
7. Start the native services, import the signed licence from **Subscription & licence**, and run health checks.

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
