#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ "${PATHLAB_CUTOVER_ENVIRONMENT:-}" != "staging" ]]; then
  echo "PostgreSQL cutover evidence is staging-only" >&2
  exit 2
fi
if [[ -z "${1:-}" || "${1:-}" != /* || -z "${2:-}" || "${2:-}" != /* ]]; then
  echo "Usage: verify-postgres-cutover.sh /absolute/source.sqlite3 /absolute/status.json" >&2
  exit 2
fi

source_database="$1"
status_file="$2"
target_url="${PATHLAB_POSTGRES_TARGET_URL:?PATHLAB_POSTGRES_TARGET_URL is required}"
password_file="${PATHLAB_POSTGRES_PASSWORD_FILE:?PATHLAB_POSTGRES_PASSWORD_FILE is required}"
release_sha="${PATHLAB_RELEASE_SHA:?PATHLAB_RELEASE_SHA is required}"
evidence_dir="${PATHLAB_CUTOVER_EVIDENCE_DIR:?PATHLAB_CUTOVER_EVIDENCE_DIR is required}"
admin_command="${PATHLAB_ADMIN_COMMAND:-pathlab-admin}"
python_command="${PATHLAB_PYTHON_COMMAND:-python3}"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

[[ "$release_sha" =~ ^[0-9a-f]{40}$ ]] || {
  echo "PATHLAB_RELEASE_SHA must be an exact lowercase release SHA" >&2
  exit 2
}
[[ "$target_url" == postgresql+psycopg://* ]] || {
  echo "PATHLAB_POSTGRES_TARGET_URL must use PostgreSQL with Psycopg 3" >&2
  exit 2
}
[[ "$target_url" =~ ^postgresql\+psycopg://[A-Za-z_][A-Za-z0-9_]*@ ]] || {
  echo "PATHLAB_POSTGRES_TARGET_URL must contain a username and no password" >&2
  exit 2
}
test -f "$source_database"
test -f "$password_file"
install -d -m 700 "$evidence_dir" "$(dirname "$status_file")"

job_id="postgres-cutover-${release_sha:0:12}"
migration_manifest="${evidence_dir}/migration-manifest.json"
source_manifest="${evidence_dir}/source-check.json"
restore_manifest="${evidence_dir}/restore-result.json"
log_file="${evidence_dir}/cutover.log"
temporary_status="${status_file}.partial"
state="FAILED_TERMINAL"
failure_code="CUTOVER_FAILED"
backup_path=""

write_status() {
  PATHLAB_STATUS_STATE="$state" \
  PATHLAB_STATUS_FAILURE="$failure_code" \
  PATHLAB_STATUS_FINISHED="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  PATHLAB_STATUS_JOB_ID="$job_id" \
  PATHLAB_STATUS_STARTED="$started_at" \
  PATHLAB_STATUS_RELEASE="$release_sha" \
  PATHLAB_STATUS_MIGRATION="$migration_manifest" \
  PATHLAB_STATUS_SOURCE="$source_manifest" \
  PATHLAB_STATUS_BACKUP="$backup_path" \
  PATHLAB_STATUS_RESTORE="$restore_manifest" \
  PATHLAB_STATUS_LOG="$log_file" \
  "$python_command" - "$temporary_status" <<'PY'
import json
import os
import sys

payload = {
    "jobId": os.environ["PATHLAB_STATUS_JOB_ID"],
    "kind": "postgres-cutover-evidence",
    "state": os.environ["PATHLAB_STATUS_STATE"],
    "releaseSha": os.environ["PATHLAB_STATUS_RELEASE"],
    "startedAt": os.environ["PATHLAB_STATUS_STARTED"],
    "finishedAt": os.environ["PATHLAB_STATUS_FINISHED"],
    "attempt": 1,
    "progressCounters": {
        "sourceChecks": 1 if os.path.isfile(os.environ["PATHLAB_STATUS_SOURCE"]) else 0,
        "migrations": 1 if os.path.isfile(os.environ["PATHLAB_STATUS_MIGRATION"]) else 0,
        "backups": 1 if os.environ["PATHLAB_STATUS_BACKUP"] else 0,
        "restoreDrills": 1 if os.path.isfile(os.environ["PATHLAB_STATUS_RESTORE"]) else 0,
    },
    "resultManifest": {
        "source": os.environ["PATHLAB_STATUS_SOURCE"],
        "migration": os.environ["PATHLAB_STATUS_MIGRATION"],
        "backup": os.environ["PATHLAB_STATUS_BACKUP"],
        "restore": os.environ["PATHLAB_STATUS_RESTORE"],
    },
    "failureCode": os.environ["PATHLAB_STATUS_FAILURE"] or None,
    "logPath": os.environ["PATHLAB_STATUS_LOG"],
}
with open(sys.argv[1], "w", encoding="utf-8") as output:
    json.dump(payload, output, sort_keys=True, separators=(",", ":"))
    output.write("\n")
PY
  mv "$temporary_status" "$status_file"
}

on_exit() {
  exit_code=$?
  if [[ "$exit_code" -ne 0 ]]; then
    write_status
  fi
}
trap on_exit EXIT

exec > >(tee -a "$log_file") 2>&1

"$admin_command" postgres-cutover-source-check \
  --source "$source_database" > "$source_manifest"
"$admin_command" migrate-sqlite-to-postgres \
  --source "$source_database" \
  --target "$target_url" \
  --target-password-file "$password_file" \
  --manifest "$migration_manifest" \
  --verify

PATHLAB_DATABASE_URL="$target_url" \
PATHLAB_DATABASE_PASSWORD_FILE="$password_file" \
  "$admin_command" deployment-check

backup_path="$(bash "$(dirname "$0")/backup-postgres.sh")"
bash "$(dirname "$0")/verify-postgres-restore-drill.sh" "$backup_path" \
  > "$restore_manifest"

state="SUCCEEDED"
failure_code=""
write_status
trap - EXIT
printf '%s\n' "$status_file"
