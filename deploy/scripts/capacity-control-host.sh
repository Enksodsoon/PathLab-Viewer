#!/usr/bin/env bash
set -Eeuo pipefail

REQUEST="${1:-${SSH_ORIGINAL_COMMAND:-}}"
LIVE_DIR="/opt/pathlab-viewer"
STATE_DIR="/run"

fail() { echo "Capacity control failed: $*" >&2; exit 1; }
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

if [[ "${REQUEST}" =~ ^capacity-arm[[:space:]]([0-9a-f]{40})[[:space:]]run=([a-z0-9-]{1,64})[[:space:]]digest=([0-9a-f]{64})[[:space:]]arm-not-after=([0-9]{10})[[:space:]]deadline=([0-9]{10})[[:space:]]fault-start=([0-9]{10})[[:space:]]fault-end=([0-9]{10})[[:space:]]evidence=([A-Za-z0-9_-]+)[[:space:]]signature=([0-9a-f]{64})[[:space:]]nonce=([A-Za-z0-9._-]{8,128})$ ]]; then
  SHA="${BASH_REMATCH[1]}"; RUN_ID="${BASH_REMATCH[2]}"; DIGEST="${BASH_REMATCH[3]}"
  ARM_NOT_AFTER="${BASH_REMATCH[4]}"; DEADLINE="${BASH_REMATCH[5]}"
  FAULT_START="${BASH_REMATCH[6]}"; FAULT_END="${BASH_REMATCH[7]}"
  EVIDENCE_B64="${BASH_REMATCH[8]}"; SIGNATURE="${BASH_REMATCH[9]}"; NONCE="${BASH_REMATCH[10]}"
  (( $(date +%s) <= ARM_NOT_AFTER )) || fail "arm authorization expired before host mutation"
  [[ "$(cat "${LIVE_DIR}/.pathlab-release" 2>/dev/null || true)" == "${SHA}" ]] || \
    fail "deployed release does not match the workflow SHA"
  PREFLIGHT="${STATE_DIR}/pathlab-capacity-${RUN_ID}-preflight.json"
  PREFLIGHT_SIG="${PREFLIGHT}.sig"
  NONCE_FILE="${STATE_DIR}/pathlab-capacity-${RUN_ID}-nonce"
  ARMED=false
  arm_failed() {
    local result=$?
    trap - EXIT
    if [[ "${ARMED}" == true ]]; then
      python3 "${LIVE_DIR}/deploy/scripts/capacity_control.py" finish \
        --run-id "${RUN_ID}" --restoration-verified >/dev/null 2>&1 || true
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
    --fault-start-epoch "${FAULT_START}" --fault-end-epoch "${FAULT_END}"
  ARMED=true
  RUNTIME_SECONDS="$((DEADLINE - $(date +%s)))"
  (( RUNTIME_SECONDS >= 120 && RUNTIME_SECONDS <= 10800 )) || fail "deadline is invalid"
  UNIT="pathlab-capacity-${RUN_ID}"
  systemd-run --unit "${UNIT}" --collect --property="RuntimeMaxSec=${RUNTIME_SECONDS}" \
    --property=TimeoutStopSec=40 \
    bash "${LIVE_DIR}/deploy/scripts/capacity-control-unit.sh" \
      "${RUN_ID}" "${SHA}" "${DIGEST}" "${NONCE_FILE}" "${PREFLIGHT}" "${PREFLIGHT_SIG}"
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

if [[ "${REQUEST}" =~ ^capacity-rollback[[:space:]]candidate=([0-9a-f]{40})[[:space:]]rollback=([0-9a-f]{40})[[:space:]]run=([a-z0-9-]{1,64})[[:space:]]digest=([0-9a-f]{64})[[:space:]]nonce=([A-Za-z0-9._-]{8,128})$ ]]; then
  python3 - "/run/pathlab-capacity-${BASH_REMATCH[3]}.json" "${BASH_REMATCH[1]}" \
    "${BASH_REMATCH[3]}" "${BASH_REMATCH[4]}" "${BASH_REMATCH[5]}" <<'PY'
import hashlib, json, sys
path, sha, run, digest, nonce = sys.argv[1:]
value = json.load(open(path, encoding="utf-8"))
valid = value.get("phase") in ("restored", "aborted-restored")
valid = valid and value.get("finalLimit") in (None, 300)
valid = valid and value.get("workflowSha") == sha and value.get("runId") == run
valid = valid and value.get("planDigest") == digest
valid = valid and value.get("nonceHash") == hashlib.sha256(nonce.encode()).hexdigest()
raise SystemExit(0 if valid else 1)
PY
  exec bash "${LIVE_DIR}/deploy/scripts/rollback-capacity-candidate.sh" \
    "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
fi

if [[ "${REQUEST}" =~ ^capacity-postflight[[:space:]]expected=([0-9a-f]{40})$ ]]; then
  EXPECTED="${BASH_REMATCH[1]}"
  RELEASE="$(cat "${LIVE_DIR}/.pathlab-release" 2>/dev/null || true)"
  cd "${LIVE_DIR}/deploy"
  SERVICES="$(docker compose ps --services --status running | sort)"
  EXPECTED_SERVICES=$'api\ncaddy\nclassroom\ntile-service\ntusd\nworker'
  LIMIT="$(awk -F= '/^PATHLAB_CLASSROOM_MAX_PARTICIPANTS=/{print $2; exit}' .env)"
  READY=false
  curl --fail --silent --insecure --max-time 10 https://127.0.0.1/readyz >/dev/null && \
    curl --fail --silent --insecure --max-time 10 https://127.0.0.1/livez >/dev/null && READY=true
  WATCHDOG=false; systemctl is-active --quiet pathlab-viewer-watchdog.timer && WATCHDOG=true
  jq -n --arg release "${RELEASE}" --arg expected "${EXPECTED}" --argjson ready "${READY}" \
    --argjson watchdog "${WATCHDOG}" --argjson capacity "${LIMIT:-0}" \
    --argjson exact "$([[ "${SERVICES}" == "${EXPECTED_SERVICES}" ]] && echo true || echo false)" \
    '{releaseSha:$release,expectedSha:$expected,releaseExact:($release==$expected),servicesExact:$exact,
      serviceCount:6,ready:$ready,watchdogExpected:true,watchdogActive:$watchdog,finalCapacity:$capacity}'
  exit 0
fi

if [[ "${REQUEST}" =~ ^capacity-finalize[[:space:]]([0-9a-f]{40})[[:space:]]run=([a-z0-9-]{1,64})[[:space:]]digest=([0-9a-f]{64})[[:space:]]evidence=([A-Za-z0-9_-]+)[[:space:]]signature=([0-9a-f]{64})[[:space:]]nonce=([A-Za-z0-9._-]{8,128})$ ]]; then
  SHA="${BASH_REMATCH[1]}"; RUN_ID="${BASH_REMATCH[2]}"; DIGEST="${BASH_REMATCH[3]}"
  EVIDENCE="${STATE_DIR}/pathlab-capacity-${RUN_ID}-decision.json"
  SIGNATURE_FILE="${EVIDENCE}.sig"
  decode "${BASH_REMATCH[4]}" "${EVIDENCE}"
  printf '%s\n' "${BASH_REMATCH[5]}" > "${SIGNATURE_FILE}"; chmod 600 "${SIGNATURE_FILE}"
  python3 "${LIVE_DIR}/deploy/scripts/capacity_control.py" finalize \
    --run-id "${RUN_ID}" --workflow-sha "${SHA}" --plan-digest "${DIGEST}" \
    --nonce "${BASH_REMATCH[6]}" --evidence "${EVIDENCE}" --signature "${SIGNATURE_FILE}"
  for _ in $(seq 1 60); do
    STATUS="$(python3 "${LIVE_DIR}/deploy/scripts/capacity_control.py" status --run-id "${RUN_ID}")"
    [[ "${STATUS}" == *'"phase": "restored"'* ]] && { printf '%s\n' "${STATUS}"; exit 0; }
    [[ "${STATUS}" == *'"phase": "restore-failed"'* ]] && fail "capacity restoration failed"
    sleep 2
  done
  fail "capacity restoration did not finish within 120 seconds"
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

if [[ "${REQUEST}" =~ ^capacity-abort[[:space:]]run=([a-z0-9-]{1,64})[[:space:]]digest=([0-9a-f]{64})$ ]]; then
  RUN_ID="${BASH_REMATCH[1]}"; DIGEST="${BASH_REMATCH[2]}"
  STATUS="$(python3 "${LIVE_DIR}/deploy/scripts/capacity_control.py" status --run-id "${RUN_ID}")"
  [[ "${STATUS}" == *"\"planDigest\": \"${DIGEST}\""* ]] || fail "abort binding is invalid"
  systemctl stop "pathlab-capacity-${RUN_ID}.service" || true
  for _ in $(seq 1 30); do
    STATUS="$(python3 "${LIVE_DIR}/deploy/scripts/capacity_control.py" status --run-id "${RUN_ID}")"
    [[ "${STATUS}" == *'"phase": "aborted-restored"'* ]] && { printf '%s\n' "${STATUS}"; exit 0; }
    [[ "${STATUS}" == *'"phase": "restore-failed"'* ]] && fail "capacity abort could not prove restoration"
    sleep 2
  done
  fail "capacity abort did not restore the prior configuration"
fi

fail "request is not an approved capacity control operation"
