#!/usr/bin/env bash
set -Eeuo pipefail

PLAN_PATH="${1:?capacity plan path is required}"
: "${CAPACITY_BASE_URL:?CAPACITY_BASE_URL is required}"
: "${CAPACITY_SENTINEL_RESULT:?CAPACITY_SENTINEL_RESULT is required}"
: "${CAPACITY_SYNTHETIC_330MB:?CAPACITY_SYNTHETIC_330MB is required}"
[[ -f "${PLAN_PATH}" ]] || { echo "Capacity plan is missing." >&2; exit 1; }
[[ -f "${CAPACITY_SYNTHETIC_330MB}" ]] || {
  echo "The approved synthetic 330-MB fixture is missing." >&2
  exit 1
}
fixture_bytes="$(wc -c < "${CAPACITY_SYNTHETIC_330MB}")"
(( fixture_bytes >= 330000000 && fixture_bytes <= 331000000 )) || {
  echo "The synthetic fixture is not the approved 330-MB size." >&2
  exit 1
}
export CAPACITY_RUN_ID="$(jq -r .runId "${PLAN_PATH}")"
export CAPACITY_WORKFLOW_SHA="$(jq -r .workflowSha "${PLAN_PATH}")"
export CAPACITY_PLAN_DIGEST="$(jq -r .planDigest "${PLAN_PATH}")"
export CAPACITY_BROWSER_CI_RUN_ID="$(jq -r .browserCiRunId "${PLAN_PATH}")"
export CAPACITY_FIXTURE_BYTES="${fixture_bytes}"
[[ "${CAPACITY_RUN_ID}" =~ ^[a-z0-9-]{1,64}$ && \
   "${CAPACITY_WORKFLOW_SHA}" =~ ^[0-9a-f]{40}$ && \
   "${CAPACITY_PLAN_DIGEST}" =~ ^[0-9a-f]{64}$ ]] || exit 1
: "${CAPACITY_CLASSROOM_JOIN_CODE:?CAPACITY_CLASSROOM_JOIN_CODE is required}"

start_epoch_ms="$(python - "${PLAN_PATH}" <<'PY'
import json, sys
plan = json.load(open(sys.argv[1], encoding="utf-8"))
stage = next(item for item in plan["stages"] if item["name"] == "sustained-1200")
print(stage["holdStartEpochMs"])
PY
)"
now_ms="$(( $(date +%s) * 1000 ))"
if (( start_epoch_ms > now_ms )); then sleep "$(( (start_epoch_ms - now_ms + 999) / 1000 ))"; fi

export CAPACITY_SYNTHETIC_OME="${CAPACITY_SYNTHETIC_330MB}"
export CAPACITY_BROWSER_RESULT="${CAPACITY_SENTINEL_RESULT}"
export CAPACITY_SENTINEL_PRIVATE_STATE="$(mktemp)"
chmod 600 "${CAPACITY_SENTINEL_PRIVATE_STATE}"
reconcile() {
  local result=0
  pnpm --dir apps/web exec playwright test \
    --config playwright.live.config.ts --workers=1 \
    e2e-live/capacity-sentinel-cleanup.spec.ts || result=$?
  rm -f -- "${CAPACITY_SENTINEL_PRIVATE_STATE}"
  return "${result}"
}
finish() {
  local result=$?
  trap - EXIT INT TERM
  reconcile || result=1
  exit "${result}"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
pnpm --dir apps/web exec playwright test \
  --config playwright.capacity-metrics.config.ts --workers=1 \
  e2e-live/capacity-frontend.spec.ts
pnpm --dir apps/web exec playwright test \
  --config playwright.live.config.ts \
  --workers=1 \
  e2e-live/capacity-certification.spec.ts \
  e2e-live/capacity-sentinels.spec.ts

reconcile
trap - EXIT INT TERM

python tests/load/validate_sentinel_evidence.py --require-cleanup "${CAPACITY_SENTINEL_RESULT}"
