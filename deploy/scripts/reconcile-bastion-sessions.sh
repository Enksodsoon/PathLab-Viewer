#!/usr/bin/env bash
set -Eeuo pipefail

CURRENT_RUN_ID="${1:-}"
OCI_COMMAND="${PATHLAB_OCI_COMMAND:-oci}"
GH_COMMAND="${PATHLAB_GH_COMMAND:-gh}"
WORK_DIR="$(mktemp -d)"
SESSIONS_FILE="${WORK_DIR}/sessions.json"
OWNED_FILE="${WORK_DIR}/owned.tsv"

cleanup() {
  rm -rf -- "${WORK_DIR}"
}
trap cleanup EXIT

fail() {
  echo "Bastion reconciliation failed: $*" >&2
  exit 1
}

[[ "${CURRENT_RUN_ID}" =~ ^[0-9]+$ ]] || fail "current workflow run ID is invalid"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
: "${GH_TOKEN:?GH_TOKEN is required}"
: "${OCI_BASTION_ID:?OCI_BASTION_ID is required}"

echo "=== Bastion Reconciliation Diagnostic ===" >&2
echo "OCI command: ${OCI_COMMAND} (resolved: $(command -v "${OCI_COMMAND}" 2>/dev/null || true))" >&2
echo "Current user: $(whoami 2>/dev/null || true), home: ${HOME:-unknown}" >&2
if [[ -f "${HOME:-}/.oci/config" ]]; then
  echo "OCI config file exists (${HOME}/.oci/config), size: $(wc -c < "${HOME}/.oci/config") bytes" >&2
else
  echo "OCI config file NOT found at ${HOME:-}/.oci/config" >&2
fi

raw_out="${WORK_DIR}/raw_stdout.json"
raw_err="${WORK_DIR}/raw_stderr.log"
oci_rc=0
"${OCI_COMMAND}" bastion session list --bastion-id "${OCI_BASTION_ID}" --all \
  > "${raw_out}" 2> "${raw_err}" || oci_rc=$?

echo "OCI invocation return code: ${oci_rc}" >&2
echo "OCI stdout bytes: $(wc -c < "${raw_out}")" >&2
echo "OCI stderr bytes: $(wc -c < "${raw_err}")" >&2

if [[ "${oci_rc}" -ne 0 ]]; then
  if [[ -s "${raw_err}" ]]; then
    echo "--- OCI stderr output ---" >&2
    cat "${raw_err}" >&2
    echo "--- End OCI stderr output ---" >&2
  fi
  fail "session inventory could not be read (exit code ${oci_rc})"
fi

if [[ ! -s "${raw_out}" ]]; then
  # When the Bastion inventory is completely empty (0 sessions), OCI CLI 3.92.0 returns 0 bytes.
  echo '{"data": []}' > "${SESSIONS_FILE}"
else
  cp "${raw_out}" "${SESSIONS_FILE}"
fi

if ! jq -e '.data | type == "array"' "${SESSIONS_FILE}" >/dev/null 2>&1; then
  echo "--- Raw stdout from OCI command (${SESSIONS_FILE}) ---" >&2
  cat "${SESSIONS_FILE}" >&2
  echo "--- End raw stdout ---" >&2
  if [[ -s "${raw_err}" ]]; then
    echo "--- Raw stderr from OCI command ---" >&2
    cat "${raw_err}" >&2
    echo "--- End raw stderr ---" >&2
  fi
  echo "--- Testing with --debug to identify API failure ---" >&2
  "${OCI_COMMAND}" bastion session list --bastion-id "${OCI_BASTION_ID}" --debug >&2 || true
  fail "session inventory is malformed"
fi

: > "${OWNED_FILE}"
unrelated_count=0
while IFS=$'\t' read -r session_id display_name session_state; do
  owner_run=""
  if [[ "${display_name}" =~ ^pathlab-capacity-([0-9]+)- ]]; then
    owner_run="${BASH_REMATCH[1]}"
  elif [[ "${display_name}" =~ ^pathlab-observe-([0-9]+)- ]]; then
    owner_run="${BASH_REMATCH[1]}"
  elif [[ "${display_name}" =~ ^pathlab-deploy-([0-9]+)- ]]; then
    owner_run="${BASH_REMATCH[1]}"
  elif [[ "${display_name}" =~ ^pathlab-([0-9]+)-[0-9]+$ ]]; then
    # Legacy deployment sessions created before explicit deploy ownership.
    owner_run="${BASH_REMATCH[1]}"
  else
    unrelated_count=$((unrelated_count + 1))
    continue
  fi
  [[ "${owner_run}" != "${CURRENT_RUN_ID}" ]] || \
    fail "the current workflow already owns a nonterminal session"
  printf '%s\t%s\t%s\n' "${session_id}" "${owner_run}" "${session_state}" >> "${OWNED_FILE}"
done < <(
  jq -r '.data[] |
    select(."lifecycle-state" == "ACTIVE" or ."lifecycle-state" == "CREATING" or
      ."lifecycle-state" == "DELETING") |
    [.id, (."display-name" // ""), ."lifecycle-state"] | @tsv' "${SESSIONS_FILE}"
)

[[ "${unrelated_count}" == 0 ]] || \
  fail "${unrelated_count} nonterminal session(s) are not owned by a PathLab workflow"

owned_count="$(wc -l < "${OWNED_FILE}" | tr -d ' ')"
[[ "${owned_count}" != 0 ]] || exit 0

while IFS= read -r owner_run; do
  run_file="${WORK_DIR}/run-${owner_run}.json"
  "${GH_COMMAND}" api "repos/${GITHUB_REPOSITORY}/actions/runs/${owner_run}" \
    > "${run_file}" 2>/dev/null || \
    fail "a session owner could not be verified against this repository"
  run_status="$(jq -r '.status // empty' "${run_file}")"
  run_conclusion="$(jq -r '.conclusion // empty' "${run_file}")"
  [[ "${run_status}" == completed ]] || \
    fail "a session is owned by a workflow that is not terminal"
  [[ "${run_conclusion}" =~ ^(failure|cancelled|timed_out)$ ]] || \
    fail "a session owner is not an approved failed recovery source"
done < <(cut -f2 "${OWNED_FILE}" | sort -u)

# Request every deletion before polling so slow OCI deletions proceed concurrently.
while IFS=$'\t' read -r session_id _owner_run _session_state; do
  "${OCI_COMMAND}" bastion session delete --session-id "${session_id}" --force \
    >/dev/null 2>&1 || true
done < "${OWNED_FILE}"

deadline=$((SECONDS + 600))
while (( SECONDS < deadline )); do
  "${OCI_COMMAND}" bastion session list --bastion-id "${OCI_BASTION_ID}" --all \
    > "${SESSIONS_FILE}" || \
    fail "session inventory could not be refreshed"
  if [[ ! -s "${SESSIONS_FILE}" ]]; then
    echo '{"data": []}' > "${SESSIONS_FILE}"
  fi
  remaining=0
  while IFS=$'\t' read -r session_id _owner_run _prior_state; do
    state="$(jq -r --arg id "${session_id}" \
      '.data[] | select(.id == $id) | ."lifecycle-state"' "${SESSIONS_FILE}" | head -n 1)"
    case "${state}" in
      ""|DELETED)
        ;;
      ACTIVE|CREATING|FAILED)
        remaining=$((remaining + 1))
        "${OCI_COMMAND}" bastion session delete --session-id "${session_id}" --force \
          >/dev/null 2>&1 || true
        ;;
      DELETING)
        remaining=$((remaining + 1))
        ;;
      *)
        fail "a session entered an unsupported lifecycle state"
        ;;
    esac
  done < "${OWNED_FILE}"
  [[ "${remaining}" == 0 ]] && {
    echo "Reconciled ${owned_count} terminal PathLab Bastion session(s)."
    exit 0
  }
  sleep 5
done

fail "terminal PathLab sessions did not finish deletion within 600 seconds"
