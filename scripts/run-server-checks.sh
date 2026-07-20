#!/usr/bin/env bash
set -euo pipefail

pytest tests/backend
ruff check server tests migrations
mypy server/wsi_viewer

if [[ "${1:-}" == "--all" ]]; then
  pnpm --dir apps/web lint
  pnpm --dir apps/web test
  pnpm --dir apps/web build
  docker compose -f deploy/compose.yaml config
fi
