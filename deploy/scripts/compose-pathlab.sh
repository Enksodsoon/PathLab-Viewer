#!/usr/bin/env bash
set -euo pipefail

deploy_dir="$(cd "$(dirname "$0")/.." && pwd)"
env_file="${PATHLAB_COMPOSE_ENV_FILE:-${deploy_dir}/.env}"

[[ "${env_file}" == /* && -f "${env_file}" && ! -L "${env_file}" ]] || {
  echo "PathLab Compose environment is unavailable or unsafe" >&2
  exit 2
}

engine="$(sed -n 's/^PATHLAB_DATABASE_ENGINE=//p' "${env_file}" | tail -n 1)"
engine="${engine%\"}"
engine="${engine#\"}"
engine="${engine%\'}"
engine="${engine#\'}"
engine="${engine:-sqlite}"

case "${engine}" in
  sqlite)
    compose_files=(-f "${deploy_dir}/compose.yaml")
    ;;
  postgres)
    compose_files=(-f "${deploy_dir}/compose.yaml" -f "${deploy_dir}/compose.postgres.yaml")
    ;;
  *)
    echo "PATHLAB_DATABASE_ENGINE must be sqlite or postgres" >&2
    exit 2
    ;;
esac

if [[ "${1:-}" == "engine" ]]; then
  [[ $# -eq 1 ]] || exit 2
  printf '%s\n' "${engine}"
  exit 0
fi

[[ $# -gt 0 ]] || {
  echo "Usage: compose-pathlab.sh engine|<docker compose arguments>" >&2
  exit 2
}

exec docker compose \
  --project-directory "${deploy_dir}" \
  --env-file "${env_file}" \
  "${compose_files[@]}" "$@"
