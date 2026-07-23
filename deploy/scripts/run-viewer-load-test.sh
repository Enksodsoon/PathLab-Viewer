#!/usr/bin/env bash
set -euo pipefail

profile="${1:-}"
case "${profile}" in
  smoke|acceptance) ;;
  *)
    echo "Usage: run-viewer-load-test.sh smoke|acceptance" >&2
    exit 2
    ;;
esac

: "${BASE_URL:?BASE_URL is required}"
: "${MANIFEST_PATH:?MANIFEST_PATH is required}"
[[ "${MANIFEST_PATH}" = /* ]] || {
  echo "MANIFEST_PATH must be absolute" >&2
  exit 2
}
[[ -f "${MANIFEST_PATH}" ]] || {
  echo "Manifest file does not exist" >&2
  exit 2
}
command -v k6 >/dev/null || {
  echo "k6 is required" >&2
  exit 2
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd "${script_dir}/../.." && pwd)"
export PROFILE="${profile}"
exec k6 run "${repository_root}/tests/load/viewer.js"
