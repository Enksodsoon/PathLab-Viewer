# Storage byte counter migration 0037

Revision `20260907_0037` follows the single `20260905_0036` merge head. It widens
`slides.source_bytes`, `slides.reserved_bytes`, `slides.derivative_bytes`,
`desktop_ingests.package_length`, `desktop_ingests.received_bytes`, and
`desktop_ingests.derivative_bytes` to PostgreSQL `BIGINT`. Supported uploads and
conversion reservations already exceed PostgreSQL's signed 32-bit integer range.
This change does not raise upload limits, storage caps, or feature defaults.

SQLite keeps its existing `INTEGER` declarations, which already store signed
64-bit values. The models use matching SQLite type variants. No SQLite parent
table is rebuilt, preserving dependent rows, indexes, and foreign keys.
Existing result delivery lengths and managed result attachment bytes are already
`BIGINT`; pixel dimensions and bounded file counts remain unchanged.

## Upgrade and rollback

Take the normal verified database backup, stop writers, and run
`alembic upgrade head` against the intended database. PostgreSQL's column type
change obtains table locks and may rewrite data and indexes; allow a maintenance
window appropriate to the actual database size. The application readiness
contract requires revision 0037 and actual PostgreSQL bigint column types.

For rollback, stop writers before running `alembic downgrade 20260905_0036`.
The migration locks both PostgreSQL tables before checking all six columns.
If any PostgreSQL value is below `-2147483648` or above `2147483647`, rollback
fails before narrowing any column.
The migration does not clamp, truncate, or delete data. Keep the upgraded schema
and application while deciding how to handle those rows, or restore the verified
pre-upgrade backup using the normal restore procedure. Never force-stamp an older
revision over out-of-range data. A successful downgrade preserves fitting values
and dependent rows.

SQLite downgrade is a no-op apart from Alembic's revision marker: revision 0036
already uses the same signed 64-bit INTEGER columns. Multi-GiB values, dependent
rows, indexes, and foreign keys remain intact through upgrade and downgrade.
No PostgreSQL int32 range restriction applies to SQLite rollback.

## Admission scope

New slide and failed slide retry reservations acquire the same database
transaction advisory lock (`lock_admission(..., "storage")`) before reading
the application-wide quota. Commit and rollback release it. SQLite retains
`BEGIN IMMEDIATE`. Read-only capacity snapshots and storage reconciliation keep
their existing behavior. PostgreSQL's configured lock and statement timeouts
remain in force; a timeout aborts an admission instead of reserving against a
stale total.

Desktop prepared and OME ingest routes currently check filesystem usage and
create desktop ingest records before creating slides during finalization. Their
separate admission lifecycle does not use this slide reservation boundary.
This migration repairs their byte storage types; it does not establish a shared
desktop ingest quota reservation contract. That lifecycle requires separate
verification before claiming cross-ingress quota atomicity.

## Bounded verification

`tests/backend/test_postgres_storage.py` runs against SQLite and isolated UUID
PostgreSQL schemas when `PATHLAB_POSTGRES_TEST_URL` is set. It checks multi-GiB
metadata round trips, migration preservation and guarded rollback, false-stamp
readiness rejection, competing new/retry reservations, cancellation rollback,
and successful reservation release. No multi-GiB payload is allocated. The
module is explicitly registered in the PostgreSQL CI job.
