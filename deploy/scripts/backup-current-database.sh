#!/usr/bin/env bash
set -euo pipefail
umask 077

script_dir="$(cd "$(dirname "$0")" && pwd)"
deploy_dir="$(cd "${script_dir}/.." && pwd)"
env_file="${deploy_dir}/.env"
engine="$(bash "${script_dir}/compose-pathlab.sh" engine)"

read_env() {
  local name="$1" value
  value="$(sed -n "s/^${name}=//p" "${env_file}" | tail -n 1)"
  value="${value%\"}"
  value="${value#\"}"
  value="${value%\'}"
  value="${value#\'}"
  printf '%s' "${value}"
}

case "${engine}" in
  sqlite)
    exec bash "${script_dir}/backup.sh"
    ;;
  postgres)
    export POSTGRES_DB="$(read_env PATHLAB_POSTGRES_DB)"
    export POSTGRES_USER="$(read_env PATHLAB_POSTGRES_USER)"
    signing_key_file="$(read_env PATHLAB_POSTGRES_BACKUP_SIGNING_KEY_FILE)"
    [[ "${POSTGRES_DB}" =~ ^[a-z_][a-z0-9_]{0,62}$ ]] || exit 2
    [[ "${POSTGRES_USER}" =~ ^[a-z_][a-z0-9_]{0,62}$ ]] || exit 2
    [[ "${signing_key_file}" =~ ^/[A-Za-z0-9._/-]+$ && "${signing_key_file}" != */../* ]] || {
      echo "PostgreSQL backup signing-key path is invalid" >&2
      exit 2
    }
    [[ -f "${signing_key_file}" && ! -L "${signing_key_file}" ]] || {
      echo "PostgreSQL backup signing key is unavailable or unsafe" >&2
      exit 2
    }
    export PATHLAB_BACKUP_SIGNING_KEY="$(cat "${signing_key_file}")"
    [[ "${#PATHLAB_BACKUP_SIGNING_KEY}" -ge 32 ]] || {
      echo "PostgreSQL backup signing key is too short" >&2
      exit 2
    }
    exec bash "${script_dir}/backup-postgres.sh"
    ;;
esac
