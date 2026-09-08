# Production PostgreSQL cutover

This is a one-time root-operated maintenance operation from the exact reviewed,
deployed release. It does not enable Assessment or certify learner capacity.
Deploy its implementation through the normal required CI and guarded release
first. Complete two isolated migration rehearsals and preserve their evidence.

The operator must have an OCI console/Bastion recovery path and a maintenance
window long enough for a full file backup and disposable restore. The measured
September 8 rehearsal processed about 5 GB and 108,328 file entries; allow at
least an hour for recovery checks, plus recovery contingency. Do not infer a
short outage from the small SQLite database alone.

## Execute

Run in a supervised root systemd service, using the full deployed SHA:

```sh
systemd-run --unit=pathlab-postgres-cutover --property=Type=exec \
  --property=TimeoutStopSec=7200 \
  /usr/bin/python3 /opt/pathlab-viewer/deploy/scripts/cutover-production-postgres.py \
  --expected-release FULL_DEPLOYED_SHA
```

Inspect `journalctl -u pathlab-postgres-cutover` and the private
`/srv/pathlab/data/.postgres-cutover-*/status.json`. Do not launch a second
operation or terminate the service to shorten a long backup.

The command holds the deployment and capacity locks, verifies the live runtime,
rejects a pre-existing production PostgreSQL volume, stops application writers
and the watchdog, and takes an integrity-checked SQLite snapshot. It imports
into a new PostgreSQL database and verifies the signed migration receipt. It
then creates and restores a signed PostgreSQL/file backup and compares every
restored table, primary key, row hash, and foreign key with the quiesced source.
Original slide files remain in place.

A root-only durable maintenance marker blocks Compose `up`, `start`, `restart`,
and `run` from normal service-manager invocations, including after reboot. Only
the current cutover invocation has the private owner token. Never publish the
marker, environment copies, migration row identifiers, keys, or operation log.

Before any PostgreSQL application starts, the command writes
`/var/lib/pathlab-viewer/postgres-authority.json`. This permanently closes the
SQLite rollback path. Original SQLite files become root-owned read-only
evidence, inaccessible to the application UID. Successful startup verifies
the seven-service inventory, readiness, liveness, and refreshes the runtime
safety manifest before declaring `SUCCEEDED`.

## Failure and interruption

Before the authority receipt exists, a handled failure restores the original
SQLite environment and services. The unused PostgreSQL volume and evidence
remain for investigation; do not automatically delete or reuse them.

After the authority receipt exists, failure retains PostgreSQL and stops public
and background writers. The state is
`FAILED_POSTGRES_FORWARD_RECOVERY_REQUIRED`. Recovery must use PostgreSQL or
forward repair. Never copy `sqlite.env` back, remove the authority receipt, or
start the old SQLite database after this boundary, even if the receipt is
malformed or unreadable.

A force kill, power loss, or failed recovery may leave the maintenance marker
present and services stopped. Use the private journal to determine which
authority applies. Do not remove the marker merely to make the site start.
Recover the selected authority with writers stopped, verify its data and
configuration, and only then retire the maintenance marker and restart the
watchdog. The command refuses an automatic rerun in this state.

## Assessment follows separately

After cutover, verify current authenticated production workflows on PostgreSQL.
Assessment service admission, its protected capacity campaign, staged learner
pilots, and activation remain separate gates. `SUCCEEDED` here means database
cutover, not Teaching Studio activation or capacity certification.
