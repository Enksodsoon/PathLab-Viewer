# Contributing to PathLab Viewer

PathLab Viewer handles private pathology data, so changes must be small, reviewable, and evidence-based.

## Before coding

Read [`docs/PROJECT_GUIDE.md`](docs/PROJECT_GUIDE.md) for the product contract and [`docs/REPOSITORY_MAP.md`](docs/REPOSITORY_MAP.md) for file ownership. Confirm that the change is inside scope; annotations, teams, gallery, raw downloads, fluorescence controls, Z-stacks, and timepoints are not part of this project.

## Branches and commits

- Start from the current reviewed branch and use a `codex/` branch for new work.
- Do not rewrite shared history or force-push.
- Keep commits focused and describe the user-visible or operational reason.
- Never commit credentials, source OME-TIFF files, generated tiles, databases, recovery codes, or `.env` files.

## Test-first workflow

For behavior changes, follow red → minimal implementation → green → focused commit. Add a regression test for validation, security, state transitions, or file handling before changing the implementation. For documentation-only changes, run at least `git diff --check`.

Run the relevant checks before requesting review:

```bash
pytest tests/backend
ruff check server tests migrations
mypy server/wsi_viewer
pnpm --dir apps/web lint
pnpm --dir apps/web test
pnpm --dir apps/web build
docker compose -f deploy/compose.yaml config
```

## Pull requests

Explain the problem, the implementation, tests run, deployment impact, and any remaining acceptance gap. Link the relevant evidence in `docs/evidence/QA.md`. Keep the PR draft until the owner has reviewed the live behavior. A green CI run is necessary but does not replace real-file, browser, load, backup-restore, or OCI cost evidence.

## Security and privacy

Original slides are private by design. Verify that a change cannot route originals, temporary uploads, logs, or credentials through public Caddy paths. Use generated IDs, atomic publication, and existing CSRF/session/throttling controls. Report suspected security issues privately rather than opening a public issue with patient data.
