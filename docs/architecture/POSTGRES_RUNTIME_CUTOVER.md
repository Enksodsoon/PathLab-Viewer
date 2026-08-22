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

## Remaining cutover gate

After this evidence slice, the remaining gate is PostgreSQL backup selection in the deployment workflow plus isolated Classroom coexistence and connection-leak testing. It must remain staging-only until that evidence is green.

## Staging cutover evidence workflow

`deploy/scripts/verify-postgres-cutover.sh` composes the existing proofs into one fail-closed Linux staging workflow. It refuses non-staging execution and password-bearing target URLs, verifies that the immutable SQLite source has no running worker, active Classroom, or non-idle Classroom guard, performs the signed row/key/hash migration, checks the migrated target, creates a signed PostgreSQL/private-file backup, restores it into a disposable database, and writes a compact atomic `status.json`.

Protected PostgreSQL CI runs this workflow with a synthetic SQLite source, a separate synthetic target database, file-mounted credentials, and non-PHI file fixtures. This evidence remains staging-only and does not select PostgreSQL for the existing production deployment.
