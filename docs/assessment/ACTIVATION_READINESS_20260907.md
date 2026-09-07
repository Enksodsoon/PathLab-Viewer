# Teaching Studio activation readiness, 2026-09-07

Status: **NOT_EVALUABLE** for full production Assessment activation.

The successful production release `37e35f14383b04111e2b8dbb4a453754169ca12a`
contains Teaching Studio code. Its live capability is disabled, so the library
does not expose the Assessment navigation entry. Release success is not Studio
activation.

## Verified prerequisites and gaps

- Live runtime inspection confirms SQLite and six services: API, Caddy,
  Classroom, tile service, upload service, and worker. Assessment is absent.
- Production Assessment configuration requires PostgreSQL and identity
  governance. The guarded deployment workflow currently has no Assessment
  input, and its expected service inventory omits Assessment.
- The current PostgreSQL Compose overlay limits connections to 20, whereas
  the existing Assessment campaign requires at least 32. This discrepancy
  needs a reviewed resource configuration and measurement, not a lowered gate.
- The `assessment-capacity` GitHub environment has now been created with the
  production reviewer and protected-branch restriction. Its six required
  qualification secrets are not configured. No certification runs exist.
- No protected qualification target or host telemetry endpoint has been
  established by this work. The boot filesystem has roughly 11 GB available;
  the separate application data volume has roughly 125 GB available and 15 GB
  used. Initial inspection of the parent directory understated available data
  storage. Same-host staging is feasible within the existing volume, subject
  to the [zero-cost staging plan](ZERO_COST_STAGING_PLAN.md). These measurements
  are time-specific.
- Two isolated PostgreSQL migration rehearsals from one immutable SQLite
  snapshot matched across 68 tables on release `37e35f14383b04111e2b8dbb4a453754169ca12a`.
  Both manifest signatures verified. A disposable PostgreSQL dump restore
  matched all 68 tables and foreign-key evidence using a read-only verification
  transaction. This does not qualify object restoration or production cutover.
- An isolated OCI browser smoke verified administrator login, Teaching Studio
  navigation, draft persistence after reload, publication, opening responses,
  anonymous learner submission (1/1), and closing responses. The teacher report
  incorrectly showed zero scores when anonymous individual rows were absent;
  the candidate now displays retained aggregate points without inventing
  unavailable percentages or learner distributions. This correction still
  requires verification in the candidate OCI release.
- The staging services have been stopped after the smoke; their private
  database and rehearsal evidence are retained on the existing data volume.
  Production remains unchanged. Static-DZI delivery, complete object restore,
  protected 500-seat campaign, and staged 30/100/300-user pilots are outstanding.

## Qualification harness repairs

The observer now rejects missing, non-finite, negative, and wrong-release host
telemetry, and scopes application session credentials separately from the host
observer token. Evidence closure checks the observer release and required
telemetry before reporting success. A workflow preflight rejects missing
configuration before fixture creation. Focused local tests exercise these
failures; they are not a capacity campaign.

## Remaining activation sequence

1. Establish an approved isolated target with sufficient storage for the
   source, PostgreSQL migration, backup, and disposable restore; bind its host
   observer to the exact deployed release and measured counters.
2. Reconcile the PostgreSQL resource configuration and production deployment,
   health, backup, rollback, and runtime-inventory support for Assessment.
3. Configure the protected environment credentials, prove migration and
   restore reconciliation, and run the campaign and staged pilots from the
   [operations runbook](RUNBOOK.md). Retain unsuccessful results honestly.
4. Activate only after the required evidence passes, then verify authenticated
   Teaching Studio authoring, learner delivery, recovery, and reporting on OCI.

The user has requested full qualification and activation. This record does not
claim qualification, change the live database engine, or activate Assessment.
