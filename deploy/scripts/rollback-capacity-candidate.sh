#!/usr/bin/env bash
set -Eeuo pipefail
EXPECTED_CANDIDATE="${1:?candidate SHA required}"
ROLLBACK_SHA="${2:?rollback SHA required}"
ROLLBACK_NOT_AFTER="${3:?rollback deadline required}"
LIVE_DIR=/opt/pathlab-viewer
[[ "${EXPECTED_CANDIDATE}" =~ ^[0-9a-f]{40}$ && "${ROLLBACK_SHA}" =~ ^[0-9a-f]{40}$ ]] || exit 1
[[ "${ROLLBACK_NOT_AFTER}" =~ ^[0-9]{10}$ ]] || exit 1
remaining_seconds() {
  local remaining="$((ROLLBACK_NOT_AFTER - $(date +%s)))"
  (( remaining > 0 )) || { echo "rollback deadline elapsed" >&2; return 1; }
  printf '%s\n' "${remaining}"
}
run_bounded() {
  local remaining timeout_seconds
  remaining="$(remaining_seconds)" || return 1
  timeout_seconds="$((remaining - 5))"
  (( timeout_seconds > 0 )) || return 1
  timeout --signal=TERM --kill-after=5s "${timeout_seconds}s" "$@"
}
sleep_bounded() {
  local remaining sleep_seconds
  remaining="$(remaining_seconds)" || return 1
  (( remaining > 1 )) || return 1
  sleep_seconds=2
  (( remaining > sleep_seconds )) || sleep_seconds="$((remaining - 1))"
  sleep "${sleep_seconds}"
}
current="$(cat "${LIVE_DIR}/.pathlab-release" 2>/dev/null || true)"
[[ "${current}" == "${EXPECTED_CANDIDATE}" || "${current}" == "${ROLLBACK_SHA}" || -z "${current}" ]] || exit 1
if [[ "${current}" != "${ROLLBACK_SHA}" ]]; then
  mapfile -t candidates < <(find /opt -maxdepth 1 -type d \
    -name "pathlab-viewer.rollback-${ROLLBACK_SHA:0:12}-*" -print | sort)
  [[ "${#candidates[@]}" -ge 1 ]] || exit 1
  rollback_dir="${candidates[${#candidates[@]}-1]}"
  [[ "$(cat "${rollback_dir}/.pathlab-release")" == "${ROLLBACK_SHA}" ]] || exit 1
  [[ -f "${rollback_dir}/deploy/.env" ]] || exit 1
  rollback_services="$(cd "${rollback_dir}/deploy" && \
    run_bounded docker compose config --services | sort)"
  [[ "${rollback_services}" == $'api\ncaddy\ntile-service\ntusd\nworker' ]] || exit 1
fi
if [[ "${current}" == "${EXPECTED_CANDIDATE}" ]]; then
  (( $(remaining_seconds) >= 180 )) || { echo "insufficient rollback runway" >&2; exit 1; }
  failed="/opt/pathlab-viewer.failed-${EXPECTED_CANDIDATE}-$(date -u +%Y%m%dT%H%M%SZ)"
  [[ ! -e "${failed}" ]] || exit 1
  run_bounded bash "${LIVE_DIR}/deploy/scripts/install-watchdog.sh" uninstall "${LIVE_DIR}" >/dev/null
  ( cd "${LIVE_DIR}/deploy" && run_bounded docker compose down ) >/dev/null
  remaining_seconds >/dev/null
  mv -- "${LIVE_DIR}" "${failed}"
  current=""
fi
if [[ -z "${current}" ]]; then
  mapfile -t failed_candidates < <(find /opt -maxdepth 1 -type d \
    -name "pathlab-viewer.failed-${EXPECTED_CANDIDATE}-*" -print | sort)
  [[ "${#failed_candidates[@]}" -ge 1 ]] || exit 1
  [[ "$(cat "${failed_candidates[${#failed_candidates[@]}-1]}/.pathlab-release")" == \
    "${EXPECTED_CANDIDATE}" ]] || exit 1
  mv -- "${rollback_dir}" "${LIVE_DIR}"
fi
[[ "$(cat "${LIVE_DIR}/.pathlab-release")" == "${ROLLBACK_SHA}" ]] || exit 1
run_bounded python3 - "${LIVE_DIR}/deploy/.env" <<'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
lines = path.read_text().splitlines()
key = "PATHLAB_CLASSROOM_MAX_PARTICIPANTS="
updated = [f"{key}300" if line.startswith(key) else line for line in lines]
if not any(line.startswith(key) for line in lines):
    updated.append(f"{key}300")
temporary = path.with_suffix(".tmp")
temporary.write_text("\n".join(updated) + "\n")
temporary.chmod(path.stat().st_mode & 0o777)
temporary.replace(path)
PY
( cd "${LIVE_DIR}/deploy" && run_bounded docker compose up -d ) >/dev/null
[[ "$(cat "${LIVE_DIR}/.pathlab-release")" == "${ROLLBACK_SHA}" ]]
grep -qx 'PATHLAB_CLASSROOM_MAX_PARTICIPANTS=300' "${LIVE_DIR}/deploy/.env"
cd "${LIVE_DIR}/deploy"
services="$(run_bounded docker compose ps --services --status running | sort)"
expected_services=$'api\ncaddy\ntile-service\ntusd\nworker'
limit="$(awk -F= '/^PATHLAB_CLASSROOM_MAX_PARTICIPANTS=/{print $2; exit}' .env)"
ready=false
for _ in $(seq 1 30); do
  if run_bounded curl --fail --silent --insecure --max-time 5 https://127.0.0.1/readyz >/dev/null && \
    run_bounded curl --fail --silent --insecure --max-time 5 https://127.0.0.1/livez >/dev/null; then
    ready=true
    break
  fi
  sleep_bounded
done
watchdog=false; run_bounded systemctl is-active --quiet pathlab-viewer-watchdog.timer && watchdog=true
remaining_seconds >/dev/null
[[ "${ready}" == true && "${services}" == "${expected_services}" && "${limit}" == 300 && \
  "${watchdog}" == false ]] || exit 1
jq -n --arg release "${ROLLBACK_SHA}" --arg expected "${ROLLBACK_SHA}" \
  --argjson ready "${ready}" --argjson watchdog "${watchdog}" --argjson capacity "${limit:-0}" \
  --argjson exact "$([[ "${services}" == "${expected_services}" ]] && echo true || echo false)" \
  '{releaseSha:$release,expectedSha:$expected,releaseExact:true,servicesExact:$exact,
    serviceCount:5,ready:$ready,watchdogExpected:false,watchdogActive:$watchdog,finalCapacity:$capacity}'
