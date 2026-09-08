#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd "$(dirname "$0")" && pwd)"
release_file="${script_dir}/../../.pathlab-release"
[[ -f "$release_file" && ! -L "$release_file" ]] || {
  echo "A deployed release marker is required for thumbnail maintenance" >&2
  exit 1
}
PATHLAB_RELEASE_IMAGE_TAG="$(cat "$release_file")"
[[ "$PATHLAB_RELEASE_IMAGE_TAG" =~ ^[0-9a-f]{40}$ ]] || exit 1
export PATHLAB_RELEASE_IMAGE_TAG
compose() { bash "$script_dir/compose-pathlab.sh" "$@"; }
# This operation must not race publication, workers, or learner delivery.
running="$(compose ps --status running --services)"
while IFS= read -r service; do
  [[ -z "$service" || "$service" == postgres ]] || {
    echo "Stop application services before thumbnail maintenance: $service is running" >&2
    exit 1
  }
done <<< "$running"
compose run --rm --no-deps --pull never api pathlab-admin reconcile-storage --repair-missing-thumbnails
