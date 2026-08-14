#!/usr/bin/env bash
set -Eeuo pipefail
EXPECTED_CANDIDATE="${1:?candidate SHA required}"
ROLLBACK_SHA="${2:?rollback SHA required}"
LIVE_DIR=/opt/pathlab-viewer
[[ "${EXPECTED_CANDIDATE}" =~ ^[0-9a-f]{40}$ && "${ROLLBACK_SHA}" =~ ^[0-9a-f]{40}$ ]] || exit 1
[[ "$(cat "${LIVE_DIR}/.pathlab-release")" == "${EXPECTED_CANDIDATE}" ]] || exit 1
mapfile -t candidates < <(find /opt -maxdepth 1 -type d \
  -name "pathlab-viewer.rollback-${ROLLBACK_SHA:0:12}-*" -print | sort)
[[ "${#candidates[@]}" -ge 1 ]] || exit 1
rollback_dir="${candidates[${#candidates[@]}-1]}"
[[ "$(cat "${rollback_dir}/.pathlab-release")" == "${ROLLBACK_SHA}" ]] || exit 1
failed="/opt/pathlab-viewer.failed-${EXPECTED_CANDIDATE}-$(date -u +%Y%m%dT%H%M%SZ)"
( bash "${LIVE_DIR}/deploy/scripts/install-watchdog.sh" uninstall "${LIVE_DIR}" ) >/dev/null
( cd "${LIVE_DIR}/deploy" && docker compose down ) >/dev/null
mv -- "${LIVE_DIR}" "${failed}"
mv -- "${rollback_dir}" "${LIVE_DIR}"
python3 - "${LIVE_DIR}/deploy/.env" <<'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
lines = path.read_text().splitlines()
key = "PATHLAB_CLASSROOM_MAX_PARTICIPANTS="
updated = [f"{key}300" if line.startswith(key) else line for line in lines]
if not any(line.startswith(key) for line in lines):
    updated.append(f"{key}300")
temporary = path.with_suffix(".tmp")
temporary.write_text("\n".join(updated) + "\n")
temporary.chmod(path.stat().st_mode & 0o777)
temporary.replace(path)
PY
( cd "${LIVE_DIR}/deploy" && docker compose up -d ) >/dev/null
[[ "$(cat "${LIVE_DIR}/.pathlab-release")" == "${ROLLBACK_SHA}" ]]
grep -qx 'PATHLAB_CLASSROOM_MAX_PARTICIPANTS=300' "${LIVE_DIR}/deploy/.env"
cd "${LIVE_DIR}/deploy"
services="$(docker compose ps --services --status running | sort)"
expected_services=$'api\ncaddy\ntile-service\ntusd\nworker'
limit="$(awk -F= '/^PATHLAB_CLASSROOM_MAX_PARTICIPANTS=/{print $2; exit}' .env)"
ready=false
for _ in $(seq 1 30); do
  if curl --fail --silent --insecure --max-time 5 https://127.0.0.1/readyz >/dev/null && \
    curl --fail --silent --insecure --max-time 5 https://127.0.0.1/livez >/dev/null; then
    ready=true
    break
  fi
  sleep 2
done
watchdog=false; systemctl is-active --quiet pathlab-viewer-watchdog.timer && watchdog=true
jq -n --arg release "${ROLLBACK_SHA}" --arg expected "${ROLLBACK_SHA}" \
  --argjson ready "${ready}" --argjson watchdog "${watchdog}" --argjson capacity "${limit:-0}" \
  --argjson exact "$([[ "${services}" == "${expected_services}" ]] && echo true || echo false)" \
  '{releaseSha:$release,expectedSha:$expected,releaseExact:true,servicesExact:$exact,
    serviceCount:5,ready:$ready,watchdogExpected:false,watchdogActive:$watchdog,finalCapacity:$capacity}'
