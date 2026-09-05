#!/usr/bin/env bash
set -Eeuo pipefail

REQUEST="${1:-${SSH_ORIGINAL_COMMAND:-}}"
LIVE_DIR="/opt/pathlab-viewer"
STATE_DIR="/run"

fail() { echo "Capacity control failed: $*" >&2; exit 1; }
lock_controller_mutation() {
  # Adopt the dispatcher's same open description before upgrading its read
  # lock. Opening a second descriptor would conflict with our inherited lock.
  # The detached unit restore path never locks: recover waits for it to stop.
  if [[ -n "${PATHLAB_CAPACITY_DISPATCH_LOCK_FD:-}" ]]; then
    [[ "${PATHLAB_CAPACITY_DISPATCH_LOCK_FD}" == 8 ]] || fail "dispatcher lock is invalid"
    python3 - "${STATE_DIR}/pathlab-capacity-controller.lock" "/proc/$$/fd/8" <<'PY' || \
      fail "dispatcher lock binding is invalid"
import os, pathlib, stat, sys
path = pathlib.Path(sys.argv[1])
try:
    expected, inherited = path.stat(), os.stat(sys.argv[2])
    valid = (not path.is_symlink() and stat.S_ISREG(expected.st_mode)
             and expected.st_uid == 0 and expected.st_mode & 0o022 == 0
             and (expected.st_dev, expected.st_ino) == (inherited.st_dev, inherited.st_ino))
except OSError:
    valid = False
raise SystemExit(0 if valid else 1)
PY
    CONTROLLER_LOCK_FD=8
  else
    exec {CONTROLLER_LOCK_FD}>"${STATE_DIR}/pathlab-capacity-controller.lock"
  fi
  flock --exclusive --nonblock "${CONTROLLER_LOCK_FD}" || \
    fail "another capacity controller mutation is in progress"
}
verify_controller_ownership() {
  python3 - "${STATE_DIR}" "$1" "${2:-}" "${3:-false}" <<'PY' || \
    fail "capacity controller ownership is unproved"
import json
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
run_id, sha, allow_missing_pointer = sys.argv[2:]
state_path = root / f"pathlab-capacity-{run_id}-control.json"
controller = root / f"pathlab-capacity-{run_id}-controller"
pointer = root / "pathlab-capacity-controller"
active_path = root / "pathlab-capacity-active.json"
try:
    if state_path.is_symlink() or controller.is_symlink():
        raise ValueError
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or state.get("runId") != run_id:
        raise ValueError
    if not re.fullmatch("[0-9a-f]{40}", str(state.get("workflowSha", ""))):
        raise ValueError
    if sha and state.get("workflowSha") != sha:
        raise ValueError
    if pointer.is_symlink():
        raise ValueError
    if pointer.exists():
        if not pointer.is_file() or pointer.read_text(encoding="utf-8").rstrip("\n") != controller.as_posix():
            raise ValueError
    elif allow_missing_pointer != "true":
        raise ValueError
    if active_path.is_symlink():
        raise ValueError
    if active_path.exists():
        active = json.loads(active_path.read_text(encoding="utf-8"))
        if not isinstance(active, dict) or active.get("runId") != run_id:
            raise ValueError
except (OSError, ValueError, TypeError):
    raise SystemExit("capacity controller ownership precondition failed") from None
PY
}
begin_owned_mutation() {
  lock_controller_mutation
  verify_controller_ownership "$1" "${2:-}"
}
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

runtime_status() {
  local expected_sha="$1" manifest_digest="${2:-}"
  local arguments=(verify-live --live-dir "${LIVE_DIR}" --expected-sha "${expected_sha}" --require-safe)
  if [[ -n "${manifest_digest}" ]]; then
    arguments+=(--manifest-digest "${manifest_digest}")
  fi
  python3 "${LIVE_DIR}/deploy/scripts/runtime_safety_manifest.py" "${arguments[@]}"
}

if [[ "${REQUEST}" =~ ^capacity-arm[[:space:]]([0-9a-f]{40})[[:space:]]run=([a-z0-9-]{1,64})[[:space:]]digest=([0-9a-f]{64})[[:space:]]manifest=([0-9a-f]{64})[[:space:]]arm-not-after=([0-9]{10})[[:space:]]window-start=([0-9]{10})[[:space:]]window-end=([0-9]{10})[[:space:]]deadline=([0-9]{10})[[:space:]]restore-not-after=([0-9]{10})[[:space:]]fault-start=([0-9]{10})[[:space:]]fault-end=([0-9]{10})[[:space:]]evidence=([A-Za-z0-9_-]+)[[:space:]]signature=([0-9a-f]{64})[[:space:]]nonce=([A-Za-z0-9._-]{8,128})$ ]]; then
  SHA="${BASH_REMATCH[1]}"; RUN_ID="${BASH_REMATCH[2]}"; DIGEST="${BASH_REMATCH[3]}"
  MANIFEST_DIGEST="${BASH_REMATCH[4]}"; ARM_NOT_AFTER="${BASH_REMATCH[5]}"
  WINDOW_START="${BASH_REMATCH[6]}"; WINDOW_END="${BASH_REMATCH[7]}"
  DEADLINE="${BASH_REMATCH[8]}"; RESTORE_NOT_AFTER="${BASH_REMATCH[9]}"
  FAULT_START="${BASH_REMATCH[10]}"; FAULT_END="${BASH_REMATCH[11]}"
  EVIDENCE_B64="${BASH_REMATCH[12]}"; SIGNATURE="${BASH_REMATCH[13]}"; NONCE="${BASH_REMATCH[14]}"
  (( $(date +%s) <= ARM_NOT_AFTER )) || fail "arm authorization expired before host mutation"
  lock_controller_mutation
  [[ ! -e "${STATE_DIR}/pathlab-capacity-controller" && \
     ! -L "${STATE_DIR}/pathlab-capacity-controller" ]] || \
    fail "existing capacity controller binding requires retirement before arm"
  [[ ! -e "${STATE_DIR}/pathlab-capacity-active.json" && \
     ! -L "${STATE_DIR}/pathlab-capacity-active.json" ]] || \
    fail "existing capacity active binding requires recovery before arm"
  (( $(date +%s) <= ARM_NOT_AFTER )) || fail "arm authorization expired before host mutation"
  (( DEADLINE < RESTORE_NOT_AFTER )) || fail "restore deadline must follow the control deadline"
  [[ "$(cat "${LIVE_DIR}/.pathlab-release" 2>/dev/null || true)" == "${SHA}" ]] || \
    fail "deployed release does not match the workflow SHA"
  runtime_status "${SHA}" "${MANIFEST_DIGEST}" >/dev/null || \
    fail "runtime safety manifest did not match the live release"
  PREFLIGHT="${STATE_DIR}/pathlab-capacity-${RUN_ID}-preflight.json"
  PREFLIGHT_SIG="${PREFLIGHT}.sig"
  NONCE_FILE="${STATE_DIR}/pathlab-capacity-${RUN_ID}-nonce"
  READY_FILE="${STATE_DIR}/pathlab-capacity-${RUN_ID}-ready.json"
  CONTROLLER_DIR="${STATE_DIR}/pathlab-capacity-${RUN_ID}-controller"
  CONTROLLER_POINTER="${STATE_DIR}/pathlab-capacity-controller"
  STABLE_DISPATCHER="/usr/local/sbin/pathlab-viewer-deploy"
  ARMED=false
  CONTROLLER_INSTALLED=false
  CONTROLLER_POINTER_INSTALLED=false
  CONTROLLER_STARTED=false
  CONTROLLER_LAUNCH_ATTEMPTED=false
  UNIT="pathlab-capacity-${RUN_ID}"
  arm_failed() {
    local result=$?
    local stopped=true restoration_proved=false unit_state
    trap - EXIT
    if [[ "${CONTROLLER_STARTED}" == true || "${CONTROLLER_LAUNCH_ATTEMPTED}" == true ]]; then
      stopped=false
      if timeout --signal=TERM --kill-after=10s "${RESTORE_GRACE_SECONDS:-300}s" \
          systemctl stop "${UNIT}.service" >/dev/null 2>&1 && \
          unit_state="$(systemctl show "${UNIT}.service" --property=ActiveState --value)" && \
          [[ "${unit_state}" == inactive ]]; then
        stopped=true
      fi
    fi
    if [[ "${ARMED}" == true ]]; then
      if [[ "${stopped}" == true ]] && runtime_status "${SHA}" "${MANIFEST_DIGEST}" >/dev/null; then
        restoration_proved=true
        python3 "${LIVE_DIR}/deploy/scripts/capacity_control.py" finish \
          --run-id "${RUN_ID}" --restoration-verified >/dev/null 2>&1 || true
      else
        python3 "${LIVE_DIR}/deploy/scripts/capacity_control.py" finish \
          --run-id "${RUN_ID}" >/dev/null 2>&1 || true
      fi
    fi
    if [[ "${stopped}" == true && ( "${ARMED}" != true || "${restoration_proved}" == true ) ]]; then
    if [[ "${CONTROLLER_INSTALLED}" == true && -f "${CONTROLLER_DIR}/prior-dispatcher" ]]; then
      systemctl stop "pathlab-capacity-${RUN_ID}-controller-cleanup.timer" >/dev/null 2>&1 || true
      # Before pointer publication this arm does not own an earlier run's
      # retired pointer or dispatcher. Never remove that prior binding.
      if [[ "${CONTROLLER_POINTER_INSTALLED}" == true && -f "${CONTROLLER_POINTER}" && \
          ! -L "${CONTROLLER_POINTER}" && "$(cat "${CONTROLLER_POINTER}")" == "${CONTROLLER_DIR}" ]]; then
        atomic_install "${CONTROLLER_DIR}/prior-dispatcher" "${STABLE_DISPATCHER}" || true
        rm -f -- "${CONTROLLER_POINTER}"
      fi
      rm -rf -- "${CONTROLLER_DIR}"
    fi
    rm -f -- "${PREFLIGHT}" "${PREFLIGHT_SIG}" "${NONCE_FILE}" "${READY_FILE}"
    fi
    exit "${result}"
  }
  trap arm_failed EXIT
  decode "${EVIDENCE_B64}" "${PREFLIGHT}"
  printf '%s\n' "${SIGNATURE}" > "${PREFLIGHT_SIG}"; chmod 600 "${PREFLIGHT_SIG}"
  printf '%s\n' "${NONCE}" > "${NONCE_FILE}"; chmod 600 "${NONCE_FILE}"
  python3 "${LIVE_DIR}/deploy/scripts/capacity_control.py" arm \
    --run-id "${RUN_ID}" --workflow-sha "${SHA}" --plan-digest "${DIGEST}" \
    --nonce "${NONCE}" --deadline-epoch "${DEADLINE}" \
    --runtime-manifest-digest "${MANIFEST_DIGEST}" --restore-not-after "${RESTORE_NOT_AFTER}" \
    --window-start-epoch "${WINDOW_START}" --window-end-epoch "${WINDOW_END}" \
    --fault-start-epoch "${FAULT_START}" --fault-end-epoch "${FAULT_END}"
  ARMED=true
  RUNTIME_SECONDS="$((DEADLINE - $(date +%s)))"
  (( RUNTIME_SECONDS >= 120 && RUNTIME_SECONDS <= 10800 )) || fail "deadline is invalid"
  RESTORE_GRACE_SECONDS="$((RESTORE_NOT_AFTER - DEADLINE))"
  (( RESTORE_GRACE_SECONDS >= 180 && RESTORE_GRACE_SECONDS <= 900 )) || \
    fail "restore grace period is invalid"
  install -d -o root -g root -m 700 "${CONTROLLER_DIR}"
  atomic_install "${STABLE_DISPATCHER}" "${CONTROLLER_DIR}/prior-dispatcher"
  CONTROLLER_INSTALLED=true
  atomic_install "${LIVE_DIR}/deploy/scripts/capacity-control-host.sh" \
    "${CONTROLLER_DIR}/capacity-control-host.sh"
  atomic_install "${LIVE_DIR}/deploy/scripts/capacity_dispatcher_binding.py" \
    "${CONTROLLER_DIR}/capacity_dispatcher_binding.py"
  restore_script="${CONTROLLER_DIR}/restore-dispatcher.sh"
  cat > "${restore_script}" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
exec 9>"${STATE_DIR}/pathlab-capacity-controller.lock"
lock_seconds=\$(( ${RESTORE_NOT_AFTER} - \$(date +%s) ))
(( lock_seconds > 0 )) || exit 1
(( lock_seconds <= 60 )) || lock_seconds=60
flock --exclusive --timeout "\${lock_seconds}" 9 || exit 1
(( \$(date +%s) < ${RESTORE_NOT_AFTER} )) || exit 1
# A retired run must never replace another run's dispatcher or pointer.
[[ -f "${CONTROLLER_POINTER}" && ! -L "${CONTROLLER_POINTER}" ]] || exit 1
[[ "\$(cat "${CONTROLLER_POINTER}")" == "${CONTROLLER_DIR}" ]] || exit 1
if [[ -e "${STATE_DIR}/pathlab-capacity-active.json" ]]; then
  jq -e --arg run "${RUN_ID}" '.runId == \$run' \
    "${STATE_DIR}/pathlab-capacity-active.json" >/dev/null || exit 1
fi
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
  runtime_tmp="${STATE_DIR}/pathlab-capacity-${RUN_ID}-runtime.json.tmp"
  final_tmp="${STATE_DIR}/pathlab-capacity-${RUN_ID}-final.json.tmp"
  bash "${STATE_DIR}/pathlab-capacity-${RUN_ID}-restore.sh" \
    "${SHA}" "${MANIFEST_DIGEST}" "${RESTORE_NOT_AFTER}" > "\${runtime_tmp}"
chmod 600 "\${runtime_tmp}"
mv -- "\${runtime_tmp}" "${STATE_DIR}/pathlab-capacity-${RUN_ID}-runtime.json"
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
  <(jq '{runId,workflowSha,planDigest,deadlineEpoch,runtimeManifestDigest,restoreNotAfter,
    windowStartEpoch,windowEndEpoch,phase,finalLimit,faultConsumed}' \
    "${STATE_DIR}/pathlab-capacity-${RUN_ID}-control.json") \
  "${STATE_DIR}/pathlab-capacity-${RUN_ID}-runtime.json" > "\${final_tmp}"
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
  cleanup_epoch="$((RESTORE_NOT_AFTER - 2))"
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
  CONTROLLER_POINTER_INSTALLED=true
  python3 - "${STATE_DIR}" <<'PY'
import os, sys
descriptor = os.open(sys.argv[1], os.O_RDONLY)
try: os.fsync(descriptor)
finally: os.close(descriptor)
PY
  CONTROLLER_LAUNCH_ATTEMPTED=true
  systemd-run --unit "${UNIT}" --collect --property="RuntimeMaxSec=${RUNTIME_SECONDS}" \
    --property="TimeoutStopSec=${RESTORE_GRACE_SECONDS}" \
    bash "${LIVE_DIR}/deploy/scripts/capacity-control-unit.sh" \
      "${RUN_ID}" "${SHA}" "${DIGEST}" "${NONCE_FILE}" "${PREFLIGHT}" "${PREFLIGHT_SIG}" \
      "${MANIFEST_DIGEST}" "${RESTORE_NOT_AFTER}" "${CONTROLLER_DIR}"
  CONTROLLER_STARTED=true
  systemctl is-active --quiet "${UNIT}.service" || fail "capacity unit did not start"
  ready_deadline=$((SECONDS + 120))
  ready=false
  while (( SECONDS < ready_deadline )); do
    systemctl is-active --quiet "${UNIT}.service" || fail "capacity unit stopped before readiness"
    if [[ -f "${READY_FILE}" ]] && python3 - "${READY_FILE}" "${RUN_ID}" "${SHA}" <<'PY'
import json
import sys

value = json.load(open(sys.argv[1], encoding="utf-8"))
valid = value == {
    "annotationsEnabled": True,
    "capacity": 2000,
    "releaseSha": sys.argv[3],
    "runId": sys.argv[2],
    "servicesReady": True,
}
raise SystemExit(0 if valid else 1)
PY
    then
      ready=true
      break
    fi
    sleep 1
  done
  [[ "${ready}" == true ]] || fail "capacity services did not become ready"
  trap - EXIT
  exit 0
fi

if [[ "${REQUEST}" =~ ^capacity-status[[:space:]]run=([a-z0-9-]{1,64})$ ]]; then
  exec python3 "${LIVE_DIR}/deploy/scripts/capacity_control.py" status --run-id "${BASH_REMATCH[1]}"
fi

if [[ "${REQUEST}" =~ ^capacity-runtime-preflight[[:space:]]expected=([0-9a-f]{40})([[:space:]]manifest=([0-9a-f]{64}))?$ ]]; then
  runtime_status "${BASH_REMATCH[1]}" "${BASH_REMATCH[3]:-}"
  exit 0
fi

if [[ "${REQUEST}" =~ ^capacity-postflight[[:space:]]expected=([0-9a-f]{40})[[:space:]]manifest=([0-9a-f]{64})$ ]]; then
  runtime_status "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
  exit 0
fi

if [[ "${REQUEST}" =~ ^capacity-finalize[[:space:]]([0-9a-f]{40})[[:space:]]run=([a-z0-9-]{1,64})[[:space:]]digest=([0-9a-f]{64})[[:space:]]evidence=([A-Za-z0-9_-]+)[[:space:]]signature=([0-9a-f]{64})[[:space:]]nonce=([A-Za-z0-9._-]{8,128})$ ]]; then
  SHA="${BASH_REMATCH[1]}"; RUN_ID="${BASH_REMATCH[2]}"; DIGEST="${BASH_REMATCH[3]}"
  EVIDENCE_B64="${BASH_REMATCH[4]}"; SIGNATURE="${BASH_REMATCH[5]}"; NONCE="${BASH_REMATCH[6]}"
  begin_owned_mutation "${RUN_ID}" "${SHA}"
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
  RESTORE_NOT_AFTER="$(jq -er --arg digest "${DIGEST}" \
    'select(.planDigest == $digest) | .restoreNotAfter' "${CONTROL_STATE}")"
  while (( $(date +%s) < RESTORE_NOT_AFTER )); do
    STATUS="$(jq -c '{runId,workflowSha,planDigest,deadlineEpoch,runtimeManifestDigest,restoreNotAfter,
      windowStartEpoch,windowEndEpoch,phase,finalLimit,faultConsumed}' "${CONTROL_STATE}")"
    if jq -e '.phase == "restored"' <<< "${STATUS}" >/dev/null && \
       [[ -s "${FINAL_RESULT}" ]]; then
      cat "${FINAL_RESULT}"
      exit 0
    fi
    jq -e '.phase == "restore-failed"' <<< "${STATUS}" >/dev/null && \
      fail "capacity restoration failed"
    remaining="$((RESTORE_NOT_AFTER - $(date +%s)))"
    (( remaining > 0 )) || break
    (( remaining > 2 )) && sleep 2 || sleep "${remaining}"
  done
  fail "capacity restoration did not finish before its bound deadline"
fi

if [[ "${REQUEST}" =~ ^capacity-fault[[:space:]]run=([a-z0-9-]{1,64})[[:space:]]digest=([0-9a-f]{64})$ ]]; then
  RUN_ID="${BASH_REMATCH[1]}"; DIGEST="${BASH_REMATCH[2]}"
  begin_owned_mutation "${RUN_ID}"
  python3 "${LIVE_DIR}/deploy/scripts/capacity_control.py" fault \
    --run-id "${RUN_ID}" --plan-digest "${DIGEST}" || fail "fault request was rejected"
  cd "${LIVE_DIR}/deploy"
  CONTAINER="$(docker compose ps -q classroom)"
  [[ -n "${CONTAINER}" ]] || fail "Classroom container is unavailable"
  docker kill --signal=STOP "${CONTAINER}" >/dev/null
  exit 0
fi

if [[ "${REQUEST}" =~ ^capacity-terminate-controller[[:space:]]run=([a-z0-9-]{1,64})[[:space:]]digest=([0-9a-f]{64})$ ]]; then
  RUN_ID="${BASH_REMATCH[1]}"; DIGEST="${BASH_REMATCH[2]}"
  begin_owned_mutation "${RUN_ID}"
  CONTROL_STATE="${STATE_DIR}/pathlab-capacity-${RUN_ID}-control.json"
  jq -e --arg run "${RUN_ID}" --arg digest "${DIGEST}" \
    '.runId == $run and .planDigest == $digest and .phase == "armed"' \
    "${CONTROL_STATE}" >/dev/null || fail "controller termination binding is invalid"
  systemctl is-active --quiet "pathlab-capacity-${RUN_ID}.service" || \
    fail "capacity controller is not active"
  # Kill only the controller shell. Its separately grouped child is then
  # contained by the exact-run recovery command, which proves same-release
  # restoration before admission can resume.
  systemctl kill --kill-whom=main --signal=KILL \
    "pathlab-capacity-${RUN_ID}.service" || fail "controller termination failed"
  jq -n --arg runId "${RUN_ID}" --arg planDigest "${DIGEST}" \
    '{runId:$runId,planDigest:$planDigest,controllerTerminated:true,recoveryRequired:true}'
  exit 0
fi

if [[ "${REQUEST}" =~ ^capacity-ack[[:space:]]run=([a-z0-9-]{1,64})[[:space:]]digest=([0-9a-f]{64})$ ]]; then
  RUN_ID="${BASH_REMATCH[1]}"; DIGEST="${BASH_REMATCH[2]}"
  begin_owned_mutation "${RUN_ID}"
  CONTROL_STATE="${STATE_DIR}/pathlab-capacity-${RUN_ID}-control.json"
  FINAL_RESULT="${STATE_DIR}/pathlab-capacity-${RUN_ID}-final.json"
  jq -e --arg run "${RUN_ID}" --arg digest "${DIGEST}" \
    '.runId == $run and .planDigest == $digest and
     (.phase == "restored" or .phase == "aborted-restored")' \
    "${CONTROL_STATE}" >/dev/null || fail "capacity acknowledgment binding is invalid"
  [[ -s "${FINAL_RESULT}" ]] || fail "capacity final result is unavailable"
  RESTORE_NOT_AFTER="$(jq -er .restoreNotAfter "${CONTROL_STATE}")"
  jq -n --arg runId "${RUN_ID}" --arg planDigest "${DIGEST}" \
    --argjson cleanupNotAfter "${RESTORE_NOT_AFTER}" \
    '{runId:$runId,planDigest:$planDigest,controllerAcknowledged:true,
      cleanupScheduled:true,cleanupNotAfter:$cleanupNotAfter}'
  exit 0
fi

if [[ "${REQUEST}" =~ ^capacity-recover[[:space:]]run=([a-z0-9-]{1,64})[[:space:]]sha=([0-9a-f]{40})$ ]]; then
  RUN_ID="${BASH_REMATCH[1]}"
  FAILED_SHA="${BASH_REMATCH[2]}"
  lock_controller_mutation
  CONTROL_STATE="${STATE_DIR}/pathlab-capacity-${RUN_ID}-control.json"
  CONTROLLER_DIR="${STATE_DIR}/pathlab-capacity-${RUN_ID}-controller"
  CONTROLLER_POINTER="${STATE_DIR}/pathlab-capacity-controller"
  verify_controller_ownership "${RUN_ID}" "${FAILED_SHA}" true
  CURRENT_SHA="$(cat "${LIVE_DIR}/.pathlab-release" 2>/dev/null || true)"
  MANIFEST_DIGEST="$(jq -er .manifestDigest "${LIVE_DIR}/.pathlab-runtime-safety.json")"
  CONTROLLER_FOUND=false
  if [[ -f "${CONTROL_STATE}" || -d "${CONTROLLER_DIR}" ]]; then
    CONTROLLER_FOUND=true
  fi
  recovery_units=("pathlab-capacity-${RUN_ID}.service"
    "pathlab-capacity-${RUN_ID}-abort-reconcile.service"
    "pathlab-capacity-${RUN_ID}-controller-cleanup.timer"
    "pathlab-capacity-${RUN_ID}-controller-cleanup.service")
  loaded_units=()
  for unit in "${recovery_units[@]}"; do
    load_state="$(systemctl show --property=LoadState --value "${unit}")" || \
      fail "recovery unit state is unavailable"
    case "${load_state}" in
      not-found) ;;
      loaded|masked) loaded_units+=("${unit}") ;;
      *) fail "recovery unit state is unproved" ;;
    esac
  done
  if (( ${#loaded_units[@]} > 0 )); then
    timeout --signal=TERM --kill-after=10s 60s systemctl stop "${loaded_units[@]}" \
      >/dev/null 2>&1 || fail "recovery unit stop failed"
  fi
  for unit in "${loaded_units[@]}"; do
    unit_state="$(systemctl show --property=ActiveState --value "${unit}")" || \
      fail "recovery unit stop is unproved"
    [[ "${unit_state}" == inactive ]] || fail "recovery unit remains active"
  done
  RESTORE_NOT_AFTER="$(( $(date +%s) + 300 ))"
  status="$(bash "${LIVE_DIR}/deploy/scripts/restore-capacity-runtime.sh" \
    "${CURRENT_SHA}" "${MANIFEST_DIGEST}" "${RESTORE_NOT_AFTER}")" || \
    fail "failed-run runtime recovery did not restore the safety floor"
  if [[ -f "${CONTROLLER_POINTER}" ]]; then
    pointer="$(cat "${CONTROLLER_POINTER}")"
    [[ "${pointer}" == "${CONTROLLER_DIR}" ]] || fail "another capacity controller is active"
    rm -f -- "${CONTROLLER_POINTER}"
  fi
  rm -rf -- "${CONTROLLER_DIR}"
  if [[ -f "${CONTROL_STATE}" ]]; then
    python3 - "${CONTROL_STATE}" "${STATE_DIR}/pathlab-capacity-active.json" "${RUN_ID}" <<'PY'
import json, os, pathlib, sys
state_path, active_path = map(pathlib.Path, sys.argv[1:3])
run_id = sys.argv[3]
value = json.loads(state_path.read_text(encoding="utf-8"))
if value.get("runId") != run_id:
    raise SystemExit(1)
value["phase"] = "aborted-restored"
value["finalLimit"] = None
temporary = state_path.with_suffix(state_path.suffix + ".tmp")
temporary.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
os.chmod(temporary, 0o600)
os.replace(temporary, state_path)
if active_path.exists():
    active = json.loads(active_path.read_text(encoding="utf-8"))
    if active.get("runId") == run_id:
        active_path.unlink()
PY
  fi
  jq -c --arg run "${RUN_ID}" --argjson found "${CONTROLLER_FOUND}" \
    '. + {recoveredRunId:$run,controllerFound:$found,controllerReconciled:true}' <<< "${status}"
  exit 0
fi

if [[ "${REQUEST}" =~ ^capacity-abort[[:space:]]run=([a-z0-9-]{1,64})[[:space:]]digest=([0-9a-f]{64})$ ]]; then
  RUN_ID="${BASH_REMATCH[1]}"; DIGEST="${BASH_REMATCH[2]}"
  begin_owned_mutation "${RUN_ID}"
  CONTROL_STATE="${STATE_DIR}/pathlab-capacity-${RUN_ID}-control.json"
  CONTROL="$(cat "${CONTROL_STATE}")"
  mapfile -t restore_binding < <(jq -er --arg digest "${DIGEST}" \
    'select(.planDigest == $digest) | .runtimeManifestDigest, (.restoreNotAfter | tostring)' <<< "${CONTROL}")
  [[ "${#restore_binding[@]}" -eq 2 ]] || fail "abort binding is invalid"
  MANIFEST_DIGEST="${restore_binding[0]}"; RESTORE_NOT_AFTER="${restore_binding[1]}"
  WORKFLOW_SHA="$(jq -er .workflowSha "${CONTROL_STATE}")"
  FINAL_RESULT="${STATE_DIR}/pathlab-capacity-${RUN_ID}-final.json"
  if [[ -s "${FINAL_RESULT}" ]] && \
    jq -e '(.phase == "aborted-restored" and .finalLimit == null) or
      (.phase == "restored" and .finalLimit == 300)' "${CONTROL_STATE}" >/dev/null && \
    jq -e --arg manifest "${MANIFEST_DIGEST}" \
      '.releaseExact == true and .servicesExact == true and .ready == true and
       .runtimeManifestDigest == $manifest and .classroomEnabled == true and
       .finalCapacity == 300 and .annotationsEnabled == false' "${FINAL_RESULT}" >/dev/null; then
    cat "${FINAL_RESULT}"
    exit 0
  fi
  # The detached host unit owns restoration; the SSH caller
  # only requests abort and waits for the retained, host-produced result.
  if jq -e '.phase == "restored" and (.finalLimit == 1200 or .finalLimit == 1500)' \
    "${CONTROL_STATE}" >/dev/null; then
    if ! systemctl is-active --quiet "pathlab-capacity-${RUN_ID}-abort-reconcile.service"; then
      remaining="$((RESTORE_NOT_AFTER - $(date +%s)))"
      (( remaining > 10 )) || fail "abort reconciliation deadline elapsed"
      systemd-run --unit "pathlab-capacity-${RUN_ID}-abort-reconcile" --collect \
        --property="RuntimeMaxSec=${remaining}" \
        bash "${STATE_DIR}/pathlab-capacity-${RUN_ID}-controller/reconcile-abort.sh"
    fi
  else
    systemctl kill --kill-whom=main --signal=USR1 "pathlab-capacity-${RUN_ID}.service" || true
  fi
  while (( $(date +%s) < RESTORE_NOT_AFTER )); do
    STATUS="$(jq -c '{runId,workflowSha,planDigest,deadlineEpoch,runtimeManifestDigest,restoreNotAfter,
      windowStartEpoch,windowEndEpoch,phase,finalLimit,faultConsumed}' "${CONTROL_STATE}")"
    if jq -e '.phase == "aborted-restored" and .finalLimit == null' <<< "${STATUS}" >/dev/null && \
       [[ "$(cat "${LIVE_DIR}/.pathlab-release" 2>/dev/null || true)" == "${WORKFLOW_SHA}" ]] && \
       [[ -s "${FINAL_RESULT}" ]]; then
      cat "${FINAL_RESULT}"
      exit 0
    fi
    remaining="$((RESTORE_NOT_AFTER - $(date +%s)))"
    (( remaining > 0 )) || break
    (( remaining > 2 )) && sleep 2 || sleep "${remaining}"
  done
  fail "capacity abort did not restore the safe runtime before its bound deadline"
fi

fail "request is not an approved capacity control operation"
