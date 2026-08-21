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
EVIDENCE_KEY_PATH="/etc/pathlab-viewer/deploy-evidence.key"
TEMP_KEY=""
STABLE_DISPATCHER="/usr/local/sbin/pathlab-viewer-deploy"
TEMP_DISPATCHER=""
BACKUP_PATH=""
DATA_DIR=""
BACKUP_DIR=""

fail() {
  echo "Deployment failed: $*" >&2
  if [[ "${SWAPPED}" -eq 1 ]]; then
    rollback_release
  fi
  restart_old_worker
  exit 1
}

interrupt_deployment() {
  trap - HUP INT TERM
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

restore_predeploy_database() {
  [[ -n "${BACKUP_PATH}" && -d "${BACKUP_PATH}" ]] || {
    echo "Deployment rollback blocked: verified pre-deployment backup is unavailable" >&2
    return 1
  }
  [[ -n "${DATA_DIR}" && -n "${BACKUP_DIR}" ]] || {
    echo "Deployment rollback blocked: data paths are unavailable" >&2
    return 1
  }
  (
    cd "${LIVE_DIR}/deploy"
    PATHLAB_DATA_DIR="${DATA_DIR}" PATHLAB_BACKUP_DIR="${BACKUP_DIR}" \
      bash "${LIVE_DIR}/deploy/scripts/restore-deploy-rollback-database.sh" \
        "${BACKUP_PATH}"
  )
}

rollback_release() {
  set +e
  trap - ERR HUP INT TERM
  echo "Health verification failed; restoring the pre-deployment database and previous release." >&2
  if [[ -d "${LIVE_DIR}" && -d "${ROLLBACK_DIR}" ]]; then
    if ! restore_predeploy_database; then
      echo "Deployment rollback failed closed: candidate release retained for schema compatibility." >&2
      systemctl restart pathlab-viewer || true
      exit 1
    fi
    failed_release="${LIVE_DIR}.failed-$(date -u +%Y%m%dT%H%M%SZ)"
    if ! mv "${LIVE_DIR}" "${failed_release}" || \
      ! mv "${ROLLBACK_DIR}" "${LIVE_DIR}"; then
      echo "Deployment rollback failed closed during release restoration." >&2
      exit 1
    fi
    systemctl reset-failed pathlab-viewer
    if systemctl is-active --quiet pathlab-viewer; then
      systemctl reload pathlab-viewer
    else
      systemctl start pathlab-viewer
    fi
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
  if [[ -n "${TEMP_KEY}" && \
    "${TEMP_KEY}" == "$(dirname "${EVIDENCE_KEY_PATH}")"/.deploy-evidence.key.* ]]; then
    rm -f -- "${TEMP_KEY}"
  fi
  if [[ -n "${TEMP_DISPATCHER}" && \
    "${TEMP_DISPATCHER}" == "$(dirname "${STABLE_DISPATCHER}")"/.pathlab-viewer-deploy.* ]]; then
    rm -f -- "${TEMP_DISPATCHER}"
  fi
}

fsync_file() {
  python3 - "$1" <<'PY'
import os
import pathlib
import sys

with pathlib.Path(sys.argv[1]).open("rb") as handle:
    os.fsync(handle.fileno())
PY
}

fsync_directory() {
  python3 - "$1" <<'PY'
import os
import sys

descriptor = os.open(sys.argv[1], os.O_RDONLY | os.O_DIRECTORY)
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
PY
}

install_stable_dispatcher() {
  local source="$1"
  local dispatcher_directory backup_dispatcher had_existing=0
  [[ -f "${source}" && ! -L "${source}" ]] || return 1
  dispatcher_directory="$(dirname "${STABLE_DISPATCHER}")"
  [[ -d "${dispatcher_directory}" ]] || return 1
  TEMP_DISPATCHER="$(mktemp "${dispatcher_directory}/.pathlab-viewer-deploy.XXXXXX")"
  backup_dispatcher="$(mktemp "${dispatcher_directory}/.pathlab-viewer-deploy.backup.XXXXXX")"
  if [[ -e "${STABLE_DISPATCHER}" ]]; then
    [[ -f "${STABLE_DISPATCHER}" && ! -L "${STABLE_DISPATCHER}" ]] || {
      rm -f -- "${backup_dispatcher}"
      return 1
    }
    install -o root -g root -m 755 "${STABLE_DISPATCHER}" "${backup_dispatcher}" || {
      rm -f -- "${backup_dispatcher}"
      return 1
    }
    had_existing=1
  else
    rm -f -- "${backup_dispatcher}"
  fi
  install -o root -g root -m 755 "${source}" "${TEMP_DISPATCHER}" || {
    rm -f -- "${backup_dispatcher}"
    return 1
  }
  fsync_file "${TEMP_DISPATCHER}" || {
    rm -f -- "${backup_dispatcher}"
    return 1
  }
  if ! mv -f -- "${TEMP_DISPATCHER}" "${STABLE_DISPATCHER}"; then
    rm -f -- "${backup_dispatcher}"
    return 1
  fi
  TEMP_DISPATCHER=""
  if ! fsync_directory "${dispatcher_directory}"; then
    if [[ "${had_existing}" -eq 1 ]]; then
      mv -f -- "${backup_dispatcher}" "${STABLE_DISPATCHER}" || true
    else
      rm -f -- "${STABLE_DISPATCHER}"
    fi
    fsync_directory "${dispatcher_directory}" || true
    return 1
  fi
  rm -f -- "${backup_dispatcher}"
}

deployment_check() {
  local release_dir="$1"
  (
    cd "${release_dir}/deploy"
    docker compose run --rm --no-deps api pathlab-admin deployment-check
  )
}

provision_evidence_key() {
  local provision_sha="$1"
  local provision_key="$2"
  local current_release_sha remote_main_sha key_directory
  [[ "${provision_sha}" =~ ^[0-9a-f]{40}$ ]] || fail "provisioning release SHA is invalid"
  [[ "${provision_key}" =~ ^[0-9a-f]{64}$ ]] || fail "deployment evidence key is invalid"
  command -v flock >/dev/null || fail "flock is required"
  exec 9>"${LOCK_FILE}"
  flock -n 9 || fail "another production deployment is already running"
  current_release_sha="$(tr -d '\r\n' < "${LIVE_DIR}/.pathlab-release" 2>/dev/null || true)"
  [[ "${current_release_sha}" == "${provision_sha}" ]] || \
    fail "evidence key provisioning is not bound to the live release"
  if [[ "${PATHLAB_DEPLOY_RELEASE_LIBRARY_ONLY:-}" == 1 && \
    -n "${PATHLAB_DEPLOY_TEST_REMOTE_MAIN_SHA:-}" ]]; then
    remote_main_sha="${PATHLAB_DEPLOY_TEST_REMOTE_MAIN_SHA}"
  else
    remote_main_sha="$(git ls-remote "${REPOSITORY_URL}" refs/heads/main | awk '{print $1}')"
  fi
  [[ "${remote_main_sha}" == "${provision_sha}" ]] || \
    fail "evidence key provisioning is not bound to current main"
  key_directory="$(dirname "${EVIDENCE_KEY_PATH}")"
  install -d -m 755 "${key_directory}"
  if [[ -e "${EVIDENCE_KEY_PATH}" ]]; then
    [[ ! -L "${EVIDENCE_KEY_PATH}" && -f "${EVIDENCE_KEY_PATH}" ]] || \
      fail "existing deployment evidence key is not a regular file"
    [[ "$(cat "${EVIDENCE_KEY_PATH}")" == "${provision_key}" ]] || \
      fail "a different deployment evidence key is already provisioned"
    if [[ "${EUID}" -eq 0 ]]; then
      chown root:root "${EVIDENCE_KEY_PATH}"
    fi
    chmod 600 "${EVIDENCE_KEY_PATH}"
    echo "Deployment evidence key provisioned for ${provision_sha}"
    return 0
  fi
  TEMP_KEY="$(mktemp "${key_directory}/.deploy-evidence.key.XXXXXX")"
  trap cleanup_exit EXIT
  printf '%s' "${provision_key}" > "${TEMP_KEY}"
  chmod 600 "${TEMP_KEY}"
  if [[ "${EUID}" -eq 0 ]]; then
    chown root:root "${TEMP_KEY}"
  fi
  python3 - "${TEMP_KEY}" <<'PY'
import os
import pathlib
import sys

with pathlib.Path(sys.argv[1]).open("rb") as handle:
    os.fsync(handle.fileno())
PY
  mv -f -- "${TEMP_KEY}" "${EVIDENCE_KEY_PATH}"
  TEMP_KEY=""
  chmod 600 "${EVIDENCE_KEY_PATH}"
  python3 - "${key_directory}" <<'PY'
import os
import sys

descriptor = os.open(sys.argv[1], os.O_RDONLY | os.O_DIRECTORY)
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
PY
  echo "Deployment evidence key provisioned for ${provision_sha}"
}

if [[ "${PATHLAB_DEPLOY_RELEASE_LIBRARY_ONLY:-}" == 1 ]]; then
  return 0 2>/dev/null || exit 0
fi

[[ "${EUID}" -eq 0 ]] || fail "this script must run as root"
if [[ "${REQUEST}" =~ ^provision-evidence-key[[:space:]]sha=([0-9a-f]{40})$ ]]; then
  PROVISION_SHA="${BASH_REMATCH[1]}"
  IFS= read -r PROVISION_KEY || fail "deployment evidence key was not provided on standard input"
  [[ "${PROVISION_KEY}" =~ ^[0-9a-f]{64}$ ]] || fail "deployment evidence key is invalid"
  if IFS= read -r _EXTRA_PROVISION_INPUT; then
    fail "unexpected additional evidence key input"
  fi
  CURRENT_RELEASE_SHA="$(tr -d '\r\n' < "${LIVE_DIR}/.pathlab-release" 2>/dev/null || true)"
  [[ "${CURRENT_RELEASE_SHA}" == "${PROVISION_SHA}" ]] || \
    fail "evidence key provisioning is not bound to the live release"
  provision_evidence_key "${PROVISION_SHA}" "${PROVISION_KEY}"
  exit 0
fi
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
  || "${REQUEST}" == capacity-ack\ * \
  || "${REQUEST}" == capacity-postflight\ * || "${REQUEST}" == capacity-rollback-preflight\ * ]]; then
  if [[ -f /run/pathlab-capacity-controller ]]; then
    CONTROLLER_DIR="$(cat /run/pathlab-capacity-controller)"
    [[ "${CONTROLLER_DIR}" =~ ^/run/pathlab-capacity-[a-z0-9-]{1,64}-controller$ && \
      -x "${CONTROLLER_DIR}/capacity-control-host.sh" ]] || \
      fail "stable capacity controller binding is invalid"
    exec bash "${CONTROLLER_DIR}/capacity-control-host.sh" "${REQUEST}"
  fi
  exec bash "${LIVE_DIR}/deploy/scripts/capacity-control-host.sh" "${REQUEST}"
fi

[[ "${REQUEST}" =~ ^deploy[[:space:]]([0-9a-f]{40})[[:space:]]evidence=([A-Za-z0-9_-]+)[[:space:]]signature=([0-9a-f]{64})[[:space:]]nonce=([A-Za-z0-9._-]{8,128})([[:space:]]classroom=(true|false))?$ ]] || \
  fail "expected an authenticated deploy, one-time evidence-key provision, observe-load, or capacity control request"
TARGET_SHA="${BASH_REMATCH[1]}"
EVIDENCE_B64="${BASH_REMATCH[2]}"
EVIDENCE_SIGNATURE="${BASH_REMATCH[3]}"
EVIDENCE_NONCE="${BASH_REMATCH[4]}"
CLASSROOM_ENABLED="${BASH_REMATCH[6]:-}"
DEPLOY_EVIDENCE="$(mktemp /run/pathlab-deploy-evidence-XXXXXX.json)"
chmod 600 "${DEPLOY_EVIDENCE}"
trap cleanup_exit EXIT
trap interrupt_deployment HUP INT TERM
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
if grep -q '^PATHLAB_RELEASE_IMAGE_TAG=' "${STAGE_DIR}/deploy/.env"; then
  sed -i "s/^PATHLAB_RELEASE_IMAGE_TAG=.*/PATHLAB_RELEASE_IMAGE_TAG=${TARGET_SHA}/" \
    "${STAGE_DIR}/deploy/.env"
else
  printf 'PATHLAB_RELEASE_IMAGE_TAG=%s\n' "${TARGET_SHA}" >> "${STAGE_DIR}/deploy/.env"
fi
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
if [[ "${ANNOTATIONS_ENABLED:-false}" == "true" ]]; then
  ACTIVATION="/var/lib/pathlab-viewer/annotation-activation.json"
  ACTIVATION_SIGNATURE="${ACTIVATION}.sig"
  for protected in "${ACTIVATION}" "${ACTIVATION_SIGNATURE}"; do
    [[ -f "${protected}" && ! -L "${protected}" && "$(stat -c '%U:%G:%a' "${protected}")" == "root:root:600" ]] || \
      fail "annotation activation evidence is unavailable or unsafe"
  done
  python3 "${STAGE_DIR}/deploy/scripts/production_safety.py" \
    annotation-activation "${ACTIVATION}" --signature "$(cat "${ACTIVATION_SIGNATURE}")" || \
    fail "annotations lack a valid strict capacity certification"
else
  [[ "${ANNOTATIONS_ENABLED:-false}" == "false" ]] || fail "annotation feature state is invalid"
fi
DATA_DIR="$(sed -n 's/^PATHLAB_DATA_DIR=//p' "${STAGE_DIR}/deploy/.env" | tail -n 1)"
[[ -n "${DATA_DIR}" ]] || fail "PATHLAB_DATA_DIR must be explicit in production"
DATA_DIR="${DATA_DIR%\"}"
DATA_DIR="${DATA_DIR#\"}"
DATA_DIR="${DATA_DIR%\'}"
DATA_DIR="${DATA_DIR#\'}"
[[ "${DATA_DIR}" =~ ^/[A-Za-z0-9._/-]+$ && "${DATA_DIR}" != */../* ]] || \
  fail "PATHLAB_DATA_DIR is missing or invalid"
BACKUP_DIR="${DATA_DIR%/}/backups"
RESTORE_DRILL_DIR="${DATA_DIR%/}/.restore-drill"

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
  cd "${STAGE_DIR}/deploy"
  PATHLAB_DATA_DIR="${DATA_DIR}" PATHLAB_BACKUP_DIR="${BACKUP_DIR}" \
    bash "${STAGE_DIR}/deploy/scripts/backup.sh"
)" || fail "production backup failed"
PATHLAB_DATA_DIR="${DATA_DIR}" PATHLAB_BACKUP_DIR="${BACKUP_DIR}" \
  PATHLAB_RESTORE_DRILL_DIR="${RESTORE_DRILL_DIR}" \
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
install_stable_dispatcher "${LIVE_DIR}/deploy/scripts/deploy-release.sh" || \
  fail "stable forced-command dispatcher refresh failed"

trap - ERR
SWAPPED=0
OLD_WORKER_STOPPED=0
OLD_SERVICES_STOPPED=0
WATCHDOG_CHANGED=0
echo "Production deployment succeeded: ${TARGET_SHA}"
