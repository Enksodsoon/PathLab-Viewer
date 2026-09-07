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
- The PostgreSQL cutover rehearsal, exact-release restore evidence, 500-seat
  campaign, and staged 30/100/300-user pilots remain outstanding.

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
