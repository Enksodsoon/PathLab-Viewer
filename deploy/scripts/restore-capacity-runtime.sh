#!/usr/bin/env bash
set -Eeuo pipefail

EXPECTED_SHA="${1:?expected release SHA is required}"
MANIFEST_DIGEST="${2:?runtime manifest digest is required}"
RESTORE_NOT_AFTER="${3:?restore deadline is required}"
LIVE_DIR="${PATHLAB_LIVE_DIR:-/opt/pathlab-viewer}"

[[ "${EXPECTED_SHA}" =~ ^[0-9a-f]{40}$ ]] || exit 2
[[ "${MANIFEST_DIGEST}" =~ ^[0-9a-f]{64}$ ]] || exit 2
[[ "${RESTORE_NOT_AFTER}" =~ ^[0-9]{10}$ ]] || exit 2
if [[ "${LIVE_DIR}" != /opt/pathlab-viewer ]]; then
  [[ "${PATHLAB_CAPACITY_TEST_MODE:-}" == true ]] || exit 2
fi

remaining_seconds() {
  local remaining="$((RESTORE_NOT_AFTER - $(date +%s)))"
  (( remaining > 0 )) || { echo "capacity restore deadline elapsed" >&2; return 1; }
  printf '%s\n' "${remaining}"
}

run_bounded() {
  local remaining timeout_seconds
  remaining="$(remaining_seconds)" || return 1
  timeout_seconds="$((remaining - 5))"
  (( timeout_seconds > 0 )) || return 1
  timeout --signal=TERM --kill-after=5s "${timeout_seconds}s" "$@"
}

compose() {
  run_bounded bash "${LIVE_DIR}/deploy/scripts/compose-pathlab.sh" "$@"
}

contain_unsafe_runtime() {
  compose stop api classroom >/dev/null 2>&1 || true
}

restore_failed() {
  local result=$?
  trap - EXIT
  contain_unsafe_runtime
  echo "Capacity restoration failed; API and Classroom were stopped" >&2
  exit "${result}"
}
trap restore_failed EXIT

[[ "$(tr -d '\r\n' < "${LIVE_DIR}/.pathlab-release" 2>/dev/null || true)" == "${EXPECTED_SHA}" ]] || \
  { echo "capacity restore release mismatch" >&2; exit 1; }
[[ -f "${LIVE_DIR}/.pathlab-runtime-safety.json" && \
   ! -L "${LIVE_DIR}/.pathlab-runtime-safety.json" ]] || exit 1
[[ "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["manifestDigest"])' \
  "${LIVE_DIR}/.pathlab-runtime-safety.json")" == "${MANIFEST_DIGEST}" ]] || exit 1

run_bounded python3 - "${LIVE_DIR}/deploy/.env" <<'PY'
import os
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
updates = {
    "PATHLAB_PRODUCTION_CLASSROOM_ENABLED": "true",
    "PATHLAB_CLASSROOM_MAX_PARTICIPANTS": "300",
    "PATHLAB_ANNOTATIONS_ENABLED": "false",
}
seen = set()
lines = []
for line in path.read_text(encoding="utf-8").splitlines():
    name = line.split("=", 1)[0] if "=" in line else ""
    if name in updates:
        if name not in seen:
            lines.append(f"{name}={updates[name]}")
            seen.add(name)
    else:
        lines.append(line)
for name, value in updates.items():
    if name not in seen:
        lines.append(f"{name}={value}")
temporary = path.with_suffix(path.suffix + ".capacity-restore")
temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
temporary.chmod(path.stat().st_mode & 0o777)
os.replace(temporary, path)
PY

compose up -d >/dev/null
run_bounded bash "${LIVE_DIR}/deploy/scripts/install-watchdog.sh" install "${LIVE_DIR}" >/dev/null

status=""
verify_err="${RUNNER_TEMP:-/tmp}/runtime-safety-verify-$$.err"
while (( $(remaining_seconds) > 8 )); do
  if status="$(run_bounded python3 "${LIVE_DIR}/deploy/scripts/runtime_safety_manifest.py" \
      verify-live --live-dir "${LIVE_DIR}" --expected-sha "${EXPECTED_SHA}" \
      --manifest-digest "${MANIFEST_DIGEST}" --require-safe 2>"${verify_err}")"; then
    break
  fi
  sleep 2
done
if [[ -z "${status}" ]]; then
  if [[ -f "${verify_err}" ]]; then
    cat "${verify_err}" >&2
    rm -f -- "${verify_err}"
  fi
  exit 1
fi
rm -f -- "${verify_err}"
trap - EXIT
printf '%s\n' "${status}"
