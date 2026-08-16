#!/usr/bin/env bash
set -Eeuo pipefail

PLAN_PATH="${1:?plan path is required}"
DECISION_PATH="${2:?decision path is required}"
SIGNATURE_PATH="${3:?decision signature path is required}"
SENTINEL_PATH="${4:?sentinel path is required}"
: "${CAPACITY_CLEANUP_RESULT:?CAPACITY_CLEANUP_RESULT is required}"
: "${DEPLOY_EVIDENCE_KEY:?DEPLOY_EVIDENCE_KEY is required}"
: "${OCI_BASTION_ID:?OCI_BASTION_ID is required}"
: "${CAPACITY_BASE_URL:?CAPACITY_BASE_URL is required}"
: "${LOAD_TEST_ADMIN_USERNAME:?LOAD_TEST_ADMIN_USERNAME is required}"
: "${LOAD_TEST_ADMIN_PASSWORD:?LOAD_TEST_ADMIN_PASSWORD is required}"
: "${CAPACITY_CLASSROOM_STAGE_MANIFEST_JSON:?CAPACITY_CLASSROOM_STAGE_MANIFEST_JSON is required}"
: "${CAPACITY_ANNOTATION_SLIDE_ID:?CAPACITY_ANNOTATION_SLIDE_ID is required}"
: "${CAPACITY_ANNOTATION_ITEM_ID:?CAPACITY_ANNOTATION_ITEM_ID is required}"

for path in "${PLAN_PATH}"; do
  [[ -f "${path}" ]] || { echo "Capacity cleanup input is missing." >&2; exit 1; }
done
started_at="$(TZ=Asia/Bangkok date --iso-8601=seconds)"
work_dir="$(mktemp -d)"
cookie_jar="${work_dir}/cookies"
run_id="$(jq -r .runId "${PLAN_PATH}")"
sha="$(jq -r .workflowSha "${PLAN_PATH}")"
digest="$(jq -r .planDigest "${PLAN_PATH}")"
rollback_not_after="$(python deploy/scripts/capacity_window.py --plan "${PLAN_PATH}" describe | \
  jq -er .restorationDeadlineEpoch)"
configuration_restored=false
fixtures_removed=false
bastion_remaining=999
cleanup_committed=false
rollback_completed=false
containment_complete=false
nonce=""
fail_safe_recovery() {
  local abort_request abort_status="" recovery_result=1
  set +e
  abort_request="capacity-abort run=${run_id} digest=${digest}"
  if [[ -n "${CAPACITY_ROLLBACK_RESULT:-}" ]]; then
    abort_status="$(bash deploy/scripts/capacity-control-via-bastion.sh \
      "${abort_request}" 2>/dev/null)"
    recovery_result="$?"
    if [[ "${recovery_result}" -eq 0 ]]; then
      printf '%s\n' "${abort_status}" > "${CAPACITY_ROLLBACK_RESULT}"
      rollback_completed=true
    fi
  else
    abort_status="$(bash deploy/scripts/capacity-control-via-bastion.sh \
      "${abort_request}" 2>/dev/null)"
  fi
  if jq -e '((.phase == "aborted-restored" and .finalLimit == null) or
      (.phase == "restored" and .finalLimit == 300)) and
      .releaseExact == true and .servicesExact == true and .ready == true and
      .finalCapacity == 300' \
    <<< "${abort_status}" >/dev/null 2>&1; then
    configuration_restored=true
  fi
  set -e
}
write_result() {
  local result=$?
  trap - EXIT
  if [[ "${result}" -ne 0 || "${cleanup_committed}" != true ]]; then
    [[ "${containment_complete}" == true ]] || fail_safe_recovery
    result=1
  fi
  local completed_at succeeded=false
  completed_at="$(TZ=Asia/Bangkok date --iso-8601=seconds)"
  [[ "${result}" -eq 0 && "${configuration_restored}" == true && \
     "${fixtures_removed}" == true && "${bastion_remaining}" == 0 ]] && succeeded=true
  jq -n --arg runId "${run_id}" --arg workflowSha "${sha}" --arg planDigest "${digest}" \
    --arg startedAt "${started_at}" --arg completedAt "${completed_at}" \
    --argjson succeeded "${succeeded}" --argjson restored "${configuration_restored}" \
    --argjson fixtures "${fixtures_removed}" --argjson remaining "${bastion_remaining}" \
    '{schemaVersion:1,runId:$runId,workflowSha:$workflowSha,planDigest:$planDigest,
      startedAt:$startedAt,completedAt:$completedAt,attempted:true,succeeded:$succeeded,
      configurationRestored:$restored,fixturesRemoved:$fixtures,
      bastionSessionsRemaining:$remaining}' > "${CAPACITY_CLEANUP_RESULT}"
  rm -rf -- "${work_dir}"
  exit "${result}"
}
trap write_result EXIT
nonce="$(python -c 'import hashlib,hmac,os; print(hmac.new(os.environ["DEPLOY_EVIDENCE_KEY"].encode(), (os.environ["GITHUB_RUN_ID"]+":"+os.environ["GITHUB_RUN_ATTEMPT"]).encode(), hashlib.sha256).hexdigest())')"
echo "::add-mask::${nonce}"

login="$(curl --fail --silent --show-error --max-time 10 \
  --cookie-jar "${cookie_jar}" --header 'Content-Type: application/json' \
  --data "$(jq -cn --arg username "${LOAD_TEST_ADMIN_USERNAME}" \
    --arg password "${LOAD_TEST_ADMIN_PASSWORD}" \
    '{username:$username,password:$password}')" \
  "${CAPACITY_BASE_URL%/}/api/v1/auth/session")"
csrf="$(jq -er .csrfToken <<< "${login}")"
while IFS= read -r session_id; do
  [[ "${session_id}" =~ ^[0-9a-f-]{36}$ ]] || {
    echo "Synthetic Classroom session ID is invalid." >&2
    exit 1
  }
  curl --fail --silent --show-error --max-time 20 \
    --cookie "${cookie_jar}" --request POST \
    --header "X-CSRF-Token: ${csrf}" \
    --header "X-PathLab-Synthetic-Run: ${run_id}" \
    "${CAPACITY_BASE_URL%/}/api/v1/admin/classroom/sessions/${session_id}/synthetic-reset" \
    >/dev/null
done < <(jq -er '[to_entries[].value.sessionId] | unique[]' \
  <<< "${CAPACITY_CLASSROOM_STAGE_MANIFEST_JSON}")

# Reconcile deterministic run-marked fixtures even when the sentinel runner
# was cancelled before its local finally block could retain an identifier.
marker="capacity-${run_id}"
slides="$(curl --fail --silent --show-error --max-time 20 --cookie "${cookie_jar}" \
  "${CAPACITY_BASE_URL%/}/api/v1/admin/slides")"
while IFS= read -r slide_id; do
  curl --fail --silent --show-error --max-time 20 --cookie "${cookie_jar}" \
    --request DELETE --header "X-CSRF-Token: ${csrf}" \
    "${CAPACITY_BASE_URL%/}/api/v1/admin/slides/${slide_id}" >/dev/null
done < <(jq -er --arg marker "${marker}" '.[] | select(.displayName | contains($marker)) | .id' \
  <<< "${slides}" || true)
slides="$(curl --fail --silent --show-error --max-time 20 --cookie "${cookie_jar}" \
  "${CAPACITY_BASE_URL%/}/api/v1/admin/slides")"
jq -e --arg marker "${marker}" 'all(.[]; (.displayName | contains($marker) | not))' \
  <<< "${slides}" >/dev/null

curl --fail --silent --show-error --max-time 20 --cookie "${cookie_jar}" \
  --request POST --header "X-CSRF-Token: ${csrf}" \
  --header "X-PathLab-Synthetic-Run: ${run_id}" \
  "${CAPACITY_BASE_URL%/}/api/v1/admin/capacity-sentinels/${run_id}/desktop-cleanup" \
  >/dev/null

curl --fail --silent --show-error --max-time 20 --cookie "${cookie_jar}" \
  --request POST --header "X-CSRF-Token: ${csrf}" \
  --header "X-PathLab-Synthetic-Run: ${run_id}" \
  "${CAPACITY_BASE_URL%/}/api/v1/admin/capacity-sentinels/${run_id}/share-cleanup" \
  >/dev/null

manifest="$(curl --fail --silent --show-error --max-time 20 --cookie "${cookie_jar}" \
  "${CAPACITY_BASE_URL%/}/api/v2/admin/annotations/slides/${CAPACITY_ANNOTATION_SLIDE_ID}/manifest")"
items="$(curl --fail --silent --show-error --max-time 20 --cookie "${cookie_jar}" \
  "${CAPACITY_BASE_URL%/}/api/v2/admin/annotations/slides/${CAPACITY_ANNOTATION_SLIDE_ID}/items?limit=5000")"
annotation="$(jq -cer --arg id "${CAPACITY_ANNOTATION_ITEM_ID}" \
  '.items[] | select(.id == $id)' <<< "${items}")"
if [[ "$(jq -r '.metadata.notes // ""' <<< "${annotation}")" == "Synthetic capacity ${run_id}" ]]; then
  mutation_id="$(python -c 'import uuid; print(uuid.uuid4())')"
  payload="$(jq -cn --arg mutation "${mutation_id}" \
    --arg id "${CAPACITY_ANNOTATION_ITEM_ID}" \
    --argjson base "$(jq -r .version <<< "${manifest}")" \
    --argjson version "$(jq -r .version <<< "${annotation}")" \
    --argjson metadata "$(jq '.metadata | del(.notes)' <<< "${annotation}")" \
    '{mutationId:$mutation,baseVersion:$base,operations:[{type:"update",id:$id,version:$version,metadata:$metadata}]}')"
  curl --fail --silent --show-error --max-time 20 --cookie "${cookie_jar}" \
    --request POST --header 'Content-Type: application/json' \
    --header "X-CSRF-Token: ${csrf}" --data "${payload}" \
    "${CAPACITY_BASE_URL%/}/api/v2/admin/annotations/slides/${CAPACITY_ANNOTATION_SLIDE_ID}/batch" \
    >/dev/null
fi

if [[ "$(jq -r '.certification.selectedCapacity // empty' "${DECISION_PATH}" 2>/dev/null || true)" != 300 ]]; then
  python tests/load/validate_sentinel_evidence.py "${SENTINEL_PATH}" --require-cleanup
fi
fixtures_removed=true

# Reconciliation and the pre-finalize Bastion audit must pass while the host is
# still armed. Any failure reaches the EXIT trap, which aborts to 300 and rolls
# the candidate back before recording a failed cleanup result.
remaining="$(oci bastion session list --bastion-id "${OCI_BASTION_ID}" --all \
  --query 'length(data[?"lifecycle-state"==`ACTIVE` || "lifecycle-state"==`CREATING`])' \
  --raw-output)"
[[ "${remaining}" == 0 ]] || { echo "Bastion sessions remain active." >&2; exit 1; }
bastion_remaining=0

decision_present=false
decision_valid=false
selected_capacity=300
if [[ -f "${DECISION_PATH}" && -f "${SIGNATURE_PATH}" ]]; then
  decision_present=true
  selected_capacity="$(jq -er '.certification.selectedCapacity' "${DECISION_PATH}")"
  evidence_b64="$(base64 -w 0 "${DECISION_PATH}" | tr '+/' '-_' | tr -d '=')"
  request="capacity-finalize ${sha} run=${run_id} digest=${digest} evidence=${evidence_b64} signature=$(cat "${SIGNATURE_PATH}") nonce=${nonce}"
  expected_phase='"phase": "restored"'
else
  request="capacity-abort run=${run_id} digest=${digest}"
  expected_phase='"phase": "aborted-restored"'
fi
status="$(bash deploy/scripts/capacity-control-via-bastion.sh "${request}")"
[[ "${status}" == *"${expected_phase}"* ]] || {
  echo "Capacity wrapper did not report restoration." >&2
  exit 1
}
configuration_restored=true
[[ "${decision_present}" == true ]] && decision_valid=true
ack_status="$(bash deploy/scripts/capacity-control-via-bastion.sh \
  "capacity-ack run=${run_id} digest=${digest}")"
jq -e --arg run "${run_id}" --arg digest "${digest}" \
  '.runId == $run and .planDigest == $digest and .controllerAcknowledged == true and
   .cleanupScheduled == true' <<< "${ack_status}" >/dev/null

# Candidate-only cleanup is complete before this authenticated rollback swaps
# to the five-service release.
if [[ "${selected_capacity}" == 300 ]]; then
  : "${CAPACITY_ROLLBACK_RESULT:?CAPACITY_ROLLBACK_RESULT is required}"
  jq -e '.releaseExact == true and .servicesExact == true and .serviceCount == 5 and
    .ready == true and .finalCapacity == 300' <<< "${status}" >/dev/null
  printf '%s\n' "${status}" > "${CAPACITY_ROLLBACK_RESULT}"
  rollback_completed=true
  containment_complete=true
fi
if [[ "${decision_valid}" != true ]]; then
  echo "Capacity decision was unavailable; candidate rolled back at the 300-seat floor." >&2
  exit 1
fi
cleanup_committed=true
