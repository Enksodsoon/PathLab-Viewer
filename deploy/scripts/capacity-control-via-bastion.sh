#!/usr/bin/env bash
set -Eeuo pipefail

REMOTE_REQUEST="${1:?an exact capacity control request is required}"
TARGET_USER="${OCI_TARGET_USER:-pathlab-deploy}"
SESSION_ID=""
WORK_DIR="$(mktemp -d)"
KEY_FILE="${WORK_DIR}/bastion-session"

fail() { echo "Capacity Bastion control failed: $*" >&2; exit 1; }
cleanup() {
  local result=$?
  trap - EXIT
  if [[ -n "${SESSION_ID}" ]]; then
    oci bastion session delete --session-id "${SESSION_ID}" --force >/dev/null 2>&1 || true
  fi
  rm -rf -- "${WORK_DIR}"
  exit "${result}"
}
trap cleanup EXIT

ARM_PATTERN='^capacity-arm [0-9a-f]{40} run=[a-z0-9-]{1,64} digest=[0-9a-f]{64} arm-not-after=[0-9]{10} deadline=[0-9]{10} fault-start=[0-9]{10} fault-end=[0-9]{10} evidence=[A-Za-z0-9_-]+ signature=[0-9a-f]{64} nonce=[A-Za-z0-9._-]{8,128}$'
STATUS_PATTERN='^capacity-status run=[a-z0-9-]{1,64}$'
FINALIZE_PATTERN='^capacity-finalize [0-9a-f]{40} run=[a-z0-9-]{1,64} digest=[0-9a-f]{64} evidence=[A-Za-z0-9_-]+ signature=[0-9a-f]{64} nonce=[A-Za-z0-9._-]{8,128}$'
FAULT_PATTERN='^capacity-fault run=[a-z0-9-]{1,64} digest=[0-9a-f]{64}$'
ABORT_PATTERN='^capacity-abort run=[a-z0-9-]{1,64} digest=[0-9a-f]{64}$'
ROLLBACK_PATTERN='^capacity-rollback candidate=[0-9a-f]{40} rollback=[0-9a-f]{40} run=[a-z0-9-]{1,64} digest=[0-9a-f]{64} nonce=[A-Za-z0-9._-]{8,128}$'
POSTFLIGHT_PATTERN='^capacity-postflight expected=[0-9a-f]{40}$'
ROLLBACK_PREFLIGHT_PATTERN='^capacity-rollback-preflight rollback=[0-9a-f]{40}$'
[[ "${REMOTE_REQUEST}" =~ ${ARM_PATTERN} || "${REMOTE_REQUEST}" =~ ${STATUS_PATTERN} || \
   "${REMOTE_REQUEST}" =~ ${FINALIZE_PATTERN} || "${REMOTE_REQUEST}" =~ ${FAULT_PATTERN} || \
   "${REMOTE_REQUEST}" =~ ${ABORT_PATTERN} || "${REMOTE_REQUEST}" =~ ${ROLLBACK_PATTERN} || \
   "${REMOTE_REQUEST}" =~ ${POSTFLIGHT_PATTERN} || \
   "${REMOTE_REQUEST}" =~ ${ROLLBACK_PREFLIGHT_PATTERN} ]] || fail "request is not allowlisted"
: "${OCI_BASTION_ID:?OCI_BASTION_ID is required}"
: "${OCI_INSTANCE_ID:?OCI_INSTANCE_ID is required}"
: "${OCI_TARGET_PRIVATE_IP:?OCI_TARGET_PRIVATE_IP is required}"
: "${OCI_KNOWN_HOSTS_FILE:?OCI_KNOWN_HOSTS_FILE is required}"
[[ -f "${OCI_KNOWN_HOSTS_FILE}" ]] || fail "pinned SSH host keys are missing"

ssh-keygen -q -t ed25519 -N "" -f "${KEY_FILE}"
SESSION_ID="$(oci bastion session create-managed-ssh \
  --bastion-id "${OCI_BASTION_ID}" --display-name "pathlab-capacity-${GITHUB_RUN_ID:-manual}" \
  --key-type PUB --ssh-public-key-file "${KEY_FILE}.pub" \
  --target-resource-id "${OCI_INSTANCE_ID}" --target-private-ip "${OCI_TARGET_PRIVATE_IP}" \
  --target-port 22 --target-os-username "${TARGET_USER}" --session-ttl 1800 \
  --query 'data.id' --raw-output)"
[[ "${SESSION_ID}" == ocid1.bastionsession.* ]] || fail "OCI did not return a session OCID"
for _ in $(seq 1 40); do
  STATE="$(oci bastion session get --session-id "${SESSION_ID}" \
    --query 'data."lifecycle-state"' --raw-output)"
  [[ "${STATE}" == ACTIVE ]] && break
  [[ "${STATE}" == FAILED ]] && fail "Bastion session failed"
  sleep 5
done
[[ "${STATE:-}" == ACTIVE ]] || fail "Bastion session did not become active"
SSH_COMMAND="$(oci bastion session get --session-id "${SESSION_ID}" \
  --query 'data."ssh-metadata".command' --raw-output)"
[[ "${SSH_COMMAND}" == ssh\ * ]] || fail "OCI did not return an SSH command"
SSH_COMMAND="${SSH_COMMAND//<privateKey>/${KEY_FILE}}"
SSH_COMMAND="${SSH_COMMAND//exec ssh /ssh }"
SSH_OPTIONS="-o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=${OCI_KNOWN_HOSTS_FILE}"
SSH_COMMAND="${SSH_COMMAND//ssh /ssh ${SSH_OPTIONS} }"
bash -c "${SSH_COMMAND} \"${REMOTE_REQUEST}\""
