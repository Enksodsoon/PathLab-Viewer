#!/usr/bin/env bash
set -Eeuo pipefail

REQUEST="${1:-${SSH_ORIGINAL_COMMAND:-}}"
LIVE_DIR="/opt/pathlab-viewer"
STATE_DIR="/run"

fail() { echo "Capacity control failed: $*" >&2; exit 1; }
atomic_install() {
  local source="${1}" target="${2}" temporary
  temporary="$(mktemp "${target}.tmp.XXXXXX")"
  install -o root -g root -m 755 "${source}" "${temporary}"
  python3 - "${temporary}" "$(dirname "${target}")" <<'PY'
import os, sys
for path in sys.argv[1:]:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
PY
  mv -f -- "${temporary}" "${target}"
  python3 - "$(dirname "${target}")" <<'PY'
import os, sys
descriptor = os.open(sys.argv[1], os.O_RDONLY)
try: os.fsync(descriptor)
finally: os.close(descriptor)
PY
}
decode() {
  python3 - "$1" "$2" <<'PY'
import base64, pathlib, sys
encoded, destination = sys.argv[1:]
padding = "=" * (-len(encoded) % 4)
data = base64.urlsafe_b64decode(encoded + padding)
if len(data) > 131072:
    raise SystemExit(1)
path = pathlib.Path(destination)
path.write_bytes(data)
path.chmod(0o600)
PY
}

if [[ "${REQUEST}" =~ ^capacity-arm[[:space:]]([0-9a-f]{40})[[:space:]]run=([a-z0-9-]{1,64})[[:space:]]digest=([0-9a-f]{64})[[:space:]]rollback=([0-9a-f]{40})[[:space:]]arm-not-after=([0-9]{10})[[:space:]]window-start=([0-9]{10})[[:space:]]window-end=([0-9]{10})[[:space:]]deadline=([0-9]{10})[[:space:]]rollback-not-after=([0-9]{10})[[:space:]]fault-start=([0-9]{10})[[:space:]]fault-end=([0-9]{10})[[:space:]]evidence=([A-Za-z0-9_-]+)[[:space:]]signature=([0-9a-f]{64})[[:space:]]nonce=([A-Za-z0-9._-]{8,128})$ ]]; then
  SHA="${BASH_REMATCH[1]}"; RUN_ID="${BASH_REMATCH[2]}"; DIGEST="${BASH_REMATCH[3]}"
  ROLLBACK_SHA="${BASH_REMATCH[4]}"; ARM_NOT_AFTER="${BASH_REMATCH[5]}"
  WINDOW_START="${BASH_REMATCH[6]}"; WINDOW_END="${BASH_REMATCH[7]}"
  DEADLINE="${BASH_REMATCH[8]}"; ROLLBACK_NOT_AFTER="${BASH_REMATCH[9]}"
  FAULT_START="${BASH_REMATCH[10]}"; FAULT_END="${BASH_REMATCH[11]}"
  EVIDENCE_B64="${BASH_REMATCH[12]}"; SIGNATURE="${BASH_REMATCH[13]}"; NONCE="${BASH_REMATCH[14]}"
  (( $(date +%s) <= ARM_NOT_AFTER )) || fail "arm authorization expired before host mutation"
  (( DEADLINE < ROLLBACK_NOT_AFTER )) || fail "rollback deadline must follow the control deadline"
  [[ "${ROLLBACK_SHA}" != "${SHA}" ]] || fail "rollback release must differ from the candidate"
  [[ "$(cat "${LIVE_DIR}/.pathlab-release" 2>/dev/null || true)" == "${SHA}" ]] || \
    fail "deployed release does not match the workflow SHA"
  PREFLIGHT="${STATE_DIR}/pathlab-capacity-${RUN_ID}-preflight.json"
  PREFLIGHT_SIG="${PREFLIGHT}.sig"
  NONCE_FILE="${STATE_DIR}/pathlab-capacity-${RUN_ID}-nonce"
  CONTROLLER_DIR="${STATE_DIR}/pathlab-capacity-${RUN_ID}-controller"
  CONTROLLER_POINTER="${STATE_DIR}/pathlab-capacity-controller"
  STABLE_DISPATCHER="/usr/local/sbin/pathlab-viewer-deploy"
  ARMED=false
  CONTROLLER_INSTALLED=false
  arm_failed() {
    local result=$?
    trap - EXIT
    if [[ "${ARMED}" == true ]]; then
      python3 "${LIVE_DIR}/deploy/scripts/capacity_control.py" finish \
        --run-id "${RUN_ID}" --restoration-verified >/dev/null 2>&1 || true
    fi
    if [[ "${CONTROLLER_INSTALLED}" == true && -f "${CONTROLLER_DIR}/prior-dispatcher" ]]; then
      systemctl stop "pathlab-capacity-${RUN_ID}-controller-cleanup.timer" >/dev/null 2>&1 || true
      atomic_install "${CONTROLLER_DIR}/prior-dispatcher" "${STABLE_DISPATCHER}" || true
      rm -f -- "${CONTROLLER_POINTER}"
      rm -rf -- "${CONTROLLER_DIR}"
    fi
    rm -f -- "${PREFLIGHT}" "${PREFLIGHT_SIG}" "${NONCE_FILE}"
    exit "${result}"
  }
  trap arm_failed EXIT
  decode "${EVIDENCE_B64}" "${PREFLIGHT}"
  printf '%s\n' "${SIGNATURE}" > "${PREFLIGHT_SIG}"; chmod 600 "${PREFLIGHT_SIG}"
  printf '%s\n' "${NONCE}" > "${NONCE_FILE}"; chmod 600 "${NONCE_FILE}"
  python3 "${LIVE_DIR}/deploy/scripts/capacity_control.py" arm \
    --run-id "${RUN_ID}" --workflow-sha "${SHA}" --plan-digest "${DIGEST}" \
    --nonce "${NONCE}" --deadline-epoch "${DEADLINE}" \
    --rollback-sha "${ROLLBACK_SHA}" --rollback-not-after "${ROLLBACK_NOT_AFTER}" \
    --window-start-epoch "${WINDOW_START}" --window-end-epoch "${WINDOW_END}" \
    --fault-start-epoch "${FAULT_START}" --fault-end-epoch "${FAULT_END}"
  ARMED=true
  RUNTIME_SECONDS="$((DEADLINE - $(date +%s)))"
  (( RUNTIME_SECONDS >= 120 && RUNTIME_SECONDS <= 10800 )) || fail "deadline is invalid"
  ROLLBACK_GRACE_SECONDS="$((ROLLBACK_NOT_AFTER - DEADLINE))"
  (( ROLLBACK_GRACE_SECONDS >= 180 && ROLLBACK_GRACE_SECONDS <= 900 )) || \
    fail "rollback grace period is invalid"
  install -d -o root -g root -m 700 "${CONTROLLER_DIR}"
  atomic_install "${STABLE_DISPATCHER}" "${CONTROLLER_DIR}/prior-dispatcher"
  CONTROLLER_INSTALLED=true
  atomic_install "${LIVE_DIR}/deploy/scripts/capacity-control-host.sh" \
    "${CONTROLLER_DIR}/capacity-control-host.sh"
  restore_script="${CONTROLLER_DIR}/restore-dispatcher.sh"
  cat > "${restore_script}" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
temporary="\$(mktemp "${STABLE_DISPATCHER}.tmp.XXXXXX")"
install -o root -g root -m 755 "${CONTROLLER_DIR}/prior-dispatcher" "\${temporary}"
python3 - "\${temporary}" "\$(dirname "${STABLE_DISPATCHER}")" <<'PY'
import os, sys
for path in sys.argv[1:]:
    descriptor = os.open(path, os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)
PY
mv -f -- "\${temporary}" "${STABLE_DISPATCHER}"
python3 - "\$(dirname "${STABLE_DISPATCHER}")" <<'PY'
import os, sys
descriptor = os.open(sys.argv[1], os.O_RDONLY)
try: os.fsync(descriptor)
finally: os.close(descriptor)
PY
rm -f -- "${CONTROLLER_POINTER}"
rm -rf -- "${CONTROLLER_DIR}"
EOF
  chmod 700 "${restore_script}"
  reconcile_script="${CONTROLLER_DIR}/reconcile-abort.sh"
  cat > "${reconcile_script}" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
rollback_tmp="${STATE_DIR}/pathlab-capacity-${RUN_ID}-rollback.json.tmp"
final_tmp="${STATE_DIR}/pathlab-capacity-${RUN_ID}-final.json.tmp"
bash "${STATE_DIR}/pathlab-capacity-${RUN_ID}-rollback.sh" \
  "${SHA}" "${ROLLBACK_SHA}" "${ROLLBACK_NOT_AFTER}" > "\${rollback_tmp}"
chmod 600 "\${rollback_tmp}"
mv -- "\${rollback_tmp}" "${STATE_DIR}/pathlab-capacity-${RUN_ID}-rollback.json"
python3 - "${STATE_DIR}/pathlab-capacity-${RUN_ID}-control.json" <<'PY'
import json, os, pathlib, sys
path = pathlib.Path(sys.argv[1])
value = json.loads(path.read_text())
value["phase"] = "aborted-restored"
value["finalLimit"] = None
temporary = path.with_suffix(path.suffix + ".tmp")
temporary.write_text(json.dumps(value, sort_keys=True) + "\n")
os.chmod(temporary, 0o600)
os.replace(temporary, path)
PY
jq -s '.[0] + .[1]' \
  <(jq '{runId,workflowSha,planDigest,deadlineEpoch,rollbackSha,rollbackNotAfter,
    windowStartEpoch,windowEndEpoch,phase,finalLimit,faultConsumed}' \
    "${STATE_DIR}/pathlab-capacity-${RUN_ID}-control.json") \
  "${STATE_DIR}/pathlab-capacity-${RUN_ID}-rollback.json" > "\${final_tmp}"
chmod 600 "\${final_tmp}"
mv -- "\${final_tmp}" "${STATE_DIR}/pathlab-capacity-${RUN_ID}-final.json"
EOF
  chmod 700 "${reconcile_script}"
  python3 - "${restore_script}" "${reconcile_script}" "${CONTROLLER_DIR}" <<'PY'
import os, sys
for path in sys.argv[1:]:
    descriptor = os.open(path, os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)
PY
  cleanup_epoch="$((ROLLBACK_NOT_AFTER - 2))"
  (( cleanup_epoch > $(date +%s) )) || fail "stable controller cleanup deadline elapsed"
  systemd-run --unit "pathlab-capacity-${RUN_ID}-controller-cleanup" --collect \
    --on-calendar="@${cleanup_epoch}" --timer-property=AccuracySec=1s bash "${restore_script}"
  systemctl is-active --quiet "pathlab-capacity-${RUN_ID}-controller-cleanup.timer" || \
    fail "stable controller cleanup timer did not start"
  atomic_install "${LIVE_DIR}/deploy/scripts/deploy-release.sh" "${STABLE_DISPATCHER}"
  pointer_tmp="$(mktemp "${CONTROLLER_POINTER}.tmp.XXXXXX")"
  printf '%s\n' "${CONTROLLER_DIR}" > "${pointer_tmp}"
  chmod 600 "${pointer_tmp}"
  python3 - "${pointer_tmp}" "${STATE_DIR}" <<'PY'
import os, sys
for path in sys.argv[1:]:
    descriptor = os.open(path, os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)
PY
  mv -f -- "${pointer_tmp}" "${CONTROLLER_POINTER}"
  python3 - "${STATE_DIR}" <<'PY'
import os, sys
descriptor = os.open(sys.argv[1], os.O_RDONLY)
try: os.fsync(descriptor)
finally: os.close(descriptor)
PY
  UNIT="pathlab-capacity-${RUN_ID}"
  systemd-run --unit "${UNIT}" --collect --property="RuntimeMaxSec=${RUNTIME_SECONDS}" \
    --property="TimeoutStopSec=${ROLLBACK_GRACE_SECONDS}" \
    bash "${LIVE_DIR}/deploy/scripts/capacity-control-unit.sh" \
      "${RUN_ID}" "${SHA}" "${DIGEST}" "${NONCE_FILE}" "${PREFLIGHT}" "${PREFLIGHT_SIG}" \
      "${ROLLBACK_SHA}" "${ROLLBACK_NOT_AFTER}" "${CONTROLLER_DIR}"
  systemctl is-active --quiet "${UNIT}.service" || fail "capacity unit did not start"
  trap - EXIT
  exit 0
fi

if [[ "${REQUEST}" =~ ^capacity-status[[:space:]]run=([a-z0-9-]{1,64})$ ]]; then
  exec python3 "${LIVE_DIR}/deploy/scripts/capacity_control.py" status --run-id "${BASH_REMATCH[1]}"
fi

if [[ "${REQUEST}" =~ ^capacity-rollback-preflight[[:space:]]rollback=([0-9a-f]{40})$ ]]; then
  ROLLBACK_SHA="${BASH_REMATCH[1]}"
  mapfile -t candidates < <(find /opt -maxdepth 1 -type d \
    -name "pathlab-viewer.rollback-${ROLLBACK_SHA:0:12}-*" -print | sort)
  [[ "${#candidates[@]}" -ge 1 ]] || fail "rollback snapshot is missing"
  rollback_dir="${candidates[${#candidates[@]}-1]}"
  [[ "$(cat "${rollback_dir}/.pathlab-release" 2>/dev/null || true)" == "${ROLLBACK_SHA}" ]] || \
    fail "rollback snapshot SHA mismatch"
  [[ -f "${rollback_dir}/deploy/.env" ]] || fail "rollback environment is missing"
  services="$(cd "${rollback_dir}/deploy" && docker compose config --services | sort)"
  expected=$'api\ncaddy\ntile-service\ntusd\nworker'
  [[ "${services}" == "${expected}" ]] || fail "rollback topology is not the approved five services"
  jq -n --arg sha "${ROLLBACK_SHA}" \
    '{rollbackSha:$sha,directoryReady:true,configValid:true,serviceCount:5}'
  exit 0
fi

if [[ "${REQUEST}" =~ ^capacity-postflight[[:space:]]expected=([0-9a-f]{40})$ ]]; then
  EXPECTED="${BASH_REMATCH[1]}"
  RELEASE="$(cat "${LIVE_DIR}/.pathlab-release" 2>/dev/null || true)"
  cd "${LIVE_DIR}/deploy"
  SERVICES="$(docker compose ps --services --status running | sort)"
  EXPECTED_SERVICES=$'api\ncaddy\nclassroom\ntile-service\ntusd\nworker'
  LIMIT="$(awk -F= '/^PATHLAB_CLASSROOM_MAX_PARTICIPANTS=/{print $2; exit}' .env)"
  ANNOTATIONS="$(awk -F= '/^PATHLAB_ANNOTATIONS_ENABLED=/{print $2; exit}' .env)"
  READY=false
  curl --fail --silent --insecure --max-time 10 https://127.0.0.1/readyz >/dev/null && \
    curl --fail --silent --insecure --max-time 10 https://127.0.0.1/livez >/dev/null && READY=true
  WATCHDOG=false; systemctl is-active --quiet pathlab-viewer-watchdog.timer && WATCHDOG=true
  jq -n --arg release "${RELEASE}" --arg expected "${EXPECTED}" --argjson ready "${READY}" \
    --argjson watchdog "${WATCHDOG}" --argjson capacity "${LIMIT:-0}" \
    --argjson annotations "${ANNOTATIONS:-false}" \
    --argjson exact "$([[ "${SERVICES}" == "${EXPECTED_SERVICES}" ]] && echo true || echo false)" \
    '{releaseSha:$release,expectedSha:$expected,releaseExact:($release==$expected),servicesExact:$exact,
      serviceCount:6,ready:$ready,watchdogExpected:true,watchdogActive:$watchdog,
      finalCapacity:$capacity,annotationsEnabled:$annotations}'
  exit 0
fi

if [[ "${REQUEST}" =~ ^capacity-finalize[[:space:]]([0-9a-f]{40})[[:space:]]run=([a-z0-9-]{1,64})[[:space:]]digest=([0-9a-f]{64})[[:space:]]evidence=([A-Za-z0-9_-]+)[[:space:]]signature=([0-9a-f]{64})[[:space:]]nonce=([A-Za-z0-9._-]{8,128})$ ]]; then
  SHA="${BASH_REMATCH[1]}"; RUN_ID="${BASH_REMATCH[2]}"; DIGEST="${BASH_REMATCH[3]}"
  EVIDENCE_B64="${BASH_REMATCH[4]}"; SIGNATURE="${BASH_REMATCH[5]}"; NONCE="${BASH_REMATCH[6]}"
  EVIDENCE="${STATE_DIR}/pathlab-capacity-${RUN_ID}-decision.json"
  SIGNATURE_FILE="${EVIDENCE}.sig"
  CONTROL_STATE="${STATE_DIR}/pathlab-capacity-${RUN_ID}-control.json"
  FINAL_RESULT="${STATE_DIR}/pathlab-capacity-${RUN_ID}-final.json"
  decode "${EVIDENCE_B64}" "${EVIDENCE}"
  if [[ -s "${FINAL_RESULT}" ]] && jq -e '.phase == "restored"' "${CONTROL_STATE}" >/dev/null; then
    python3 - "${CONTROL_STATE}" "${EVIDENCE}" "${SHA}" "${RUN_ID}" "${DIGEST}" \
      "${SIGNATURE}" "${NONCE}" <<'PY'
import hashlib, json, sys
state_path, evidence_path, sha, run, digest, signature, nonce = sys.argv[1:]
state = json.load(open(state_path, encoding="utf-8"))
valid = state.get("workflowSha") == sha and state.get("runId") == run
valid = valid and state.get("planDigest") == digest
valid = valid and state.get("nonceHash") == hashlib.sha256(nonce.encode()).hexdigest()
valid = valid and state.get("decisionSignature") == signature
valid = valid and state.get("evidenceDigest") == hashlib.sha256(open(evidence_path, "rb").read()).hexdigest()
raise SystemExit(0 if valid else 1)
PY
    cat "${FINAL_RESULT}"
    exit 0
  fi
  printf '%s\n' "${SIGNATURE}" > "${SIGNATURE_FILE}"; chmod 600 "${SIGNATURE_FILE}"
  python3 "${LIVE_DIR}/deploy/scripts/capacity_control.py" finalize \
    --run-id "${RUN_ID}" --workflow-sha "${SHA}" --plan-digest "${DIGEST}" \
    --nonce "${NONCE}" --evidence "${EVIDENCE}" --signature "${SIGNATURE_FILE}"
  ROLLBACK_NOT_AFTER="$(jq -er --arg digest "${DIGEST}" \
    'select(.planDigest == $digest) | .rollbackNotAfter' "${CONTROL_STATE}")"
  while (( $(date +%s) < ROLLBACK_NOT_AFTER )); do
    STATUS="$(jq -c '{runId,workflowSha,planDigest,deadlineEpoch,rollbackSha,rollbackNotAfter,
      windowStartEpoch,windowEndEpoch,phase,finalLimit,faultConsumed}' "${CONTROL_STATE}")"
    if jq -e '.phase == "restored"' <<< "${STATUS}" >/dev/null && \
       [[ -s "${FINAL_RESULT}" ]]; then
      cat "${FINAL_RESULT}"
      exit 0
    fi
    jq -e '.phase == "restore-failed"' <<< "${STATUS}" >/dev/null && \
      fail "capacity restoration failed"
    remaining="$((ROLLBACK_NOT_AFTER - $(date +%s)))"
    (( remaining > 0 )) || break
    (( remaining > 2 )) && sleep 2 || sleep "${remaining}"
  done
  fail "capacity restoration did not finish before its bound deadline"
fi

if [[ "${REQUEST}" =~ ^capacity-fault[[:space:]]run=([a-z0-9-]{1,64})[[:space:]]digest=([0-9a-f]{64})$ ]]; then
  RUN_ID="${BASH_REMATCH[1]}"; DIGEST="${BASH_REMATCH[2]}"
  python3 "${LIVE_DIR}/deploy/scripts/capacity_control.py" fault \
    --run-id "${RUN_ID}" --plan-digest "${DIGEST}" || fail "fault request was rejected"
  cd "${LIVE_DIR}/deploy"
  CONTAINER="$(docker compose ps -q classroom)"
  [[ -n "${CONTAINER}" ]] || fail "Classroom container is unavailable"
  docker kill --signal=STOP "${CONTAINER}" >/dev/null
  exit 0
fi

if [[ "${REQUEST}" =~ ^capacity-ack[[:space:]]run=([a-z0-9-]{1,64})[[:space:]]digest=([0-9a-f]{64})$ ]]; then
  RUN_ID="${BASH_REMATCH[1]}"; DIGEST="${BASH_REMATCH[2]}"
  CONTROL_STATE="${STATE_DIR}/pathlab-capacity-${RUN_ID}-control.json"
  FINAL_RESULT="${STATE_DIR}/pathlab-capacity-${RUN_ID}-final.json"
  jq -e --arg run "${RUN_ID}" --arg digest "${DIGEST}" \
    '.runId == $run and .planDigest == $digest and
     (.phase == "restored" or .phase == "aborted-restored")' \
    "${CONTROL_STATE}" >/dev/null || fail "capacity acknowledgment binding is invalid"
  [[ -s "${FINAL_RESULT}" ]] || fail "capacity final result is unavailable"
  ROLLBACK_NOT_AFTER="$(jq -er .rollbackNotAfter "${CONTROL_STATE}")"
  jq -n --arg runId "${RUN_ID}" --arg planDigest "${DIGEST}" \
    --argjson cleanupNotAfter "${ROLLBACK_NOT_AFTER}" \
    '{runId:$runId,planDigest:$planDigest,controllerAcknowledged:true,
      cleanupScheduled:true,cleanupNotAfter:$cleanupNotAfter}'
  exit 0
fi

if [[ "${REQUEST}" =~ ^capacity-abort[[:space:]]run=([a-z0-9-]{1,64})[[:space:]]digest=([0-9a-f]{64})$ ]]; then
  RUN_ID="${BASH_REMATCH[1]}"; DIGEST="${BASH_REMATCH[2]}"
  CONTROL_STATE="${STATE_DIR}/pathlab-capacity-${RUN_ID}-control.json"
  CONTROL="$(cat "${CONTROL_STATE}")"
  mapfile -t rollback_binding < <(jq -er --arg digest "${DIGEST}" \
    'select(.planDigest == $digest) | .rollbackSha, (.rollbackNotAfter | tostring)' <<< "${CONTROL}")
  [[ "${#rollback_binding[@]}" -eq 2 ]] || fail "abort binding is invalid"
  ROLLBACK_SHA="${rollback_binding[0]}"; ROLLBACK_NOT_AFTER="${rollback_binding[1]}"
  FINAL_RESULT="${STATE_DIR}/pathlab-capacity-${RUN_ID}-final.json"
  if [[ -s "${FINAL_RESULT}" ]] && \
    jq -e '(.phase == "aborted-restored" and .finalLimit == null) or
      (.phase == "restored" and .finalLimit == 300)' "${CONTROL_STATE}" >/dev/null && \
    jq -e '.releaseExact == true and .servicesExact == true and .serviceCount == 5 and
      .ready == true and .finalCapacity == 300 and .annotationsEnabled == false' "${FINAL_RESULT}" >/dev/null; then
    cat "${FINAL_RESULT}"
    exit 0
  fi
  # The detached host unit owns both restoration and rollback; the SSH caller
  # only requests abort and waits for the retained, host-produced result.
  if jq -e '.phase == "restored" and (.finalLimit == 1200 or .finalLimit == 1500)' \
    "${CONTROL_STATE}" >/dev/null; then
    if ! systemctl is-active --quiet "pathlab-capacity-${RUN_ID}-abort-reconcile.service"; then
      remaining="$((ROLLBACK_NOT_AFTER - $(date +%s)))"
      (( remaining > 10 )) || fail "abort reconciliation deadline elapsed"
      systemd-run --unit "pathlab-capacity-${RUN_ID}-abort-reconcile" --collect \
        --property="RuntimeMaxSec=${remaining}" \
        bash "${STATE_DIR}/pathlab-capacity-${RUN_ID}-controller/reconcile-abort.sh"
    fi
  else
    systemctl kill --kill-whom=main --signal=USR1 "pathlab-capacity-${RUN_ID}.service" || true
  fi
  while (( $(date +%s) < ROLLBACK_NOT_AFTER )); do
    STATUS="$(jq -c '{runId,workflowSha,planDigest,deadlineEpoch,rollbackSha,rollbackNotAfter,
      windowStartEpoch,windowEndEpoch,phase,finalLimit,faultConsumed}' "${CONTROL_STATE}")"
    if jq -e '.phase == "aborted-restored" and .finalLimit == null' <<< "${STATUS}" >/dev/null && \
       [[ "$(cat "${LIVE_DIR}/.pathlab-release" 2>/dev/null || true)" == "${ROLLBACK_SHA}" ]] && \
       [[ -s "${FINAL_RESULT}" ]]; then
      cat "${FINAL_RESULT}"
      exit 0
    fi
    remaining="$((ROLLBACK_NOT_AFTER - $(date +%s)))"
    (( remaining > 0 )) || break
    (( remaining > 2 )) && sleep 2 || sleep "${remaining}"
  done
  fail "capacity abort did not restore and roll back before its bound deadline"
fi

fail "request is not an approved capacity control operation"
