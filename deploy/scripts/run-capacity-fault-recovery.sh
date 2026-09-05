#!/usr/bin/env bash
set -Eeuo pipefail

PLAN_PATH="${1:?capacity plan path is required}"
: "${CAPACITY_BASE_URL:?CAPACITY_BASE_URL is required}"
: "${CAPACITY_FAULT_RESULT:?CAPACITY_FAULT_RESULT is required}"
: "${CAPACITY_CLASSROOM_SESSION_ID:?CAPACITY_CLASSROOM_SESSION_ID is required}"
: "${LOAD_TEST_ADMIN_USERNAME:?LOAD_TEST_ADMIN_USERNAME is required}"
: "${LOAD_TEST_ADMIN_PASSWORD:?LOAD_TEST_ADMIN_PASSWORD is required}"
: "${GH_TOKEN:?GH_TOKEN is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
: "${GITHUB_RUN_ID:?GITHUB_RUN_ID is required}"
: "${GITHUB_RUN_ATTEMPT:?GITHUB_RUN_ATTEMPT is required}"
[[ "${CAPACITY_BASE_URL}" =~ ^https://[^/?#]+/?$ ]] || { echo "Fault target must be an HTTPS origin." >&2; exit 1; }
[[ -f "${PLAN_PATH}" ]] || { echo "Capacity plan is missing." >&2; exit 1; }

WORK_DIR="$(mktemp -d)"
COOKIE_JAR="${WORK_DIR}/cookies"
STATE_BODY="${WORK_DIR}/state.json"
cleanup() { rm -rf -- "${WORK_DIR}"; }
trap cleanup EXIT

run_id="$(jq -r .runId "${PLAN_PATH}")"
sha="$(jq -r .workflowSha "${PLAN_PATH}")"
digest="$(jq -r .planDigest "${PLAN_PATH}")"
recovery_epoch_ms="$(jq -r '.stages[] | select(.name == "recovery-1200") | .holdStartEpochMs + 15000' "${PLAN_PATH}")"
[[ "${run_id}" =~ ^[a-z0-9-]{1,64}$ && "${sha}" =~ ^[0-9a-f]{40}$ && "${digest}" =~ ^[0-9a-f]{64}$ ]] || exit 1

now_ms="$(( $(date +%s) * 1000 ))"
if (( recovery_epoch_ms > now_ms )); then
  sleep "$(( (recovery_epoch_ms - now_ms + 999) / 1000 ))"
fi

# Fail closed immediately before the first scheduled production mutation. The
# gate is read-only and bound to this workflow attempt; it cannot replace the
# independent normal-cancellation watchdog or host cleanup controller.
python scripts/watch_capacity_shards.py --gate-mutation \
  --repository "${GITHUB_REPOSITORY}" --run-id "${GITHUB_RUN_ID}" \
  --run-attempt "${GITHUB_RUN_ATTEMPT}" --expected-shards 6
unset GH_TOKEN

# Authenticate an administrator without consuming a Classroom seat. The six
# shards must retain all 1,200 student seats for the strict recovery hold.
login="$(curl --fail --silent --show-error --max-time 10 \
  --cookie-jar "${COOKIE_JAR}" --header 'Content-Type: application/json' \
  --data "$(jq -cn --arg username "${LOAD_TEST_ADMIN_USERNAME}" \
    --arg password "${LOAD_TEST_ADMIN_PASSWORD}" '{username:$username,password:$password}')" \
  "${CAPACITY_BASE_URL%/}/api/v1/auth/session")"
csrf="$(jq -er .csrfToken <<< "${login}")"

started_epoch="$(date +%s)"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
bash deploy/scripts/capacity-control-via-bastion.sh \
  "capacity-fault run=${run_id} digest=${digest}"

general_ok=true
outage_seen=false
ready_epoch=""
deadline="$((started_epoch + 90))"
while (( $(date +%s) <= deadline )); do
  curl --fail --silent --show-error --max-time 3 "${CAPACITY_BASE_URL%/}/readyz" >/dev/null || general_ok=false
  if curl --fail --silent --show-error --max-time 3 --cookie "${COOKIE_JAR}" \
    "${CAPACITY_BASE_URL%/}/api/v1/admin/classroom/sessions/${CAPACITY_CLASSROOM_SESSION_ID}" \
    -o "${STATE_BODY}"; then
    if [[ "${outage_seen}" == true ]] && jq -e '.hubEpoch | type == "string" and length > 0' "${STATE_BODY}" >/dev/null; then
      ready_epoch="$(date +%s)"
      break
    fi
  else
    outage_seen=true
  fi
  sleep 2
done
[[ "${outage_seen}" == true && -n "${ready_epoch}" && "${general_ok}" == true ]] || {
  echo "Classroom-only fault recovery proof failed." >&2
  exit 1
}
curl --fail --silent --show-error --max-time 10 --cookie "${COOKIE_JAR}" \
  --request POST --header 'Content-Type: application/json' \
  --header "X-CSRF-Token: ${csrf}" --header "X-PathLab-Synthetic-Run: ${run_id}" \
  --data "$(jq -cn --argjson epochMs "$((ready_epoch * 1000))" '{epochMs:$epochMs}')" \
  "${CAPACITY_BASE_URL%/}/api/v1/admin/classroom/sessions/${CAPACITY_CLASSROOM_SESSION_ID}/synthetic-recovery-ready" \
  >/dev/null

converged_epoch=""
convergence_deadline="$((ready_epoch + 30))"
while (( $(date +%s) <= convergence_deadline )); do
  if curl --fail --silent --show-error --max-time 3 --cookie "${COOKIE_JAR}" \
    "${CAPACITY_BASE_URL%/}/api/v1/admin/classroom/sessions/${CAPACITY_CLASSROOM_SESSION_ID}" \
    -o "${STATE_BODY}" && jq -e '.hubEpoch | type == "string" and length > 0' "${STATE_BODY}" >/dev/null; then
    converged_epoch="$(date +%s)"
    break
  fi
  sleep 1
done
[[ -n "${converged_epoch}" ]] || { echo "Fault client did not converge within 30 seconds." >&2; exit 1; }
completed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
jq -n \
  --arg runId "${run_id}" --arg workflowSha "${sha}" --arg planDigest "${digest}" \
  --arg startedAt "${started_at}" --arg completedAt "${completed_at}" \
  --argjson readiness "$((ready_epoch - started_epoch))" \
  --argjson convergence "$((converged_epoch - ready_epoch))" \
  '{schemaVersion:1,runId:$runId,workflowSha:$workflowSha,planDigest:$planDigest,
    startedAt:$startedAt,completedAt:$completedAt,classroomOnly:true,
    generalApiResponsive:true,readinessRecoverySeconds:$readiness,
    convergenceSeconds:$convergence,
    privacy:{aggregateOnly:true,credentialsMasked:true,syntheticFixturesOnly:true}}' \
  > "${CAPACITY_FAULT_RESULT}"
