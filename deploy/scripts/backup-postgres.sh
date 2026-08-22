#!/usr/bin/env bash
set -euo pipefail
umask 077

data_dir="${PATHLAB_DATA_DIR:-/srv/pathlab/data}"
backup_dir="${PATHLAB_BACKUP_DIR:-/srv/pathlab/data/backups}"
postgres_service="${PATHLAB_POSTGRES_SERVICE:-postgres}"
postgres_container="${PATHLAB_POSTGRES_CONTAINER:-}"
database_name="${POSTGRES_DB:-pathlab}"
database_user="${POSTGRES_USER:-pathlab}"
release_sha="${PATHLAB_RELEASE_SHA:?PATHLAB_RELEASE_SHA is required}"
python_command="${PATHLAB_PYTHON_COMMAND:-python3}"
test -n "${PATHLAB_BACKUP_SIGNING_KEY:-}" || {
  echo "PATHLAB_BACKUP_SIGNING_KEY is required" >&2
  exit 2
}
[[ "$release_sha" =~ ^[0-9a-f]{40}$ ]] || {
  echo "PATHLAB_RELEASE_SHA must be an exact lowercase release SHA" >&2
  exit 2
}
[[ "$database_name" =~ ^[A-Za-z_][A-Za-z0-9_]{0,62}$ ]] || exit 2
[[ "$database_user" =~ ^[A-Za-z_][A-Za-z0-9_]{0,62}$ ]] || exit 2
if [[ -n "$postgres_container" && ! "$postgres_container" =~ ^[A-Za-z0-9_.-]{1,128}$ ]]; then
  echo "PATHLAB_POSTGRES_CONTAINER is invalid" >&2
  exit 2
fi
postgres_exec() {
  if [[ -n "$postgres_container" ]]; then
    docker exec -i "$postgres_container" "$@"
  else
    bash "$(dirname "$0")/compose-pathlab.sh" exec -T "$postgres_service" "$@"
  fi
}

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
destination="${backup_dir}/pathlab-postgres-${timestamp}"
test -d "$data_dir"
install -d -m 700 "$backup_dir"
test ! -e "$destination" || {
  echo "Backup destination already exists" >&2
  exit 1
}
install -d -m 700 "$destination" "$destination/database"
cleanup_incomplete() {
  rm -f "$destination/database/pathlab.dump.partial" \
    "$destination/database/pathlab.dump" "$destination/files.tar.gz" \
    "$destination/manifest.json" "$destination/SHA256SUMS"
  rmdir "$destination/database" "$destination" 2>/dev/null || true
}
trap cleanup_incomplete EXIT

database_facts="$(
  postgres_exec \
    psql --no-psqlrc --tuples-only --no-align --username "$database_user" \
      --dbname "$database_name" \
      --command "SELECT current_setting('server_version_num'), version_num, pg_database_size(current_database()) FROM alembic_version"
)"
database_facts="${database_facts//$'\r'/}"
database_facts="${database_facts//$'\n'/}"
IFS='|' read -r server_version schema_revision database_bytes <<<"$database_facts"
[[ "$server_version" == "180006" ]] || {
  echo "Backup requires PostgreSQL server 18.6" >&2
  exit 1
}
[[ "$schema_revision" =~ ^[0-9A-Za-z_]{1,128}$ ]] || {
  echo "Could not determine the database schema revision" >&2
  exit 1
}
[[ "$database_bytes" =~ ^[0-9]+$ ]] || exit 1
source_bytes="$(du -sb "${data_dir}/originals" "${data_dir}/private" "${data_dir}/public" | awk '{total += $1} END {print total}')"
available_bytes="$(df --output=avail -B1 "$backup_dir" | tail -n 1 | tr -d ' ')"
required_bytes="$((source_bytes + source_bytes / 100 + database_bytes + 1073741824))"
[[ "$available_bytes" -ge "$required_bytes" ]] || {
  echo "Backup refused: insufficient space within the existing data volume" >&2
  exit 1
}

partial="${destination}/database/pathlab.dump.partial"
postgres_exec \
  pg_dump --format=custom --compress=6 --no-owner --no-acl \
    --username "$database_user" --dbname "$database_name" > "$partial"
test -s "$partial"
mv "$partial" "${destination}/database/pathlab.dump"

tar --create --gzip --file "${destination}/files.tar.gz" \
  --directory "$data_dir" originals private public
"$python_command" "$(dirname "$0")/postgres_backup_manifest.py" create "$destination" \
  --release-sha "$release_sha" \
  --schema-revision "$schema_revision" \
  --database-name "$database_name" >/dev/null
(
  cd "$destination"
  sha256sum database/pathlab.dump files.tar.gz manifest.json > SHA256SUMS
)
trap - EXIT
echo "$destination"
