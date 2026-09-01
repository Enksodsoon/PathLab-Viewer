#!/usr/bin/env bash
set -euo pipefail
umask 077

data_dir="${PATHLAB_DATA_DIR:-/srv/pathlab/data}"
backup_dir="${PATHLAB_BACKUP_DIR:-/srv/pathlab/data/backups}"
retention_count="${PATHLAB_BACKUP_RETENTION_COUNT:-5}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
destination="${backup_dir}/pathlab-${timestamp}"

test -d "$data_dir"
[[ "$retention_count" =~ ^[1-9][0-9]*$ ]] || {
  echo "Backup refused: PATHLAB_BACKUP_RETENTION_COUNT must be a positive integer" >&2
  exit 1
}
install -d -m 700 "$backup_dir"
exec 9>"${backup_dir}/.backup.lock"
flock -n 9 || {
  echo "Backup refused: another backup is already running" >&2
  exit 1
}
install -d -m 700 "$destination" "$destination/database"
complete=false
cleanup_incomplete_backup() {
  if [[ "$complete" != true && -d "$destination" && ! -L "$destination" ]]; then
    rm -rf -- "$destination"
  fi
}
trap cleanup_incomplete_backup EXIT
source_bytes="$(du -sb "${data_dir}/originals" "${data_dir}/private" "${data_dir}/public" | awk '{total += $1} END {print total}')"
database_bytes="$(stat -c %s "${data_dir}/database/pathlab.sqlite3")"
available_bytes="$(df --output=avail -B1 "${backup_dir}" | tail -n 1 | tr -d ' ')"
required_bytes="$((source_bytes + source_bytes / 100 + database_bytes + 1073741824))"
[[ "${available_bytes}" -ge "${required_bytes}" ]] || {
  echo "Backup refused: insufficient space within the existing data volume" >&2
  rmdir "${destination}/database" "${destination}"
  exit 1
}
docker compose run --rm --no-deps --entrypoint python api -c \
  "import sqlite3; source=sqlite3.connect('/data/database/pathlab.sqlite3'); target=sqlite3.connect('/data/database/backup.sqlite3'); source.backup(target); target.close(); source.close()"
mv "${data_dir}/database/backup.sqlite3" "${destination}/database/pathlab.sqlite3"
tar --create --gzip --file "${destination}/files.tar.gz" \
  --directory "$data_dir" originals private public
(
  cd "${destination}"
  sha256sum database/pathlab.sqlite3 files.tar.gz > SHA256SUMS
  sha256sum --check --status SHA256SUMS
)
complete=true
"$(dirname "$0")/prune-backups.sh" "$backup_dir" "$retention_count"
echo "$destination"
