#!/usr/bin/env bash
set -Eeuo pipefail

TARGET_SHA="${1:-}"
CLASSROOM_ENABLED="${2:-}"
ANNOTATIONS_ENABLED="${3:-}"
PROVISION_EVIDENCE_KEY="${PATHLAB_PROVISION_DEPLOY_EVIDENCE_KEY:-0}"
TARGET_USER="${OCI_TARGET_USER:-pathlab-deploy}"
SESSION_ID=""
SESSION_NAME="pathlab-deploy-${GITHUB_RUN_ID:-manual}-$(date -u +%s)"
SESSION_CREATE_ACCEPTED=0
SESSION_SEEN=0
TUNNEL_PID=""
WORK_DIR="$(mktemp -d)"
KEY_FILE="${WORK_DIR}/bastion-session"
if [[ "${PROVISION_EVIDENCE_KEY}" == 1 ]]; then
  : "${PATHLAB_DEPLOY_EVIDENCE_KEY:?PATHLAB_DEPLOY_EVIDENCE_KEY is required}"
else
  : "${PATHLAB_DEPLOY_EVIDENCE_FILE:?PATHLAB_DEPLOY_EVIDENCE_FILE is required}"
  : "${PATHLAB_DEPLOY_EVIDENCE_SIGNATURE:?PATHLAB_DEPLOY_EVIDENCE_SIGNATURE is required}"
  : "${PATHLAB_DEPLOY_EVIDENCE_NONCE:?PATHLAB_DEPLOY_EVIDENCE_NONCE is required}"
fi

fail() {
  echo "Bastion deployment failed: $*" >&2
  exit 1
}

cleanup_bastion_session() {
  local exit_code=$?
  local cleanup_failed=0
  local cleanup_deadline session_state sessions_file
  trap - EXIT
  if [[ -n "${TUNNEL_PID}" ]] && kill -0 "${TUNNEL_PID}" >/dev/null 2>&1; then
    kill "${TUNNEL_PID}" >/dev/null 2>&1 || true
    wait "${TUNNEL_PID}" >/dev/null 2>&1 || true
  fi
  if [[ "${SESSION_CREATE_ACCEPTED}" == 1 ]]; then
    sessions_file="${WORK_DIR}/cleanup-sessions.json"
    cleanup_deadline=$((SECONDS + 600))
    while (( SECONDS < cleanup_deadline )); do
      oci bastion session list --bastion-id "${OCI_BASTION_ID}" \
        --display-name "${SESSION_NAME}" --all > "${sessions_file}" 2>/dev/null || {
          cleanup_failed=1
          break
        }
      SESSION_ID="$(jq -r '.data[0].id // empty' "${sessions_file}")"
      session_state="$(jq -r '.data[0]."lifecycle-state" // empty' "${sessions_file}")"
      if [[ "${SESSION_ID}" == ocid1.bastionsession.* ]]; then
        SESSION_SEEN=1
      elif [[ "${SESSION_SEEN}" == 1 ]]; then
        break
      else
        sleep 5
        continue
      fi
      case "${session_state}" in
        DELETED)
          break
          ;;
        ACTIVE|CREATING|FAILED)
          oci bastion session delete --session-id "${SESSION_ID}" --force \
            >/dev/null 2>&1 || true
          ;;
        DELETING)
          ;;
        *)
          cleanup_failed=1
          break
          ;;
      esac
      sleep 5
    done
    if [[ "${SESSION_SEEN}" != 1 ]]; then
      cleanup_failed=1
    elif [[ "${session_state:-}" != DELETED ]]; then
      session_state="$(
        oci bastion session get --session-id "${SESSION_ID}" \
          --query 'data."lifecycle-state"' --raw-output 2>/dev/null
      )" || session_state=DELETED
    fi
    [[ "${session_state:-}" == DELETED ]] || cleanup_failed=1
  fi
  rm -rf -- "${WORK_DIR}"
  if [[ "${cleanup_failed}" -ne 0 ]]; then
    echo "Exact Bastion session terminal deletion could not be proved." >&2
    exit 1
  fi
  exit "${exit_code}"
}
trap cleanup_bastion_session EXIT

[[ "${TARGET_SHA}" =~ ^[0-9a-f]{40}$ ]] || fail "a full lowercase commit SHA is required"
if [[ "${PROVISION_EVIDENCE_KEY}" != 0 && "${PROVISION_EVIDENCE_KEY}" != 1 ]]; then
  fail "PATHLAB_PROVISION_DEPLOY_EVIDENCE_KEY must be 0 or 1"
fi
if [[ "${PROVISION_EVIDENCE_KEY}" == 1 ]]; then
  [[ "${PATHLAB_DEPLOY_EVIDENCE_KEY}" =~ ^[0-9a-f]{64}$ ]] || \
    fail "deployment evidence key must be 64 lowercase hex characters"
  [[ -z "${CLASSROOM_ENABLED}${ANNOTATIONS_ENABLED}" ]] || \
    fail "feature modes are invalid during key provisioning"
elif [[ -n "${CLASSROOM_ENABLED}" && ! "${CLASSROOM_ENABLED}" =~ ^(true|false)$ ]]; then
  fail "classroom enabled must be true, false, or empty"
elif [[ -n "${ANNOTATIONS_ENABLED}" && ! "${ANNOTATIONS_ENABLED}" =~ ^(true|false)$ ]]; then
  fail "annotations enabled must be true, false, or empty"
fi
: "${OCI_BASTION_ID:?OCI_BASTION_ID is required}"
: "${OCI_INSTANCE_ID:?OCI_INSTANCE_ID is required}"
: "${OCI_TARGET_PRIVATE_IP:?OCI_TARGET_PRIVATE_IP is required}"
: "${OCI_KNOWN_HOSTS_FILE:?OCI_KNOWN_HOSTS_FILE is required}"
: "${OCI_TARGET_KEY_FILE:?OCI_TARGET_KEY_FILE is required}"
: "${OCI_TARGET_KNOWN_HOSTS_FILE:?OCI_TARGET_KNOWN_HOSTS_FILE is required}"
[[ -f "${OCI_KNOWN_HOSTS_FILE}" ]] || fail "pinned SSH host keys are missing"
[[ -f "${OCI_TARGET_KEY_FILE}" ]] || fail "target deployment key is missing"
[[ -f "${OCI_TARGET_KNOWN_HOSTS_FILE}" ]] || fail "pinned target host keys are missing"
if [[ "${PROVISION_EVIDENCE_KEY}" == 0 ]]; then
  [[ -f "${PATHLAB_DEPLOY_EVIDENCE_FILE}" ]] || fail "deployment evidence is missing"
  [[ "$(wc -c < "${PATHLAB_DEPLOY_EVIDENCE_FILE}")" -le 65536 ]] || \
    fail "deployment evidence is too large"
  [[ "${PATHLAB_DEPLOY_EVIDENCE_SIGNATURE}" =~ ^[0-9a-f]{64}$ ]] || \
    fail "deployment evidence signature is invalid"
  [[ "${PATHLAB_DEPLOY_EVIDENCE_NONCE}" =~ ^[A-Za-z0-9._-]{8,128}$ ]] || \
    fail "deployment evidence nonce is invalid"
fi

NONTERMINAL_SESSIONS="$(
  oci bastion session list --bastion-id "${OCI_BASTION_ID}" --all \
    --query 'length(data[?"lifecycle-state" == `ACTIVE` || "lifecycle-state" == `CREATING` || "lifecycle-state" == `DELETING`])' \
    --raw-output
)" || fail "Bastion preflight could not verify nonterminal sessions"
[[ "${NONTERMINAL_SESSIONS}" == 0 ]] || \
  fail "Bastion preflight requires zero nonterminal sessions"

ssh-keygen -q -t ed25519 -N "" -f "${KEY_FILE}"

oci bastion session create-port-forwarding \
  --bastion-id "${OCI_BASTION_ID}" \
  --display-name "${SESSION_NAME}" \
  --key-type PUB \
  --ssh-public-key-file "${KEY_FILE}.pub" \
  --target-resource-id "${OCI_INSTANCE_ID}" \
  --target-private-ip "${OCI_TARGET_PRIVATE_IP}" \
  --target-port 22 \
  --session-ttl 1800 \
  >/dev/null
SESSION_CREATE_ACCEPTED=1

activation_deadline=$((SECONDS + 300))
while (( SECONDS < activation_deadline )); do
  SESSION_ID="$(
    oci bastion session list \
      --bastion-id "${OCI_BASTION_ID}" \
      --display-name "${SESSION_NAME}" \
      --all \
      --query 'data[0].id' \
      --raw-output
  )"
  if [[ "${SESSION_ID}" == ocid1.bastionsession.* ]]; then
    SESSION_SEEN=1
    SESSION_STATE="$(
      oci bastion session get \
        --session-id "${SESSION_ID}" \
        --query 'data."lifecycle-state"' \
        --raw-output
    )"
    [[ "${SESSION_STATE}" == "ACTIVE" ]] && break
    [[ "${SESSION_STATE}" == "FAILED" ]] && fail "OCI Bastion session creation failed"
    [[ "${SESSION_STATE}" == "DELETING" || "${SESSION_STATE}" == "DELETED" ]] && \
      fail "OCI Bastion session was deleted before activation"
  fi
  sleep 5
done
[[ "${SESSION_ID}" == ocid1.bastionsession.* ]] || fail "OCI did not return a session OCID"
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
    TUNNEL_READY=1
    break
  fi
  sleep 0.5
done
[[ "${TUNNEL_READY:-0}" == 1 ]] || fail "Bastion tunnel did not become ready"

TARGET_SSH=(
  ssh -i "${OCI_TARGET_KEY_FILE}" -p "${LOCAL_PORT}"
  -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes
  -o HostKeyAlias=pathlab-target -o UserKnownHostsFile="${OCI_TARGET_KNOWN_HOSTS_FILE}"
  -o ConnectTimeout=10 -o ConnectionAttempts=1
  -o ServerAliveInterval=15 -o ServerAliveCountMax=40 -o TCPKeepAlive=yes
  "${TARGET_USER}@127.0.0.1"
)

if [[ "${PROVISION_EVIDENCE_KEY}" == 1 ]]; then
  REMOTE_REQUEST="provision-evidence-key sha=${TARGET_SHA}"
  printf '%s\n' "${PATHLAB_DEPLOY_EVIDENCE_KEY}" | "${TARGET_SSH[@]}" "${REMOTE_REQUEST}"
else
  EVIDENCE_B64="$(base64 -w 0 "${PATHLAB_DEPLOY_EVIDENCE_FILE}" | tr '+/' '-_' | tr -d '=')"
  REMOTE_REQUEST="deploy ${TARGET_SHA} evidence=${EVIDENCE_B64} signature=${PATHLAB_DEPLOY_EVIDENCE_SIGNATURE} nonce=${PATHLAB_DEPLOY_EVIDENCE_NONCE}"
  if [[ -n "${CLASSROOM_ENABLED}" ]]; then
    REMOTE_REQUEST="${REMOTE_REQUEST} classroom=${CLASSROOM_ENABLED}"
  fi
  # Older stable dispatchers do not know the annotation token. False is the
  # safe default whenever Classroom mode is explicit, so omit it for bootstrap.
  if [[ "${ANNOTATIONS_ENABLED}" == true ]]; then
    REMOTE_REQUEST="${REMOTE_REQUEST} annotations=${ANNOTATIONS_ENABLED}"
  fi
  "${TARGET_SSH[@]}" "${REMOTE_REQUEST}"
fi
