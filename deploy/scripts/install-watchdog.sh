#!/usr/bin/env bash
set -Eeuo pipefail

ACTION="${1:-}"
RELEASE_DIR="$(realpath -m "${2:-/opt/pathlab-viewer}")"
UNIT_DIR="$(realpath -m "${PATHLAB_SYSTEMD_UNIT_DIR:-/etc/systemd/system}")"
STATE_DIR="$(realpath -m "${PATHLAB_WATCHDOG_STATE_DIR:-/var/lib/pathlab-viewer-watchdog}")"
SERVICE_UNIT="${UNIT_DIR}/pathlab-viewer-watchdog.service"
TIMER_UNIT="${UNIT_DIR}/pathlab-viewer-watchdog.timer"

if [[ "${UNIT_DIR}" == /etc/systemd/system ]]; then
  case "${RELEASE_DIR}" in
    /opt/pathlab-viewer|/opt/pathlab-viewer.rollback-*) ;;
    *) echo "Refusing unexpected release directory: ${RELEASE_DIR}" >&2; exit 2 ;;
  esac
  [[ "${STATE_DIR}" == /var/lib/pathlab-viewer-watchdog ]] || {
    echo "Refusing unexpected watchdog state directory" >&2
    exit 2
  }
else
  [[ "${STATE_DIR}" != /var/lib/pathlab-viewer-watchdog ]] || {
    echo "Non-production unit tests require an isolated state directory" >&2
    exit 2
  }
fi

WORK_DIR="$(mktemp -d)"
cleanup() { rm -rf -- "${WORK_DIR}"; }
trap cleanup EXIT

snapshot_units() {
  [[ ! -f "${SERVICE_UNIT}" ]] || cp -- "${SERVICE_UNIT}" "${WORK_DIR}/service"
  [[ ! -f "${TIMER_UNIT}" ]] || cp -- "${TIMER_UNIT}" "${WORK_DIR}/timer"
  PRIOR_ENABLED=0
  PRIOR_ACTIVE=0
  set +e
  systemctl is-enabled --quiet pathlab-viewer-watchdog.timer
  enabled_code=$?
  systemctl is-active --quiet pathlab-viewer-watchdog.timer
  active_code=$?
  set -e
  case "${enabled_code}" in 0) PRIOR_ENABLED=1 ;; 1) ;; 4)
    [[ ! -f "${TIMER_UNIT}" ]] || return "${enabled_code}" ;; *)
    return "${enabled_code}" ;;
  esac
  case "${active_code}" in 0) PRIOR_ACTIVE=1 ;; 3) ;; 4)
    [[ ! -f "${TIMER_UNIT}" ]] || return "${active_code}" ;; *)
    return "${active_code}" ;;
  esac
}

restore_snapshot() {
  local exit_code=$?
  local restore_failed=0
  trap - ERR
  systemctl disable --now pathlab-viewer-watchdog.timer >/dev/null 2>&1 || restore_failed=1
  if [[ -f "${WORK_DIR}/service" ]]; then
    install -m 0644 "${WORK_DIR}/service" "${SERVICE_UNIT}" || restore_failed=1
  else
    rm -f -- "${SERVICE_UNIT}" || restore_failed=1
  fi
  if [[ -f "${WORK_DIR}/timer" ]]; then
    install -m 0644 "${WORK_DIR}/timer" "${TIMER_UNIT}" || restore_failed=1
  else
    rm -f -- "${TIMER_UNIT}" || restore_failed=1
  fi
  systemctl daemon-reload || restore_failed=1
  if [[ "${PRIOR_ENABLED}" -eq 1 ]]; then
    systemctl enable pathlab-viewer-watchdog.timer || restore_failed=1
  fi
  if [[ "${PRIOR_ACTIVE}" -eq 1 ]]; then
    systemctl start pathlab-viewer-watchdog.timer || restore_failed=1
  fi
  if [[ "${restore_failed}" -ne 0 ]]; then
    echo "Watchdog prior state restoration failed" >&2
    exit 1
  fi
  exit "${exit_code}"
}

case "${ACTION}" in
  install)
    test -f "${RELEASE_DIR}/deploy/systemd/pathlab-viewer-watchdog.service"
    test -f "${RELEASE_DIR}/deploy/systemd/pathlab-viewer-watchdog.timer"
    snapshot_units
    trap restore_snapshot ERR
    if [[ "${UNIT_DIR}" == /etc/systemd/system ]]; then
      install -d -m 0755 "${UNIT_DIR}"
      install -d -m 0700 "${STATE_DIR}"
    else
      mkdir -p -- "${UNIT_DIR}" "${STATE_DIR}"
    fi
    install -m 0644 "${RELEASE_DIR}/deploy/systemd/pathlab-viewer-watchdog.service" \
      "${SERVICE_UNIT}"
    install -m 0644 "${RELEASE_DIR}/deploy/systemd/pathlab-viewer-watchdog.timer" \
      "${TIMER_UNIT}"
    systemctl daemon-reload
    systemctl enable --now pathlab-viewer-watchdog.timer
    trap - ERR
    ;;
  uninstall)
    snapshot_units
    trap restore_snapshot ERR
    systemctl disable --now pathlab-viewer-watchdog.timer
    rm -f -- "${SERVICE_UNIT}" "${TIMER_UNIT}"
    systemctl daemon-reload
    trap - ERR
    ;;
  *)
    echo "Usage: install-watchdog.sh install|uninstall [/opt/pathlab-viewer]" >&2
    exit 2
    ;;
esac
