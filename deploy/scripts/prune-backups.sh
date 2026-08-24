#!/usr/bin/env bash
set -euo pipefail

backup_dir="${1:?backup directory is required}"
retention_count="${2:-5}"

[[ "$retention_count" =~ ^[1-9][0-9]*$ ]] || {
  echo "Backup retention count must be a positive integer" >&2
  exit 1
}
backup_root="$(readlink -f -- "$backup_dir")"
test -d "$backup_root"

valid_backups=()
while IFS= read -r name; do
  [[ "$name" =~ ^pathlab-[0-9]{8}T[0-9]{6}Z$ ]] || continue
  candidate="${backup_root}/${name}"
  [[ -d "$candidate" && ! -L "$candidate" ]] || continue
  resolved="$(readlink -f -- "$candidate")"
  [[ "$(dirname "$resolved")" == "$backup_root" ]] || continue
  [[ -f "$resolved/database/pathlab.sqlite3" && -f "$resolved/files.tar.gz" && -f "$resolved/SHA256SUMS" ]] || continue
  if (cd "$resolved" && sha256sum --check --status SHA256SUMS); then
    valid_backups+=("$resolved")
  fi
done < <(find -P "$backup_root" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | LC_ALL=C sort -r)

for ((index = retention_count; index < ${#valid_backups[@]}; index++)); do
  candidate="${valid_backups[$index]}"
  [[ "$(dirname "$candidate")" == "$backup_root" ]] || {
    echo "Refusing to prune a backup outside the configured backup directory" >&2
    exit 1
  }
  rm -rf -- "$candidate"
done
