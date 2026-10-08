#!/usr/bin/env bash
set -euo pipefail
umask 077

# Operator-installed outside release checkouts so retention survives deployments.
script_dir="$(cd "$(dirname "$0")" && pwd)"
exec 8>/var/lock/pathlab-viewer-deploy.lock
flock -n -E 75 8 || exit 75
source "$script_dir/backup-lock.sh"
key=/etc/pathlab-viewer/postgres/backup-signing-key
[[ -f "$key" && ! -L "$key" ]] || exit 2
export PATHLAB_BACKUP_SIGNING_KEY="$(cat "$key")"
nice -n 10 ionice -c 2 -n 7 bash "$script_dir/prune-backups.sh" /srv/pathlab/data/backups 5 postgres
docker builder prune --all --force --filter until=24h --keep-storage 2GB
