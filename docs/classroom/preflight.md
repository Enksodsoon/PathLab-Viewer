# PathLab Classroom preflight

## Baseline

- Base ref: `origin/main`
- Base SHA: `ec97febbb9706f4b1109ba8fa45c3f807b3ff510`
- Worktree: isolated `codex/lightweight-classroom` branch
- Existing checkout changes: not imported

Baseline verification on 2026-08-11:

- Backend: 428 passed, 4 skipped
- Frontend: 226 passed
- Ruff: passed
- mypy: passed
- ESLint: passed
- production web build: passed
- Docker Compose configuration: passed with non-production placeholder environment values

Baseline web build sizes relevant to the classroom budget:

- HTML-linked application chunk: 222.31 kB raw / 70.88 kB gzip
- OpenSeadragon lazy chunk: 356.53 kB raw / 90.72 kB gzip
- Shared viewer page: 6.58 kB raw / 2.47 kB gzip
- Shared viewer CSS: 7.38 kB raw / 1.95 kB gzip

## Existing runtime contracts

- Production Compose starts one Uvicorn process with `--workers 1`.
- Compose defines one API service and no horizontal replica pool.
- Caddy serves static DZI bodies without routing them through FastAPI.
- SQLite connections enable WAL, foreign keys, and a 5,000 ms busy timeout.
- The database is stored under the local `/data/database` volume contract.
- The API uses synchronous SQLAlchemy sessions; SSE generators must never retain one.
- Current slides record source SHA-256, derivative bytes/file count, and render mode.
- Current slides do not have an immutable published-DZI asset identifier or manifest hash.

## Mandatory implementation safeguards

- Classroom remains disabled by default.
- In-process hub requires one API process and a lifetime-held singleton lock.
- No Redis, WebSocket server, polling loop, new worker, or scheduled cleanup service.
- Session creation pins the existing immutable publication version and validates its bounded DZI descriptor; it never scans or copies a tile tree.
- Missing, dynamic, unpublished, dimension-mismatched, or incomplete descriptor roots are not classroom-ready.
- Screenshot support remains unavailable until the browser spike passes with a non-PHI DZI produced by the current pipeline.

## Evidence boundary

This file records a local development baseline. It is not production capacity,
deployment, security certification, or authorization to enable the feature.
