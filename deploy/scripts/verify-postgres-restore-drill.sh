#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${1:-}" || "${1:-}" != /* ]]; then
  echo "Usage: verify-postgres-restore-drill.sh /absolute/path/to/backup" >&2
  exit 2
fi
backup="$1"
postgres_service="${PATHLAB_POSTGRES_SERVICE:-postgres}"
postgres_container="${PATHLAB_POSTGRES_CONTAINER:-}"
database_user="${POSTGRES_USER:-pathlab}"
python_command="${PATHLAB_PYTHON_COMMAND:-python3}"
[[ "$database_user" =~ ^[A-Za-z_][A-Za-z0-9_]{0,62}$ ]] || exit 2
if [[ -n "$postgres_container" && ! "$postgres_container" =~ ^[A-Za-z0-9_.-]{1,128}$ ]]; then
  exit 2
fi
postgres_exec() {
  if [[ -n "$postgres_container" ]]; then
    docker exec -i "$postgres_container" "$@"
  else
    docker compose exec -T "$postgres_service" "$@"
  fi
}
test -n "${PATHLAB_BACKUP_SIGNING_KEY:-}" || exit 2
test -f "$backup/database/pathlab.dump"
test -f "$backup/files.tar.gz"
test -f "$backup/manifest.json"
(cd "$backup" && sha256sum --check SHA256SUMS)
manifest="$("$python_command" "$(dirname "$0")/postgres_backup_manifest.py" verify "$backup")"
schema_revision="$("$python_command" -c 'import json,sys; print(json.load(sys.stdin)["schemaRevision"])' <<<"$manifest")"

drill_database="pathlab_restore_drill_$(date -u +%Y%m%d%H%M%S)_$$"
[[ "$drill_database" =~ ^[A-Za-z_][A-Za-z0-9_]{0,62}$ ]] || exit 2
cleanup() {
  postgres_exec \
    dropdb --if-exists --force --username "$database_user" "$drill_database" >/dev/null 2>&1 || true
}
trap cleanup EXIT
postgres_exec \
  createdb --username "$database_user" "$drill_database"
postgres_exec \
  pg_restore --exit-on-error --no-owner --no-acl --username "$database_user" \
    --dbname "$drill_database" < "$backup/database/pathlab.dump"
restored_revision="$(
  postgres_exec \
    psql --no-psqlrc --tuples-only --no-align --username "$database_user" \
      --dbname "$drill_database" --command 'SELECT version_num FROM alembic_version'
)"
restored_revision="${restored_revision//$'\r'/}"
restored_revision="${restored_revision//$'\n'/}"
[[ "$restored_revision" == "$schema_revision" ]] || {
  echo "Restored schema revision does not match the signed manifest" >&2
  exit 1
}
server_version="$(
  postgres_exec \
    psql --no-psqlrc --tuples-only --no-align --username "$database_user" \
      --dbname "$drill_database" --command "SELECT current_setting('server_version_num')"
)"
server_version="${server_version//$'\r'/}"
server_version="${server_version//$'\n'/}"
[[ "$server_version" == "180006" ]] || {
  echo "Restore drill requires PostgreSQL server 18.6" >&2
  exit 1
}
table_count="$(
  postgres_exec \
    psql --no-psqlrc --tuples-only --no-align --username "$database_user" \
      --dbname "$drill_database" \
      --command "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname = 'public'"
)"
table_count="${table_count//$'\r'/}"
table_count="${table_count//$'\n'/}"
[[ "$table_count" =~ ^[1-9][0-9]*$ ]] || {
  echo "Restored database has no application tables" >&2
  exit 1
}
printf '{"archiveRoots":["originals","private","public"],"databaseIntegrity":"restored","schemaRevision":"%s","tableCount":%s}\n' \
  "$restored_revision" "$table_count"
