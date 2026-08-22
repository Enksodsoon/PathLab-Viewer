#!/usr/bin/env bash
set -euo pipefail
umask 077

[[ -n "${1:-}" && "${1:-}" == /* ]] || {
  echo "Usage: verify-current-restore-drill.sh /absolute/path/to/backup" >&2
  exit 2
}

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
    exec python3 "${script_dir}/verify_restore_drill.py" "$1"
    ;;
  postgres)
    export POSTGRES_DB="$(read_env PATHLAB_POSTGRES_DB)"
    export POSTGRES_USER="$(read_env PATHLAB_POSTGRES_USER)"
    signing_key_file="$(read_env PATHLAB_POSTGRES_BACKUP_SIGNING_KEY_FILE)"
    [[ -f "${signing_key_file}" && ! -L "${signing_key_file}" ]] || exit 2
    export PATHLAB_BACKUP_SIGNING_KEY="$(cat "${signing_key_file}")"
    exec bash "${script_dir}/verify-postgres-restore-drill.sh" "$1"
    ;;
esac
