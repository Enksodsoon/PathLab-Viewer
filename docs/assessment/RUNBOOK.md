# Assessment operations runbook

Assessment remains disabled in production. Activation requires PostgreSQL and identity governance, an exact-release backup/restore reconciliation, successful static-DZI preflight, a protected 500-seat certification, staged 30/100/300 pilots, and explicit approval.

Current evidence state: `NOT_EVALUABLE`. The protected workflow and evidence schema are implementation artifacts only; no 500-seat campaign or production activation is claimed.

The dedicated service uses the optional Compose profile `assessment`. Production keeps that profile absent and `PATHLAB_ASSESSMENT_ENABLED=false` until activation; Caddy rejects both Assessment API and asset paths in that state. For an isolated qualification target, set `PATHLAB_DATABASE_ENGINE=postgres`, `PATHLAB_ASSESSMENT_ENABLED=true`, and `PATHLAB_IDENTITY_GOVERNANCE_ENABLED=true` in its private Compose environment. `deploy/scripts/compose-pathlab.sh` selects the Assessment profile and PostgreSQL overlay together, including the 32-connection Assessment configuration. It rejects enabled Assessment without both prerequisites. Guarded releases can preserve and verify the eighth service in an already activated deployment. These settings prepare a qualification target; they do not establish capacity or activate production.

## Prepare and open

Before database cutover or release maintenance, verify that systemd's effective
`ExecStart`, `ExecReload`, and `ExecStop` use `compose-pathlab.sh`. The preflight
command `python3 deploy/scripts/runtime_safety_manifest.py verify-service-manager`
rejects an older unit that invokes base `docker compose` directly: that unit
omits the PostgreSQL overlay and can remove its container as an orphan. Install
the reviewed `deploy/pathlab-viewer.service` into `/etc/systemd/system/` and run
`systemctl daemon-reload` before retrying. Preserve the PostgreSQL volume and
authority receipt during recovery; do not switch back to SQLite.

Confirm one Alembic head and `/readyz`, verify every selected slide is privacy-passed `static_dzi`, create administration-scoped hardlink grants, prewarm the declared DZI levels, drain upload/conversion/background work, and confirm Classroom is idle. Only one Formative or Quiz/Test administration may be preparing or open.

## Monitor and close

Poll count-only monitoring at 15 seconds. Do not expose live answers. Watch API p95, database connections, pool/lock timeouts, tile p95, CPU, memory, swap, restarts, and OOM events. Closing begins a 120-second cooldown before background work or another recorded administration resumes.

PostgreSQL pools now count actual connection checkout timeouts and PostgreSQL
`55P03` lock pressure, including unavailable NOWAIT locks. The internal
`/api/v1/internal/capacity/pressure` endpoint requires a dedicated
`PATHLAB_CAPACITY_OBSERVER_TOKEN` of at least 32 characters in
`X-PathLab-Observer-Token`; it is disabled without that token and denied by the
public Caddy internal-route rule. It returns no SQL, parameters, answers, or user
identifiers. Its counters belong to one pool generation in one process. An
observer must collect both Assessment worker generations and reject replacement
or missing generations during a campaign; a single response is not a two-worker
measurement. SQLite returns `PRESSURE_NOT_MEASURED`, rather than invented zeros.
This endpoint alone is not the host observer or capacity certification.

## Retention and recovery

Legal or academic hold blocks purge. Purge runs in bounded batches, removes participant/session/attempt/response/score/gradebook data and static grants, preserves approved aggregate snapshots, and reconciles after restore. Missing grants, schema mismatch, SQLite production configuration, or disabled identity governance must fail readiness closed.

## Evidence closure

Use `SUCCESS` only when every exact-release functional, resource, recovery, export, and cleanup gate passes. Use `PARTIAL` for a completed but incomplete campaign, `NEGATIVE` for a failed gate, and `NOT_EVALUABLE` when prerequisites or trustworthy evidence are absent. Workflow existence is not certification.

## Protected workflow prerequisites

The `assessment-capacity` GitHub environment requires explicit reviewer approval and these secrets:

- `ASSESSMENT_CAPACITY_BASE_URL`: protected HTTPS origin running the requested release.
- `ASSESSMENT_CAPACITY_ACCESS_CODE`: single-use synthetic fixture code; never print or retain it.
- `ASSESSMENT_ADMIN_COOKIE` and `ASSESSMENT_ADMIN_CSRF`: bounded synthetic-fixture administrator session.
- `ASSESSMENT_HOST_OBSERVER_URL` and `ASSESSMENT_OBSERVER_TOKEN`: read-only observer returning exact `releaseSha`, PostgreSQL engine/max/current connections, pool/lock timeouts, two-worker health, restarts, OOM kills, CPU, memory, and swap.

Dispatch `.github/workflows/assessment-capacity.yml` with the exact deployed 40-character SHA and a privacy-passed real `static_dzi` slide ID. The workflow verifies the deployed SHA through the protected observer before it creates data. It provisions a 500-entry class, immutable Formative publication, roster snapshot, and administration-scoped real-DZI hardlinks; a second isolated one-seat administration is created only after the capacity fixture is closed and removed for the browser recovery canary.

The five k6 jobs wait at one shared barrier and each execute exactly 100 single-iteration seats. The observer samples every 15 seconds and stops after three consecutive failures. Cleanup runs with `if: always()`, closes the administration, verifies exactly 500 responses and every learner/question pair in the CSV export (two question rows per learner), purges in batches of 100, removes grants/sessions/participants and the isolated class/draft/learner fixtures, then repeats cleanup for the browser canary. Any missing artifact closes as `NOT_EVALUABLE`; any observed gate failure closes as `NEGATIVE`.

The provisioning job transfers only the validated tile path between jobs. Each
protected consumer reconstructs the URL from its origin secret. Passing the full
URL as a job output causes GitHub to suppress it because it contains that secret;
the load clients must reject missing paths before starting. Do not weaken secret
masking or expose the protected origin to work around this boundary.

The fixture resolves the DZI descriptor into a full-resolution center JPEG tile
and verifies image bytes before admitting the campaign. The shards and observer
measure that image URL, not `slide.dzi` metadata. An HTML success response or
descriptor response must not count as successful image delivery.

## Backup and restore reconciliation

Before any pilot, capture a PostgreSQL backup and the exact release/configuration manifest. Restore into an isolated target, run Alembic to the recorded single head, verify `/readyz`, reconcile every closed Assessment aggregate, and compare administration counts, aggregate versions, gradebook latest-score pointers, retention/hold settings, and grant manifests. Open administrations with missing or malformed grants must keep readiness failed. A restore test is evidence only for the exact backup, release, and target recorded in the artifact.

PostgreSQL backups include the `delivery` tree when present, preserving hardlinks
between source derivatives and assessment grants. The disposable restore drill
extracts authenticated file archives into an empty directory on the data volume,
checks file bytes and hardlink identity, and reports `filesIntegrity=restored`
alongside the database result. Older three-root backups remain readable, but do
not prove restoration of assessment grants. The `restore-files` manifest command
accepts only an empty isolated destination; it never replaces live directories.
Database/asset reconciliation and production cutover remain separate from this
file-level restore check. PostgreSQL rollback stops the optional Assessment
service before replacing the database.

## Staged rollout

After a successful protected 500-seat synthetic campaign and separately approved restore evidence, run distinct 30-, 100-, and 300-user pilots. Record release SHA, PostgreSQL target, static-DZI assets, latency/resource gates, recovery, aggregate/export checks, cleanup, user/accessibility findings, and an explicit decision at each stage. Do not infer the next state from local checks, workflow presence, or an earlier release. Production activation still requires a separate approval that changes the production flag; this runbook never changes it.

## Incident and privacy response

Close the administration first; do not inspect or export live answers to diagnose capacity. Preserve count-only monitor, service, host, database, Caddy, and exact-release evidence. Revoke synthetic/admin sessions and remove hardlink grants. Do not collect pointer paths, pan/zoom history, screenshots, keystrokes, fingerprints, raw access codes, or raw login identifiers. Assessment recovery must not restart or activate Study Coach/TRACE-SIM.
