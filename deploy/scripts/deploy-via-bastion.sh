#!/usr/bin/env bash
set -Eeuo pipefail

TARGET_SHA="${1:-}"
TARGET_USER="${OCI_TARGET_USER:-pathlab-deploy}"
SESSION_ID=""
SESSION_NAME="pathlab-${GITHUB_RUN_ID:-manual}-$(date -u +%s)"
WORK_DIR="$(mktemp -d)"
KEY_FILE="${WORK_DIR}/bastion-session"

fail() {
  echo "Bastion deployment failed: $*" >&2
  exit 1
}

cleanup_bastion_session() {
  local exit_code=$?
  trap - EXIT
  if [[ -n "${SESSION_ID}" ]]; then
    oci bastion session delete --session-id "${SESSION_ID}" --force >/dev/null 2>&1 || \
      echo "Warning: Bastion session cleanup must be checked manually: ${SESSION_ID}" >&2
  fi
  rm -rf -- "${WORK_DIR}"
  exit "${exit_code}"
}
trap cleanup_bastion_session EXIT

[[ "${TARGET_SHA}" =~ ^[0-9a-f]{40}$ ]] || fail "a full lowercase commit SHA is required"
: "${OCI_BASTION_ID:?OCI_BASTION_ID is required}"
: "${OCI_INSTANCE_ID:?OCI_INSTANCE_ID is required}"
: "${OCI_TARGET_PRIVATE_IP:?OCI_TARGET_PRIVATE_IP is required}"
: "${OCI_KNOWN_HOSTS_FILE:?OCI_KNOWN_HOSTS_FILE is required}"
[[ -f "${OCI_KNOWN_HOSTS_FILE}" ]] || fail "pinned SSH host keys are missing"

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
SSH_OPTIONS="-o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=${OCI_KNOWN_HOSTS_FILE}"
SSH_COMMAND="${SSH_COMMAND//ssh /ssh ${SSH_OPTIONS} }"

bash -c "${SSH_COMMAND} \"deploy ${TARGET_SHA}\""
