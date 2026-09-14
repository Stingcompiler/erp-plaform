# Standalone licence — commercial terms and how the software enforces them

This is the vendor's working definition of what a standalone customer buys,
written so that the contract, the licence file and the software say the same
thing. It is not legal advice; have counsel turn it into the signed agreement
for each jurisdiction. Every term below maps to a field the software actually
reads (`issue_license` flags in brackets).

## 1. What is licensed

The right to run one installation of Vezano — identified by its
**installation ID** — on infrastructure the customer controls, for the
organisation named in the licence [`--organisation`], with the modules
[`--modules`] and capacity limits [`--limit users=N --limit branches=N`]
stated in the licence file.

- One licence = one installation ID. A licence file is refused on any other
  installation. Restoring a backup or moving the server with a backup keeps
  the ID; a fresh install gets a new ID and needs a reissued licence, which
  maintenance covers free of charge.
- The customer owns their data without qualification. Nothing in the
  software sends data to the vendor, and no licence state deletes or hides
  data.

## 2. Two commercial models

### 2.1 Perpetual + annual maintenance (default offer)

| Term | Licence field | Runtime effect |
|---|---|---|
| Perpetual right to run | `--kind perpetual` | never expires |
| Maintenance period (upgrades + support) | `--maintenance-until YYYY-MM-DD` | informational; `preflight` warns after it passes |
| Highest release covered | `--max-version X.Y.Z` | a release above it puts the installation in `version_not_covered` (read-only) until renewal or rollback |

Pricing shape: a one-time licence fee plus an annual maintenance fee (a
percentage of the licence fee). Renewal extends `maintenance_until` and
raises `max-version`; the customer receives a new licence file. If
maintenance lapses the customer keeps running the releases they have, for
ever, with full write access. Rejoining maintenance later may carry a
catch-up fee — a contract term, not a software one.

### 2.2 Fixed term (subscription-like, self-hosted)

| Term | Licence field | Runtime effect |
|---|---|---|
| Last usable day | `--kind term --usable-until YYYY-MM-DD` | `active` until that day |
| Grace period | `--grace-days N` (offer 14) | `grace`: full use, renewal banner shown |
| After grace | — | `read_only`: reads, reports and exports work; no new writes |

Renewal = a new licence file with later dates; import restores `active`
immediately. Term licences always include a grace period (see
`SHIP_CHECKLIST.md` §E).

## 3. The states, in contract language

| State | Customer can | Customer cannot | Exit |
|---|---|---|---|
| `active` | everything | — | — |
| `grace` | everything | — (banner only) | renew, or wait for read-only |
| `read_only` | sign in, read, report, export (GET), back up on the server with `backup.sh` | create or change records — any non-read request, including the in-app backup button | import a renewed licence |
| `version_not_covered` | as read-only | as read-only | renew maintenance, or roll back to a covered release |
| `unlicensed` | as read-only | as read-only | import a licence |

**No data loss clause.** In every state the database, media and backups are
intact and exportable; the software never removes access to existing data
because of the licence. This is a promise the vendor can make because the
code enforces exactly this (`licensing/services.py`), and it is the sentence
that makes a self-hosted licence acceptable to a customer's auditors.

## 4. Capacity limits

`users` counts active user accounts; `branches` counts active branches.
Reaching a limit blocks creating the next one and nothing else. Raising a
limit is a reissued licence file (same ID); it is a paper change, no
downtime.

## 5. What maintenance includes

- All releases up to `max-version`, delivered as signed archives.
- Reissued licence files for the same organisation (new installation ID after
  a reinstall or migration, raised limits, corrected name).
- Support for the customer's engineer on install, upgrade, backup, restore
  and rollback as documented in `OPERATIONS.md`.

What it does not include: operating the server, taking the customer's
backups, custom development, or data recovery from a host that never ran
`backup.sh`.

## 6. Customer obligations that the software relies on

- Keep `/etc/vezano/vezano.env`, the licence public keys and the licence
  file confidential to the operating team.
- Take and test backups (`backup.sh` / `restore.sh`); the vendor holds no
  copy of customer data.
- Do not alter the release tree; `verify_release` and the signed manifest
  detect it, and support is void for a tree that fails verification.
- Do not run a release above `max-version` outside a renewed licence.

## 7. Transfer, termination, verification

- Transfer to another legal entity = a new licence for the same installation
  ID with the new organisation name; the vendor's consent is a contract term.
- Termination by the customer: they keep their data; the perpetual licence
  survives, maintenance stops. Termination for breach: no remote action
  exists; the remedy is contractual.
- The vendor can verify a licence claim only from what the customer sends
  (licence page screenshot or `/api/license/` output); there is no telemetry.

## 8. Migration paths

Between hosted and standalone, in either direction, via
`export_company` / `import_company` (`OPERATIONS.md`, last section). The
standalone licence and the hosted subscription are separate purchases; the
contract states which one is active after a move.
