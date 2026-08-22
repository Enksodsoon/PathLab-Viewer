# PostgreSQL runtime cutover

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

## Current slice

This slice adds the process roles, bounded database settings, PostgreSQL job-claim isolation, PostgreSQL upload-expiry compatibility, and an explicit PostgreSQL Compose overlay for isolated staging. The existing production Compose invocation is unchanged. This slice does not migrate production data, change backup selection, deploy a release, or activate a feature.

## Required next slice

The next cutover slice must add PostgreSQL backup selection, a verified SQLite-to-PostgreSQL migration manifest, disposable restore evidence, and Classroom coexistence tests. It must remain staging-only until that evidence is green.
