#!/usr/bin/env bash
set -Eeuo pipefail

REPOSITORY_URL="https://github.com/Enksodsoon/PathLab-Viewer.git"
LIVE_DIR="/opt/pathlab-viewer"
LOCK_FILE="/var/lock/pathlab-viewer-deploy.lock"
HEALTH_URL="https://pathlab-viewer.140-245-126-212.sslip.io/readyz"
REQUEST="${1:-${SSH_ORIGINAL_COMMAND:-}}"
SWAPPED=0
OLD_WORKER_STOPPED=0
STAGE_DIR=""
ROLLBACK_DIR=""

fail() {
  echo "Deployment failed: $*" >&2
  if [[ "${SWAPPED}" -eq 1 ]]; then
    rollback_release
  fi
  restart_old_worker
  exit 1
}

restart_old_worker() {
  if [[ "${OLD_WORKER_STOPPED}" -eq 1 && -d "${LIVE_DIR}/deploy" ]]; then
    (
      cd "${LIVE_DIR}/deploy"
      docker compose start worker
    ) || echo "Deployment failed: unable to restart the existing worker" >&2
    OLD_WORKER_STOPPED=0
  fi
}

rollback_release() {
  set +e
  trap - ERR
  echo "Health verification failed; restoring the previous release." >&2
  if [[ -d "${LIVE_DIR}" && -d "${ROLLBACK_DIR}" ]]; then
    mv "${LIVE_DIR}" "${LIVE_DIR}.failed-$(date -u +%Y%m%dT%H%M%SZ)"
    mv "${ROLLBACK_DIR}" "${LIVE_DIR}"
    systemctl reload pathlab-viewer
  fi
  OLD_WORKER_STOPPED=0
  SWAPPED=0
  exit 1
}

cleanup_stage() {
  if [[ "${STAGE_DIR}" == /opt/pathlab-viewer.stage-* && -d "${STAGE_DIR}" ]]; then
    rm -rf -- "${STAGE_DIR}"
  fi
}

cleanup_exit() {
  if [[ "${SWAPPED}" -eq 0 ]]; then
    restart_old_worker
  fi
  cleanup_stage
}

deployment_check() {
  local release_dir="$1"
  (
    cd "${release_dir}/deploy"
    docker compose run --rm --no-deps api pathlab-admin deployment-check
  )
}

[[ "${REQUEST}" =~ ^deploy[[:space:]]([0-9a-f]{40})$ ]] || \
  fail "expected: deploy <40-character lowercase commit SHA>"
TARGET_SHA="${BASH_REMATCH[1]}"

[[ "${EUID}" -eq 0 ]] || fail "this script must run as root"
command -v flock >/dev/null || fail "flock is required"
exec 9>"${LOCK_FILE}"
flock -n 9 || fail "another production deployment is already running"

REMOTE_MAIN_SHA="$(git ls-remote "${REPOSITORY_URL}" refs/heads/main | awk '{print $1}')"
[[ "${REMOTE_MAIN_SHA}" == "${TARGET_SHA}" ]] || \
  fail "requested commit is not the current main commit"
[[ -f "${LIVE_DIR}/deploy/.env" ]] || fail "live deploy/.env is missing"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
STAGE_DIR="/opt/pathlab-viewer.stage-${TARGET_SHA}-${TIMESTAMP}"
CURRENT_SHA="$(
  cat "${LIVE_DIR}/.pathlab-release" 2>/dev/null | cut -c1-12 || \
    git -c safe.directory="${LIVE_DIR}" -C "${LIVE_DIR}" rev-parse --short=12 HEAD 2>/dev/null || \
    echo unknown
)"
ROLLBACK_DIR="/opt/pathlab-viewer.rollback-${CURRENT_SHA}-${TIMESTAMP}"
trap cleanup_exit EXIT

git clone --quiet --branch main --single-branch "${REPOSITORY_URL}" "${STAGE_DIR}"
[[ "$(git -C "${STAGE_DIR}" rev-parse HEAD)" == "${TARGET_SHA}" ]] || \
  fail "staged checkout does not match the requested commit"
install -m 600 "${LIVE_DIR}/deploy/.env" "${STAGE_DIR}/deploy/.env"
printf '%s\n' "${TARGET_SHA}" > "${STAGE_DIR}/.pathlab-release"
chown -R ubuntu:ubuntu "${STAGE_DIR}"

(
  cd "${STAGE_DIR}/deploy"
  docker compose config --quiet
  docker compose build
)

deployment_check "${STAGE_DIR}" || fail "worker job is active"
OLD_WORKER_STOPPED=1
(
  cd "${LIVE_DIR}/deploy"
  docker compose stop worker
)
deployment_check "${STAGE_DIR}" || fail "worker job did not stop cleanly"

mv "${LIVE_DIR}" "${ROLLBACK_DIR}"
mv "${STAGE_DIR}" "${LIVE_DIR}"
STAGE_DIR=""
SWAPPED=1
trap rollback_release ERR

systemctl reload pathlab-viewer
systemctl is-active --quiet pathlab-viewer

for _ in $(seq 1 30); do
  if curl --fail --silent --show-error --max-time 5 "${HEALTH_URL}" >/dev/null; then
    break
  fi
  sleep 2
done
curl --fail --silent --show-error --max-time 5 "${HEALTH_URL}" >/dev/null

RUNNING_SERVICES="$(
  cd "${LIVE_DIR}/deploy"
  docker compose ps --status running --services | sort
)"
EXPECTED_SERVICES=$'api\ncaddy\ntusd\nworker'
[[ "${RUNNING_SERVICES}" == "${EXPECTED_SERVICES}" ]] || \
  fail "not all production services are running"
[[ "$(cat "${LIVE_DIR}/.pathlab-release")" == "${TARGET_SHA}" ]] || \
  fail "live checkout does not match the requested commit"

trap - ERR
SWAPPED=0
OLD_WORKER_STOPPED=0
echo "Production deployment succeeded: ${TARGET_SHA}"
