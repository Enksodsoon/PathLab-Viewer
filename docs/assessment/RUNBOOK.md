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
