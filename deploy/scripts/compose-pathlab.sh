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

# A durable marker also blocks service-manager startup after a host reboot.
# Only the cutover owner supplies its private, invocation-scoped token.
if [[ -e /var/lib/pathlab-viewer/postgres-cutover-in-progress.json || \
  -L /var/lib/pathlab-viewer/postgres-cutover-in-progress.json ]]; then
  python3 "${deploy_dir}/scripts/postgres_cutover_state.py" "$1"
fi

assessment="$(sed -n 's/^PATHLAB_ASSESSMENT_ENABLED=//p' "${env_file}" | tail -n 1)"
assessment="${assessment:-false}"
compose_profiles=()
case "${assessment}" in
  true)
    governance="$(sed -n 's/^PATHLAB_IDENTITY_GOVERNANCE_ENABLED=//p' "${env_file}" | tail -n 1)"
    [[ "${engine}" == postgres && "${governance}" == true ]] || {
      echo "Teaching Studio requires PostgreSQL and identity governance" >&2
      exit 2
    }
    compose_profiles=(--profile assessment)
    compose_files+=(-f "${deploy_dir}/compose.assessment.yaml")
    export PATHLAB_IDENTITY_GOVERNANCE_ENABLED="${governance}"
    ;;
  false) ;;
  *)
    echo "PATHLAB_ASSESSMENT_ENABLED must be true or false" >&2
    exit 2
    ;;
esac

# Compose gives inherited variables precedence over --env-file. Keep the
# advertised capability consistent with the profile selected from that file.
export PATHLAB_ASSESSMENT_ENABLED="${assessment}"
unset COMPOSE_PROFILES

exec docker compose \
  --project-directory "${deploy_dir}" \
  --env-file "${env_file}" \
  "${compose_files[@]}" "${compose_profiles[@]}" "$@"
