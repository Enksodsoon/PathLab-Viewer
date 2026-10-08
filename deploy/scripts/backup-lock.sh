#!/usr/bin/env bash
# Shared by backup creation and retention; never place privileged locks on /data.
lock_dir="${PATHLAB_BACKUP_LOCK_DIR:-/run/pathlab-storage}"
operator_uid="$(id -u)"
if [[ -z "${PATHLAB_BACKUP_LOCK_DIR:-}" && "$operator_uid" != 0 ]]; then
  lock_dir="${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}/pathlab-storage-${operator_uid}"
fi
mkdir -m 700 -- "$lock_dir" 2>/dev/null || true
[[ -d "$lock_dir" && ! -L "$lock_dir" &&
   "$(stat -c '%u:%a' "$lock_dir")" == "$operator_uid:700" ]] || {
  echo "Backup lock directory must be private and owned by the operator" >&2
  exit 2
}
[[ ! -L "$lock_dir/backup.lock" &&
   ( ! -e "$lock_dir/backup.lock" || -f "$lock_dir/backup.lock" ) ]] || {
  echo "Backup lock must be a regular file, not a symlink" >&2
  exit 2
}
exec 9>>"$lock_dir/backup.lock"
flock -n -E 75 9 || exit 75
