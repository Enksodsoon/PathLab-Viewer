#!/usr/bin/env bash
set -euo pipefail

data_dir="${PATHLAB_DATA_DIR:-/srv/pathlab/data}"
backup_dir="${PATHLAB_BACKUP_DIR:-/srv/pathlab/backups}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
destination="${backup_dir}/pathlab-${timestamp}"

test -d "$data_dir"
mkdir -p "$destination/database"
docker compose exec -T api python -c \
  "import sqlite3; source=sqlite3.connect('/data/database/pathlab.sqlite3'); target=sqlite3.connect('/data/database/backup.sqlite3'); source.backup(target); target.close(); source.close()"
mv "${data_dir}/database/backup.sqlite3" "${destination}/database/pathlab.sqlite3"
tar --create --gzip --file "${destination}/files.tar.gz" \
  --directory "$data_dir" originals private public
sha256sum "${destination}/database/pathlab.sqlite3" "${destination}/files.tar.gz" \
  > "${destination}/SHA256SUMS"
echo "$destination"
