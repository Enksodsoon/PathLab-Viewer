# SQLite to PostgreSQL

The current SQLite store remains authoritative until one rehearsed maintenance cutover. Long-lived dual write is prohibited.

## Rehearsal

1. Copy a verified SQLite backup and authoritative object manifests into an isolated migration environment.
2. Inventory every source table, column, row count, null pattern, enum value, large-byte field, timestamp convention, identifier, and external object relationship.
3. Define a deterministic source-to-context mapping. Preserve stable identifiers where valid; otherwise record a signed old-to-new mapping. Email and external subject values become mappings, never identity keys.
4. Use PostgreSQL `BIGINT` for byte sizes and counters that can exceed two GB, explicit UTC timestamps, Institution-scoped uniqueness, per-context migrations, and no cross-context foreign keys.
5. Import into empty context databases and verify row counts, canonical row hashes, mapping totals, referential projections, object hashes, ownership, retention state, audit origins, and every representative end-to-end workflow.
6. Repeat until two clean rehearsals from the same source snapshot produce identical manifests and no unexplained differences.

## Cutover

1. Enter a maintenance Mode Reservation, reject new writes, drain workers, reconcile jobs and outboxes, and issue a cutover NO-GO or READY receipt.
2. Create and acknowledge fresh SQLite, object, key, and infrastructure backups; record the source database and object-manifest hashes.
3. Run the pinned exporter, transformer, context migrations, importers, validators, and synthetic workflows from the Offline Release Kit.
4. Keep the original SQLite files immutable and inaccessible to applications, atomically switch configuration to PostgreSQL/PgBouncer, and start the candidate release.
5. Before the first PostgreSQL write, a failed gate may switch back to the untouched SQLite authority. The exact PostgreSQL commit that accepts the first write permanently closes that rollback path and is recorded in the Audit Integrity Chain.
6. After authority moves, recovery uses PostgreSQL backups, outboxes, import evidence, and forward repair; SQLite is evidence only and expires with its 35-day Backup Generation.

Cutover is incomplete until all context counts and hashes, object references, sessions, permissions, viewer routes, annotations, Classroom history, Study data, Desktop pairings, and current production features pass on the active PostgreSQL release.
