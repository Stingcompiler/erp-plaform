# OVH Vezano Pro SaaS upgrade review

Reviewed 2026-09-30 against repository commit `b37fcfd6` in
[Stingcompiler/erp-plaform](https://github.com/Stingcompiler/erp-plaform).
The supplied VPS state comes from the user and the referenced conversation.
This session did not connect to the VPS, alter systemd, or promote production.

## Decision

Use the adapted orchestration with the existing SaaS configuration, no worker,
and `--require-no-migrations` for this repackaged candidate. Keep:

- Current: `/opt/vezano/releases/1.0.0-b37fcfd6`
- Candidate: `/opt/vezano/releases/1.0.0-b37fcfd6-packaged`
- Link: `/opt/vezano/current`
- Settings file: `/etc/vezano/vezano.env`
- Mode: `saas`
- Web: `vezano-web.service`, expected on `127.0.0.1:8000`
- Health Host: `pro.vezano.app`

Do not install a dummy worker, change the deployment mode, bypass the manifest,
or run the original upgrade script unchanged. The candidate was reported to
have passed `check --deploy`, an empty migration plan, and HTTP smoke tests on
8001. Those are useful readiness evidence, but live unit configuration and the
manifest at the candidate's exact path still need verification.

## Findings in the original workflow

| Finding | Consequence | Adaptation |
|---|---|---|
| Unconditional `systemctl start vezano-worker.service` after promotion | Missing worker makes the script exit after switching the link; final preflight never runs | Inspect LoadState and ActiveState before maintenance; preserve only an already active optional worker |
| Unconditional standalone bootstrap, with errors reduced to warnings | SaaS invokes a command that intentionally refuses its mode; real standalone failures are also hidden | Read the effective mode through Django; skip in SaaS; treat standalone bootstrap failure as a database-write recovery case |
| No failure handler once web/worker stop | Migration, static collection or deployment checks can leave web down | Complete preparation before stopping web; explicit failure recovery with database-write boundary |
| Stop errors reported as “not running” | Permission failures and unusable units can be mistaken for absence, allowing migration while writers still run | Require a usable active web unit, reject failed/masked worker states, and make stop failure fatal |
| Backup occurs while writers run; timers are not paused | Database, media and fingerprint need not describe the same instant; scans can write during migration | Pause active Vezano timers, drain their running jobs, stop writers, then back up |
| `ln -sfn` with only a directory existence check | No strict symlink contract or atomic replacement guarantee | Require a valid current symlink and rename a sibling symlink atomically with GNU `mv -T` |
| Post-upgrade `preflight` only | Checks application state, but does not prove that systemd serves the promoted release | Require service paths through current; verify web active state and HTTP health JSON after restart |
| Commands run as the invoking user | Root may pass writable-media checks that fail for `vezano`, or create root-owned collected assets | Run candidate management and venv preparation as the web service user |
| No deployment lock | Concurrent promotions can interleave | Nonblocking flock on a file alongside the current link |

The repository's [README](https://github.com/Stingcompiler/erp-plaform/blob/b37fcfd6/deploy/standalone/README.md)
explicitly says current features do not need Celery/Redis and that the worker
must not be enabled alongside the scheduled timers, which would duplicate scans.
The absence of `vezano-worker.service` is therefore a supported deployment
shape, not a reason to add Redis or Celery.

## Correct the earlier manifest diagnosis

The candidate test unit was transient and had already been stopped. Its empty
WorkingDirectory is consistent with the unit no longer being available. The
subsequent manifest check used an empty CANDIDATE_DIR, so its negative result
does not establish that the packaged candidate lacks a manifest.

Check the actual directory directly:

```bash
readlink -f /opt/vezano/current
systemctl show vezano-web.service \
  -p LoadState -p ActiveState -p User -p Group -p WorkingDirectory
if test -f /opt/vezano/releases/1.0.0-b37fcfd6-packaged/release-manifest.json; then
    printf 'candidate manifest: present\n'
else
    printf 'candidate manifest: missing\n'
fi
```

These outputs do not include unit environment values or command arguments.
The adapted script checks ExecStart and Environment privately and reports only
whether they match the supported configuration.

## Installed service assumptions

The repository web template uses:

```ini
User=vezano
Group=vezano
WorkingDirectory=/opt/vezano/current/backend
Environment=VEZANO_ENV_FILE=/etc/vezano/vezano.env
ExecStart=/opt/vezano/current/venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3 --timeout 120
```

The VPS's effective unit, including drop-ins, must follow the same current link
for BOTH working directory and executable. A unit pointing at
`/srv/apps/vezano-pro` or a fixed release does not switch code when the symlink
changes. Fix that unit in a separately reviewed change if preparation rejects
it. Restarting a service is required to load the new release; changing a
symlink alone does not change a running process. `daemon-reload` is needed
after unit edits, not after a symlink-only promotion.

The supported units use only VEZANO_ENV_FILE for application settings. Extra
Environment or EnvironmentFile overrides are rejected, because Django's file
parser preserves existing process variables and an operator shell could
otherwise validate a different database or mode from the live service.

The candidate's static root is release-local (`backend/staticfiles` in the
reviewed settings), so preparation does not overwrite the old release's static
files. Uploaded media must remain in the existing persistent shared media
directory. Candidate code, venv, static assets and the protected env file must
be readable by the service user; media must be writable by that user. Preparation
checks these through the application user, rather than treating root success
as sufficient.

## Apply and prepare before promotion

Integrate the supplied `vezano-upgrade.patch` into the VPS control checkout at
`/srv/apps/vezano-pro` after checking it applies to the reviewed revision. Keep
the previously tested release and its venv unchanged. The patch modifies the
control script and its documentation; it is not a live deployment command.

On that checkout, after integrating the patch:

```bash
sudo bash /srv/apps/vezano-pro/deploy/standalone/upgrade.sh \
  --release /opt/vezano/releases/1.0.0-b37fcfd6-packaged \
  --worker-service none \
  --require-no-migrations \
  --health-host pro.vezano.app \
  --prepare-only
```

Preparation validates unit layout, manifest, effective deployment mode,
deployment checks, migration state and preflight, collects candidate static
files, and verifies the current web endpoint. It does not stop services,
back up or promote. It can create a candidate venv and perform the preflight
media write probe; it is not a purely read-only operation.

Once preparation passes and the maintenance window is ready, invoke the same
command without `--prepare-only`. Keep the default backup enabled. The script
will ask before starting maintenance; `--yes` is available for an established
automated deployment pipeline.

The promotion pauses active scheduled timers, waits for current jobs, stops
web and any managed active worker, backs up, checks again for pending migrations,
skips applying migrations when none are pending, skips standalone bootstrap in
SaaS, atomically promotes, and restarts web. Success requires healthy JSON
(`status=ok`, `database=ok`, `deployment_mode=saas`) from the selected local
endpoint. It then restores originally active services/timers and runs preflight.

This is a maintenance-window upgrade, with interruption covering the backup
and restart. The successful parallel smoke test was not itself a zero-downtime
promotion mechanism. Confirm all other writers are stopped: cron jobs, Celery
beat, other hosts, and any candidate process sharing production settings.

After promotion, verify the public path through the reverse proxy and confirm
the link points to the packaged release. For privacy, check health without
printing the full response:

```bash
systemctl is-active vezano-web.service
readlink -f /opt/vezano/current
curl --fail --silent --show-error --max-time 10 \
  --output /dev/null https://pro.vezano.app/api/health/
```

## Recovery and acceptance limits

- For this SaaS candidate, an empty migration state means the workflow does
  not invoke write migrations or standalone bootstrap. A startup/health failure
  restores the previous link and originally active runtime state, then checks
  old web health. Failure to restore any component is explicitly reported.
- Once any migration or standalone bootstrap is attempted, database state may
  have changed even if the command fails. Managed writers are stopped on failure;
  recovery requires examining the matching backup and migration state. No
  automatic schema reversal or destructive database restore is attempted.
- No pending migrations establishes a schema condition, not universal
  compatibility of future business-data changes. Review downgrade compatibility
  for future versions. This particular candidate is reported to be a repackaging
  of the same application version and commit.
- A restore can discard writes after the backup; coordinate it explicitly and
  validate in isolation. Also review `rollback.sh` separately before relying on
  it for SaaS: this change is limited to upgrade orchestration.
- SIGKILL, host loss and failures to communicate with systemd cannot be repaired
  by a shell exit trap. The old release and backup remain essential recovery
  assets. Keep application ownership and service stop permissions correct.
- `verify_release` checks VERSION, migrations, the requirements lock and the
  frontend inventory. It does not itself verify a cryptographic signature or
  hash all backend source. Archive checksum/signature verification against a
  trusted source remains a separate gate. Do not regenerate a manifest just to
  silence a mismatch on an untrusted artifact.
- Backups contain database data, media and a copy of the protected environment
  file. The orchestrator uses umask 077. Keep backup folders protected and never
  share environment contents, DATABASE_URL, shell traces or unredacted unit
  arguments. This review did not read production secrets.

## Validation

The provided standard-library tests execute the actual shell control flow with
isolated systemctl, Django, backup and HTTP doubles. They cover SaaS without a
worker, standalone bootstrap, active/inactive worker state, timers, service
layout/settings checks, manifest/check/static/backup failures, concurrent-lock
rejection, migration-state changes during maintenance, HTTP failure and
database-aware recovery. They use real temporary symlinks and atomic rename;
GNU mv is represented by the equivalent operating-system rename on macOS.

Run locally:

```bash
python3 -m unittest discover -s deploy/tests -v
bash -n deploy/standalone/upgrade.sh
git diff --check
```

These tests validate orchestration, not actual Linux systemd, PostgreSQL backup
restorability, archive provenance or VPS deployment. Run `--prepare-only` and
perform the real-host acceptance checks before scheduling promotion.

Operational references:
[Django migration command](https://docs.djangoproject.com/en/5.2/ref/django-admin/#migrate),
[systemd state model](https://wiki.freedesktop.org/www/Software/systemd/dbus/).
