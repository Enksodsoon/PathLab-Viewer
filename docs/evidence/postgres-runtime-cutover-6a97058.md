# PostgreSQL runtime cutover evidence

- Implementation SHA: `6a97058cc8cbfe27bedb9ff039908199f4496aeb`
- Protected workflow: `32551830132`
- PostgreSQL job: `96979734198`
- Evidence date: 2026-08-22
- Evidence state: `SYNTHETICALLY_VERIFIED`

The protected Linux PostgreSQL job passed the PostgreSQL foundation and
SQLite-to-PostgreSQL migration suites, held 300 synthetic Classroom SSE streams
open while background and isolated jobs remained blocked, verified that no
Classroom database connection survived a stream yield, created a signed
PostgreSQL custom-format backup, and restored it into a disposable database.

The same job completed the staging-only cutover evidence workflow with a
synthetic SQLite source, non-PHI file fixtures, an exact release SHA, a
file-mounted credential, deterministic table/key/content verification, and a
terminal `SUCCEEDED` status.

Workflow evidence:
https://github.com/Enksodsoon/PathLab-Viewer/actions/runs/32551830132

## Claim restrictions

- This is isolated synthetic engineering evidence, not production capacity
  certification.
- It does not prove external-network latency, physical-device behavior, a
  real-user pilot, or production readiness.
- The production database was not migrated or switched.
- Classroom and Classroom protection were not activated in production.
- Ordinary release deployments refuse database-engine changes; production
  cutover requires a separate reviewed migration and explicit approval.
