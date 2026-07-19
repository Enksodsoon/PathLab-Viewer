# Repository map

Use this page to find the right place to change something.

## Top level

| Path | Purpose |
|---|---|
| `apps/web` | React/TypeScript admin and public viewer SPA |
| `server/wsi_viewer` | FastAPI API, auth, database, storage, OME validation, conversion, and worker |
| `migrations` | Alembic database migrations |
| `deploy` | Docker Compose, Caddy, systemd, Terraform, DNS, backup, and restore assets |
| `tests/backend` | Backend and worker contract tests |
| `tests/load` | k6 viewer-load scenario |
| `docs/evidence` | QA ledger and browser/real-file evidence |
| `docs/design` | Design references and visual assets |
| `docs/superpowers` | Implementation plans and specifications |

## Where to change what

- Upload behavior, admission, tus callbacks: `server/wsi_viewer/api.py`, `storage.py`, and `worker.py`.
- OME acceptance or stable error codes: `server/wsi_viewer/ome.py` and `tests/backend/test_ome.py`.
- DZI/JPEG conversion: `server/wsi_viewer/conversion.py` and conversion tests.
- Login, sessions, CSRF, password change/recovery: `server/wsi_viewer/security.py`, auth routes, and `apps/web/src` security components.
- Slide state transitions and publication: domain/API modules plus `storage.py`.
- Admin layout and upload progress: `apps/web/src` admin components and styles.
- Public OpenSeadragon viewer: `apps/web/src` viewer route/components.
- OCI service topology: `deploy/compose.yaml`, `deploy/Caddyfile`, and `deploy/terraform`.
- Backups and recovery: `deploy/scripts` and `deploy/README.md`.

## Command matrix

| Need | Command |
|---|---|
| Backend tests | `pytest tests/backend` |
| Python lint | `ruff check server tests migrations` |
| Python types | `mypy server/wsi_viewer` |
| Web lint/test/build | `pnpm --dir apps/web lint`, `test`, `build` |
| Compose validation | `docker compose -f deploy/compose.yaml config` |
| Local admin | `http://127.0.0.1:5173/admin` |
| Public local route | `http://127.0.0.1:5173/s/{publicId}` |

## Documentation index

- [`README.md`](../README.md): quick orientation and local commands.
- [`PROJECT_GUIDE.md`](PROJECT_GUIDE.md): full plain-language handoff and current status.
- [`CONTRIBUTING.md`](../CONTRIBUTING.md): branch, test, commit, and PR rules.
- [`evidence/QA.md`](evidence/QA.md): evidence ledger, screenshots, and remaining gates.
- [`../deploy/README.md`](../deploy/README.md): OCI operations, password recovery, backup, and restore.
- [`superpowers/plans`](superpowers/plans): implementation history.

## Change flow

Work from a `codex/*` branch, make the smallest focused change, add or update a failing test first when behavior changes, run the relevant checks, and open/update the draft PR. Keep `main` unchanged until the owner explicitly merges it. Never commit secrets, source slides, recovery codes, generated tile trees, or local databases.
