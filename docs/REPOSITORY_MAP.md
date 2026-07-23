# Repository Map

Use this guide to locate the code, documentation, tests, and operational assets responsible for a change.

## Top-level structure

| Path | Responsibility |
|---|---|
| `apps/web` | React and TypeScript administration interface and public viewer |
| `server/wsi_viewer` | FastAPI application, authentication, persistence, storage, validation, conversion, and worker |
| `migrations` | Alembic database migrations |
| `deploy` | Docker Compose, Caddy, systemd, Terraform, DNS, backup, restore, and release assets |
| `tests/backend` | Backend, worker, security, storage, API, and deployment-contract tests |
| `tests/load` | k6 public-viewer load scenario |
| `docs/architecture` | Durable processing and security design references |
| `docs/design` | Visual references and design assets |
| `docs/evidence` | QA ledger, browser evidence, real-file verification, and unresolved acceptance gates |
| `.github/workflows` | Continuous integration and deployment workflows |

## Common change locations

| Change | Primary files |
|---|---|
| Upload admission, tus callbacks, and finalization | `server/wsi_viewer/api.py`, `storage.py`, `worker.py` |
| OME-TIFF acceptance and stable failure codes | `server/wsi_viewer/ome.py`, `tests/backend/test_ome.py` |
| DZI and JPEG conversion | `server/wsi_viewer/conversion.py`, conversion tests |
| Authentication, sessions, CSRF, password change, and recovery | `server/wsi_viewer/auth.py`, `security.py`, API routes, `apps/web/src/components/AuthPanels.tsx` |
| Slide state transitions and publication | domain and API modules plus `server/wsi_viewer/storage.py` |
| Admin layout, uploads, and slide actions | `apps/web/src/pages/AdminPage.tsx`, components, tests, and `styles.css` |
| Public OpenSeadragon viewer | `apps/web/src/pages/ViewerPage.tsx`, `components/OpenSeadragonViewer.tsx` |
| OCI service topology | `deploy/compose.yaml`, `deploy/Caddyfile`, `deploy/terraform` |
| Backups and recovery | `deploy/scripts`, `deploy/README.md` |
| Continuous integration | `.github/workflows/ci.yml` |

## Documentation index

- [`../README.md`](../README.md): project overview, supported contract, setup, and verification commands.
- [`PROJECT_GUIDE.md`](PROJECT_GUIDE.md): product scope, architecture, lifecycle, and operational boundaries.
- [`architecture/OME_TIFF_PIPELINE.md`](architecture/OME_TIFF_PIPELINE.md): input validation, processing, publication, and privacy architecture.
- [`architecture/PASSWORD_RECOVERY.md`](architecture/PASSWORD_RECOVERY.md): administrator credential lifecycle and abuse controls.
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md): branch, testing, review, documentation, and privacy standards.
- [`evidence/QA.md`](evidence/QA.md): current verification results and unresolved evidence gates.
- [`../deploy/README.md`](../deploy/README.md): deployment, update, password recovery, backup, and restore operations.

## Command matrix

| Purpose | Command |
|---|---|
| Backend tests | `pytest tests/backend` |
| Python lint | `ruff check server tests migrations` |
| Python type checking | `mypy server/wsi_viewer` |
| Web lint | `pnpm --dir apps/web lint` |
| Web tests | `pnpm --dir apps/web test` |
| Web production build | `pnpm --dir apps/web build` |
| Compose validation | `docker compose -f deploy/compose.yaml config` |
| Local administration | `http://127.0.0.1:5173/admin` |
| Local public route | `http://127.0.0.1:5173/s/{publicId}` |

## Change flow

1. Create a focused branch from the current default branch.
2. Add a failing regression test before a behavior fix or feature.
3. Make the smallest implementation that satisfies the contract.
4. Run the relevant checks and review the diff for secrets or stale documentation.
5. Open a draft pull request and document deployment or acceptance impact.
6. Merge only after review and required verification are complete.

Never commit credentials, recovery codes, source slides, generated tile trees, databases, patient information, private prompts, conversation transcripts, or internal agent instructions.
