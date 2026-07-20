# PathLab Viewer Agent Guide

## Purpose

PathLab Viewer is a private-first pathology whole-slide web viewer. The current production path accepts OME-TIFF, validates it, generates Deep Zoom JPEG tiles with libvips, and serves private previews and unlisted public links. The next product path accepts a locally prepared `.plslide` package so the server does not decode or convert the original WSI.

## Start here

Read only the documents needed for the active task:

1. `docs/plans/active/current.md`
2. The files explicitly linked by that task
3. `docs/architecture/PATHLAB_PREP_SYSTEM.md` only when architectural context is needed
4. `docs/compatibility/PREPARED_SLIDE_V1.md` for the package contract
5. `docs/PROJECT_GUIDE.md` and `docs/REPOSITORY_MAP.md` for the existing application

Do not read every future plan before starting a focused task.

## Repository map

- API, domain, database, storage and workers: `server/wsi_viewer/`
- Existing OME validation: `server/wsi_viewer/ome.py`
- Existing DZI conversion: `server/wsi_viewer/conversion.py`
- Existing upload and admin API: `server/wsi_viewer/api.py`
- Existing storage/publication: `server/wsi_viewer/storage.py`
- Database migrations: `migrations/`
- Backend tests: `tests/backend/`
- Web application: `apps/web/`
- Deployment: `deploy/`
- Prepared-slide contracts: `contracts/`
- Active Codex plan: `docs/plans/active/current.md`

## Working rules

- Work on exactly one task from the active plan.
- Do not implement later tasks or unrelated improvements.
- Use a `codex/` branch created from current `main`.
- Use test-driven development for behavior changes: failing test, minimal implementation, passing test.
- Preserve the legacy OME-TIFF path until the prepared-package workflow is validated end to end.
- Treat all uploaded archives and metadata as hostile.
- Use stable machine-readable error codes.
- Keep modules focused; avoid adding more unrelated responsibility to `api.py` or `worker.py`.
- Use atomic staging and rename for file operations.
- Never expose originals, upload staging paths, filesystem paths, credentials or tokens publicly.
- Do not weaken authentication, HTTPS, checksum or archive-validation rules for older clients.

## Prohibited commits

Never commit:

- Patient or source WSI files (`.vsi`, `.ets`, `.svs`, `.ndpi`, `.mrxs`, `.scn`, `.czi`, `.oir`)
- Generated OME-TIFF files
- Generated DZI tile trees
- `.plslide` output packages except tiny deterministic synthetic test fixtures
- Databases, secrets, `.env` files, tokens or recovery codes
- Local build outputs, caches or installer artifacts

## Verification

Run focused tests while implementing. Before committing backend changes run:

```bash
pytest tests/backend
ruff check server tests migrations
mypy server/wsi_viewer
```

Run these only when the relevant areas changed:

```bash
pnpm --dir apps/web lint
pnpm --dir apps/web test
pnpm --dir apps/web build
docker compose -f deploy/compose.yaml config
```

The convenience command is:

```bash
bash scripts/run-server-checks.sh
```

## Completion report

Every task must end with:

```text
TASK RESULT
- Task:
- Branch:
- Commit:
- Files changed:
- Focused tests:
- Full checks:
- Evidence:
- Known limitations:
- Next task:
```

Commit the completed task and stop. Do not start the next task automatically.

## Product boundaries

This work is limited to local WSI preparation, batch conversion, RGB OME-TIFF, DZI generation, prepared-package upload, lightweight server import and static viewing. Do not add AI diagnosis, annotations, collaboration, fluorescence analysis, Z-stack navigation, DICOM WSI, PACS integration or automatic public publication.