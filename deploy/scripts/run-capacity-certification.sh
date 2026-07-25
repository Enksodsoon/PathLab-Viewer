#!/usr/bin/env bash
set -Eeuo pipefail

: "${CAPACITY_BASE_URL:?CAPACITY_BASE_URL is required}"
: "${LOAD_TEST_PUBLIC_ID:?LOAD_TEST_PUBLIC_ID is required}"
: "${LOAD_TEST_ADMIN_SLIDE_ID:?LOAD_TEST_ADMIN_SLIDE_ID is required}"
: "${LOAD_TEST_ADMIN_USERNAME:?LOAD_TEST_ADMIN_USERNAME is required}"
: "${LOAD_TEST_ADMIN_PASSWORD:?LOAD_TEST_ADMIN_PASSWORD is required}"
: "${GITHUB_SHA:?GITHUB_SHA is required}"
: "${GITHUB_RUN_ID:?GITHUB_RUN_ID is required}"
: "${CAPACITY_EVIDENCE_DIR:?CAPACITY_EVIDENCE_DIR is required}"

[[ "${CAPACITY_BASE_URL}" =~ ^https://[^/?#]+/?$ ]] || {
  echo "CAPACITY_BASE_URL must be an HTTPS origin." >&2
  exit 1
}
[[ "${LOAD_TEST_PUBLIC_ID}" =~ ^[A-Za-z0-9_-]+$ ]] || {
  echo "LOAD_TEST_PUBLIC_ID is invalid." >&2
  exit 1
}
[[ "${LOAD_TEST_ADMIN_SLIDE_ID}" =~ ^[A-Za-z0-9-]+$ ]] || {
  echo "LOAD_TEST_ADMIN_SLIDE_ID is invalid." >&2
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
export MANIFEST_PATH
export CAPACITY_SYNTHETIC_OME="${SYNTHETIC_PATH}"
export CAPACITY_BROWSER_RESULT="${WORK_DIR}/browser-result.json"
mkdir -p "${CAPACITY_EVIDENCE_DIR}"

cleanup() {
  local exit_code=$?
  trap - EXIT
  jobs -pr | xargs -r kill >/dev/null 2>&1 || true
  rm -rf -- "${WORK_DIR}"
  exit "${exit_code}"
}
trap cleanup EXIT

python tests/load/generate_remote_manifest.py \
  --base-url "${CAPACITY_BASE_URL}" \
  --public-id "${LOAD_TEST_PUBLIC_ID}" \
  --output "${MANIFEST_PATH}" \
  --seed "${GITHUB_RUN_ID}"
python tests/load/generate_synthetic_ome.py --output "${SYNTHETIC_PATH}"

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

run_profile smoke 50 false
run_profile acceptance 630 false
run_profile capacity300 900 true

python tests/load/certification_report.py \
  --summary "${WORK_DIR}/capacity-summary.json" \
  --observer "${WORK_DIR}/capacity-observer.ndjson" \
  --browser "${CAPACITY_BROWSER_RESULT}" \
  --commit "${GITHUB_SHA}" \
  --json-output "${CAPACITY_EVIDENCE_DIR}/capacity-certification.json" \
  --markdown-output "${CAPACITY_EVIDENCE_DIR}/capacity-certification.md"
