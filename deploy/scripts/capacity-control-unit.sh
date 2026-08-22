#!/usr/bin/env bash
set -Eeuo pipefail

RUN_ID="${1:?run ID is required}"
WORKFLOW_SHA="${2:?workflow SHA is required}"
PLAN_DIGEST="${3:?plan digest is required}"
NONCE_FILE="${4:?nonce file is required}"
PREFLIGHT_EVIDENCE="${5:?preflight evidence is required}"
PREFLIGHT_SIGNATURE_FILE="${6:?preflight signature file is required}"
RUNTIME_MANIFEST_DIGEST="${7:?runtime manifest digest is required}"
RESTORE_NOT_AFTER="${8:?restore deadline is required}"
CONTROLLER_DIR="${9:?stable controller directory is required}"
INTERRUPT_STATUS=0
CHILD_PID=""
STATE_DIR="${PATHLAB_CAPACITY_RUNTIME_DIR:-/run}"
LIVE_DIR="${PATHLAB_LIVE_DIR:-/opt/pathlab-viewer}"
DECISION_FILE="${STATE_DIR}/pathlab-capacity-${RUN_ID}.json"
DECISION_SIGNATURE_FILE="${DECISION_FILE}.sig"
RESTORE_EVIDENCE="${STATE_DIR}/pathlab-capacity-${RUN_ID}-restore.json"
RUNTIME_EVIDENCE="${STATE_DIR}/pathlab-capacity-${RUN_ID}-runtime.json"
FINAL_EVIDENCE="${STATE_DIR}/pathlab-capacity-${RUN_ID}-final.json"
CONTROL_STATE="${STATE_DIR}/pathlab-capacity-${RUN_ID}-control.json"
RESTORE_SCRIPT="${STATE_DIR}/pathlab-capacity-${RUN_ID}-restore.sh"
START_EPOCH="$(date +%s)"
[[ "${CONTROLLER_DIR}" == "${STATE_DIR}/pathlab-capacity-${RUN_ID}-controller" ]] || exit 2
[[ "${NONCE_FILE}" == "${STATE_DIR}/pathlab-capacity-${RUN_ID}-nonce" ]] || exit 2
[[ "${PREFLIGHT_SIGNATURE_FILE}" == "${PREFLIGHT_EVIDENCE}.sig" ]] || exit 2
NONCE="$(cat "${NONCE_FILE}")"
PREFLIGHT_SIGNATURE="$(cat "${PREFLIGHT_SIGNATURE_FILE}")"

restore_safe_runtime() {
  local remaining temporary
  [[ "$(cat "${LIVE_DIR}/.pathlab-release" 2>/dev/null || true)" == "${WORKFLOW_SHA}" ]] || return 1
  while :; do
    remaining="$((RESTORE_NOT_AFTER - $(date +%s)))"
    (( remaining > 10 )) || return 1
    temporary="${RUNTIME_EVIDENCE}.tmp"
    if timeout --signal=TERM --kill-after=10s "$((remaining - 5))s" \
      bash "${RESTORE_SCRIPT}" \
        "${WORKFLOW_SHA}" "${RUNTIME_MANIFEST_DIGEST}" "${RESTORE_NOT_AFTER}" \
        > "${temporary}"; then
      chmod 600 "${temporary}"
      mv -- "${temporary}" "${RUNTIME_EVIDENCE}"
      return 0
    fi
    rm -f -- "${temporary}"
    remaining="$((RESTORE_NOT_AFTER - $(date +%s)))"
    (( remaining > 12 )) || return 1
    sleep 2
  done
}

write_final_result() {
  local temporary="${FINAL_EVIDENCE}.tmp"
  if [[ -s "${RUNTIME_EVIDENCE}" ]]; then
    jq -s '.[0] + .[1]' \
      <(jq '{runId,workflowSha,planDigest,deadlineEpoch,runtimeManifestDigest,restoreNotAfter,
        windowStartEpoch,windowEndEpoch,phase,finalLimit,faultConsumed}' "${CONTROL_STATE}") \
      "${RUNTIME_EVIDENCE}" > "${temporary}"
  else
    jq '{runId,workflowSha,planDigest,deadlineEpoch,runtimeManifestDigest,restoreNotAfter,
      windowStartEpoch,windowEndEpoch,phase,finalLimit,faultConsumed}' \
      "${CONTROL_STATE}" > "${temporary}"
  fi
  chmod 600 "${temporary}"
  mv -- "${temporary}" "${FINAL_EVIDENCE}"
}

finish_failed() {
  local result=$?
  local restored=()
  if [[ -f "${RESTORE_EVIDENCE}" ]] && \
    timeout --signal=TERM --kill-after=2s 5s python3 - "${RESTORE_EVIDENCE}" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
raise SystemExit(0 if value.get("configurationRestored") is True and value.get("servicesReady") is True else 1)
PY
  then
    restored=(--restoration-verified)
  fi
  timeout --signal=TERM --kill-after=2s 5s \
    python3 "${LIVE_DIR}/deploy/scripts/capacity_control.py" --state-dir "${STATE_DIR}" \
    finish --run-id "${RUN_ID}" "${restored[@]}" >/dev/null 2>&1 || true
  rm -f -- "${NONCE_FILE}" "${PREFLIGHT_EVIDENCE}" "${PREFLIGHT_SIGNATURE_FILE}" \
    "${DECISION_FILE}" "${DECISION_SIGNATURE_FILE}" "${RESTORE_EVIDENCE}"
  if restore_safe_runtime; then
    python3 "${LIVE_DIR}/deploy/scripts/capacity_control.py" --state-dir "${STATE_DIR}" \
      finish --run-id "${RUN_ID}" --restoration-verified >/dev/null 2>&1 || true
    write_final_result || true
  fi
  exit "${result}"
}
trap finish_failed EXIT

forward_interrupt() {
  INTERRUPT_STATUS="$2"
  if [[ -n "${CHILD_PID}" ]]; then
    kill -TERM -- "-${CHILD_PID}" 2>/dev/null || true
  fi
}
trap 'forward_interrupt INT 130' INT
trap 'forward_interrupt TERM 143' TERM
trap 'forward_interrupt USR1 143' USR1

[[ "$(cat "${LIVE_DIR}/.pathlab-release" 2>/dev/null || true)" == "${WORKFLOW_SHA}" ]] || exit 2
install -m 700 "${LIVE_DIR}/deploy/scripts/restore-capacity-runtime.sh" "${RESTORE_SCRIPT}"
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
PATHLAB_CAPACITY_RESTORE_NOT_AFTER="$((RESTORE_NOT_AFTER - 210))" \
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
restore_safe_runtime
write_final_result
trap - EXIT
rm -f -- "${NONCE_FILE}" "${PREFLIGHT_EVIDENCE}" "${PREFLIGHT_SIGNATURE_FILE}" \
  "${DECISION_FILE}" "${DECISION_SIGNATURE_FILE}" "${RESTORE_EVIDENCE}"
