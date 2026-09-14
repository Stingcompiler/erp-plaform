# Ship / never-ship checklist — standalone release and licence

Vendor side. Every line is a gate; one unchecked line means the release or
the licence does not leave the building. Keep the completed copy with the
acceptance record for that version.

## A. Before cutting a release

- [ ] `main` is green on all three CI legs (SQLite, PostgreSQL, frontend).
- [ ] `VERSION` bumped; `CHANGELOG`/release notes name every migration in the release.
- [ ] `frontend/out` was rebuilt from this exact source (`npm ci && npm run build`) and committed.
- [ ] `manage.py makemigrations --check` is clean.
- [ ] The runbook in `OPERATIONS.md` was executed for this version on a clean
      PostgreSQL 16 host **including** `upgrade.sh` from the previous shipped
      version and `rollback.sh` back to it. The acceptance table is updated.
- [ ] Any change to `deploy/standalone/*.sh`, the unit files or
      `vezano.env.example` was exercised in that run, not only read.

## B. Cutting and signing

- [ ] Built with `package_release.sh --signing-key <release key>`; the script's
      archive audit passed (it fails the build on `.env`, keys, databases,
      media, caches, `.claude/`, `.github/`).
- [ ] `sha256sum -c` and `openssl dgst -verify` pass on the produced files, on
      a machine other than the build machine.
- [ ] The release signing private key never left the secrets manager; the
      public key shipped beside the archive is the one customers already hold.
- [ ] The archive was opened and spot-checked: no `backend/.env`, no `*.pem`,
      no `*.sqlite3`, no `node_modules`, `VERSION` matches the file name.

## C. Never ship

- A release whose `check --deploy` shows errors (warnings are reviewed, errors block).
- A release whose `preflight` fails on the acceptance host.
- An unsigned archive, or one signed with a key customers do not have.
- A release that changes `VEZANO_DEPLOYMENT_MODE` semantics, the
  `Installation` identity, or licence verification without a matching
  migration and an upgrade test from the previous version.
- A developer environment file, a database file, media, a private key, or a
  virtual environment inside the archive — in any form.
- A default or documented password. Owners are created with `create_owner`
  on the customer host with a password we never see.

## D. Issuing a licence

- [ ] The installation ID came from the customer's *Subscription & licence*
      page (or `bootstrap_standalone` output), not typed from memory.
- [ ] `--organisation` is the legal name on the contract.
- [ ] Kind, dates, `--max-version`, modules and limits match the signed contract
      (see `LICENCE_TERMS.md`): perpetual + `maintenance_until` + `max-version`,
      or term + `usable_until` + `grace_days`.
- [ ] Signed with the current key id; the customer's `license-keys/` holds that public key.
- [ ] The JSON was imported on a scratch install with the same key to confirm
      it activates, before it is sent.
- [ ] The licence file, its parameters and the installation ID are recorded in
      the customer record (needed for reissue and renewal).

## E. Never issue

- A licence for an installation ID you cannot trace to a customer record.
- A licence with `--max-version` above the release you are able to support.
- A term licence without a grace period (customers lose write access at
  midnight with no warning window).
- A licence signed with a rotated-out key that customers no longer trust.

## F. After delivery

- [ ] Customer confirmed *active* on the licence page and `preflight` passed on their host.
- [ ] Customer confirmed a backup was taken **and restored** once (`restore.sh`).
- [ ] Renewal date and `max-version` ceiling are in the renewals calendar 60 days ahead.
