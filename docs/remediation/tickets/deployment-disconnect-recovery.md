# Deployment disconnect recovery

## Confirmed defect and reproduction

The forced deployment dispatcher handles HUP, INT and TERM, but not PIPE.
Recovery also writes to the same SSH output channel. Closing that channel can
interrupt recovery itself. `tests/load/test_deploy_disconnect.py` closes the
real Bash process's output pipe with mocked runtime commands. Both pre-swap
restart and post-swap rollback failed before the patch and pass after it.

Handle PIPE through the existing interruption path and detach its output
before restarting services or rolling back. Preserve deployment locking,
signed preflight, backup and schema-compatible rollback guards.

## Production incident, 2026-10-03 UTC

- Run 37083776978 attempt 1 was cancelled after stopping worker, Caddy and
  tusd. Root cancelled it following a fresh dependency advisory failure.
- Attempt 2 failed Bastion reconciliation; recovery run 37084254075 then
  failed because the original remote deployment still held the lock.
- An existing operator key and temporary managed Bastion session established
  read-only host inspection. The original process had exited, the lock had no
  holder, release `3cb26bc14ec64bc3dad85a29a6da823082615d6c` was unchanged,
  and precisely those three containers were stopped. No release swap occurred.
- Under nonblocking acquisition of the same deployment lock, root started
  those existing containers. All eight production services were running;
  API, Classroom, Assessment, tiles, PostgreSQL and worker were healthy.
  Public `/readyz` and `/livez` returned HTTP 200. The temporary admin session
  was deleted. No access rules, data, release checkout or feature gates changed.

The remote process's exact exit signal was not captured. Closed-pipe recovery
is a reproduced defect consistent with the incident, not proof of its entire
causal chain. The staged candidate remains for investigation; no production
deployment or authenticated workflow pass is claimed for `54f7c40`.

## Release status

Local regression passes. Protected review/checks and deployment are pending.
Do not cancel another deployment during its maintenance phase to fix a newly
discovered dependency issue; restore availability first through its reviewed
rollback/health path.
