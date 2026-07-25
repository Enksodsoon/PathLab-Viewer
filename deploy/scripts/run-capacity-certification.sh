#!/usr/bin/env bash
set -Eeuo pipefail

: "${CAPACITY_BASE_URL:?CAPACITY_BASE_URL is required}"
: "${LOAD_TEST_ADMIN_USERNAME:?LOAD_TEST_ADMIN_USERNAME is required}"
: "${LOAD_TEST_ADMIN_PASSWORD:?LOAD_TEST_ADMIN_PASSWORD is required}"
: "${GITHUB_SHA:?GITHUB_SHA is required}"
: "${GITHUB_RUN_ID:?GITHUB_RUN_ID is required}"
: "${CAPACITY_EVIDENCE_DIR:?CAPACITY_EVIDENCE_DIR is required}"

[[ "${CAPACITY_BASE_URL}" =~ ^https://[^/?#]+/?$ ]] || {
  echo "CAPACITY_BASE_URL must be an HTTPS origin." >&2
  exit 1
}
[[ "${GITHUB_SHA}" =~ ^[0-9a-f]{40}$ ]] || {
  echo "GITHUB_SHA must be a full lowercase commit SHA." >&2
  exit 1
}
command -v k6 >/dev/null || { echo "k6 is required." >&2; exit 1; }
command -v curl >/dev/null || { echo "curl is required." >&2; exit 1; }

WORK_DIR="$(mktemp -d)"
MANIFEST_PATH="${WORK_DIR}/viewer-manifest.json"
SYNTHETIC_PATH="${WORK_DIR}/synthetic-capacity.ome.tiff"
FIXTURE_PATH="${WORK_DIR}/synthetic-public-fixture.ome.tiff"
export CAPACITY_FIXTURE_OME="${FIXTURE_PATH}"
export CAPACITY_FIXTURE_RESULT="${WORK_DIR}/capacity-fixture.json"
export CAPACITY_FIXTURE_DIAGNOSTIC="${CAPACITY_EVIDENCE_DIR}/capacity-fixture-diagnostic.json"
export MANIFEST_PATH
export CAPACITY_SYNTHETIC_OME="${SYNTHETIC_PATH}"
export CAPACITY_BROWSER_RESULT="${WORK_DIR}/browser-result.json"
mkdir -p "${CAPACITY_EVIDENCE_DIR}"

cleanup() {
  local exit_code=$?
  trap - EXIT
  jobs -pr | xargs -r kill >/dev/null 2>&1 || true
  if [[ -f "${CAPACITY_FIXTURE_RESULT}" ]]; then
    set +e
    CAPACITY_FIXTURE_ACTION=cleanup \
      pnpm --dir apps/web exec playwright test \
      --config playwright.live.config.ts \
      e2e-live/capacity-fixture.spec.ts \
      > "${WORK_DIR}/fixture-cleanup-private.log" 2>&1
    cleanup_status=$?
    set -e
    if [[ "${cleanup_status}" -ne 0 ]]; then
      echo "Synthetic capacity fixture cleanup failed." >&2
      [[ "${exit_code}" -eq 0 ]] && exit_code=1
    fi
  fi
  rm -rf -- "${WORK_DIR}"
  exit "${exit_code}"
}
trap cleanup EXIT

echo "Capacity phase: synthetic fixture generation."
if ! python tests/load/generate_synthetic_ome.py \
  --output "${FIXTURE_PATH}" \
  --width 4096 \
  --height 4096; then
  echo "Capacity certification failed during synthetic fixture generation." >&2
  exit 1
fi
echo "Capacity phase: synthetic fixture preparation."
set +e
CAPACITY_FIXTURE_ACTION=prepare \
  pnpm --dir apps/web exec playwright test \
    --config playwright.live.config.ts \
    e2e-live/capacity-fixture.spec.ts \
    > "${WORK_DIR}/fixture-prepare-private.log" 2>&1
fixture_prepare_status=$?
set -e
if [[ "${fixture_prepare_status}" -ne 0 ]]; then
  python -c \
    'import json,sys; print("Synthetic fixture preparation failed at stage: " + json.load(open(sys.argv[1], encoding="utf-8"))["stage"], file=sys.stderr)' \
    "${CAPACITY_FIXTURE_DIAGNOSTIC}" 2>/dev/null || \
    echo "Synthetic fixture preparation failed before a diagnostic stage was recorded." >&2
  exit 1
fi
echo "Capacity phase: synthetic fixture result validation."
if ! LOAD_TEST_PUBLIC_ID="$(
  python -c \
    'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["publicId"])' \
    "${CAPACITY_FIXTURE_RESULT}"
)"; then
  echo "Synthetic fixture result did not contain a public ID." >&2
  exit 1
fi
export LOAD_TEST_PUBLIC_ID
if ! LOAD_TEST_ADMIN_SLIDE_ID="$(
  python -c \
    'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["slideId"])' \
    "${CAPACITY_FIXTURE_RESULT}"
)"; then
  echo "Synthetic fixture result did not contain an admin slide ID." >&2
  exit 1
fi
export LOAD_TEST_ADMIN_SLIDE_ID
[[ "${LOAD_TEST_PUBLIC_ID}" =~ ^[A-Za-z0-9_-]+$ ]] || {
  echo "Synthetic fixture public ID is invalid." >&2
  exit 1
}
[[ "${LOAD_TEST_ADMIN_SLIDE_ID}" =~ ^[A-Za-z0-9-]+$ ]] || {
  echo "Synthetic fixture slide ID is invalid." >&2
  exit 1
}

echo "Capacity phase: private load manifest generation."
if ! python tests/load/generate_remote_manifest.py \
  --base-url "${CAPACITY_BASE_URL}" \
  --public-id "${LOAD_TEST_PUBLIC_ID}" \
  --output "${MANIFEST_PATH}" \
  --seed "${GITHUB_RUN_ID}"; then
  echo "Capacity certification failed during private manifest generation." >&2
  exit 1
fi
echo "Capacity phase: conversion fixture generation."
if ! python tests/load/generate_synthetic_ome.py --output "${SYNTHETIC_PATH}"; then
  echo "Capacity certification failed during conversion fixture generation." >&2
  exit 1
fi

echo "Capacity phase: readiness probes."
for _ in 1 2 3; do
  curl --fail --silent --show-error --max-time 10 \
    "${CAPACITY_BASE_URL%/}/readyz" >/dev/null
done

abort_profile() {
  local message="$1"
  shift
  for pid in "$@"; do
    [[ -n "${pid}" ]] && kill "${pid}" >/dev/null 2>&1 || true
  done
  echo "Capacity profile aborted: ${message}" >&2
  return 1
}

run_profile() {
  local profile="$1"
  local observe_duration="$2"
  local browser_enabled="$3"
  local observer="${WORK_DIR}/${profile}-observer.ndjson"
  local k6_json="${WORK_DIR}/${profile}-k6.ndjson"
  local summary="${WORK_DIR}/${profile}-summary.json"
  local done_file="${WORK_DIR}/${profile}.done"
  local observer_status="${WORK_DIR}/${profile}-observer.status"
  local k6_status="${WORK_DIR}/${profile}-k6.status"
  local watchdog_status="${WORK_DIR}/${profile}-watchdog.status"
  local browser_status="${WORK_DIR}/${profile}-browser.status"
  local browser_pid=""
  local k6_pid=""
  local watchdog_pid=""

  (
    set +e
    child=""
    trap '[[ -n "${child}" ]] && kill "${child}" >/dev/null 2>&1; wait "${child}" 2>/dev/null; exit 143' TERM INT
    deploy/scripts/observe-via-bastion.sh "${observe_duration}" > "${observer}" &
    child=$!
    wait "${child}"
    result=$?
    printf '%s\n' "${result}" > "${observer_status}"
  ) &
  local observer_pid=$!

  observer_ready=0
  for _ in $(seq 1 120); do
    if [[ -s "${observer}" ]]; then
      observer_ready=1
      break
    fi
    if [[ -f "${observer_status}" ]]; then
      abort_profile "host observation failed before load started" "${observer_pid}"
      return 1
    fi
    sleep 2
  done
  if [[ "${observer_ready}" -ne 1 ]]; then
    abort_profile "host observation did not start" "${observer_pid}"
    return 1
  fi
  python -c \
    'import json,sys; first=json.loads(open(sys.argv[1], encoding="utf-8").readline()); raise SystemExit(0 if first.get("releaseSha") == sys.argv[2] else 1)' \
    "${observer}" "${GITHUB_SHA}" || {
      abort_profile "the live release does not match the workflow commit" "${observer_pid}"
      return 1
    }

  (
    set +e
    child=""
    trap '[[ -n "${child}" ]] && kill "${child}" >/dev/null 2>&1; wait "${child}" 2>/dev/null; exit 143' TERM INT
    BASE_URL="${CAPACITY_BASE_URL%/}" PROFILE="${profile}" \
      k6 run --quiet --address 127.0.0.1:6565 \
      --out "json=${k6_json}" \
      --summary-export "${summary}" \
      tests/load/viewer.js &
    child=$!
    wait "${child}"
    result=$?
    printf '%s\n' "${result}" > "${k6_status}"
  ) &
  k6_pid=$!
  (
    set +e
    python tests/load/certification_watchdog.py \
      --observer "${observer}" \
      --k6-json "${k6_json}" \
      --done "${done_file}"
    printf '%s\n' "$?" > "${watchdog_status}"
  ) &
  watchdog_pid=$!

  if [[ "${browser_enabled}" == "true" ]]; then
    (
      set +e
      child=""
      trap '[[ -n "${child}" ]] && kill "${child}" >/dev/null 2>&1; wait "${child}" 2>/dev/null; exit 143' TERM INT
      reached=0
      for _ in $(seq 1 120); do
        if curl --fail --silent --max-time 2 http://127.0.0.1:6565/v1/status |
          python -c 'import json,sys; raise SystemExit(0 if json.load(sys.stdin)["data"]["attributes"]["vus"] >= 300 else 1)' \
          >/dev/null 2>&1; then
          reached=1
          break
        fi
        sleep 2
      done
      if [[ "${reached}" -ne 1 ]]; then
        printf '2\n' > "${browser_status}"
        exit 0
      fi
      pnpm --dir apps/web exec playwright test \
        --config playwright.live.config.ts \
        > "${WORK_DIR}/browser-private.log" 2>&1 &
      child=$!
      wait "${child}"
      result=$?
      printf '%s\n' "${result}" > "${browser_status}"
    ) &
    browser_pid=$!
  fi

  while [[ ! -f "${k6_status}" || ! -f "${observer_status}" \
    || ( "${browser_enabled}" == "true" && ! -f "${browser_status}" ) ]]; do
    if [[ -f "${watchdog_status}" ]] && [[ "$(cat "${watchdog_status}")" != "0" ]]; then
      abort_profile "a safety limit was reached" \
        "${k6_pid}" "${observer_pid}" "${browser_pid}" "${watchdog_pid}"
      return 1
    fi
    if [[ -f "${k6_status}" ]] && [[ "$(cat "${k6_status}")" != "0" ]]; then
      abort_profile "k6 failed" "${observer_pid}" "${browser_pid}" "${watchdog_pid}"
      return 1
    fi
    if [[ -f "${observer_status}" ]] && [[ "$(cat "${observer_status}")" != "0" ]]; then
      abort_profile "host observation failed" "${k6_pid}" "${browser_pid}" "${watchdog_pid}"
      return 1
    fi
    if [[ -f "${observer_status}" ]] \
      && [[ ! -f "${k6_status}" \
        || ( "${browser_enabled}" == "true" && ! -f "${browser_status}" ) ]]; then
      abort_profile "host observation ended before the workload" \
        "${k6_pid}" "${browser_pid}" "${watchdog_pid}"
      return 1
    fi
    if [[ -f "${browser_status}" ]] && [[ "$(cat "${browser_status}")" != "0" ]]; then
      abort_profile "production browser checks failed" \
        "${k6_pid}" "${observer_pid}" "${watchdog_pid}"
      return 1
    fi
    sleep 2
  done
  touch "${done_file}"
  wait "${watchdog_pid}"
  [[ "$(cat "${watchdog_status}")" == "0" ]] || \
    abort_profile "a safety limit was reached" "" "" ""

  if [[ "${profile}" == "capacity300" ]]; then
    cp "${observer}" "${WORK_DIR}/capacity-observer.ndjson"
    cp "${summary}" "${WORK_DIR}/capacity-summary.json"
  fi
}

echo "Capacity phase: smoke profile."
run_profile smoke 50 false
echo "Capacity phase: 100-user acceptance profile."
run_profile acceptance 630 false
echo "Capacity phase: 300-user capacity profile."
run_profile capacity300 900 true

echo "Capacity phase: aggregate report generation."
python tests/load/certification_report.py \
  --summary "${WORK_DIR}/capacity-summary.json" \
  --observer "${WORK_DIR}/capacity-observer.ndjson" \
  --browser "${CAPACITY_BROWSER_RESULT}" \
  --commit "${GITHUB_SHA}" \
  --json-output "${CAPACITY_EVIDENCE_DIR}/capacity-certification.json" \
  --markdown-output "${CAPACITY_EVIDENCE_DIR}/capacity-certification.md"
