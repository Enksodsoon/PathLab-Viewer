#!/usr/bin/env bash
set -Eeuo pipefail

RUN_ID="${1:?run ID is required}"
WORKFLOW_SHA="${2:?workflow SHA is required}"
PLAN_DIGEST="${3:?plan digest is required}"
NONCE_FILE="${4:?nonce file is required}"
PREFLIGHT_EVIDENCE="${5:?preflight evidence is required}"
PREFLIGHT_SIGNATURE_FILE="${6:?preflight signature file is required}"
STATE_DIR="${PATHLAB_CAPACITY_RUNTIME_DIR:-/run}"
LIVE_DIR="${PATHLAB_LIVE_DIR:-/opt/pathlab-viewer}"
DECISION_FILE="${STATE_DIR}/pathlab-capacity-${RUN_ID}.json"
DECISION_SIGNATURE_FILE="${DECISION_FILE}.sig"
RESTORE_EVIDENCE="${STATE_DIR}/pathlab-capacity-${RUN_ID}-restore.json"
START_EPOCH="$(date +%s)"
[[ "${NONCE_FILE}" == "${STATE_DIR}/pathlab-capacity-${RUN_ID}-nonce" ]] || exit 2
[[ "${PREFLIGHT_SIGNATURE_FILE}" == "${PREFLIGHT_EVIDENCE}.sig" ]] || exit 2
NONCE="$(cat "${NONCE_FILE}")"
PREFLIGHT_SIGNATURE="$(cat "${PREFLIGHT_SIGNATURE_FILE}")"

finish_failed() {
  RESTORED_FLAG=()
  if [[ -f "${RESTORE_EVIDENCE}" ]] && \
    python3 - "${RESTORE_EVIDENCE}" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
raise SystemExit(0 if value.get("configurationRestored") is True and value.get("servicesReady") is True else 1)
PY
  then
    RESTORED_FLAG=(--restoration-verified)
  fi
  python3 "${LIVE_DIR}/deploy/scripts/capacity_control.py" --state-dir "${STATE_DIR}" \
    finish --run-id "${RUN_ID}" "${RESTORED_FLAG[@]}" >/dev/null 2>&1 || true
  rm -f -- "${NONCE_FILE}" "${PREFLIGHT_EVIDENCE}" "${PREFLIGHT_SIGNATURE_FILE}" \
    "${DECISION_FILE}" "${DECISION_SIGNATURE_FILE}" "${RESTORE_EVIDENCE}"
}
trap finish_failed EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

[[ "$(cat "${LIVE_DIR}/.pathlab-release" 2>/dev/null || true)" == "${WORKFLOW_SHA}" ]] || exit 2

PATHLAB_CAPACITY_DECISION_FILE="${DECISION_FILE}" \
PATHLAB_CAPACITY_DECISION_SIGNATURE_FILE="${DECISION_SIGNATURE_FILE}" \
PATHLAB_CAPACITY_PREFLIGHT_EVIDENCE="${PREFLIGHT_EVIDENCE}" \
PATHLAB_CAPACITY_PREFLIGHT_SIGNATURE="${PREFLIGHT_SIGNATURE}" \
PATHLAB_CAPACITY_CANDIDATE_SHA="${WORKFLOW_SHA}" \
PATHLAB_CAPACITY_RUN_ID="${RUN_ID}" \
PATHLAB_CAPACITY_NONCE="${NONCE}" \
PATHLAB_CAPACITY_RESTORE_EVIDENCE="${RESTORE_EVIDENCE}" \
bash "${LIVE_DIR}/deploy/scripts/with-capacity-override.sh" \
  python3 "${LIVE_DIR}/deploy/scripts/capacity_control.py" --state-dir "${STATE_DIR}" hold \
    --run-id "${RUN_ID}" --workflow-sha "${WORKFLOW_SHA}" \
    --plan-digest "${PLAN_DIGEST}" --nonce "${NONCE}" \
    --decision-output "${DECISION_FILE}" --signature-output "${DECISION_SIGNATURE_FILE}"

FINAL_LIMIT="$(python3 "${LIVE_DIR}/deploy/scripts/production_safety.py" \
  capacity-decision "${DECISION_FILE}" "${WORKFLOW_SHA}" \
  --signature "$(cat "${DECISION_SIGNATURE_FILE}")" --run-id "${RUN_ID}" \
  --nonce "${NONCE}" --not-before "${START_EPOCH}")"
python3 "${LIVE_DIR}/deploy/scripts/capacity_control.py" --state-dir "${STATE_DIR}" \
  finish --run-id "${RUN_ID}" --success --final-limit "${FINAL_LIMIT}"
trap - EXIT
rm -f -- "${NONCE_FILE}" "${PREFLIGHT_EVIDENCE}" "${PREFLIGHT_SIGNATURE_FILE}" \
  "${DECISION_FILE}" "${DECISION_SIGNATURE_FILE}" "${RESTORE_EVIDENCE}"
