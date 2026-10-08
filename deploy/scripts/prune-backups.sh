#!/usr/bin/env bash
set -euo pipefail

backup_dir="${1:?backup directory is required}"
retention_count="${2:-5}"
engine="${3:-sqlite}"
script_dir="$(cd "$(dirname "$0")" && pwd)"
case "$engine" in
  sqlite) pattern='^pathlab-[0-9]{8}T[0-9]{6}Z$'; database=pathlab.sqlite3 ;;
  postgres)
    pattern='^pathlab-postgres-[0-9]{8}T[0-9]{6}Z$'
    database=pathlab.dump
    test -n "${PATHLAB_BACKUP_SIGNING_KEY:-}" || {
      echo "PostgreSQL retention requires the backup signing key" >&2
      exit 2
    }
    ;;
  *) echo "Unsupported backup engine" >&2; exit 2 ;;
esac

[[ "$retention_count" =~ ^[1-9][0-9]*$ ]] || {
  echo "Backup retention count must be a positive integer" >&2
  exit 1
}
backup_root="$(readlink -f -- "$backup_dir")"
test -d "$backup_root"

valid_count=0
while IFS= read -r name; do
  [[ "$name" =~ $pattern ]] || continue
  candidate="${backup_root}/${name}"
  [[ -d "$candidate" && ! -L "$candidate" ]] || continue
  resolved="$(readlink -f -- "$candidate")"
  [[ "$(dirname "$resolved")" == "$backup_root" ]] || continue
  [[ -f "$resolved/database/$database" && -f "$resolved/files.tar.gz" && -f "$resolved/SHA256SUMS" ]] || continue
  if [[ "$engine" == postgres ]]; then
    "${PATHLAB_PYTHON_COMMAND:-python3}" "$script_dir/postgres_backup_manifest.py" verify-retention "$resolved" >/dev/null || continue
  else
    (cd "$resolved" && sha256sum --check --status SHA256SUMS) || continue
  fi
  valid_count=$((valid_count + 1))
  if (( valid_count <= retention_count )); then
    echo "Retained verified backup: $name" >&2
    continue
  fi
  [[ "$(dirname "$resolved")" == "$backup_root" ]] || {
    echo "Refusing to prune a backup outside the configured backup directory" >&2
    exit 1
  }
  rm -rf -- "$resolved"
  echo "Pruned verified backup: $name" >&2
done < <(find -P "$backup_root" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | LC_ALL=C sort -r)
