#!/usr/bin/env bash
set -Eeuo pipefail

: "${CAPACITY_MODE:?CAPACITY_MODE is required}"
: "${CAPACITY_WINDOW_START_ICT:?CAPACITY_WINDOW_START_ICT is required}"
: "${CAPACITY_BASE_URL:?CAPACITY_BASE_URL is required}"
: "${LOAD_TEST_ADMIN_USERNAME:?LOAD_TEST_ADMIN_USERNAME is required}"
: "${LOAD_TEST_ADMIN_PASSWORD:?LOAD_TEST_ADMIN_PASSWORD is required}"
: "${LOAD_TEST_ADMIN_SLIDE_ID:?LOAD_TEST_ADMIN_SLIDE_ID is required}"
: "${LOAD_TEST_PUBLIC_ID:?LOAD_TEST_PUBLIC_ID is required}"
: "${DEPLOY_EVIDENCE_KEY:?DEPLOY_EVIDENCE_KEY is required}"
: "${PROJECTED_EGRESS_BYTES:?PROJECTED_EGRESS_BYTES is required}"
: "${GITHUB_RUN_ID:?GITHUB_RUN_ID is required}"
: "${GITHUB_RUN_ATTEMPT:?GITHUB_RUN_ATTEMPT is required}"
: "${GITHUB_SHA:?GITHUB_SHA is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"

case "${CAPACITY_MODE}" in
  controlled-abort|controller-termination|delayed-cleanup|full-300) ;;
  *) echo "Safe capacity mode is invalid." >&2; exit 2 ;;
esac
[[ "${CAPACITY_WINDOW_START_ICT}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:00\+07:00$ ]] || {
  echo "Protected window must use YYYY-MM-DDTHH:MM:00+07:00." >&2
  exit 2
}
[[ "${GITHUB_SHA}" =~ ^[0-9a-f]{40}$ ]]
[[ "${GITHUB_RUN_ID}" =~ ^[1-9][0-9]{5,19}$ ]]

work_dir="${RUNNER_TEMP}/capacity-safe"
mkdir -p -- "${work_dir}"
status_path="${work_dir}/status.json"
plan_path="${work_dir}/plan.json"
bundle_path="${work_dir}/capacity-fixtures.fernet"
fixture_dir="${work_dir}/fixture"
runtime_path="${work_dir}/runtime.json"
load_path="${work_dir}/load.json"
checks_path="${work_dir}/check-runs.json"
armed=false
restored=false
fixture_created=false
cleanup_proved=false
bastion_remaining=-1
primary_failure="NONE"
plan_digest=""
manifest_digest=""
nonce=""

for value in "${CAPACITY_BASE_URL}" "${LOAD_TEST_ADMIN_USERNAME}" \
  "${LOAD_TEST_ADMIN_PASSWORD}" "${LOAD_TEST_ADMIN_SLIDE_ID}" \
  "${LOAD_TEST_PUBLIC_ID}" "${DEPLOY_EVIDENCE_KEY}"; do
  [[ -n "${value}" ]]
  echo "::add-mask::${value}"
done

write_status() {
  local state="$1" finished="null"
  [[ "${state}" == RUNNING ]] || finished="\"$(date --iso-8601=seconds)\""
  jq -n --arg jobId "${GITHUB_RUN_ID}" --arg kind "capacity-safe-${CAPACITY_MODE}" \
    --arg state "${state}" --arg releaseSha "${GITHUB_SHA}" \
    --arg startedAt "${started_at}" --argjson finishedAt "${finished}" \
    --argjson attempt "${GITHUB_RUN_ATTEMPT}" --arg failureCode "${primary_failure}" \
    --arg restorationState "$([[ "${restored}" == true ]] && echo PROVED || echo NOT_PROVED)" \
    --argjson fixtureCount "$([[ "${cleanup_proved}" == true ]] && echo 0 || echo -1)" \
    --argjson runOwnedBastionCount "${bastion_remaining}" \
    --arg resultManifest "$([[ -s "${load_path}" ]] && echo capacity-safe/load.json || echo '')" \
    '{jobId:$jobId,kind:$kind,state:$state,releaseSha:$releaseSha,startedAt:$startedAt,
      finishedAt:$finishedAt,attempt:$attempt,progressCounters:{fixtureCount:$fixtureCount,
      runOwnedBastionCount:$runOwnedBastionCount},resultManifest:$resultManifest,
      failureCode:$failureCode,restorationState:$restorationState,
      logPath:"protected-actions-artifact"}' > "${status_path}"
}

owned_bastion_count() {
  local owner_run="${1:-${GITHUB_RUN_ID}}"
  local sessions="${work_dir}/bastion.json"
  oci bastion session list --bastion-id "${OCI_BASTION_ID}" --all > "${sessions}"
  jq --arg prefix "pathlab-capacity-${owner_run}-" \
    '[.data[] | select((."display-name" // "") | startswith($prefix)) |
      select(."lifecycle-state" == "ACTIVE" or ."lifecycle-state" == "CREATING" or
        ."lifecycle-state" == "DELETING")] | length' "${sessions}"
}

delete_owned_bastion() {
  local owner_run="$1" sessions="${work_dir}/bastion-delete.json"
  oci bastion session list --bastion-id "${OCI_BASTION_ID}" --all > "${sessions}"
  while IFS= read -r session_id; do
    delete_requested=false
    for _ in 1 2 3; do
      if oci bastion session delete --session-id "${session_id}" --force >/dev/null 2>&1; then
        delete_requested=true
        break
      fi
      sleep 2
    done
    deleted=false
    for _ in $(seq 1 60); do
      if state="$(oci bastion session get --session-id "${session_id}" \
          --query 'data."lifecycle-state"' --raw-output 2>&1)"; then
        [[ "${state}" == DELETED ]] && { deleted=true; break; }
      elif grep -Eq 'NotAuthorizedOrNotFound|NotFound|404' <<< "${state}"; then
        deleted=true
        break
      fi
      sleep 5
    done
    [[ "${deleted}" == true ]] || {
      [[ "${delete_requested}" == true ]] && echo "Bastion deletion was not terminal." >&2
      return 1
    }
  done < <(jq -r --arg prefix "pathlab-capacity-${owner_run}-" \
    '.data[] | select((."display-name" // "") | startswith($prefix)) |
     select(."lifecycle-state" != "DELETED") | .id' "${sessions}")
  [[ "$(owned_bastion_count "${owner_run}")" == 0 ]]
}

reconcile_fixture() {
  python deploy/scripts/capacity_fixtures.py reconcile \
    --run-id "${GITHUB_RUN_ID}" --base-url "${CAPACITY_BASE_URL}" \
    --username "${LOAD_TEST_ADMIN_USERNAME}" --password "${LOAD_TEST_ADMIN_PASSWORD}"
  cleanup_proved=true
}

recover_runtime() {
  local original_failure="${primary_failure}"
  if [[ "${armed}" == true && -n "${plan_digest}" ]]; then
    if abort_runtime; then
      return 0
    fi
    primary_failure="CAPACITY_ABORT_FAILED"
    if ! status="$(bash deploy/scripts/capacity-control-via-bastion.sh \
        "capacity-recover run=${GITHUB_RUN_ID} sha=${GITHUB_SHA}")"; then
      primary_failure="CAPACITY_RECOVERY_FAILED"
      return 1
    fi
    if ! jq -e --arg sha "${GITHUB_SHA}" \
      '.releaseSha == $sha and .releaseExact == true and .servicesExact == true and
       .ready == true and .classroomEnabled == true and .finalCapacity == 300 and
       .annotationsEnabled == false and .controllerReconciled == true' \
      <<< "${status}" >/dev/null; then
      primary_failure="CAPACITY_RECOVERY_INVALID"
      return 1
    fi
    restored=true
    armed=false
    primary_failure="${original_failure}"
  fi
}

abort_runtime() {
  local status
  if ! status="$(bash deploy/scripts/capacity-control-via-bastion.sh \
      "capacity-abort run=${GITHUB_RUN_ID} digest=${plan_digest}")"; then
    primary_failure="CAPACITY_ABORT_FAILED"
    return 1
  fi
  if ! jq -e --arg sha "${GITHUB_SHA}" \
    '.releaseSha == $sha and .releaseExact == true and .servicesExact == true and
     .ready == true and .classroomEnabled == true and .finalCapacity == 300 and
     .annotationsEnabled == false' <<< "${status}" >/dev/null; then
    primary_failure="CAPACITY_ABORT_INVALID"
    return 1
  fi
  # A verified abort is itself the same-release restoration result. Do not
  # issue a second capacity-recover request: it adds no safety evidence and a
  # transient second tunnel must not turn a proved restoration into failure.
  restored=true
  armed=false
}

finish() {
  local result=$?
  trap - EXIT INT TERM
  set +e
  if [[ "${result}" -ne 0 ]]; then
    primary_failure="${primary_failure/NONE/SAFE_VERIFICATION_FAILED}"
  fi
  reconcile_fixture >/dev/null 2>&1 || true
  recover_runtime >/dev/null 2>&1 || true
  if [[ -n "${manifest_digest}" ]]; then
    post="$(bash deploy/scripts/capacity-control-via-bastion.sh \
      "capacity-postflight expected=${GITHUB_SHA} manifest=${manifest_digest}" 2>/dev/null)"
    if jq -e --arg sha "${GITHUB_SHA}" --arg manifest "${manifest_digest}" \
      '.releaseSha == $sha and .runtimeManifestDigest == $manifest and .releaseExact == true and
       .servicesExact == true and .ready == true and .classroomEnabled == true and
       .finalCapacity == 300 and .annotationsEnabled == false' <<< "${post}" >/dev/null 2>&1; then
      restored=true
    else
      result=1
      primary_failure="POSTFLIGHT_NOT_PROVED"
    fi
  fi
  if delete_owned_bastion "${GITHUB_RUN_ID}" >/dev/null 2>&1; then
    bastion_remaining="$(owned_bastion_count 2>/dev/null)" || {
      bastion_remaining=-1
      result=1
      primary_failure="BASTION_CLEANUP_NOT_PROVED"
    }
  else
    bastion_remaining=-1
    result=1
    primary_failure="BASTION_CLEANUP_NOT_PROVED"
  fi
  if [[ "${bastion_remaining}" != 0 ]]; then
    result=1
    primary_failure="BASTION_RESIDUE"
  fi
  if [[ "${result}" -eq 0 && "${restored}" == true && "${cleanup_proved}" == true ]]; then
    write_status SUCCEEDED
  else
    write_status FAILED_TERMINAL
    result=1
  fi
  rm -rf -- "${fixture_dir}" "${work_dir}/deploy-evidence.key" \
    "${work_dir}/deploy-evidence.json" "${work_dir}/deploy-evidence.signature" \
    "${work_dir}/check-runs.json" "${work_dir}/bastion.json"
  exit "${result}"
}
trap finish EXIT INT TERM

started_at="$(date --iso-8601=seconds)"
write_status RUNNING

window_start_epoch="$(date -d "${CAPACITY_WINDOW_START_ICT}" +%s)"
now_epoch="$(date +%s)"
lead_seconds="$((window_start_epoch - now_epoch))"
(( lead_seconds >= 1200 && lead_seconds <= 2400 )) || {
  primary_failure="WINDOW_LEAD_INVALID"
  exit 1
}
window_end_epoch="$((window_start_epoch + 10800))"
start_epoch_ms="$(((window_start_epoch + 540) * 1000))"

test "$(git rev-parse HEAD)" = "${GITHUB_SHA}"
test "$(git ls-remote origin refs/heads/main | awk '{print $1}')" = "${GITHUB_SHA}"
gh api "repos/${GITHUB_REPOSITORY}/commits/${GITHUB_SHA}/check-runs?filter=latest&per_page=100" \
  > "${checks_path}"
browser_ci_id=""
for check in backend browser web containers repository-and-dependencies \
  "CodeQL (python)" "CodeQL (javascript-typescript)"; do
  record="$(jq -r --arg check "${check}" --arg sha "${GITHUB_SHA}" \
    '[.check_runs[] | select(.name == $check and .head_sha == $sha and
      .status == "completed" and .conclusion == "success")] | sort_by(.id) | last |
      if . == null then empty else [.id,.conclusion] | @tsv end' "${checks_path}")"
  [[ -n "${record}" ]] || { primary_failure="PROTECTED_CHECK_MISSING"; exit 1; }
  if [[ "${check}" == browser ]]; then browser_ci_id="${record%%$'\t'*}"; fi
done

if [[ -n "${CAPACITY_RECOVERY_RUN_ID:-}" ]]; then
  [[ "${CAPACITY_RECOVERY_RUN_ID}" =~ ^[1-9][0-9]{5,19}$ ]]
  prior="$(gh run view "${CAPACITY_RECOVERY_RUN_ID}" \
    --json status,conclusion,headSha,headBranch,event,workflowName)"
  jq -e '.status == "completed" and
    (.conclusion == "failure" or .conclusion == "cancelled" or .conclusion == "timed_out") and
    .headBranch == "main" and .event == "workflow_dispatch" and
    .workflowName == "Capacity certification" and (.headSha | test("^[0-9a-f]{40}$"))' \
    <<< "${prior}" >/dev/null
  prior_sha="$(jq -er .headSha <<< "${prior}")"
  python deploy/scripts/capacity_fixtures.py reconcile \
    --run-id "${CAPACITY_RECOVERY_RUN_ID}" --base-url "${CAPACITY_BASE_URL}" \
    --username "${LOAD_TEST_ADMIN_USERNAME}" --password "${LOAD_TEST_ADMIN_PASSWORD}"
  prior_recovery="$(bash deploy/scripts/capacity-control-via-bastion.sh \
    "capacity-recover run=${CAPACITY_RECOVERY_RUN_ID} sha=${prior_sha}")"
  jq -e --arg sha "${GITHUB_SHA}" \
    '.releaseSha == $sha and .releaseExact == true and .servicesExact == true and
     .ready == true and .classroomEnabled == true and .finalCapacity == 300 and
     .annotationsEnabled == false and .controllerReconciled == true' \
    <<< "${prior_recovery}" >/dev/null
  delete_owned_bastion "${CAPACITY_RECOVERY_RUN_ID}"
fi

python deploy/scripts/capacity_fixtures.py assert-empty --base-url "${CAPACITY_BASE_URL}" \
  --username "${LOAD_TEST_ADMIN_USERNAME}" --password "${LOAD_TEST_ADMIN_PASSWORD}"
runtime="$(bash deploy/scripts/capacity-control-via-bastion.sh \
  "capacity-runtime-preflight expected=${GITHUB_SHA}")"
manifest_digest="$(jq -er '.runtimeManifestDigest | select(test("^[0-9a-f]{64}$"))' <<< "${runtime}")"

python tests/load/distributed_certification.py plan --run-id "${GITHUB_RUN_ID}" \
  --workflow-sha "${GITHUB_SHA}" --browser-ci-run-id "${browser_ci_id}" \
  --window-start-epoch-ms "$((window_start_epoch * 1000))" \
  --start-epoch-ms "${start_epoch_ms}" --output "${plan_path}"
plan_digest="$(jq -er .planDigest "${plan_path}")"

remaining="$((window_start_epoch - $(date +%s)))"
(( remaining > 0 )) && sleep "${remaining}"

python deploy/scripts/capacity_fixtures.py create --plan "${plan_path}" \
  --run-id "${GITHUB_RUN_ID}" --workflow-sha "${GITHUB_SHA}" \
  --base-url "${CAPACITY_BASE_URL}" --username "${LOAD_TEST_ADMIN_USERNAME}" \
  --password "${LOAD_TEST_ADMIN_PASSWORD}" --slide-id "${LOAD_TEST_ADMIN_SLIDE_ID}" \
  --public-id "${LOAD_TEST_PUBLIC_ID}" --evidence-key "${DEPLOY_EVIDENCE_KEY}" \
  --output "${bundle_path}"
fixture_created=true
python deploy/scripts/capacity_fixtures.py materialize --input "${bundle_path}" \
  --output-dir "${fixture_dir}" --evidence-key "${DEPLOY_EVIDENCE_KEY}" \
  --run-id "${GITHUB_RUN_ID}" --workflow-sha "${GITHUB_SHA}"

evidence_key_file="${work_dir}/deploy-evidence.key"
evidence_file="${work_dir}/deploy-evidence.json"
signature_file="${work_dir}/deploy-evidence.signature"
install -m 600 /dev/null "${evidence_key_file}"
printf '%s' "${DEPLOY_EVIDENCE_KEY}" > "${evidence_key_file}"
nonce="$(python -c 'import hashlib,hmac,os; print(hmac.new(os.environ["DEPLOY_EVIDENCE_KEY"].encode(), (os.environ["GITHUB_RUN_ID"]+":"+os.environ["GITHUB_RUN_ATTEMPT"]+":"+os.environ["CAPACITY_MODE"]).encode(), hashlib.sha256).hexdigest())')"
echo "::add-mask::${nonce}"
python deploy/scripts/build_deploy_evidence.py --checks "${checks_path}" \
  --candidate-sha "${GITHUB_SHA}" --repository "${GITHUB_REPOSITORY}" \
  --workflow-run-id "${GITHUB_RUN_ID}" --nonce "${nonce}" \
  --projected-monthly-egress-bytes "${PROJECTED_EGRESS_BYTES}" \
  --month-to-date-cost-sgd 0 --key-file "${evidence_key_file}" \
  --output "${evidence_file}" --signature-output "${signature_file}"

now_epoch="$(date +%s)"
deadline="$((now_epoch + 1200))"
restore_not_after="$((deadline + 300))"
# The Bastion session is intentionally short-lived but can take several
# minutes to become ACTIVE. Bind the unused fault window to the controller
# deadline, not the runner clock immediately before session creation.
fault_start="$((deadline - 600))"
fault_end="$((deadline - 300))"
evidence_b64="$(base64 -w 0 "${evidence_file}" | tr '+/' '-_' | tr -d '=')"
request="capacity-arm ${GITHUB_SHA} run=${GITHUB_RUN_ID} digest=${plan_digest} manifest=${manifest_digest} arm-not-after=$((now_epoch + 120)) window-start=${window_start_epoch} window-end=${window_end_epoch} deadline=${deadline} restore-not-after=${restore_not_after} fault-start=${fault_start} fault-end=${fault_end} evidence=${evidence_b64} signature=$(cat "${signature_file}") nonce=${nonce}"
bash deploy/scripts/capacity-control-via-bastion.sh \
  "capacity-runtime-preflight expected=${GITHUB_SHA} manifest=${manifest_digest}" \
  "${request}" >/dev/null
armed=true

stage_name=smoke-2
participants=2
duration=20
if [[ "${CAPACITY_MODE}" == full-300 ]]; then
  stage_name=boundary-300
  participants=300
  duration=600
fi
stage="$(jq -cer --arg name "${stage_name}" '.[$name]' "${fixture_dir}/stage-manifest.json")"
jq -r '.. | strings' <<< "${stage}" | while IFS= read -r value; do echo "::add-mask::${value}"; done
PATHLAB_CLASSROOM_BASE_URL="${CAPACITY_BASE_URL}" \
PATHLAB_CLASSROOM_ADMIN_USERNAME="${LOAD_TEST_ADMIN_USERNAME}" \
PATHLAB_CLASSROOM_ADMIN_PASSWORD="${LOAD_TEST_ADMIN_PASSWORD}" \
PATHLAB_CLASSROOM_PROTECTED_REMOTE=true PATHLAB_CLASSROOM_SYNTHETIC_ONLY=true \
PATHLAB_CLASSROOM_JOIN_CODE="$(jq -er .joinCode <<< "${stage}")" \
PATHLAB_CLASSROOM_SESSION_ID="$(jq -er .sessionId <<< "${stage}")" \
PATHLAB_CLASSROOM_SLIDE_ID="$(jq -er .slideId <<< "${stage}")" \
PATHLAB_CLASSROOM_MEDIA_MANIFEST="${fixture_dir}/media-manifest.json" \
PATHLAB_CLASSROOM_PARTICIPANTS="${participants}" \
PATHLAB_CLASSROOM_GLOBAL_TARGET="${participants}" \
PATHLAB_CLASSROOM_DURATION_SECONDS="${duration}" \
PATHLAB_CLASSROOM_PRESENTER_RATE=2 \
python tests/load/classroom_sse.py > "${load_path}"
jq -e '.participants == '"${participants}"' and .participantErrors == [] and
  .taskErrors == [] and .unexpectedSseDisconnects == 0' "${load_path}" >/dev/null

if [[ "${CAPACITY_MODE}" == controlled-abort ]]; then
  abort_runtime
elif [[ "${CAPACITY_MODE}" == controller-termination ]]; then
  terminated="$(bash deploy/scripts/capacity-control-via-bastion.sh \
    "capacity-terminate-controller run=${GITHUB_RUN_ID} digest=${plan_digest}")"
  jq -e '.controllerTerminated == true and .recoveryRequired == true' <<< "${terminated}" >/dev/null
  recovered="$(bash deploy/scripts/capacity-control-via-bastion.sh \
    "capacity-recover run=${GITHUB_RUN_ID} sha=${GITHUB_SHA}")"
  jq -e --arg sha "${GITHUB_SHA}" '.releaseSha == $sha and .releaseExact == true and
    .servicesExact == true and .ready == true and .finalCapacity == 300 and
    .annotationsEnabled == false and .controllerReconciled == true' <<< "${recovered}" >/dev/null
  armed=false
  restored=true
elif [[ "${CAPACITY_MODE}" == delayed-cleanup ]]; then
  rm -f -- "${bundle_path}"
  sleep 15
  reconcile_fixture
  recover_runtime
else
  recover_runtime
fi

reconcile_fixture
python deploy/scripts/capacity_fixtures.py assert-empty --base-url "${CAPACITY_BASE_URL}" \
  --username "${LOAD_TEST_ADMIN_USERNAME}" --password "${LOAD_TEST_ADMIN_PASSWORD}"
post="$(bash deploy/scripts/capacity-control-via-bastion.sh \
  "capacity-postflight expected=${GITHUB_SHA} manifest=${manifest_digest}")"
jq -e --arg sha "${GITHUB_SHA}" --arg manifest "${manifest_digest}" \
  '.releaseSha == $sha and .runtimeManifestDigest == $manifest and .releaseExact == true and
   .servicesExact == true and .ready == true and .watchdogActive == true and
   .classroomEnabled == true and .finalCapacity == 300 and .annotationsEnabled == false' \
  <<< "${post}" >/dev/null
printf '%s\n' "${post}" > "${runtime_path}"
restored=true
delete_owned_bastion "${GITHUB_RUN_ID}"
bastion_remaining="$(owned_bastion_count)"
[[ "${bastion_remaining}" == 0 ]]
trap - EXIT INT TERM
write_status SUCCEEDED
rm -rf -- "${fixture_dir}" "${evidence_key_file}" "${evidence_file}" "${signature_file}" \
  "${checks_path}" "${work_dir}/bastion.json"
