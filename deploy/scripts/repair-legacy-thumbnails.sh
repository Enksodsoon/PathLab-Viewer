#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd "$(dirname "$0")" && pwd)"
compose() { bash "$script_dir/compose-pathlab.sh" "$@"; }
# This operation must not race publication, workers, or learner delivery.
running="$(compose ps --status running --services)"
while IFS= read -r service; do
  [[ -z "$service" || "$service" == postgres ]] || {
    echo "Stop application services before thumbnail maintenance: $service is running" >&2
    exit 1
  }
done <<< "$running"
compose run --rm --no-deps api pathlab-admin reconcile-storage --repair-missing-thumbnails
