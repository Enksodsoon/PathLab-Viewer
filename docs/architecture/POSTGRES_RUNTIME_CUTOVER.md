# PostgreSQL runtime cutover

> **Status: legacy baseline and migration input only.** This pre-ratification Compose-era document records earlier fixed-pool, selector, `pg_dump`, and staging evidence behavior; it is not the Full-Surface production runtime or cutover authority. The controlling contracts are [Final Production Endpoint](./FINAL_PRODUCTION_ENDPOINT.md), [Zero-Cash Runtime](./ZERO_CASH_RUNTIME.md), [SQLite to PostgreSQL](./SQLITE_TO_POSTGRESQL.md), accepted ADRs [0034](../adr/0034-use-one-postgresql-cluster-with-context-owned-namespaces.md), [0035](../adr/0035-use-one-logical-database-per-bounded-context.md), [0036](../adr/0036-cap-postgresql-at-48-backends.md), [0059](../adr/0059-use-opentofu-and-native-systemd-as-production-authorities.md), and [0082](../adr/0082-cut-sqlite-over-once-without-dual-write.md), plus the current [Phase 1 execution cards](../execution/PHASE_1_RESIDENT_FOUNDATION.md). Those controllers win on every conflict. Nothing below authorizes Compose as production authority, a single logical database, fixed legacy pool allocations, or `pg_dump` as the production durability/rollback mechanism.

This phase prepares PathLab for PostgreSQL as the authoritative deployment database without changing or activating the current production topology.

## Runtime contract

- General API: pool 5, no overflow, 5 second statement timeout.
- Classroom API: pool 4, no overflow, 2 second statement timeout, 250 ms lock timeout.
- Worker: pool 2, no overflow, 30 second statement timeout.
- Tile process: pool 1, no overflow, 5 second statement timeout.
- Every role uses a 1 second pool checkout timeout.
- Worker claims use `FOR UPDATE SKIP LOCKED` on PostgreSQL.
- SQLite-only `BEGIN IMMEDIATE` is never issued on PostgreSQL.
- Image processing and other external I/O remain outside job-claim transactions.

## Deployment selector

`PATHLAB_DATABASE_ENGINE` accepts only `sqlite` or `postgres` and defaults to
`sqlite`. `deploy/scripts/compose-pathlab.sh` is the sole host-side Compose
selector used by systemd and the release workflow. PostgreSQL adds the pinned
overlay; an unknown value fails before Docker is called.

Ordinary deployments preserve the current engine. They refuse to change from
SQLite to PostgreSQL or back. Engine cutover remains a separate, explicit,
staging-first operation.

The release workflow now selects the matching backup and disposable restore
drill. PostgreSQL backups are signed, bind the release and schema revision, and
use `pg_dump` custom format. If a candidate release fails, PostgreSQL rollback
renames and preserves the failed database, restores the verified dump into the
original database name, and returns to the previous release. A restore failure
renames the preserved database back and fails closed.

The protected PostgreSQL suite holds 300 synthetic Classroom SSE streams open
simultaneously, verifies background and isolated jobs stay blocked, verifies the
Classroom pool is bounded at four, and verifies no connection remains checked
out after any stream yield. This is isolated synthetic evidence, not production
capacity certification.

## Staging cutover evidence workflow

`deploy/scripts/verify-postgres-cutover.sh` composes the existing proofs into one fail-closed Linux staging workflow. It refuses non-staging execution and password-bearing target URLs, verifies that the immutable SQLite source has no running worker, active Classroom, or non-idle Classroom guard, performs the signed row/key/hash migration, checks the migrated target, creates a signed PostgreSQL/private-file backup, restores it into a disposable database, and writes a compact atomic `status.json`.

Protected PostgreSQL CI runs this workflow with a synthetic SQLite source, a separate synthetic target database, file-mounted credentials, and non-PHI file fixtures. This evidence remains staging-only and does not select PostgreSQL for the existing production deployment.

## Production boundary

The merged selector does not change the production `.env`, migrate production
data, enable Classroom, or activate Classroom protection. Production remains on
its current engine until a separately reviewed cutover run supplies a verified
source manifest, signed backup, restore drill, exact release SHA, and explicit
production approval.
