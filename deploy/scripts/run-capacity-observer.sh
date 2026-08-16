#!/usr/bin/env bash
set -Eeuo pipefail

PLAN_PATH="${1:?plan path is required}"
OUTPUT_PATH="${2:?observer output path is required}"
DONE_PATH="${OUTPUT_PATH}.done"
run_id="$(jq -r .runId "${PLAN_PATH}")"
digest="$(jq -r .planDigest "${PLAN_PATH}")"
start_epoch="$(jq -r '.startEpochMs / 1000 | floor' "${PLAN_PATH}")"
session_id="$(jq -er 'to_entries[0].value.sessionId' "${PATHLAB_CLASSROOM_STAGE_MANIFEST}")"
[[ "${run_id}" =~ ^[a-z0-9-]{1,64}$ && "${digest}" =~ ^[0-9a-f]{64}$ ]] || exit 1
rm -f -- "${OUTPUT_PATH}" "${DONE_PATH}"

observer_pid=""
cleanup() {
  local result=$?
  trap - EXIT INT TERM
  [[ -z "${observer_pid}" ]] || kill "${observer_pid}" >/dev/null 2>&1 || true
  if [[ "${result}" -ne 0 ]]; then
    bash deploy/scripts/capacity-control-via-bastion.sh \
      "capacity-abort run=${run_id} digest=${digest}" >/dev/null 2>&1 || true
  fi
  exit "${result}"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

(
  set +e
  bash deploy/scripts/observe-via-bastion.sh 9340 "${start_epoch}" > "${OUTPUT_PATH}"
  printf '%s\n' "$?" > "${DONE_PATH}"
) &
observer_pid="$!"
python tests/load/monitor_distributed_observer.py \
  --plan "${PLAN_PATH}" --observer "${OUTPUT_PATH}" --done "${DONE_PATH}" \
  --session-id "${session_id}"
wait "${observer_pid}"
observer_pid=""
trap - EXIT
