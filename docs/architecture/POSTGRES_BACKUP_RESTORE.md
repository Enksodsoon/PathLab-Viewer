# PostgreSQL backup and restore evidence

This is a Program 0B staging mechanism. It is not active in the current SQLite
deployment and does not constitute production certification.

`backup-postgres.sh` creates a PostgreSQL custom-format dump and archives only
the durable `originals`, `private`, and `public` trees. It records the exact
release SHA and Alembic revision in a private HMAC-SHA256 signed manifest, then
writes checksums for every payload. The signing key must be an independent
secret of at least 32 bytes in `PATHLAB_BACKUP_SIGNING_KEY`.

The database container must run PostgreSQL 18.6 and expose `pg_dump`,
`pg_restore`, `psql`, `createdb`, and `dropdb` through the Compose service named
`postgres` (or `PATHLAB_POSTGRES_SERVICE`). The scripts use the database and
role in `POSTGRES_DB` and `POSTGRES_USER`; they never place a password or URL in
the evidence manifest.

CI may set `PATHLAB_POSTGRES_CONTAINER` to a strictly validated disposable
container identifier. Deployment leaves it unset and uses the Compose service.

```bash
PATHLAB_RELEASE_SHA=<exact-40-character-sha> \
PATHLAB_BACKUP_SIGNING_KEY=<private-backup-key> \
bash deploy/scripts/backup-postgres.sh

PATHLAB_BACKUP_SIGNING_KEY=<private-backup-key> \
bash deploy/scripts/verify-postgres-restore-drill.sh \
  /srv/pathlab/data/backups/pathlab-postgres-<timestamp>
```

The drill validates the checksum file and signed manifest, checks the archive
without extracting it, restores the dump into a new disposable database,
verifies its Alembic revision and application-table presence, and drops the
database on every exit path. A later Program 0B cutover PR will make this the
deployment backup path only after Compose uses PostgreSQL authoritatively.
