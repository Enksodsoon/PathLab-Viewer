#!/usr/bin/env bash
set -Eeuo pipefail

RUN_ID="${1:?run ID is required}"
WORKFLOW_SHA="${2:?workflow SHA is required}"
PLAN_DIGEST="${3:?plan digest is required}"
NONCE_FILE="${4:?nonce file is required}"
PREFLIGHT_EVIDENCE="${5:?preflight evidence is required}"
PREFLIGHT_SIGNATURE_FILE="${6:?preflight signature file is required}"
ROLLBACK_SHA="${7:?rollback SHA is required}"
ROLLBACK_NOT_AFTER="${8:?rollback deadline is required}"
CONTROLLER_DIR="${9:?stable controller directory is required}"
INTERRUPT_STATUS=0
CHILD_PID=""
STATE_DIR="${PATHLAB_CAPACITY_RUNTIME_DIR:-/run}"
LIVE_DIR="${PATHLAB_LIVE_DIR:-/opt/pathlab-viewer}"
DECISION_FILE="${STATE_DIR}/pathlab-capacity-${RUN_ID}.json"
DECISION_SIGNATURE_FILE="${DECISION_FILE}.sig"
RESTORE_EVIDENCE="${STATE_DIR}/pathlab-capacity-${RUN_ID}-restore.json"
ROLLBACK_EVIDENCE="${STATE_DIR}/pathlab-capacity-${RUN_ID}-rollback.json"
FINAL_EVIDENCE="${STATE_DIR}/pathlab-capacity-${RUN_ID}-final.json"
CONTROL_STATE="${STATE_DIR}/pathlab-capacity-${RUN_ID}-control.json"
RECOVERY_SCRIPT="${STATE_DIR}/pathlab-capacity-${RUN_ID}-rollback.sh"
START_EPOCH="$(date +%s)"
[[ "${CONTROLLER_DIR}" == "${STATE_DIR}/pathlab-capacity-${RUN_ID}-controller" ]] || exit 2
[[ "${NONCE_FILE}" == "${STATE_DIR}/pathlab-capacity-${RUN_ID}-nonce" ]] || exit 2
[[ "${PREFLIGHT_SIGNATURE_FILE}" == "${PREFLIGHT_EVIDENCE}.sig" ]] || exit 2
NONCE="$(cat "${NONCE_FILE}")"
PREFLIGHT_SIGNATURE="$(cat "${PREFLIGHT_SIGNATURE_FILE}")"

rollback_failed_candidate() {
  local current remaining temporary
  current="$(cat "${LIVE_DIR}/.pathlab-release" 2>/dev/null || true)"
  [[ "${current}" == "${WORKFLOW_SHA}" || "${current}" == "${ROLLBACK_SHA}" || -z "${current}" ]] || \
    return 1
  while :; do
    remaining="$((ROLLBACK_NOT_AFTER - $(date +%s)))"
    (( remaining > 10 )) || return 1
    temporary="${ROLLBACK_EVIDENCE}.tmp"
    if timeout --signal=TERM --kill-after=10s "$((remaining - 10))s" \
      bash "${RECOVERY_SCRIPT}" \
        "${WORKFLOW_SHA}" "${ROLLBACK_SHA}" "${ROLLBACK_NOT_AFTER}" > "${temporary}"; then
      chmod 600 "${temporary}"
      mv -- "${temporary}" "${ROLLBACK_EVIDENCE}"
      return 0
    fi
    rm -f -- "${temporary}"
    remaining="$((ROLLBACK_NOT_AFTER - $(date +%s)))"
    (( remaining > 12 )) || return 1
    sleep 2
  done
}

write_final_result() {
  local temporary="${FINAL_EVIDENCE}.tmp"
  if [[ -s "${ROLLBACK_EVIDENCE}" ]]; then
    jq -s '.[0] + .[1]' \
      <(jq '{runId,workflowSha,planDigest,deadlineEpoch,rollbackSha,rollbackNotAfter,
        windowStartEpoch,windowEndEpoch,phase,finalLimit,faultConsumed}' "${CONTROL_STATE}") \
      "${ROLLBACK_EVIDENCE}" > "${temporary}"
  else
    jq '{runId,workflowSha,planDigest,deadlineEpoch,rollbackSha,rollbackNotAfter,
      windowStartEpoch,windowEndEpoch,phase,finalLimit,faultConsumed}' "${CONTROL_STATE}" > "${temporary}"
  fi
  chmod 600 "${temporary}"
  mv -- "${temporary}" "${FINAL_EVIDENCE}"
}

finish_failed() {
  local result=$?
  RESTORED_FLAG=()
  if [[ -f "${RESTORE_EVIDENCE}" ]] && \
    timeout --signal=TERM --kill-after=2s 5s python3 - "${RESTORE_EVIDENCE}" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
raise SystemExit(0 if value.get("configurationRestored") is True and value.get("servicesReady") is True else 1)
PY
  then
    RESTORED_FLAG=(--restoration-verified)
  fi
  timeout --signal=TERM --kill-after=2s 5s \
    python3 "${LIVE_DIR}/deploy/scripts/capacity_control.py" --state-dir "${STATE_DIR}" \
    finish --run-id "${RUN_ID}" "${RESTORED_FLAG[@]}" >/dev/null 2>&1 || true
  rm -f -- "${NONCE_FILE}" "${PREFLIGHT_EVIDENCE}" "${PREFLIGHT_SIGNATURE_FILE}" \
    "${DECISION_FILE}" "${DECISION_SIGNATURE_FILE}" "${RESTORE_EVIDENCE}"
  if rollback_failed_candidate; then
    write_final_result || true
  fi
  exit "${result}"
}
trap finish_failed EXIT
forward_interrupt() {
  local signal="${1}" status="${2}"
  INTERRUPT_STATUS="${status}"
  if [[ -n "${CHILD_PID}" ]]; then
    kill -TERM -- "-${CHILD_PID}" 2>/dev/null || true
  fi
}
trap 'forward_interrupt INT 130' INT
trap 'forward_interrupt TERM 143' TERM
trap 'forward_interrupt USR1 143' USR1

[[ "$(cat "${LIVE_DIR}/.pathlab-release" 2>/dev/null || true)" == "${WORKFLOW_SHA}" ]] || exit 2
install -m 700 "${LIVE_DIR}/deploy/scripts/rollback-capacity-candidate.sh" "${RECOVERY_SCRIPT}"
WINDOW_START_EPOCH="$(jq -er .windowStartEpoch "${CONTROL_STATE}")"
WINDOW_END_EPOCH="$(jq -er .windowEndEpoch "${CONTROL_STATE}")"

PATHLAB_CAPACITY_DECISION_FILE="${DECISION_FILE}" \
PATHLAB_CAPACITY_DECISION_SIGNATURE_FILE="${DECISION_SIGNATURE_FILE}" \
PATHLAB_CAPACITY_PREFLIGHT_EVIDENCE="${PREFLIGHT_EVIDENCE}" \
PATHLAB_CAPACITY_PREFLIGHT_SIGNATURE="${PREFLIGHT_SIGNATURE}" \
PATHLAB_CAPACITY_CANDIDATE_SHA="${WORKFLOW_SHA}" \
PATHLAB_CAPACITY_RUN_ID="${RUN_ID}" \
PATHLAB_CAPACITY_NONCE="${NONCE}" \
PATHLAB_CAPACITY_RESTORE_EVIDENCE="${RESTORE_EVIDENCE}" \
PATHLAB_CAPACITY_RESTORE_NOT_AFTER="$((ROLLBACK_NOT_AFTER - 210))" \
PATHLAB_CAPACITY_WINDOW_START_EPOCH="${WINDOW_START_EPOCH}" \
PATHLAB_CAPACITY_WINDOW_END_EPOCH="${WINDOW_END_EPOCH}" \
setsid bash "${LIVE_DIR}/deploy/scripts/with-capacity-override.sh" \
  python3 "${LIVE_DIR}/deploy/scripts/capacity_control.py" --state-dir "${STATE_DIR}" hold \
    --run-id "${RUN_ID}" --workflow-sha "${WORKFLOW_SHA}" \
    --plan-digest "${PLAN_DIGEST}" --nonce "${NONCE}" \
    --decision-output "${DECISION_FILE}" --signature-output "${DECISION_SIGNATURE_FILE}" &
CHILD_PID="$!"
set +e
wait "${CHILD_PID}"
CHILD_STATUS="$?"
while kill -0 "${CHILD_PID}" 2>/dev/null; do
  wait "${CHILD_PID}"
  CHILD_STATUS="$?"
done
set -e
(( INTERRUPT_STATUS == 0 )) || exit "${INTERRUPT_STATUS}"
(( CHILD_STATUS == 0 )) || exit "${CHILD_STATUS}"

FINAL_LIMIT="$(python3 "${LIVE_DIR}/deploy/scripts/production_safety.py" \
  capacity-decision "${DECISION_FILE}" "${WORKFLOW_SHA}" \
  --signature "$(cat "${DECISION_SIGNATURE_FILE}")" --run-id "${RUN_ID}" \
  --nonce "${NONCE}" --not-before "${START_EPOCH}")"
python3 "${LIVE_DIR}/deploy/scripts/capacity_control.py" --state-dir "${STATE_DIR}" \
  finish --run-id "${RUN_ID}" --success --final-limit "${FINAL_LIMIT}"
if [[ "${FINAL_LIMIT}" == 300 ]]; then
  rollback_failed_candidate
fi
write_final_result
trap - EXIT
rm -f -- "${NONCE_FILE}" "${PREFLIGHT_EVIDENCE}" "${PREFLIGHT_SIGNATURE_FILE}" \
  "${DECISION_FILE}" "${DECISION_SIGNATURE_FILE}" "${RESTORE_EVIDENCE}"
