# OCI storage maintenance

The 2026-10-08 audit found 28 full backups using 69,529,477,120 bytes.
PostgreSQL backups were missing retention cleanup; the SQLite-only pruner
did not recognize their names. Each release added approximately 2.48 GB.
The data volume had 62,569,500,672 bytes (58.27 GiB) available. Docker build
cache also occupied 7.86 GB on the separate root filesystem.

`storage-maintenance.sh` retains the newest five verified PostgreSQL backups
and prunes unused Docker build cache older than 24 hours, keeping 2 GB of cache.
Signed manifests, payload hashes and `SHA256SUMS` must pass before a backup
counts toward retention. Archive layout was validated when signed; retention
hashes unchanged archive bytes once, while restore keeps full layout validation.
Invalid backups and SQLite migration
backups are preserved. Live originals, derivatives, database volumes, Docker
images and qualification/cutover evidence are excluded.

Install as root, outside the release checkout, so deployments cannot replace
the maintenance code. Copy `storage-maintenance.sh`, `prune-backups.sh` and
`postgres_backup_manifest.py` into `/usr/local/lib/pathlab-storage/` with
root ownership, scripts mode 755 and Python mode 644. Install the supplied
service and timer into `/etc/systemd/system/` with root ownership and mode 644.
Then run:

```sh
systemd-analyze verify /etc/systemd/system/pathlab-storage-maintenance.{service,timer}
systemctl daemon-reload
systemctl start pathlab-storage-maintenance.service
systemctl enable --now pathlab-storage-maintenance.timer
```

The service holds both the deployment lock and backup lock; contention exits
75 without cleanup. PostgreSQL backup creation uses the same backup lock.
The existing signing key stays in `/etc/pathlab-viewer/postgres/backup-signing-key`
and is never logged. The daily timer runs at 20:00 UTC (03:00 Bangkok the next day), with up
to 15 minutes of jitter. Check completion and actual recovered space with:

```sh
systemctl show pathlab-storage-maintenance.service -p Result -p ExecMainStatus
journalctl -u pathlab-storage-maintenance.service --no-pager
df -B1 / /srv/pathlab/data
systemctl list-timers pathlab-storage-maintenance.timer
```

Disable recurring cleanup with `systemctl disable --now pathlab-storage-maintenance.timer`.
Removing the timer does not restore deleted expired backups or build cache.

## Verified result on 2026-10-08

The host maintenance run finished with `Result=success` and `ExecMainStatus=0`.
Eighteen verified expired PostgreSQL backups were removed; five PostgreSQL and
five legacy SQLite backups remain. Qualification and cutover evidence was kept.

| Filesystem | Available before | Available after |
| --- | ---: | ---: |
| Data volume | 58.27 GiB | 99.90 GiB |
| Root filesystem | 9.54 GiB | 12.62 GiB |

Data-volume recovery was 44,698,607,616 bytes (41.63 GiB). Root cleanup removed
unused old build cache. Live originals, derivatives, database volumes and the
deployed application release were not changed. Readiness remained successful.
The timer is enabled. After moving it to overnight maintenance, the server
confirmed its next run as 2026-10-09 03:05:45 Bangkok (2026-10-08 20:05:45 UTC).
The source and installation instructions are versioned separately; operator-installed maintenance is active
on the host independently of a future application release.

Local validation: full backend run had 1,443 passed, 109 skipped and one security
inventory failure for the new unit. Its local-only control flow was catalogued;
the affected security and backup suites then passed all 33 tests. Security
baseline validation and Ruff also passed. The full suite was not repeated after
the inventory-only correction. All temporary Bastion sessions were confirmed
`DELETED` after host verification.
