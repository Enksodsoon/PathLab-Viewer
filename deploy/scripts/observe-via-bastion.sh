#!/usr/bin/env bash
set -Eeuo pipefail

DURATION="${1:-}"
START_EPOCH="${2:-}"
TARGET_USER="${OCI_TARGET_USER:-pathlab-deploy}"
SESSION_ID=""
SESSION_NAME="pathlab-observe-${GITHUB_RUN_ID:-manual}-$(date -u +%s)"
TUNNEL_PID=""
WORK_DIR="$(mktemp -d)"
KEY_FILE="${WORK_DIR}/bastion-session"
TARGET_KEY_FILE="${OCI_TARGET_KEY_FILE:-${HOME}/.ssh/target_deploy_key}"
TARGET_KNOWN_HOSTS_FILE="${OCI_TARGET_KNOWN_HOSTS_FILE:-${HOME}/.ssh/target_known_hosts}"

fail() {
  echo "Bastion observation failed: $*" >&2
  exit 1
}

cleanup_bastion_session() {
  local exit_code=$?
  local state="" output="" cleanup_deadline delete_requested=false
  trap - EXIT
  if [[ -n "${TUNNEL_PID}" ]] && kill -0 "${TUNNEL_PID}" >/dev/null 2>&1; then
    kill "${TUNNEL_PID}" >/dev/null 2>&1 || true
    wait "${TUNNEL_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${SESSION_ID}" ]]; then
    for _ in $(seq 1 3); do
      if oci bastion session delete --session-id "${SESSION_ID}" --force \
        >/dev/null 2>&1; then
        delete_requested=true
        break
      fi
      sleep 2
    done
    cleanup_deadline=$((SECONDS + 600))
    while (( SECONDS < cleanup_deadline )); do
      if output="$(oci bastion session get --session-id "${SESSION_ID}" \
          --query 'data."lifecycle-state"' --raw-output 2>&1)"; then
        state="${output}"
        [[ "${state}" == DELETED ]] && break
        if [[ "${delete_requested}" != true && \
              "${state}" =~ ^(ACTIVE|CREATING|FAILED)$ ]]; then
          if oci bastion session delete --session-id "${SESSION_ID}" --force \
            >/dev/null 2>&1; then
            delete_requested=true
          fi
        elif [[ ! "${state}" =~ ^(ACTIVE|CREATING|FAILED|DELETING)$ ]]; then
          state=""
          break
        fi
      elif grep -Eq 'NotAuthorizedOrNotFound|NotFound|404' <<< "${output}"; then
        state=DELETED
        break
      else
        state=""
        break
      fi
      sleep 5
    done
    if [[ "${state}" != DELETED ]]; then
      echo "Bastion observation failed: exact session deletion could not be proved" >&2
      exit_code=1
    fi
  fi
  rm -rf -- "${WORK_DIR}"
  exit "${exit_code}"
}
trap cleanup_bastion_session EXIT

[[ "${DURATION}" =~ ^[0-9]{2,5}$ ]] || fail "duration must be an integer"
(( DURATION >= 10 && DURATION <= 10000 && DURATION % 10 == 0 )) || \
  fail "duration must be a multiple of 10 from 10 to 10000 seconds"
[[ -z "${START_EPOCH}" || "${START_EPOCH}" =~ ^[0-9]{10}$ ]] || \
  fail "optional synchronized start epoch is invalid"
: "${OCI_BASTION_ID:?OCI_BASTION_ID is required}"
: "${OCI_INSTANCE_ID:?OCI_INSTANCE_ID is required}"
: "${OCI_TARGET_PRIVATE_IP:?OCI_TARGET_PRIVATE_IP is required}"
: "${OCI_KNOWN_HOSTS_FILE:?OCI_KNOWN_HOSTS_FILE is required}"
[[ -f "${OCI_KNOWN_HOSTS_FILE}" ]] || fail "pinned SSH host keys are missing"
[[ -f "${TARGET_KEY_FILE}" ]] || fail "target deployment key is missing"
[[ -f "${TARGET_KNOWN_HOSTS_FILE}" ]] || fail "pinned target host keys are missing"

ssh-keygen -q -t ed25519 -N "" -f "${KEY_FILE}"
SESSION_ID="$(
  oci bastion session create-port-forwarding \
    --bastion-id "${OCI_BASTION_ID}" \
    --display-name "${SESSION_NAME}" \
    --key-type PUB \
    --ssh-public-key-file "${KEY_FILE}.pub" \
    --target-resource-id "${OCI_INSTANCE_ID}" \
    --target-private-ip "${OCI_TARGET_PRIVATE_IP}" \
    --target-port 22 \
    --session-ttl 10800 \
    --query 'data.id' \
    --raw-output
)"
[[ "${SESSION_ID}" == ocid1.bastionsession.* ]] || fail "OCI did not return a session OCID"

activation_deadline=$((SECONDS + 300))
while (( SECONDS < activation_deadline )); do
  SESSION_STATE="$(
    oci bastion session get \
      --session-id "${SESSION_ID}" \
      --query 'data."lifecycle-state"' \
      --raw-output
  )"
  [[ "${SESSION_STATE}" == "ACTIVE" ]] && break
  [[ "${SESSION_STATE}" == "FAILED" ]] && fail "OCI Bastion session creation failed"
  sleep 5
done
[[ "${SESSION_STATE:-}" == "ACTIVE" ]] || fail "OCI Bastion session did not become active"

SSH_COMMAND="$(
  oci bastion session get \
    --session-id "${SESSION_ID}" \
    --query 'data."ssh-metadata".command' \
    --raw-output
)"
[[ "${SSH_COMMAND}" == ssh\ * && "${SSH_COMMAND}" == *"<localPort>"* ]] || \
  fail "OCI did not return a port-forwarding SSH command"
SSH_COMMAND="${SSH_COMMAND//<privateKey>/${KEY_FILE}}"
LOCAL_PORT="$(python3 - <<'PY'
import socket

with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    print(listener.getsockname()[1])
PY
)"
[[ "${LOCAL_PORT}" =~ ^[0-9]{4,5}$ ]] || fail "local tunnel port allocation failed"
SSH_COMMAND="${SSH_COMMAND//<localPort>/${LOCAL_PORT}}"
SSH_COMMAND="${SSH_COMMAND//exec ssh /ssh }"
SSH_OPTIONS="-o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=${OCI_KNOWN_HOSTS_FILE} -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=40 -o TCPKeepAlive=yes"
SSH_COMMAND="${SSH_COMMAND//ssh /ssh ${SSH_OPTIONS} }"
bash -c "${SSH_COMMAND}" >"${WORK_DIR}/tunnel.out" 2>"${WORK_DIR}/tunnel.err" &
TUNNEL_PID=$!
for _ in $(seq 1 60); do
  kill -0 "${TUNNEL_PID}" >/dev/null 2>&1 || fail "Bastion tunnel exited before readiness"
  if python3 - "${LOCAL_PORT}" <<'PY'
import socket
import sys

try:
    with socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=0.25):
        pass
except OSError:
    raise SystemExit(1)
PY
  then
    break
  fi
  sleep 0.5
done
python3 - "${LOCAL_PORT}" <<'PY' || fail "Bastion tunnel did not become ready"
import socket
import sys

with socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=0.5):
    pass
PY

REMOTE_REQUEST="observe-load ${DURATION}"
[[ -n "${START_EPOCH}" ]] && REMOTE_REQUEST+=" start=${START_EPOCH}"
ssh -i "${TARGET_KEY_FILE}" -p "${LOCAL_PORT}" \
  -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
  -o HostKeyAlias=pathlab-target -o UserKnownHostsFile="${TARGET_KNOWN_HOSTS_FILE}" \
  -o ConnectTimeout=10 -o ConnectionAttempts=1 \
  -o ServerAliveInterval=15 -o ServerAliveCountMax=40 -o TCPKeepAlive=yes \
  "${TARGET_USER}@127.0.0.1" "${REMOTE_REQUEST}"
