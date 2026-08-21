#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

if [[ $# -ne 1 ]]; then
  echo "Usage: restore-deploy-rollback-database.sh /absolute/path/to/pathlab-backup" >&2
  exit 2
fi

data_dir="$(realpath -m "${PATHLAB_DATA_DIR:?PATHLAB_DATA_DIR is required}")"
backup_root="$(realpath -m "${PATHLAB_BACKUP_DIR:?PATHLAB_BACKUP_DIR is required}")"
backup_dir="$(realpath "$1")"
database_dir="${data_dir}/database"
database_path="${database_dir}/pathlab.sqlite3"
backup_database="${backup_dir}/database/pathlab.sqlite3"
checksum_manifest="${backup_dir}/SHA256SUMS"

[[ "${data_dir}" =~ ^/[A-Za-z0-9._/-]+$ && "${data_dir}" != */../* ]] || {
  echo "Deployment rollback data directory is invalid" >&2
  exit 3
}
[[ "${backup_root}" == "${data_dir%/}/backups" ]] || {
  echo "Deployment rollback backup root is invalid" >&2
  exit 3
}
case "${backup_dir}" in
  "${backup_root}"/*) ;;
  *) echo "Deployment rollback backup is outside the approved root" >&2; exit 3 ;;
esac
[[ -f "${database_path}" && ! -L "${database_path}" ]] || {
  echo "Live deployment database is unavailable or unsafe" >&2
  exit 4
}
[[ -f "${backup_database}" && ! -L "${backup_database}" ]] || {
  echo "Deployment rollback database backup is unavailable or unsafe" >&2
  exit 4
}
[[ -f "${checksum_manifest}" && ! -L "${checksum_manifest}" ]] || {
  echo "Deployment rollback checksum manifest is unavailable or unsafe" >&2
  exit 4
}

(
  cd "${backup_dir}"
  sha256sum --check --status SHA256SUMS
) || {
  echo "Deployment rollback backup checksum verification failed" >&2
  exit 5
}

python3 - "${backup_database}" <<'PY'
import sqlite3
import sys

database_path = sys.argv[1]
with sqlite3.connect(f"file:{database_path}?mode=ro", uri=True) as database:
    result = database.execute("PRAGMA integrity_check").fetchone()
if result != ("ok",):
    raise SystemExit("Deployment rollback database integrity check failed")
PY

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
staged_database="${database_dir}/.pathlab.sqlite3.rollback-${timestamp}"
preserved_database="${database_dir}/pathlab.sqlite3.failed-deploy-${timestamp}"
preserved_wal="${database_dir}/pathlab.sqlite3-wal.failed-deploy-${timestamp}"
preserved_shm="${database_dir}/pathlab.sqlite3-shm.failed-deploy-${timestamp}"

for target in "${staged_database}" "${preserved_database}" "${preserved_wal}" "${preserved_shm}"; do
  [[ ! -e "${target}" ]] || {
    echo "Deployment rollback evidence target already exists" >&2
    exit 6
  }
done

cp --reflink=auto --sparse=always "${backup_database}" "${staged_database}"
chown --reference="${database_path}" "${staged_database}"
chmod --reference="${database_path}" "${staged_database}"
sync -f "${staged_database}"

docker compose stop caddy api classroom tile-service tusd worker

mv "${database_path}" "${preserved_database}"
if [[ -f "${database_path}-wal" && ! -L "${database_path}-wal" ]]; then
  mv "${database_path}-wal" "${preserved_wal}"
fi
if [[ -f "${database_path}-shm" && ! -L "${database_path}-shm" ]]; then
  mv "${database_path}-shm" "${preserved_shm}"
fi
mv "${staged_database}" "${database_path}"
sync -f "${database_dir}"

echo "Pre-deployment database restored; failed database preserved at ${preserved_database}"
