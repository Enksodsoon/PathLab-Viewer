#!/usr/bin/env bash
set -Eeuo pipefail

REPOSITORY_URL="https://github.com/Enksodsoon/PathLab-Viewer.git"
LIVE_DIR="/opt/pathlab-viewer"
LOCK_FILE="/var/lock/pathlab-viewer-deploy.lock"
HEALTH_URL=""
REQUEST="${1:-${SSH_ORIGINAL_COMMAND:-}}"
SWAPPED=0
STAGE_DIR=""
ROLLBACK_DIR=""

fail() {
  echo "Deployment failed: $*" >&2
  if [[ "${SWAPPED}" -eq 1 ]]; then
    rollback_release
  fi
  exit 1
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
  exit 1
}

cleanup_stage() {
  if [[ "${STAGE_DIR}" == /opt/pathlab-viewer.stage-* && -d "${STAGE_DIR}" ]]; then
    rm -rf -- "${STAGE_DIR}"
  fi
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
ENV_FILE="${LIVE_DIR}/deploy/.env"
[[ -f "${ENV_FILE}" ]] || fail "live deploy/.env is missing"
ENV_PERMISSIONS="$(stat -c '%a' "${ENV_FILE}")"
[[ "${ENV_PERMISSIONS: -2}" == "00" ]] || fail "live deploy/.env must not be group- or world-readable"
DOMAIN="$(awk -F= '
  /^[[:space:]]*DOMAIN[[:space:]]*=/ {
    value = substr($0, index($0, "=") + 1)
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
    print value
  }
' "${ENV_FILE}" | tail -n 1 | tr -d '\r')"
if [[ "${DOMAIN}" == \"*\" && "${DOMAIN}" == *\" ]]; then
  DOMAIN="${DOMAIN:1:${#DOMAIN}-2}"
elif [[ "${DOMAIN}" == \'*\' && "${DOMAIN}" == *\' ]]; then
  DOMAIN="${DOMAIN:1:${#DOMAIN}-2}"
fi
[[ "${DOMAIN}" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]] || \
  fail "live DOMAIN is missing or invalid"
[[ "${DOMAIN}" != *..* ]] || fail "live DOMAIN is invalid"
HEALTH_URL="https://${DOMAIN}/readyz"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
STAGE_DIR="/opt/pathlab-viewer.stage-${TARGET_SHA}-${TIMESTAMP}"
CURRENT_SHA="$(
  cat "${LIVE_DIR}/.pathlab-release" 2>/dev/null | cut -c1-12 || \
    git -c safe.directory="${LIVE_DIR}" -C "${LIVE_DIR}" rev-parse --short=12 HEAD 2>/dev/null || \
    echo unknown
)"
ROLLBACK_DIR="/opt/pathlab-viewer.rollback-${CURRENT_SHA}-${TIMESTAMP}"
trap cleanup_stage EXIT

git clone --quiet --branch main --single-branch "${REPOSITORY_URL}" "${STAGE_DIR}"
[[ "$(git -C "${STAGE_DIR}" rev-parse HEAD)" == "${TARGET_SHA}" ]] || \
  fail "staged checkout does not match the requested commit"
install -m 600 "${ENV_FILE}" "${STAGE_DIR}/deploy/.env"
printf '%s\n' "${TARGET_SHA}" > "${STAGE_DIR}/.pathlab-release"
chown -R ubuntu:ubuntu "${STAGE_DIR}"

(
  cd "${STAGE_DIR}/deploy"
  docker compose config --quiet
  docker compose build
)

mv "${LIVE_DIR}" "${ROLLBACK_DIR}"
mv "${STAGE_DIR}" "${LIVE_DIR}"
STAGE_DIR=""
SWAPPED=1
trap rollback_release ERR

systemctl reload pathlab-viewer
systemctl is-active --quiet pathlab-viewer

for _ in $(seq 1 30); do
  if curl --fail --silent --max-time 5 "${HEALTH_URL}" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
curl --fail --silent --max-time 5 "${HEALTH_URL}" >/dev/null 2>&1 || \
  fail "readiness verification failed"

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
echo "Production deployment succeeded: ${TARGET_SHA}"
