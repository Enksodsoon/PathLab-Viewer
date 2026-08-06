# Contributing to PathLab Viewer

PathLab Viewer handles private pathology data. Contributions must be focused, reviewable, tested, and explicit about privacy, storage, or deployment impact.

## Before making a change

1. Read [`docs/PROJECT_GUIDE.md`](docs/PROJECT_GUIDE.md) for the product and architecture contract.
2. Use [`docs/REPOSITORY_MAP.md`](docs/REPOSITORY_MAP.md) to identify the responsible files.
3. Confirm that the proposed change is within scope.
4. Check for an existing issue or pull request covering the same work.

Do not expand the product boundary through an unrelated change. Features such as teams, raw public downloads, fluorescence controls, Z-stacks, and timepoints require a reviewed proposal before implementation.

## Branches and commits

Create a focused branch from the current default branch. Use a descriptive prefix:

- `feature/` for new behavior;
- `fix/` for defects;
- `docs/` for documentation; and
- `cleanup/` or `chore/` for maintenance.

Name branches and commits after the problem being solved, not the tool used to produce the change. Do not rewrite shared history or force-push after review has started. Keep commits narrow and explain the user-visible, operational, or security reason for each change.

## Development workflow

Behavior changes require regression coverage that fails before the implementation and passes afterward. Cover validation, security boundaries, state transitions, and file handling at the appropriate layer.

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

A pull request should explain:

- the problem and its user or operational impact;
- the chosen implementation approach;
- tests and manual verification performed;
- deployment, migration, storage, or rollback considerations; and
- any remaining acceptance gap.

Keep a pull request in draft while behavior is incomplete or required checks are failing. A green CI run is necessary, but it does not replace real-file, browser, load, backup-and-restore, or infrastructure verification when those areas are affected.

Do not close, replace, rewrite, or retarget unrelated pull requests as part of cleanup work. Keep repository maintenance isolated in its own reviewable change.

## Repository hygiene

The public repository should contain durable product documentation and maintainable source code—not the private working process used to create them.

Do not commit:

- assistant or editor workspaces such as `.superpowers`, `.claude`, `.codex`, or `.cursor`;
- prompts, conversation transcripts, agent instructions, generated task reports, or implementation scratchpads;
- temporary branch instructions, command logs, or tool-specific delivery notes;
- hard-coded production addresses, temporary commit hashes, current pull-request status, or test counts that quickly become stale;
- credentials, recovery codes, source OME-TIFF files, generated tiles, databases, private screenshots, `.env` files, or patient information.

Write documentation in direct, durable language. State the product decision, rationale, boundary, and verification method without describing which assistant, model, or editor produced it.

Place durable system decisions in `docs/architecture`, product and interface references in `docs/design`, operational procedures in `deploy/README.md`, and current verification evidence in `docs/evidence/QA.md`.

## Security and privacy review

Before requesting review, confirm that the change cannot expose originals, temporary uploads, private derivatives, databases, logs, credentials, recovery codes, or patient data through the public web path.

Preserve generated identifiers, atomic publication, CSRF and session protections, throttling, storage admission controls, upload validation, audit redaction, and the existing authorization boundary. Report suspected security issues privately rather than opening a public issue containing sensitive details.
