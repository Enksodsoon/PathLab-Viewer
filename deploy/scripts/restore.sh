#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

if [[ "${1:-}" != "--confirm" || -z "${2:-}" ]]; then
  echo "Usage: restore.sh --confirm /absolute/path/to/pathlab-backup" >&2
  exit 2
fi

backup_dir="$(realpath "${2}")"
data_dir="$(realpath -m "${PATHLAB_DATA_DIR:-/srv/pathlab/data}")"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
compose_file="${script_dir%/scripts}/compose.yaml"
case "${data_dir}" in
  /srv/pathlab/data|/mnt/pathlab/data) ;;
  *) echo "Refusing unexpected data directory: ${data_dir}" >&2; exit 3 ;;
esac

test -d "${backup_dir}"
test -f "${compose_file}"
test -f "${backup_dir}/database/pathlab.sqlite3"
test -f "${backup_dir}/files.tar.gz"
test -f "${backup_dir}/SHA256SUMS"
(cd "${backup_dir}" && sha256sum --strict --check SHA256SUMS)

archive="${backup_dir}/files.tar.gz"
while IFS= read -r entry; do
  case "/${entry}/" in
    *"/../"*|"//"*|*"//"*)
      echo "Refusing unsafe archive entry: ${entry}" >&2
      exit 4
      ;;
  esac
  case "${entry}" in
    originals|originals/*|private|private/*|public|public/*) ;;
    *)
      echo "Refusing unsafe archive entry: ${entry}" >&2
      exit 4
      ;;
  esac
done < <(tar --list --gzip --file "${archive}")

python3 - "${archive}" <<'PY'
import sys
import tarfile
from pathlib import PurePosixPath

archive = sys.argv[1]
allowed_roots = {"originals", "private", "public"}
with tarfile.open(archive, mode="r:gz") as source:
    for member in source.getmembers():
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise SystemExit(f"Refusing unsafe archive entry: {member.name}")
        if not path.parts or path.parts[0] not in allowed_roots:
            raise SystemExit(f"Refusing unsafe archive entry: {member.name}")
        if not (member.isdir() or member.isfile()):
            raise SystemExit(f"Refusing unsafe archive entry type: {member.name}")
PY

docker compose -f "${compose_file}" stop api worker tusd caddy
recovery="${data_dir}.before-restore-$(date -u +%Y%m%dT%H%M%SZ)"
test ! -e "${recovery}"
restore_started=0
rollback_restore() {
  local exit_code=$?
  trap - ERR
  if [[ "${restore_started}" -eq 1 && -d "${recovery}" ]]; then
    rm -rf -- "${data_dir}"
    mv -- "${recovery}" "${data_dir}"
    docker compose -f "${compose_file}" up -d >/dev/null 2>&1 || true
  fi
  exit "${exit_code}"
}
trap rollback_restore ERR

mv -- "${data_dir}" "${recovery}"
restore_started=1
install -d -m 700 "${data_dir}/database"
install -m 600 "${backup_dir}/database/pathlab.sqlite3" \
  "${data_dir}/database/pathlab.sqlite3"
tar --extract --gzip --file "${archive}" --directory "${data_dir}" \
  --no-same-owner --no-same-permissions --delay-directory-restore
chown -R 10001:10001 "${data_dir}"
docker compose -f "${compose_file}" up -d
trap - ERR
restore_started=0
echo "Restored. Previous data remains at ${recovery}"
