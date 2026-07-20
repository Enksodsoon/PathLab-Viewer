# Start PathLab Prep Work in Codex

## Repository and branch

```text
Repository: Enksodsoon/PathLab-Viewer
Starting branch: codex/pathlab-prep-bootstrap
```

This branch contains the permanent architecture, package contract, short agent instructions, roadmap and the currently active task.

## Paste this into Codex

```text
Open `Enksodsoon/PathLab-Viewer` and start from branch `codex/pathlab-prep-bootstrap`.

Read `AGENTS.md` and `docs/plans/active/current.md`. Work on Task 1 only: Contract, typed manifest and fixture generator.

Read only the files linked by Task 1 plus `docs/compatibility/PREPARED_SLIDE_V1.md`. Do not implement Task 2 or any later work. Do not create the desktop application yet.

Follow test-driven development exactly:
1. Add the focused failing tests.
2. Run them and confirm the expected failure.
3. Implement the smallest complete solution.
4. Run the focused checks.
5. Run the full backend checks required by `AGENTS.md`.
6. Review the diff for security, consistency and scope.
7. Commit the completed Task 1.
8. Return the required TASK RESULT report.
9. Stop.
```

No other project description needs to be pasted. The repository contains the durable context.

## What Codex should produce in the first run

Codex should create only:

```text
contracts/prepared-slide-v1.schema.json
server/wsi_viewer/prepared/__init__.py
server/wsi_viewer/prepared/contract.py
server/wsi_viewer/prepared/manifest.py
server/wsi_viewer/prepared/errors.py
tests/backend/prepared/__init__.py
tests/backend/prepared/fixtures.py
tests/backend/prepared/test_contract.py
tests/backend/prepared/test_manifest.py
```

It may modify `pyproject.toml` only when a small justified test/runtime dependency is necessary.

It must not modify API, worker, storage, models, domain, migrations, deployment or frontend files in the first run.

## After Codex finishes

Review its `TASK RESULT` and commit. Do not tell it to “continue everything.” The active plan deliberately stops before Task 2.

Once Task 1 is accepted, update `docs/plans/active/current.md` so Task 2 becomes the active detailed task, then launch a fresh Codex run with the same short pattern:

```text
Read `AGENTS.md` and `docs/plans/active/current.md`. Work on the active task only, commit it, report evidence, and stop.
```

## Why this setup is token-efficient

- Permanent context lives in the repository once.
- `AGENTS.md` is a short map, not a giant specification.
- Codex reads one active task rather than the complete future roadmap.
- Mechanical rules are enforced by tests and scripts.
- Each run has one observable outcome and one commit.
- Proprietary VSI work and old operating-system packaging are deferred until the core contracts are stable.