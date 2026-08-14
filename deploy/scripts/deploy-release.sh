#!/usr/bin/env bash
set -Eeuo pipefail

REPOSITORY_URL="https://github.com/Enksodsoon/PathLab-Viewer.git"
LIVE_DIR="/opt/pathlab-viewer"
LOCK_FILE="/var/lock/pathlab-viewer-deploy.lock"
REQUEST="${1:-${SSH_ORIGINAL_COMMAND:-}}"
SWAPPED=0
OLD_WORKER_STOPPED=0
OLD_SERVICES_STOPPED=0
STAGE_DIR=""
ROLLBACK_DIR=""
CLASSROOM_ENABLED=""
WATCHDOG_CHANGED=0
DEPLOY_EVIDENCE=""
EVIDENCE_SIGNATURE=""
EVIDENCE_NONCE=""

fail() {
  echo "Deployment failed: $*" >&2
  if [[ "${SWAPPED}" -eq 1 ]]; then
    rollback_release
  fi
  restart_old_worker
  exit 1
}

restart_old_worker() {
  if [[ "${OLD_SERVICES_STOPPED}" -eq 1 && -d "${LIVE_DIR}/deploy" ]]; then
    (
      cd "${LIVE_DIR}/deploy"
      docker compose up -d
    ) || echo "Deployment failed: unable to restart existing services" >&2
    OLD_SERVICES_STOPPED=0
    OLD_WORKER_STOPPED=0
    return
  fi
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
    restore_watchdog
  fi
  OLD_WORKER_STOPPED=0
  SWAPPED=0
  exit 1
}

restore_watchdog() {
  if [[ -x "${LIVE_DIR}/deploy/scripts/install-watchdog.sh" ]]; then
    bash "${LIVE_DIR}/deploy/scripts/install-watchdog.sh" install "${LIVE_DIR}" || \
      echo "Deployment failed: watchdog rollback requires manual verification" >&2
  elif [[ "${WATCHDOG_CHANGED}" -eq 1 ]]; then
    systemctl disable --now pathlab-viewer-watchdog.timer || true
    rm -f -- /etc/systemd/system/pathlab-viewer-watchdog.service \
      /etc/systemd/system/pathlab-viewer-watchdog.timer
    systemctl daemon-reload
  fi
  WATCHDOG_CHANGED=0
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
  if [[ "${DEPLOY_EVIDENCE}" == /run/pathlab-deploy-evidence-* ]]; then
    rm -f -- "${DEPLOY_EVIDENCE}"
  fi
}

deployment_check() {
  local release_dir="$1"
  (
    cd "${release_dir}/deploy"
    docker compose run --rm --no-deps api pathlab-admin deployment-check
  )
}

if [[ "${PATHLAB_DEPLOY_RELEASE_LIBRARY_ONLY:-}" == 1 ]]; then
  return 0 2>/dev/null || exit 0
fi

[[ "${EUID}" -eq 0 ]] || fail "this script must run as root"
if [[ "${REQUEST}" =~ ^observe-load[[:space:]]([0-9]{2,5})([[:space:]]start=([0-9]{10}))?$ ]]; then
  OBSERVE_DURATION="${BASH_REMATCH[1]}"
  OBSERVE_START="${BASH_REMATCH[3]:-}"
  (( OBSERVE_DURATION >= 10 && OBSERVE_DURATION <= 10000 && OBSERVE_DURATION % 10 == 0 )) || \
    fail "observe-load duration must be a multiple of 10 from 10 to 10000 seconds"
  exec bash "${LIVE_DIR}/deploy/scripts/observe-load.sh" "${OBSERVE_DURATION}" "${OBSERVE_START}"
fi
if [[ "${REQUEST}" == capacity-arm\ * || "${REQUEST}" == capacity-status\ * \
  || "${REQUEST}" == capacity-finalize\ * || "${REQUEST}" == capacity-fault\ * \
  || "${REQUEST}" == capacity-abort\ * || "${REQUEST}" == capacity-rollback\ * \
  || "${REQUEST}" == capacity-postflight\ * || "${REQUEST}" == capacity-rollback-preflight\ * ]]; then
  exec bash "${LIVE_DIR}/deploy/scripts/capacity-control-host.sh" "${REQUEST}"
fi

[[ "${REQUEST}" =~ ^deploy[[:space:]]([0-9a-f]{40})[[:space:]]evidence=([A-Za-z0-9_-]+)[[:space:]]signature=([0-9a-f]{64})[[:space:]]nonce=([A-Za-z0-9._-]{8,128})([[:space:]]classroom=(true|false))?$ ]] || \
  fail "expected an authenticated deploy, observe-load, or capacity control request"
TARGET_SHA="${BASH_REMATCH[1]}"
EVIDENCE_B64="${BASH_REMATCH[2]}"
EVIDENCE_SIGNATURE="${BASH_REMATCH[3]}"
EVIDENCE_NONCE="${BASH_REMATCH[4]}"
CLASSROOM_ENABLED="${BASH_REMATCH[6]:-}"
DEPLOY_EVIDENCE="$(mktemp /run/pathlab-deploy-evidence-XXXXXX.json)"
chmod 600 "${DEPLOY_EVIDENCE}"
trap cleanup_exit EXIT
python3 - "${EVIDENCE_B64}" "${DEPLOY_EVIDENCE}" <<'PY' || fail "deployment evidence transfer failed"
import base64
import pathlib
import sys

encoded, destination = sys.argv[1:]
padding = "=" * (-len(encoded) % 4)
payload = base64.urlsafe_b64decode(encoded + padding)
if len(payload) > 65536:
    raise SystemExit(1)
pathlib.Path(destination).write_bytes(payload)
PY

command -v flock >/dev/null || fail "flock is required"
exec 9>"${LOCK_FILE}"
flock -n 9 || fail "another production deployment is already running"

REMOTE_MAIN_SHA="$(git ls-remote "${REPOSITORY_URL}" refs/heads/main | awk '{print $1}')"
[[ "${REMOTE_MAIN_SHA}" == "${TARGET_SHA}" ]] || \
  fail "requested commit is not the current main commit"
[[ -f "${LIVE_DIR}/deploy/.env" ]] || fail "live deploy/.env is missing"
DOMAIN="$(sed -n 's/^DOMAIN=//p' "${LIVE_DIR}/deploy/.env" | tail -n 1)"
DOMAIN="${DOMAIN%\"}"
DOMAIN="${DOMAIN#\"}"
DOMAIN="${DOMAIN%\'}"
DOMAIN="${DOMAIN#\'}"
[[ "${DOMAIN}" =~ ^[A-Za-z0-9.-]+$ ]] || fail "DOMAIN is missing or invalid"
HEALTH_URL="https://${DOMAIN}/readyz"

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
if [[ -n "${CLASSROOM_ENABLED}" ]]; then
  if grep -q '^PATHLAB_PRODUCTION_CLASSROOM_ENABLED=' "${STAGE_DIR}/deploy/.env"; then
    sed -i "s/^PATHLAB_PRODUCTION_CLASSROOM_ENABLED=.*/PATHLAB_PRODUCTION_CLASSROOM_ENABLED=${CLASSROOM_ENABLED}/" \
      "${STAGE_DIR}/deploy/.env"
  else
    printf 'PATHLAB_PRODUCTION_CLASSROOM_ENABLED=%s\n' "${CLASSROOM_ENABLED}" >> "${STAGE_DIR}/deploy/.env"
  fi
fi
printf '%s\n' "${TARGET_SHA}" > "${STAGE_DIR}/.pathlab-release"
chown -R ubuntu:ubuntu "${STAGE_DIR}"

python3 "${STAGE_DIR}/deploy/scripts/production_safety.py" \
  preflight "${DEPLOY_EVIDENCE}" "${TARGET_SHA}" \
  --signature "${EVIDENCE_SIGNATURE}" --nonce "${EVIDENCE_NONCE}" || \
  fail "production preflight guards failed"
ANNOTATIONS_ENABLED="$(sed -n 's/^PATHLAB_ANNOTATIONS_ENABLED=//p' "${STAGE_DIR}/deploy/.env" | tail -n 1)"
[[ "${ANNOTATIONS_ENABLED:-false}" == "false" ]] || fail "annotations must remain disabled"

(
  cd "${STAGE_DIR}/deploy"
  docker compose config --quiet
  docker compose build
)

deployment_check "${STAGE_DIR}" || fail "worker job is active"
OLD_WORKER_STOPPED=1
OLD_SERVICES_STOPPED=1
(
  cd "${LIVE_DIR}/deploy"
  docker compose stop worker
  docker compose stop caddy tusd
)
deployment_check "${STAGE_DIR}" || fail "worker job did not stop cleanly"

BACKUP_PATH="$(
  cd "${LIVE_DIR}/deploy"
  bash scripts/backup.sh
)" || fail "production backup failed"
python3 "${STAGE_DIR}/deploy/scripts/verify_restore_drill.py" "${BACKUP_PATH}" || \
  fail "production backup restore drill failed"

mv "${LIVE_DIR}" "${ROLLBACK_DIR}"
mv "${STAGE_DIR}" "${LIVE_DIR}"
STAGE_DIR=""
SWAPPED=1
trap rollback_release ERR

systemctl reload pathlab-viewer
systemctl is-active --quiet pathlab-viewer
WATCHDOG_CHANGED=1
bash "${LIVE_DIR}/deploy/scripts/install-watchdog.sh" install "${LIVE_DIR}"

for _ in $(seq 1 30); do
  if curl --fail --silent --show-error --max-time 5 "${HEALTH_URL}" >/dev/null && \
    curl --fail --silent --show-error --max-time 5 "https://${DOMAIN}/livez" >/dev/null; then
    break
  fi
  sleep 2
done
curl --fail --silent --show-error --max-time 5 "${HEALTH_URL}" >/dev/null
curl --fail --silent --show-error --max-time 5 "https://${DOMAIN}/livez" >/dev/null
curl --fail --silent --show-error --max-time 5 "https://${DOMAIN}/" >/dev/null
curl --fail --silent --show-error --max-time 5 -X OPTIONS \
  -H 'Tus-Resumable: 1.0.0' "https://${DOMAIN}/api/v1/uploads/" >/dev/null

RUNNING_SERVICES="$(
  cd "${LIVE_DIR}/deploy"
  docker compose ps --status running --services | sort
)"
EXPECTED_SERVICES=$'api\ncaddy\nclassroom\ntile-service\ntusd\nworker'
[[ "${RUNNING_SERVICES}" == "${EXPECTED_SERVICES}" ]] || \
  fail "not all production services are running"
for service in api classroom tile-service worker; do
  container_id="$(cd "${LIVE_DIR}/deploy" && docker compose ps -q "${service}")"
  [[ -n "${container_id}" ]] || fail "${service} container identity is missing"
  [[ "$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' \
    "${container_id}")" == healthy ]] || fail "${service} is not healthy"
done
[[ "$(cat "${LIVE_DIR}/.pathlab-release")" == "${TARGET_SHA}" ]] || \
  fail "live checkout does not match the requested commit"

trap - ERR
SWAPPED=0
OLD_WORKER_STOPPED=0
OLD_SERVICES_STOPPED=0
WATCHDOG_CHANGED=0
echo "Production deployment succeeded: ${TARGET_SHA}"
