# Contributing to PathLab Viewer

PathLab Viewer handles private pathology data. Changes must be focused, reviewable, tested, and explicit about privacy or deployment impact.

## Before making a change

1. Read [`docs/PROJECT_GUIDE.md`](docs/PROJECT_GUIDE.md) for the product and architecture contract.
2. Use [`docs/REPOSITORY_MAP.md`](docs/REPOSITORY_MAP.md) to identify the responsible files.
3. Confirm that the proposed change is within scope.
4. Check for an existing issue or pull request covering the same work.

Annotations, teams, galleries, raw public downloads, fluorescence controls, Z-stacks, and timepoints are outside the current product scope unless a reviewed proposal changes that contract.

## Branches and commits

Create a focused branch from the current default branch. Use a descriptive prefix such as:

- `feature/` for new behavior;
- `fix/` for defects;
- `docs/` for documentation;
- `chore/` or `cleanup/` for maintenance.

Do not rewrite shared history or force-push a branch after review has started. Keep commits narrow and explain the user-visible, operational, or security reason for each change.

Never commit credentials, recovery codes, source OME-TIFF files, generated tiles, databases, private screenshots, `.env` files, or patient information.

## Development workflow

Behavior changes require a regression test that fails before the implementation and passes afterward. Cover validation, security boundaries, state transitions, and file handling at the appropriate layer.

Documentation-only changes should still be checked for broken links, stale claims, formatting errors, and unintended disclosure of infrastructure details.

Run the checks relevant to the change:

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

A pull request should describe:

- the problem and its user or operational impact;
- the implementation approach;
- tests and manual verification performed;
- deployment, migration, storage, or rollback considerations;
- any remaining acceptance gap.

Keep a pull request in draft while behavior is incomplete or CI is failing. A green CI run is required, but it does not replace real-file, browser, load, backup-and-restore, or infrastructure verification when those areas are affected.

## Documentation standards

Public repository documentation should be durable and product-focused. Do not commit private prompts, conversation transcripts, agent instructions, implementation scratchpads, hard-coded production addresses, temporary commit hashes, current pull-request status, or test counts that will quickly become stale.

Place durable system decisions in `docs/architecture`, operational procedures in `deploy/README.md`, and current verification evidence in `docs/evidence/QA.md`.

## Security and privacy review

Before requesting review, confirm that the change cannot expose originals, temporary uploads, private derivatives, databases, logs, credentials, recovery codes, or patient data through the public web path.

Preserve generated identifiers, atomic publication, CSRF and session protections, throttling, storage admission controls, and audit redaction. Report suspected security issues privately rather than opening a public issue containing sensitive details.
