# SQLite to PostgreSQL migration contract

> **Status: legacy single-database migration implementation input only.** This document records a pre-ratification staging command and HMAC manifest; it is not the current production authority-cutover or per-context migration contract. [Final Production Endpoint](./FINAL_PRODUCTION_ENDPOINT.md), [SQLite to PostgreSQL](./SQLITE_TO_POSTGRESQL.md), accepted ADRs [0034](../adr/0034-use-one-postgresql-cluster-with-context-owned-namespaces.md), [0035](../adr/0035-use-one-logical-database-per-bounded-context.md), [0036](../adr/0036-cap-postgresql-at-48-backends.md), and [0082](../adr/0082-cut-sqlite-over-once-without-dual-write.md), and the current [Phase 1 migration/cutover cards](../execution/PHASE_1_RESIDENT_FOUNDATION.md) control all conflicts. The single-target-database assumptions, HMAC-only evidence, `PATHLAB_SECRET_KEY`, and “Program 0B” wording below do not authorize or define the ratified production cutover.

This command is a one-way staging migration. It does not modify or delete the
SQLite source and it is not a production migration certificate.

## Preconditions

- Stop every API, worker, Classroom, and maintenance process that can write SQLite.
- Checkpoint and close SQLite. The command rejects `-wal` and `-shm` sidecars.
- Use an empty or previously partially migrated PostgreSQL database dedicated to
  this migration attempt.
- Set `PATHLAB_SECRET_KEY` to a private value of at least 32 bytes. It signs the
  private verification manifest.
- Set `PATHLAB_RELEASE_SHA` to the exact 40-character release SHA when running
  outside a Git checkout.
- Keep the SQLite file and generated manifest private; primary-key sets are
  evidence and may contain internal identifiers.

## Command

```text
pathlab-admin migrate-sqlite-to-postgres \
  --source <pathlab.sqlite3> \
  --target <postgresql+psycopg-url> \
  --manifest <private-manifest.json> \
  --verify
```

`--verify` is mandatory. The command upgrades the target schema to the current
Alembic head, requires the source and target revisions and table sets to match,
and copies tables in foreign-key order. Batches use primary-key conflict handling
and compare any existing target row byte-for-byte after canonical normalization.
An interrupted run can be repeated: matching rows are accepted and conflicting
rows fail closed. A PostgreSQL advisory lock prevents two migration commands from
copying concurrently.

## Evidence and failure rules

The HMAC-signed manifest contains the exact release SHA, schema revision, source
file hash before and after, per-table counts, complete primary-key sets,
deterministic source and target content hashes, and target foreign-key results.
The target password is not written to the manifest.

No manifest is written when verification fails. Earlier verified batches can
remain in PostgreSQL so a run can resume, but PostgreSQL is not authoritative
until the complete manifest is generated and independently retained with the
immutable SQLite source. Backup/restore replacement and runtime cutover are
separate Program 0B gates.
