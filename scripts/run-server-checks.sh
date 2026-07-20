#!/usr/bin/env bash
set -euo pipefail

pytest tests/backend
ruff check server tests migrations
mypy server/wsi_viewer

if [[ "${PATHLAB_CHECK_WEB:-0}" == "1" ]]; then
  pnpm --dir apps/web lint
  pnpm --dir apps/web test
  pnpm --dir apps/web build
fi

if [[ "${PATHLAB_CHECK_COMPOSE:-0}" == "1" ]]; then
  docker compose -f deploy/compose.yaml config
fi
