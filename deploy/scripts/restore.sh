#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--confirm" || -z "${2:-}" ]]; then
  echo "Usage: restore.sh --confirm /absolute/path/to/pathlab-backup" >&2
  exit 2
fi

backup_dir="$(realpath "$2")"
data_dir="$(realpath -m "${PATHLAB_DATA_DIR:-/srv/pathlab/data}")"
case "$data_dir" in
  /srv/pathlab/data|/mnt/pathlab/data) ;;
  *) echo "Refusing unexpected data directory: $data_dir" >&2; exit 3 ;;
esac
test -f "${backup_dir}/database/pathlab.sqlite3"
test -f "${backup_dir}/files.tar.gz"
(cd "$backup_dir" && sha256sum --check SHA256SUMS)

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
recovery="${data_dir}.before-restore-${timestamp}"
staged="${data_dir}.restore-staged-${timestamp}"
test ! -e "$recovery"
test ! -e "$staged"
mkdir -p "$staged/database"
cp "${backup_dir}/database/pathlab.sqlite3" "$staged/database/pathlab.sqlite3"
python3 - "${backup_dir}/files.tar.gz" "$staged" <<'PY'
import sys
import tarfile

archive, destination = sys.argv[1:]
with tarfile.open(archive, "r:gz") as stored:
    stored.extractall(destination, filter="data")
PY
chown -R 10001:10001 "$staged"

docker compose stop caddy api classroom tile-service tusd worker
mv "$data_dir" "$recovery"
if ! mv "$staged" "$data_dir"; then
  mv "$recovery" "$data_dir"
  docker compose up -d
  echo "Restore failed before data activation; original data was restarted" >&2
  exit 1
fi
if [[ -d "${recovery}/backups" && ! -e "${data_dir}/backups" ]]; then
  mv "${recovery}/backups" "${data_dir}/backups"
fi
docker compose run --rm --no-deps tile-service pathlab-tiles --purge-cache
docker compose up -d
echo "Restored. Previous data remains at $recovery"
