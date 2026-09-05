#!/usr/bin/env bash
set -Eeuo pipefail

EXPECTED_SHA="${1:?expected release SHA is required}"
MANIFEST_DIGEST="${2:?runtime manifest digest is required}"
RESTORE_NOT_AFTER="${3:?restore deadline is required}"
LIVE_DIR="${PATHLAB_LIVE_DIR:-/opt/pathlab-viewer}"
DEPLOY_LOCK_FILE="${PATHLAB_DEPLOY_LOCK_FILE:-/var/lock/pathlab-viewer-deploy.lock}"
COMMAND_KILL_SECONDS=5
CONTAINMENT_RESERVE_SECONDS=20
CONTAINMENT_PROBE_SECONDS=5
CONTAINMENT_PROBE_KILL_SECONDS=1
CONTAINMENT_STOP_SECONDS=10
CONTAINMENT_STOP_KILL_SECONDS=2
CONTAINMENT_SLACK_SECONDS=2

[[ "${EXPECTED_SHA}" =~ ^[0-9a-f]{40}$ ]] || exit 2
[[ "${MANIFEST_DIGEST}" =~ ^[0-9a-f]{64}$ ]] || exit 2
[[ "${RESTORE_NOT_AFTER}" =~ ^[0-9]{10}$ ]] || exit 2
if [[ "${LIVE_DIR}" != /opt/pathlab-viewer ]]; then
  [[ "${PATHLAB_CAPACITY_TEST_MODE:-}" == true ]] || exit 2
else
  [[ "${DEPLOY_LOCK_FILE}" == /var/lock/pathlab-viewer-deploy.lock ]] || exit 2
fi

remaining_seconds() {
  local remaining="$((RESTORE_NOT_AFTER - $(date +%s)))"
  (( remaining > 0 )) || { echo "capacity restore deadline elapsed" >&2; return 1; }
  printf '%s\n' "${remaining}"
}

run_bounded() {
  local remaining timeout_seconds
  remaining="$(remaining_seconds)" || return 1
  timeout_seconds="$((remaining - CONTAINMENT_RESERVE_SECONDS - COMMAND_KILL_SECONDS))"
  (( timeout_seconds > 0 )) || return 1
  timeout --signal=TERM --kill-after="${COMMAND_KILL_SECONDS}s" "${timeout_seconds}s" "$@"
}

run_containment_probe() {
  local available remaining timeout_seconds
  remaining="$(remaining_seconds)" || return 1
  available="$((remaining - CONTAINMENT_STOP_SECONDS - CONTAINMENT_STOP_KILL_SECONDS -
    CONTAINMENT_SLACK_SECONDS - CONTAINMENT_PROBE_KILL_SECONDS))"
  (( available > 0 )) || return 1
  timeout_seconds="${CONTAINMENT_PROBE_SECONDS}"
  (( timeout_seconds <= available )) || timeout_seconds="${available}"
  timeout --signal=TERM --kill-after="${CONTAINMENT_PROBE_KILL_SECONDS}s" \
    "${timeout_seconds}s" "$@"
}

run_containment_stop() {
  local available remaining timeout_seconds
  remaining="$(remaining_seconds)" || return 1
  available="$((remaining - CONTAINMENT_STOP_KILL_SECONDS - CONTAINMENT_SLACK_SECONDS))"
  (( available > 0 )) || return 1
  timeout_seconds="${CONTAINMENT_STOP_SECONDS}"
  (( timeout_seconds <= available )) || timeout_seconds="${available}"
  timeout --signal=TERM --kill-after="${CONTAINMENT_STOP_KILL_SECONDS}s" \
    "${timeout_seconds}s" "$@"
}

compose() {
  run_bounded bash "${LIVE_DIR}/deploy/scripts/compose-pathlab.sh" "$@"
}

contain_unsafe_runtime() {
  run_containment_stop bash "${LIVE_DIR}/deploy/scripts/compose-pathlab.sh" \
    stop api classroom >/dev/null 2>&1
}

restore_failed() {
  local result=$?
  trap - EXIT
  (( result != 0 )) || result=1
  if verify_runtime_binding containment; then
    if contain_unsafe_runtime; then
      echo "Capacity restoration failed; API and Classroom were stopped" >&2
    else
      echo "Capacity restoration failed; API and Classroom containment is unproved" >&2
    fi
  else
    echo "Capacity restoration failed; runtime binding changed before containment" >&2
  fi
  rm -f -- "${VERIFY_ERROR:-}" 2>/dev/null || true
  exit "${result}"
}

verify_runtime_binding() {
  local runner=run_bounded
  [[ "${1:-normal}" == containment ]] && runner=run_containment_probe
  "${runner}" python3 - "${LIVE_DIR}" "${EXPECTED_SHA}" "${MANIFEST_DIGEST}" <<'PY'
import hmac
import importlib.util
import os
import pathlib
import stat
import sys

live = pathlib.Path(sys.argv[1])
expected_sha, expected_digest = sys.argv[2:]
release_path = live / ".pathlab-release"
manifest_path = live / ".pathlab-runtime-safety.json"
validator_path = live / "deploy" / "scripts" / "runtime_safety_manifest.py"
try:
    release_info = release_path.lstat()
    if not stat.S_ISREG(release_info.st_mode) or not 40 <= release_info.st_size <= 41:
        raise ValueError("release marker is not regular")
    release_bytes = release_path.read_bytes()
    if release_bytes not in {expected_sha.encode(), (expected_sha + "\n").encode()}:
        raise ValueError("release marker does not match")
    manifest_info = manifest_path.lstat()
    if not stat.S_ISREG(manifest_info.st_mode) or not 1 <= manifest_info.st_size <= 65536:
        raise ValueError("manifest is not regular")
    if os.name == "posix" and stat.S_IMODE(manifest_info.st_mode) != 0o600:
        raise ValueError("manifest mode is unsafe")
    validator_info = validator_path.lstat()
    if not stat.S_ISREG(validator_info.st_mode) or not 1 <= validator_info.st_size <= 262144:
        raise ValueError("manifest validator is not regular")
    spec = importlib.util.spec_from_file_location("pathlab_runtime_safety", validator_path)
    if spec is None or spec.loader is None:
        raise ValueError("manifest validator cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    value = module.load_manifest(manifest_path)
    if value["releaseSha"] != expected_sha:
        raise ValueError("manifest release binding is invalid")
    if not hmac.compare_digest(value["manifestDigest"], expected_digest):
        raise ValueError("manifest digest binding is invalid")
except Exception as error:
    raise SystemExit(f"capacity restore runtime binding is invalid: {error}") from None
PY
}

# A controller from an older release may be stopped after a newer release has
# become live. Prove the exact current binding before arming containment so the
# old controller can never stop the newly selected runtime.
command -v flock >/dev/null || {
  echo "capacity restore requires the deployment lock" >&2
  exit 1
}
if [[ "${LIVE_DIR}" == /opt/pathlab-viewer ]]; then
  [[ -f "${DEPLOY_LOCK_FILE}" && ! -L "${DEPLOY_LOCK_FILE}" ]] || {
    echo "capacity restore deployment lock is unavailable or unsafe" >&2
    exit 1
  }
fi
exec {DEPLOY_LOCK_FD}<>"${DEPLOY_LOCK_FILE}"
python3 - "${DEPLOY_LOCK_FILE}" "/proc/$$/fd/${DEPLOY_LOCK_FD}" \
  "${LIVE_DIR}" <<'PY' || {
import os
import pathlib
import stat
import sys

path = pathlib.Path(sys.argv[1])
try:
    expected = path.lstat()
    if os.name == "posix":
        inherited = os.stat(sys.argv[2])
        valid = (
            stat.S_ISREG(expected.st_mode)
            and expected.st_mode & 0o022 == 0
            and (expected.st_dev, expected.st_ino) == (inherited.st_dev, inherited.st_ino)
            and (sys.argv[3] != "/opt/pathlab-viewer" or expected.st_uid == 0)
        )
    else:
        valid = sys.argv[3] != "/opt/pathlab-viewer" and stat.S_ISREG(expected.st_mode)
except OSError:
    valid = False
raise SystemExit(0 if valid else 1)
PY
  echo "capacity restore deployment lock is unavailable or unsafe" >&2
  exit 1
}
flock --exclusive --nonblock "${DEPLOY_LOCK_FD}" || {
  echo "capacity restore refused while a deployment or another restore is active" >&2
  exit 1
}
verify_runtime_binding || exit 1
VERIFY_ERROR="$(mktemp)"
chmod 600 "${VERIFY_ERROR}"
trap restore_failed EXIT

run_bounded python3 - "${LIVE_DIR}/deploy/.env" <<'PY'
import os
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
updates = {
    "PATHLAB_PRODUCTION_CLASSROOM_ENABLED": "true",
    "PATHLAB_CLASSROOM_MAX_PARTICIPANTS": "300",
    "PATHLAB_ANNOTATIONS_ENABLED": "false",
}
seen = set()
lines = []
for line in path.read_text(encoding="utf-8").splitlines():
    name = line.split("=", 1)[0] if "=" in line else ""
    if name in updates:
        if name not in seen:
            lines.append(f"{name}={updates[name]}")
            seen.add(name)
    else:
        lines.append(line)
for name, value in updates.items():
    if name not in seen:
        lines.append(f"{name}={value}")
temporary = path.with_suffix(path.suffix + ".capacity-restore")
temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
temporary.chmod(path.stat().st_mode & 0o777)
os.replace(temporary, path)
PY

compose up -d >/dev/null
run_bounded bash "${LIVE_DIR}/deploy/scripts/install-watchdog.sh" install "${LIVE_DIR}" >/dev/null

status=""
verified=false
while remaining="$(remaining_seconds)"; do
  (( remaining > CONTAINMENT_RESERVE_SECONDS + 2 )) || break
  : > "${VERIFY_ERROR}"
  if status="$(run_bounded python3 "${LIVE_DIR}/deploy/scripts/runtime_safety_manifest.py" \
      verify-live --live-dir "${LIVE_DIR}" --expected-sha "${EXPECTED_SHA}" \
      --manifest-digest "${MANIFEST_DIGEST}" --require-safe 2>"${VERIFY_ERROR}")"; then
    verified=true
    break
  fi
  sleep 2
done
if [[ "${verified}" != true || -z "${status}" ]]; then
  if [[ -s "${VERIFY_ERROR}" ]]; then
    echo "Last capacity runtime verification error:" >&2
    sanitized="$(tail -c 4096 "${VERIFY_ERROR}" | LC_ALL=C tr -cd '\11\12\40-\176' | tail -c 2048 || true)"
    printf '%s\n' "${sanitized}" >&2
  fi
  exit 1
fi
trap - EXIT
rm -f -- "${VERIFY_ERROR}"
printf '%s\n' "${status}"
