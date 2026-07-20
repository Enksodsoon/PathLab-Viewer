# PathLab Viewer Agent Guide

## Purpose

PathLab Viewer is the lightweight server and browser half of the PathLab ecosystem. PathLab Forge is a separate Windows/macOS desktop application that reads, crops, downscales, renders and batch-converts WSI files locally. The two products communicate only through a versioned HTTPS API, resumable tus upload and the `.plslide` prepared-slide package.

This repository must remain focused on server responsibilities:

- authenticate administrators and approved desktop clients;
- reserve upload space;
- receive `.plslide` packages through tus;
- verify checksums and package safety;
- import validated DZI assets without WSI conversion;
- provide private preview, publish/unpublish and static tile delivery;
- retain the legacy OME-TIFF ingestion path until migration evidence is complete.

Desktop conversion, QuPath, Bio-Formats, OpenSlide, Windows installers and macOS installers belong in the separate `PathLab-Forge` repository.

## Start here

Read only what the active task needs:

1. `docs/plans/active/current.md`
2. files explicitly listed by that task
3. `docs/compatibility/PREPARED_SLIDE_V1.md` for the package contract
4. `docs/architecture/PATHLAB_FORGE_INTEGRATION.md` for the boundary between repositories
5. existing `docs/PROJECT_GUIDE.md` and `docs/REPOSITORY_MAP.md` when current server behavior is relevant

Do not preload the whole roadmap or implement later tasks.

## Repository map

- API, domain, database, storage and workers: `server/wsi_viewer/`
- Existing OME validation: `server/wsi_viewer/ome.py`
- Existing DZI conversion: `server/wsi_viewer/conversion.py`
- Existing upload/admin routes: `server/wsi_viewer/api.py`
- Existing publication/storage: `server/wsi_viewer/storage.py`
- Database migrations: `migrations/`
- Backend tests: `tests/backend/`
- Web application: `apps/web/`
- Deployment: `deploy/`
- Shared package contract: `contracts/`
- Active Codex task: `docs/plans/active/current.md`

## Working rules

- Work on exactly one active-plan task.
- Use a `codex/` branch based on the branch named by the handoff.
- Follow red → minimal implementation → green for behavior changes.
- Preserve all current OME-TIFF and published-slide behavior unless the task explicitly migrates it.
- Treat every archive, manifest and uploaded filename as hostile input.
- Use stable machine-readable error codes.
- Use bounded streaming I/O; do not buffer complete packages in memory.
- Use staging plus atomic rename for filesystem mutations.
- Never expose originals, staging paths, local filesystem paths, credentials or tokens.
- Do not add desktop conversion libraries or GUI code to this repository.
- Commit the completed task and stop; never start the next task automatically.

## Prohibited commits

Never commit:

- patient or source WSI files (`.vsi`, `.ets`, `.svs`, `.ndpi`, `.mrxs`, `.scn`, `.czi`, `.oir`);
- generated OME-TIFF or DZI trees;
- normal `.plslide` packages except tiny deterministic test fixtures generated at test time;
- databases, secrets, `.env` files, tokens or recovery codes;
- caches, build outputs or installer artifacts.

## Verification

Run focused tests while implementing. Before committing backend changes run:

```bash
pytest tests/backend
ruff check server tests migrations
mypy server/wsi_viewer
```

Run these only when relevant areas changed:

```bash
pnpm --dir apps/web lint
pnpm --dir apps/web test
pnpm --dir apps/web build
docker compose -f deploy/compose.yaml config
```

Convenience command:

```bash
bash scripts/run-server-checks.sh
```

## Completion report

Every task ends with:

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

Stop after the report.