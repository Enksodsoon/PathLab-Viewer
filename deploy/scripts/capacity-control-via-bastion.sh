#!/usr/bin/env bash
set -Eeuo pipefail

[[ "$#" -ge 1 && "$#" -le 2 ]] || {
  echo "Capacity Bastion control failed: one request, or the exact preflight/arm pair, is required" >&2
  exit 1
}
REMOTE_REQUESTS=("$@")
TARGET_USER="${OCI_TARGET_USER:-pathlab-deploy}"
if [[ -n "${PATHLAB_CAPACITY_OCI_COMMAND:-}${PATHLAB_CAPACITY_SSH_KEYGEN_COMMAND:-}${PATHLAB_CAPACITY_SSH_COMMAND:-}${PATHLAB_CAPACITY_JQ_COMMAND:-}" && \
      "${PATHLAB_CAPACITY_TEST_MODE:-}" != true ]]; then
  echo "Capacity Bastion control failed: command overrides require capacity test mode" >&2
  exit 1
fi
OCI_COMMAND="${PATHLAB_CAPACITY_OCI_COMMAND:-oci}"
SSH_KEYGEN_COMMAND="${PATHLAB_CAPACITY_SSH_KEYGEN_COMMAND:-ssh-keygen}"
SSH_COMMAND_EXECUTABLE="${PATHLAB_CAPACITY_SSH_COMMAND:-ssh}"
JQ_COMMAND="${PATHLAB_CAPACITY_JQ_COMMAND:-jq}"
SESSION_ID=""
WORK_DIR="$(mktemp -d)"
KEY_FILE="${WORK_DIR}/bastion-session"

fail() { echo "Capacity Bastion control failed: $*" >&2; exit 1; }
delete_session() {
  local state="" output="" deleted=false
  [[ -n "${SESSION_ID}" ]] || return 0
  for _ in $(seq 1 3); do
    if "${OCI_COMMAND}" bastion session delete --session-id "${SESSION_ID}" --force \
      >/dev/null 2>&1; then
      deleted=true
      break
    fi
    sleep 2
  done
  if [[ "${deleted}" != true ]]; then
    if output="$("${OCI_COMMAND}" bastion session get --session-id "${SESSION_ID}" \
        --query 'data."lifecycle-state"' --raw-output 2>&1)"; then
      [[ "${output}" == DELETED ]] && return 0
    elif grep -Eq 'NotAuthorizedOrNotFound|NotFound|404' <<< "${output}"; then
      return 0
    fi
    return 1
  fi
  for _ in $(seq 1 20); do
    if output="$("${OCI_COMMAND}" bastion session get --session-id "${SESSION_ID}" \
        --query 'data."lifecycle-state"' --raw-output 2>&1)"; then
      state="${output}"
      [[ "${state}" == DELETED ]] && return 0
    elif grep -Eq 'NotAuthorizedOrNotFound|NotFound|404' <<< "${output}"; then
      return 0
    else
      return 1
    fi
    sleep 2
  done
  return 1
}
cleanup() {
  local result=$?
  trap - EXIT
  if ! delete_session; then
    echo "Capacity Bastion control failed: session deletion could not be proved" >&2
    result=1
  fi
  rm -rf -- "${WORK_DIR}"
  exit "${result}"
}
trap cleanup EXIT

ARM_PATTERN='^capacity-arm [0-9a-f]{40} run=[a-z0-9-]{1,64} digest=[0-9a-f]{64} manifest=[0-9a-f]{64} arm-not-after=[0-9]{10} window-start=[0-9]{10} window-end=[0-9]{10} deadline=[0-9]{10} restore-not-after=[0-9]{10} fault-start=[0-9]{10} fault-end=[0-9]{10} evidence=[A-Za-z0-9_-]+ signature=[0-9a-f]{64} nonce=[A-Za-z0-9._-]{8,128}$'
STATUS_PATTERN='^capacity-status run=[a-z0-9-]{1,64}$'
FINALIZE_PATTERN='^capacity-finalize [0-9a-f]{40} run=[a-z0-9-]{1,64} digest=[0-9a-f]{64} evidence=[A-Za-z0-9_-]+ signature=[0-9a-f]{64} nonce=[A-Za-z0-9._-]{8,128}$'
FAULT_PATTERN='^capacity-fault run=[a-z0-9-]{1,64} digest=[0-9a-f]{64}$'
TERMINATE_PATTERN='^capacity-terminate-controller run=[a-z0-9-]{1,64} digest=[0-9a-f]{64}$'
ABORT_PATTERN='^capacity-abort run=[a-z0-9-]{1,64} digest=[0-9a-f]{64}$'
ACK_PATTERN='^capacity-ack run=[a-z0-9-]{1,64} digest=[0-9a-f]{64}$'
POSTFLIGHT_PATTERN='^capacity-postflight expected=[0-9a-f]{40} manifest=[0-9a-f]{64}$'
RUNTIME_PREFLIGHT_PATTERN='^capacity-runtime-preflight expected=[0-9a-f]{40}( manifest=[0-9a-f]{64})?$'
RECOVER_PATTERN='^capacity-recover run=[a-z0-9-]{1,64} sha=[0-9a-f]{40}$'
if [[ "${#REMOTE_REQUESTS[@]}" -eq 2 ]]; then
  [[ "${REMOTE_REQUESTS[0]}" =~ ${RUNTIME_PREFLIGHT_PATTERN} && \
     "${REMOTE_REQUESTS[1]}" =~ ${ARM_PATTERN} ]] || \
    fail "only runtime preflight and arm may share a session"
fi
for remote_request in "${REMOTE_REQUESTS[@]}"; do
  [[ "${remote_request}" =~ ${ARM_PATTERN} || "${remote_request}" =~ ${STATUS_PATTERN} || \
     "${remote_request}" =~ ${FINALIZE_PATTERN} || "${remote_request}" =~ ${FAULT_PATTERN} || \
      "${remote_request}" =~ ${TERMINATE_PATTERN} || \
      "${remote_request}" =~ ${ABORT_PATTERN} || "${remote_request}" =~ ${ACK_PATTERN} || \
      "${remote_request}" =~ ${POSTFLIGHT_PATTERN} || "${remote_request}" =~ ${RECOVER_PATTERN} || \
      "${remote_request}" =~ ${RUNTIME_PREFLIGHT_PATTERN} ]] || fail "request is not allowlisted"
done
: "${OCI_BASTION_ID:?OCI_BASTION_ID is required}"
: "${OCI_INSTANCE_ID:?OCI_INSTANCE_ID is required}"
: "${OCI_TARGET_PRIVATE_IP:?OCI_TARGET_PRIVATE_IP is required}"
: "${OCI_KNOWN_HOSTS_FILE:?OCI_KNOWN_HOSTS_FILE is required}"
[[ -f "${OCI_KNOWN_HOSTS_FILE}" ]] || fail "pinned SSH host keys are missing"

"${SSH_KEYGEN_COMMAND}" -q -t ed25519 -N "" -f "${KEY_FILE}"
action="${REMOTE_REQUESTS[0]%% *}"
action="${action#capacity-}"
SESSION_ID="$("${OCI_COMMAND}" bastion session create-managed-ssh \
  --bastion-id "${OCI_BASTION_ID}" --display-name "pathlab-capacity-${GITHUB_RUN_ID:-manual}-${action}" \
  --key-type PUB --ssh-public-key-file "${KEY_FILE}.pub" \
  --target-resource-id "${OCI_INSTANCE_ID}" --target-private-ip "${OCI_TARGET_PRIVATE_IP}" \
  --target-port 22 --target-os-username "${TARGET_USER}" --session-ttl 1800 \
  --query 'data.id' --raw-output)"
[[ "${SESSION_ID}" == ocid1.bastionsession.* ]] || fail "OCI did not return a session OCID"
for _ in $(seq 1 40); do
  STATE="$("${OCI_COMMAND}" bastion session get --session-id "${SESSION_ID}" \
    --query 'data."lifecycle-state"' --raw-output)"
  [[ "${STATE}" == ACTIVE ]] && break
  [[ "${STATE}" == FAILED ]] && fail "Bastion session failed"
  sleep 5
done
[[ "${STATE:-}" == ACTIVE ]] || fail "Bastion session did not become active"
SSH_COMMAND="$("${OCI_COMMAND}" bastion session get --session-id "${SESSION_ID}" \
  --query 'data."ssh-metadata".command' --raw-output)"
[[ "${SSH_COMMAND}" == ssh\ * ]] || fail "OCI did not return an SSH command"
SSH_COMMAND="${SSH_COMMAND//<privateKey>/${KEY_FILE}}"
SSH_COMMAND="${SSH_COMMAND//exec ssh /ssh }"
SSH_OPTIONS="-o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=${OCI_KNOWN_HOSTS_FILE} -o ConnectTimeout=10 -o ConnectionAttempts=1 -o ServerAliveInterval=5 -o ServerAliveCountMax=2"
SSH_COMMAND="${SSH_COMMAND#ssh }"
run_remote() {
  bash -c "\"${SSH_COMMAND_EXECUTABLE}\" ${SSH_OPTIONS} ${SSH_COMMAND} \"$1\""
}
if [[ "${#REMOTE_REQUESTS[@]}" -eq 1 ]]; then
  single_status="$(run_remote "${REMOTE_REQUESTS[0]}")"
  if [[ "${REMOTE_REQUESTS[0]}" =~ ${ABORT_PATTERN} ]]; then
    abort_run="${REMOTE_REQUESTS[0]#*run=}"
    abort_run="${abort_run%% digest=*}"
    abort_digest="${REMOTE_REQUESTS[0]##*digest=}"
    "${JQ_COMMAND}" -e --arg run "${abort_run}" --arg digest "${abort_digest}" \
      '((.phase == "aborted-restored" and .finalLimit == null) or
       (.phase == "restored" and .finalLimit == 300)) and
       .runId == $run and .planDigest == $digest and .releaseExact == true and
       .servicesExact == true and .ready == true and .classroomEnabled == true and
       .finalCapacity == 300 and .annotationsEnabled == false' <<< "${single_status}" >/dev/null || \
      fail "capacity abort did not restore the safe runtime"
    "${JQ_COMMAND}" -c . <<< "${single_status}"
  else
    printf '%s\n' "${single_status}"
  fi
  exit
fi

first_status="$(run_remote "${REMOTE_REQUESTS[0]}")"
if [[ "${REMOTE_REQUESTS[0]}" =~ ${RUNTIME_PREFLIGHT_PATTERN} ]]; then
  expected_sha="$(sed -n 's/^capacity-runtime-preflight expected=\([0-9a-f]\{40\}\).*/\1/p' \
    <<< "${REMOTE_REQUESTS[0]}")"
  "${JQ_COMMAND}" -e --arg sha "${expected_sha}" \
    '.releaseSha == $sha and .releaseExact == true and .servicesExact == true and
     .ready == true and .classroomEnabled == true and .finalCapacity == 300 and
     .annotationsEnabled == false and (.runtimeManifestDigest | test("^[0-9a-f]{64}$"))' \
    <<< "${first_status}" >/dev/null || fail "runtime preflight did not pass"
fi
"${JQ_COMMAND}" -c . <<< "${first_status}"
run_remote "${REMOTE_REQUESTS[1]}"
