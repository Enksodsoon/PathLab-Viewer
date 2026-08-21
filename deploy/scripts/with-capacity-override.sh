#!/usr/bin/env bash
set -Eeuo pipefail

: "${PATHLAB_CAPACITY_DECISION_FILE:?PATHLAB_CAPACITY_DECISION_FILE is required}"
: "${PATHLAB_CAPACITY_DECISION_SIGNATURE_FILE:?PATHLAB_CAPACITY_DECISION_SIGNATURE_FILE is required}"
: "${PATHLAB_CAPACITY_PREFLIGHT_EVIDENCE:?PATHLAB_CAPACITY_PREFLIGHT_EVIDENCE is required}"
: "${PATHLAB_CAPACITY_PREFLIGHT_SIGNATURE:?PATHLAB_CAPACITY_PREFLIGHT_SIGNATURE is required}"
: "${PATHLAB_CAPACITY_CANDIDATE_SHA:?PATHLAB_CAPACITY_CANDIDATE_SHA is required}"
: "${PATHLAB_CAPACITY_RUN_ID:?PATHLAB_CAPACITY_RUN_ID is required}"
: "${PATHLAB_CAPACITY_NONCE:?PATHLAB_CAPACITY_NONCE is required}"
ENV_FILE="${PATHLAB_CAPACITY_ENV_FILE:-/opt/pathlab-viewer/deploy/.env}"
COMPOSE_DIR="${PATHLAB_COMPOSE_DIR:-/opt/pathlab-viewer/deploy}"
PYTHON_BIN="${PATHLAB_PYTHON:-python3}"
RUNTIME_DIR="${PATHLAB_CAPACITY_RUNTIME_DIR:-/run}"
RESTORE_EVIDENCE="${PATHLAB_CAPACITY_RESTORE_EVIDENCE:-${RUNTIME_DIR}/pathlab-capacity-${PATHLAB_CAPACITY_RUN_ID}-restore.json}"
[[ "$#" -gt 0 ]] || { echo "Usage: with-capacity-override.sh command [args...]" >&2; exit 2; }
if [[ "${ENV_FILE}" == /opt/pathlab-viewer/deploy/.env ]]; then
  [[ "${COMPOSE_DIR}" == /opt/pathlab-viewer/deploy && "${RUNTIME_DIR}" == /run ]] || {
    echo "Refusing unexpected production capacity paths" >&2
    exit 2
  }
else
  [[ -n "${PATHLAB_CAPACITY_TEST_MODE:-}" && "${ENV_FILE}" == "${COMPOSE_DIR}/.env" && \
    "${RUNTIME_DIR}" == "${COMPOSE_DIR}/runtime" ]] || {
    echo "Refusing unexpected capacity environment file" >&2
    exit 2
  }
fi
[[ "${PATHLAB_CAPACITY_DECISION_FILE}" == "${RUNTIME_DIR}/pathlab-capacity-${PATHLAB_CAPACITY_RUN_ID}.json" ]] || {
  echo "Capacity decision path is not run-bound" >&2
  exit 2
}
[[ "${PATHLAB_CAPACITY_DECISION_SIGNATURE_FILE}" == "${PATHLAB_CAPACITY_DECISION_FILE}.sig" ]] || {
  echo "Capacity decision signature path is not run-bound" >&2
  exit 2
}

"${PYTHON_BIN}" "${COMPOSE_DIR}/scripts/production_safety.py" \
  preflight "${PATHLAB_CAPACITY_PREFLIGHT_EVIDENCE}" \
  "${PATHLAB_CAPACITY_CANDIDATE_SHA}" \
  --signature "${PATHLAB_CAPACITY_PREFLIGHT_SIGNATURE}" \
  --nonce "${PATHLAB_CAPACITY_NONCE}"
NOW_EPOCH="$(date +%s)"
if [[ -n "${PATHLAB_CAPACITY_TEST_MODE:-}" ]]; then
  REQUIRED_RUNTIME_SECONDS="${PATHLAB_CAPACITY_TEST_REQUIRED_RUNTIME_SECONDS:-7200}"
  KILL_AFTER_SECONDS="${PATHLAB_CAPACITY_TEST_KILL_AFTER_SECONDS:-5}"
  DEADLINE_SAFETY_SECONDS="${PATHLAB_CAPACITY_TEST_DEADLINE_SAFETY_SECONDS:-1}"
  DEFAULT_TEST_REMAINING=10800
  if [[ "${PATHLAB_CAPACITY_TEST_ICT_SECONDS:-}" =~ ^[0-9]+$ ]]; then
    DEFAULT_TEST_REMAINING="$((5 * 3600 - PATHLAB_CAPACITY_TEST_ICT_SECONDS))"
  fi
  TEST_LAUNCH_REMAINING="${PATHLAB_CAPACITY_TEST_LAUNCH_SECONDS_UNTIL_END:-${DEFAULT_TEST_REMAINING}}"
  [[ "${TEST_LAUNCH_REMAINING}" =~ ^[1-9][0-9]*$ ]] || {
    echo "Capacity test deadline is invalid" >&2
    exit 2
  }
  WINDOW_END_EPOCH="$(($(date +%s) + TEST_LAUNCH_REMAINING))"
  WINDOW_START_EPOCH="${PATHLAB_CAPACITY_WINDOW_START_EPOCH:-${NOW_EPOCH}}"
else
  : "${PATHLAB_CAPACITY_WINDOW_START_EPOCH:?authorized capacity window start is required}"
  : "${PATHLAB_CAPACITY_WINDOW_END_EPOCH:?authorized capacity window end is required}"
  REQUIRED_RUNTIME_SECONDS=7200
  KILL_AFTER_SECONDS=30
  DEADLINE_SAFETY_SECONDS=5
  WINDOW_START_EPOCH="${PATHLAB_CAPACITY_WINDOW_START_EPOCH}"
  WINDOW_END_EPOCH="${PATHLAB_CAPACITY_WINDOW_END_EPOCH}"
fi
[[ "${REQUIRED_RUNTIME_SECONDS}" =~ ^[1-9][0-9]*$ && \
  "${KILL_AFTER_SECONDS}" =~ ^[1-9][0-9]*$ && \
  "${DEADLINE_SAFETY_SECONDS}" =~ ^[1-9][0-9]*$ && \
  "${WINDOW_START_EPOCH}" =~ ^[1-9][0-9]*$ && \
  "${WINDOW_END_EPOCH}" =~ ^[1-9][0-9]*$ ]] || {
  echo "Capacity runtime deadline is invalid" >&2
  exit 2
}
if [[ -z "${PATHLAB_CAPACITY_TEST_MODE:-}" ]]; then
  [[ "$((WINDOW_END_EPOCH - WINDOW_START_EPOCH))" -eq 10800 && \
    "${NOW_EPOCH}" -ge "${WINDOW_START_EPOCH}" && \
    "${NOW_EPOCH}" -le "$((WINDOW_START_EPOCH + 300))" ]] || {
    echo "Capacity override is outside its explicit three-hour authorized window" >&2
    exit 2
  }
fi
SECONDS_UNTIL_WINDOW_END="$((WINDOW_END_EPOCH - NOW_EPOCH))"
[[ "${SECONDS_UNTIL_WINDOW_END}" -ge "${REQUIRED_RUNTIME_SECONDS}" ]] || {
  echo "Capacity override lacks two hours before the authorized hard stop" >&2
  exit 2
}

existing="$(sed -n 's/^PATHLAB_CLASSROOM_MAX_PARTICIPANTS=//p' "${ENV_FILE}")"
[[ -z "${existing}" || "${existing}" =~ ^([1-9][0-9]{0,2}|1[0-9]{3}|2000)$ ]] || {
  echo "Existing Classroom capacity is invalid" >&2
  exit 2
}
PRIOR_LIMIT="${existing:-300}"
RESTORE_LIMIT="300"
existing_annotations="$(sed -n 's/^PATHLAB_ANNOTATIONS_ENABLED=//p' "${ENV_FILE}" | tail -n 1)"
[[ "${existing_annotations:-false}" =~ ^(true|false)$ ]] || {
  echo "Existing annotation feature state is invalid" >&2
  exit 2
}
RESTORE_ANNOTATIONS="${existing_annotations:-__absent__}"
if [[ "${RUNTIME_DIR}" == /run ]]; then
  install -d -m 0700 "${RUNTIME_DIR}"
else
  mkdir -p -- "${RUNTIME_DIR}"
fi
PRIOR_SNAPSHOT="$(mktemp "${RUNTIME_DIR}/pathlab-capacity-prior-XXXXXX.env")"
install -m 0600 "${ENV_FILE}" "${PRIOR_SNAPSHOT}"
START_EPOCH="$(date +%s)"
rm -f -- "${PATHLAB_CAPACITY_DECISION_FILE}" "${PATHLAB_CAPACITY_DECISION_SIGNATURE_FILE}"

set_environment() {
  local limit="$1"
  local annotations="$2"
  local temporary
  temporary="$(mktemp "${ENV_FILE}.XXXXXX")"
  awk -v value="${limit}" '
    BEGIN { found=0 }
    /^PATHLAB_CLASSROOM_MAX_PARTICIPANTS=/ {
      if (!found) print "PATHLAB_CLASSROOM_MAX_PARTICIPANTS=" value
      found=1
      next
    }
    { print }
    END { if (!found) print "PATHLAB_CLASSROOM_MAX_PARTICIPANTS=" value }
  ' "${ENV_FILE}" > "${temporary}"
  chmod --reference="${ENV_FILE}" "${temporary}"
  mv -- "${temporary}" "${ENV_FILE}"
  temporary="$(mktemp "${ENV_FILE}.XXXXXX")"
  awk -v value="${annotations}" '
    BEGIN { found=0 }
    /^PATHLAB_ANNOTATIONS_ENABLED=/ {
      if (!found && value != "__absent__") print "PATHLAB_ANNOTATIONS_ENABLED=" value
      found=1
      next
    }
    { print }
    END { if (!found && value != "__absent__") print "PATHLAB_ANNOTATIONS_ENABLED=" value }
  ' "${ENV_FILE}" > "${temporary}"
  chmod --reference="${ENV_FILE}" "${temporary}"
  mv -- "${temporary}" "${ENV_FILE}"
}

reload_capacity_services() {
  local remaining
  remaining="$((RESTORE_NOT_AFTER - $(date +%s) - 5))"
  (( remaining > 0 )) || return 1
  (
    cd "${COMPOSE_DIR}"
    timeout --signal=TERM --kill-after=5s "${remaining}s" \
      docker compose up -d --no-deps --force-recreate api classroom || exit 1
    remaining="$((RESTORE_NOT_AFTER - $(date +%s) - 5))"
    (( remaining > 0 )) || exit 1
    running="$(timeout --signal=TERM --kill-after=5s "${remaining}s" \
      docker compose ps --status running --services api classroom | sort)" || exit 1
    [[ "${running}" == $'api\nclassroom' ]]
  )
}

contain_unsafe_runtime() {
  local remaining="$((RESTORE_NOT_AFTER - $(date +%s) - 5))"
  (( remaining > 0 )) || return 1
  (
    cd "${COMPOSE_DIR}"
    timeout --signal=TERM --kill-after=5s "${remaining}s" docker compose stop api classroom
  ) || true
}

ACTIVATION_DIR="${PATHLAB_ANNOTATION_ACTIVATION_DIR:-/var/lib/pathlab-viewer}"
if [[ -n "${PATHLAB_CAPACITY_TEST_MODE:-}" ]]; then
  ACTIVATION_DIR="${RUNTIME_DIR}/annotation-activation"
fi
mkdir -p -- "${ACTIVATION_DIR}"
ACTIVATION_DECISION_READY=0

apply_activation_decision() {
  (( ACTIVATION_DECISION_READY == 1 )) || return 0
  if [[ "${RESTORE_ANNOTATIONS}" == true ]]; then
    install -m 0600 "${PATHLAB_CAPACITY_DECISION_FILE}" \
      "${ACTIVATION_DIR}/annotation-activation.json" || return 1
    install -m 0600 "${PATHLAB_CAPACITY_DECISION_SIGNATURE_FILE}" \
      "${ACTIVATION_DIR}/annotation-activation.json.sig" || return 1
  else
    rm -f -- "${ACTIVATION_DIR}/annotation-activation.json" \
      "${ACTIVATION_DIR}/annotation-activation.json.sig"
  fi
}

restore_prior() {
  local exit_code=$?
  trap - EXIT INT TERM
  if ! set_environment "${RESTORE_LIMIT}" "${RESTORE_ANNOTATIONS}" || ! reload_capacity_services; then
    install -m 0600 "${PRIOR_SNAPSHOT}" "${ENV_FILE}" || true
    contain_unsafe_runtime
    echo "Capacity restoration failed; API and Classroom were stopped" >&2
    rm -f -- "${PRIOR_SNAPSHOT}"
    exit 1
  fi
  grep -qx "PATHLAB_CLASSROOM_MAX_PARTICIPANTS=${RESTORE_LIMIT}" "${ENV_FILE}" || exit 1
  if [[ "${RESTORE_ANNOTATIONS}" == __absent__ ]]; then
    ! grep -q '^PATHLAB_ANNOTATIONS_ENABLED=' "${ENV_FILE}" || exit 1
  else
    grep -qx "PATHLAB_ANNOTATIONS_ENABLED=${RESTORE_ANNOTATIONS}" "${ENV_FILE}" || exit 1
  fi
  if ! apply_activation_decision; then
    rm -f -- "${ACTIVATION_DIR}/annotation-activation.json" \
      "${ACTIVATION_DIR}/annotation-activation.json.sig"
    if ! set_environment "${RESTORE_LIMIT}" false || ! reload_capacity_services; then
      contain_unsafe_runtime
    fi
    echo "Annotation activation marker installation failed; annotations were disabled" >&2
    rm -f -- "${PRIOR_SNAPSHOT}"
    exit 1
  fi
  local restore_temporary="${RESTORE_EVIDENCE}.tmp"
  printf '{"configurationRestored":true,"finalLimit":%s,"servicesReady":true}\n' \
    "${RESTORE_LIMIT}" > "${restore_temporary}"
  chmod 0600 "${restore_temporary}"
  mv -- "${restore_temporary}" "${RESTORE_EVIDENCE}"
  rm -f -- "${PRIOR_SNAPSHOT}"
  exit "${exit_code}"
}
RESTORE_NOT_AFTER="${PATHLAB_CAPACITY_RESTORE_NOT_AFTER:-${WINDOW_END_EPOCH}}"
[[ "${RESTORE_NOT_AFTER}" =~ ^[1-9][0-9]*$ ]] || {
  echo "Capacity restoration deadline is invalid" >&2
  exit 2
}
trap restore_prior EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

set_environment 2000 true
grep -qx 'PATHLAB_CLASSROOM_MAX_PARTICIPANTS=2000' "${ENV_FILE}"
grep -qx 'PATHLAB_ANNOTATIONS_ENABLED=true' "${ENV_FILE}"
reload_capacity_services
LAUNCH_REMAINING_SECONDS="$((WINDOW_END_EPOCH - $(date +%s)))"
COMMAND_TIMEOUT_SECONDS="$((LAUNCH_REMAINING_SECONDS - KILL_AFTER_SECONDS - DEADLINE_SAFETY_SECONDS))"
[[ "${COMMAND_TIMEOUT_SECONDS}" -ge 1 ]] || {
  echo "Capacity runtime deadline elapsed during setup" >&2
  exit 2
}
timeout --signal=TERM --kill-after="${KILL_AFTER_SECONDS}s" \
  "${COMMAND_TIMEOUT_SECONDS}s" "$@"
[[ -f "${PATHLAB_CAPACITY_DECISION_FILE}" ]] || {
  echo "Capacity command did not produce a decision" >&2
  exit 1
}
[[ -f "${PATHLAB_CAPACITY_DECISION_SIGNATURE_FILE}" ]] || {
  echo "Capacity command did not produce a decision signature" >&2
  exit 1
}
[[ "$(stat -c %Y "${PATHLAB_CAPACITY_DECISION_FILE}")" -ge "${START_EPOCH}" ]] || {
  echo "Capacity decision is stale" >&2
  exit 1
}
FINAL_LIMIT="$("${PYTHON_BIN}" "${COMPOSE_DIR}/scripts/production_safety.py" \
  capacity-decision "${PATHLAB_CAPACITY_DECISION_FILE}" \
  "${PATHLAB_CAPACITY_CANDIDATE_SHA}" \
  --signature "$(cat "${PATHLAB_CAPACITY_DECISION_SIGNATURE_FILE}")" \
  --run-id "${PATHLAB_CAPACITY_RUN_ID}" \
  --nonce "${PATHLAB_CAPACITY_NONCE}" \
  --not-before "${START_EPOCH}")"
[[ "${FINAL_LIMIT}" =~ ^(300|1200|1500)$ ]] || {
  echo "Capacity decision is invalid" >&2
  exit 2
}
RESTORE_LIMIT="${FINAL_LIMIT}"
if [[ "${FINAL_LIMIT}" == 1200 || "${FINAL_LIMIT}" == 1500 ]]; then
  RESTORE_ANNOTATIONS="true"
else
  RESTORE_ANNOTATIONS="false"
fi
ACTIVATION_DECISION_READY=1
