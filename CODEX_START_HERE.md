# Codex Start Here — PathLab Viewer Server Integration

## Repository and branch

Open:

```text
Enksodsoon/PathLab-Viewer
```

Start from:

```text
codex/pathlab-forge-server-bootstrap
```

This branch contains server-only instructions. The desktop converter is a different product named **PathLab Forge** and must be developed in a separate repository.

## Paste this into Codex

```text
Open Enksodsoon/PathLab-Viewer and start from branch codex/pathlab-forge-server-bootstrap.

Read AGENTS.md and docs/plans/active/current.md. Work on Task 1 only: prepared-slide contract, typed manifest and deterministic test fixture generator.

Read only the files listed by Task 1 plus docs/compatibility/PREPARED_SLIDE_V1.md. Do not implement the archive importer, upload API, desktop application, QuPath integration, GUI, VSI support or operating-system packaging.

Use test-driven development:
1. Add the focused failing tests.
2. Run them and confirm the expected failure.
3. Implement the smallest complete solution.
4. Run the focused checks.
5. Run all backend checks required by AGENTS.md.
6. Review the diff for security, naming consistency and scope.
7. Commit Task 1.
8. Return the required TASK RESULT report.
9. Stop.
```

## Expected result

Codex should complete only the package contract foundation. It must not begin Task 2 automatically.