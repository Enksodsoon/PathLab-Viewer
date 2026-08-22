#!/usr/bin/env bash
set -Eeuo pipefail

TARGET_SHA="${1:-}"
CLASSROOM_ENABLED="${2:-}"
ANNOTATIONS_ENABLED="${3:-}"
PROVISION_EVIDENCE_KEY="${PATHLAB_PROVISION_DEPLOY_EVIDENCE_KEY:-0}"
TARGET_USER="${OCI_TARGET_USER:-pathlab-deploy}"
SESSION_ID=""
SESSION_NAME="pathlab-${GITHUB_RUN_ID:-manual}-$(date -u +%s)"
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
  trap - EXIT
  if [[ -n "${SESSION_ID}" ]]; then
    oci bastion session delete --session-id "${SESSION_ID}" --force >/dev/null 2>&1 || \
      cleanup_failed=1
    for _ in $(seq 1 30); do
      active_count="$(
        oci bastion session list --bastion-id "${OCI_BASTION_ID}" --all \
          --query 'length(data[?"lifecycle-state" == `ACTIVE`])' --raw-output 2>/dev/null
      )" || { cleanup_failed=1; break; }
      [[ "${active_count}" == 0 ]] && break
      sleep 2
    done
    [[ "${active_count:-}" == 0 ]] || cleanup_failed=1
  fi
  rm -rf -- "${WORK_DIR}"
  if [[ "${cleanup_failed}" -ne 0 ]]; then
    echo "Bastion session cleanup or zero-session verification failed." >&2
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
[[ -f "${OCI_KNOWN_HOSTS_FILE}" ]] || fail "pinned SSH host keys are missing"
if [[ "${PROVISION_EVIDENCE_KEY}" == 0 ]]; then
  [[ -f "${PATHLAB_DEPLOY_EVIDENCE_FILE}" ]] || fail "deployment evidence is missing"
  [[ "$(wc -c < "${PATHLAB_DEPLOY_EVIDENCE_FILE}")" -le 65536 ]] || \
    fail "deployment evidence is too large"
  [[ "${PATHLAB_DEPLOY_EVIDENCE_SIGNATURE}" =~ ^[0-9a-f]{64}$ ]] || \
    fail "deployment evidence signature is invalid"
  [[ "${PATHLAB_DEPLOY_EVIDENCE_NONCE}" =~ ^[A-Za-z0-9._-]{8,128}$ ]] || \
    fail "deployment evidence nonce is invalid"
fi

ACTIVE_SESSIONS="$(
  oci bastion session list --bastion-id "${OCI_BASTION_ID}" --all \
    --query 'length(data[?"lifecycle-state" == `ACTIVE`])' --raw-output
)" || fail "Bastion preflight could not verify active sessions"
[[ "${ACTIVE_SESSIONS}" == 0 ]] || fail "Bastion preflight requires zero active sessions"

ssh-keygen -q -t ed25519 -N "" -f "${KEY_FILE}"

oci bastion session create-managed-ssh \
  --bastion-id "${OCI_BASTION_ID}" \
  --display-name "${SESSION_NAME}" \
  --key-type PUB \
  --ssh-public-key-file "${KEY_FILE}.pub" \
  --target-resource-id "${OCI_INSTANCE_ID}" \
  --target-private-ip "${OCI_TARGET_PRIVATE_IP}" \
  --target-port 22 \
  --target-os-username "${TARGET_USER}" \
  --session-ttl 1800 \
  >/dev/null

for _ in $(seq 1 40); do
  SESSION_ID="$(
    oci bastion session list \
      --bastion-id "${OCI_BASTION_ID}" \
      --display-name "${SESSION_NAME}" \
      --all \
      --query 'data[0].id' \
      --raw-output
  )"
  if [[ "${SESSION_ID}" == ocid1.bastionsession.* ]]; then
    SESSION_STATE="$(
      oci bastion session get \
        --session-id "${SESSION_ID}" \
        --query 'data."lifecycle-state"' \
        --raw-output
    )"
    [[ "${SESSION_STATE}" == "ACTIVE" ]] && break
    [[ "${SESSION_STATE}" == "FAILED" ]] && fail "OCI Bastion session creation failed"
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
[[ "${SSH_COMMAND}" == ssh\ * ]] || fail "OCI did not return a managed SSH command"

SSH_COMMAND="${SSH_COMMAND//<privateKey>/${KEY_FILE}}"
SSH_COMMAND="${SSH_COMMAND//exec ssh /ssh }"
SSH_OPTIONS="-o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=${OCI_KNOWN_HOSTS_FILE} -o ServerAliveInterval=15 -o ServerAliveCountMax=40 -o TCPKeepAlive=yes"
SSH_COMMAND="${SSH_COMMAND//ssh /ssh ${SSH_OPTIONS} }"

if [[ "${PROVISION_EVIDENCE_KEY}" == 1 ]]; then
  REMOTE_REQUEST="provision-evidence-key sha=${TARGET_SHA}"
  printf '%s\n' "${PATHLAB_DEPLOY_EVIDENCE_KEY}" | bash -c "${SSH_COMMAND} \"${REMOTE_REQUEST}\""
else
  EVIDENCE_B64="$(base64 -w 0 "${PATHLAB_DEPLOY_EVIDENCE_FILE}" | tr '+/' '-_' | tr -d '=')"
  REMOTE_REQUEST="deploy ${TARGET_SHA} evidence=${EVIDENCE_B64} signature=${PATHLAB_DEPLOY_EVIDENCE_SIGNATURE} nonce=${PATHLAB_DEPLOY_EVIDENCE_NONCE}"
  if [[ -n "${CLASSROOM_ENABLED}" ]]; then
    REMOTE_REQUEST="${REMOTE_REQUEST} classroom=${CLASSROOM_ENABLED}"
  fi
  if [[ -n "${ANNOTATIONS_ENABLED}" ]]; then
    REMOTE_REQUEST="${REMOTE_REQUEST} annotations=${ANNOTATIONS_ENABLED}"
  fi
  bash -c "${SSH_COMMAND} \"${REMOTE_REQUEST}\""
fi
