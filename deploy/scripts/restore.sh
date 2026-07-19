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

docker compose stop api worker tusd caddy
recovery="${data_dir}.before-restore-$(date -u +%Y%m%dT%H%M%SZ)"
mv "$data_dir" "$recovery"
mkdir -p "$data_dir/database"
cp "${backup_dir}/database/pathlab.sqlite3" "$data_dir/database/pathlab.sqlite3"
tar --extract --gzip --file "${backup_dir}/files.tar.gz" --directory "$data_dir"
chown -R 10001:10001 "$data_dir"
docker compose up -d
echo "Restored. Previous data remains at $recovery"
