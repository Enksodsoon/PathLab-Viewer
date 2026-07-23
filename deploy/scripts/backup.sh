#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

data_dir="$(realpath -m "${PATHLAB_DATA_DIR:-/srv/pathlab/data}")"
backup_dir="$(realpath -m "${PATHLAB_BACKUP_DIR:-/srv/pathlab/backups}")"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
compose_file="${script_dir%/scripts}/compose.yaml"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
destination="${backup_dir}/pathlab-${timestamp}"
temporary_name=".backup-${timestamp}-$$.sqlite3"
temporary_backup="${data_dir}/database/${temporary_name}"

cleanup_temporary_backup() {
  rm -f -- "${temporary_backup}"
}
trap cleanup_temporary_backup EXIT

test -d "${data_dir}"
test -f "${compose_file}"
install -d -m 700 "${destination}/database"

docker compose -f "${compose_file}" exec -T api python - "${temporary_name}" <<'PY'
import sqlite3
import sys

name = sys.argv[1]
if not name.startswith(".backup-") or "/" in name or "\\" in name:
    raise SystemExit("invalid temporary backup name")
source = sqlite3.connect("/data/database/pathlab.sqlite3")
target = sqlite3.connect(f"/data/database/{name}")
try:
    source.backup(target)
finally:
    target.close()
    source.close()
PY

mv -- "${temporary_backup}" "${destination}/database/pathlab.sqlite3"
tar --create --gzip --file "${destination}/files.tar.gz" \
  --directory "${data_dir}" originals private public
sha256sum "${destination}/database/pathlab.sqlite3" "${destination}/files.tar.gz" \
  > "${destination}/SHA256SUMS"
chmod 600 "${destination}/database/pathlab.sqlite3" \
  "${destination}/files.tar.gz" "${destination}/SHA256SUMS"
echo "${destination}"
