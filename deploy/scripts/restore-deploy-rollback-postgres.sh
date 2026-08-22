#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

[[ $# -eq 1 && "$1" == /* ]] || {
  echo "Usage: restore-deploy-rollback-postgres.sh /absolute/path/to/pathlab-backup" >&2
  exit 2
}

script_dir="$(cd "$(dirname "$0")" && pwd)"
deploy_dir="$(cd "${script_dir}/.." && pwd)"
env_file="${deploy_dir}/.env"
data_dir="$(realpath -m "${PATHLAB_DATA_DIR:?PATHLAB_DATA_DIR is required}")"
backup_root="$(realpath -m "${PATHLAB_BACKUP_DIR:?PATHLAB_BACKUP_DIR is required}")"
backup_dir="$(realpath "$1")"

read_env() {
  local name="$1" value
  value="$(sed -n "s/^${name}=//p" "${env_file}" | tail -n 1)"
  value="${value%\"}"
  value="${value#\"}"
  value="${value%\'}"
  value="${value#\'}"
  printf '%s' "${value}"
}

database_name="$(read_env PATHLAB_POSTGRES_DB)"
database_user="$(read_env PATHLAB_POSTGRES_USER)"
signing_key_file="$(read_env PATHLAB_POSTGRES_BACKUP_SIGNING_KEY_FILE)"
[[ "${database_name}" =~ ^[a-z_][a-z0-9_]{0,40}$ ]] || exit 2
[[ "${database_user}" =~ ^[a-z_][a-z0-9_]{0,62}$ ]] || exit 2
[[ "${backup_root}" == "${data_dir%/}/backups" ]] || exit 3
case "${backup_dir}" in
  "${backup_root}"/*) ;;
  *) echo "Deployment rollback backup is outside the approved root" >&2; exit 3 ;;
esac
[[ -f "${signing_key_file}" && ! -L "${signing_key_file}" ]] || exit 4
export PATHLAB_BACKUP_SIGNING_KEY="$(cat "${signing_key_file}")"
manifest="$(python3 "${script_dir}/postgres_backup_manifest.py" verify "${backup_dir}")"
manifest_revision="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["schemaRevision"])' \
  <<<"${manifest}")"
(cd "${backup_dir}" && sha256sum --check --status SHA256SUMS)

postgres_container="$(bash "${script_dir}/compose-pathlab.sh" ps -q postgres)"
[[ "${postgres_container}" =~ ^[a-f0-9]{12,64}$ ]] || {
  echo "PostgreSQL rollback container identity is unavailable" >&2
  exit 4
}
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
failed_database="${database_name}_failed_${timestamp,,}"
[[ "${failed_database}" =~ ^[a-z_][a-z0-9_]{0,62}$ ]] || exit 2

postgres_exec() {
  docker exec -i "${postgres_container}" "$@"
}

bash "${script_dir}/compose-pathlab.sh" stop caddy api classroom tile-service tusd worker
postgres_exec psql --no-psqlrc --username "${database_user}" --dbname postgres \
  --set ON_ERROR_STOP=1 \
  --command "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${database_name}' AND pid <> pg_backend_pid();"
postgres_exec psql --no-psqlrc --username "${database_user}" --dbname postgres \
  --set ON_ERROR_STOP=1 --command "ALTER DATABASE \"${database_name}\" RENAME TO \"${failed_database}\";"

restore_failed_database() {
  set +e
  postgres_exec dropdb --if-exists --force --username "${database_user}" "${database_name}" >/dev/null 2>&1
  postgres_exec psql --no-psqlrc --username "${database_user}" --dbname postgres \
    --command "ALTER DATABASE \"${failed_database}\" RENAME TO \"${database_name}\";" >/dev/null 2>&1
}
trap restore_failed_database ERR

postgres_exec createdb --username "${database_user}" --owner "${database_user}" "${database_name}"
postgres_exec pg_restore --exit-on-error --no-owner --no-acl \
  --username "${database_user}" --dbname "${database_name}" \
  < "${backup_dir}/database/pathlab.dump"
restored_revision="$(postgres_exec psql --no-psqlrc --tuples-only --no-align \
  --username "${database_user}" --dbname "${database_name}" \
  --command 'SELECT version_num FROM alembic_version')"
restored_revision="${restored_revision//$'\r'/}"
restored_revision="${restored_revision//$'\n'/}"
[[ "${restored_revision}" == "${manifest_revision}" ]] || {
  echo "Restored PostgreSQL schema revision does not match the signed backup" >&2
  exit 1
}
trap - ERR
echo "Pre-deployment PostgreSQL database restored; failed database preserved as ${failed_database}"
