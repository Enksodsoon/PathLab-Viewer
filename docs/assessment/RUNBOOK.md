# Assessment operations runbook

Assessment remains disabled in production. Activation requires PostgreSQL and identity governance, an exact-release backup/restore reconciliation, successful static-DZI preflight, a protected 500-seat certification, staged 30/100/300 pilots, and explicit approval.

Current evidence state: `NOT_EVALUABLE`. The protected workflow and evidence schema are implementation artifacts only; no 500-seat campaign or production activation is claimed.

## Prepare and open

Confirm one Alembic head and `/readyz`, verify every selected slide is privacy-passed `static_dzi`, create administration-scoped hardlink grants, prewarm the declared DZI levels, drain upload/conversion/background work, and confirm Classroom is idle. Only one Formative or Quiz/Test administration may be preparing or open.

## Monitor and close

Poll count-only monitoring at 15 seconds. Do not expose live answers. Watch API p95, database connections, pool/lock timeouts, tile p95, CPU, memory, swap, restarts, and OOM events. Closing begins a 120-second cooldown before background work or another recorded administration resumes.

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

The five k6 jobs wait at one shared barrier and each execute exactly 100 single-iteration seats. The observer samples every 15 seconds and stops after three consecutive failures. Cleanup runs with `if: always()`, closes the administration, verifies exactly 500 aggregate/CSV rows, purges in batches of 100, removes grants/sessions/participants and the isolated class/draft/learner fixtures, then repeats cleanup for the browser canary. Any missing artifact closes as `NOT_EVALUABLE`; any observed gate failure closes as `NEGATIVE`.

## Backup and restore reconciliation

Before any pilot, capture a PostgreSQL backup and the exact release/configuration manifest. Restore into an isolated target, run Alembic to the recorded single head, verify `/readyz`, reconcile every closed Assessment aggregate, and compare administration counts, aggregate versions, gradebook latest-score pointers, retention/hold settings, and grant manifests. Open administrations with missing or malformed grants must keep readiness failed. A restore test is evidence only for the exact backup, release, and target recorded in the artifact.

## Staged rollout

After a successful protected 500-seat synthetic campaign and separately approved restore evidence, run distinct 30-, 100-, and 300-user pilots. Record release SHA, PostgreSQL target, static-DZI assets, latency/resource gates, recovery, aggregate/export checks, cleanup, user/accessibility findings, and an explicit decision at each stage. Do not infer the next state from local checks, workflow presence, or an earlier release. Production activation still requires a separate approval that changes the production flag; this runbook never changes it.

## Incident and privacy response

Close the administration first; do not inspect or export live answers to diagnose capacity. Preserve count-only monitor, service, host, database, Caddy, and exact-release evidence. Revoke synthetic/admin sessions and remove hardlink grants. Do not collect pointer paths, pan/zoom history, screenshots, keystrokes, fingerprints, raw access codes, or raw login identifiers. Assessment recovery must not restart or activate Study Coach/TRACE-SIM.
