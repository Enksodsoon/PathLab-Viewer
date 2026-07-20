# Active Milestone — Prepared-Slide Server Vertical Slice

> Work on one task only. Commit it, report evidence, and stop. Do not start the next task automatically.

## Goal

Make one tiny synthetic `.plslide` package reach the existing private OpenSeadragon preview without server-side WSI conversion.

## Architecture boundary

This milestone changes only `PathLab-Viewer`. It does not create the PathLab Prep desktop repository, GUI, VSI support, device pairing or legacy OS builds.

The legacy OME-TIFF path must remain functional throughout.

---

# Task 1 — Contract, typed manifest and fixture generator

## Observable result

The repository contains one canonical JSON Schema, equivalent typed Python validation, and code that generates a tiny valid `.plslide` fixture plus targeted invalid fixtures entirely during tests.

## Files

Create:

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

Modify only if required:

```text
pyproject.toml
```

Do not modify API, worker, storage, models, domain, migrations, deployment or frontend files in Task 1.

## Required interfaces

Define stable names for later tasks:

```python
class PreparedPackageError(ValueError):
    code: str

class PreparedManifest(...):
    ...

def validate_manifest_json(payload: bytes | str) -> PreparedManifest:
    ...

def build_valid_prepared_package(destination: Path, *, overrides: dict | None = None) -> Path:
    ...
```

The exact internal model library may follow the repository's existing Pydantic conventions. Public field names must match `docs/compatibility/PREPARED_SLIDE_V1.md`.

## Test-first steps

- [ ] Add a failing test that loads `contracts/prepared-slide-v1.schema.json` and validates the canonical example manifest.
- [ ] Run the focused test and confirm it fails because the schema does not exist.
- [ ] Add the smallest complete JSON Schema for package version 1.
- [ ] Add failing typed-model tests for valid and invalid manifests.
- [ ] Implement the typed manifest and stable `MANIFEST_INVALID` / `PREPARED_SCHEMA_UNSUPPORTED` errors.
- [ ] Add a failing test for a generated minimal valid package.
- [ ] Implement the deterministic fixture generator using tiny generated JPEG bytes and a minimal DZI descriptor; do not commit a generated binary package.
- [ ] Add invalid fixture cases for unsupported schema, missing manifest field, invalid crop, invalid downsample, archive flag/path mismatch and DZI path mismatch.
- [ ] Run focused tests until they pass.
- [ ] Run all backend checks.
- [ ] Review the diff for placeholders, inconsistent names and scope creep.
- [ ] Commit and stop.

## Focused verification

```bash
pytest tests/backend/prepared/test_contract.py -q
pytest tests/backend/prepared/test_manifest.py -q
ruff check server/wsi_viewer/prepared tests/backend/prepared
mypy server/wsi_viewer/prepared
```

## Full verification

```bash
pytest tests/backend
ruff check server tests migrations
mypy server/wsi_viewer
```

## Acceptance criteria

- Schema version 1 is machine-readable and is the canonical source of field requirements.
- Typed Python validation agrees with the schema for all Task 1 fixtures.
- Valid package fixtures are generated at runtime in temporary test directories.
- No real WSI, generated DZI tree or `.plslide` binary is committed.
- Stable error codes exist for invalid manifest and unsupported schema.
- Existing backend tests pass.
- No production behavior changes.

## Required completion report

```text
TASK RESULT
- Task: 1 — Contract, typed manifest and fixture generator
- Branch:
- Commit:
- Files changed:
- Focused tests:
- Full checks:
- Evidence:
- Known limitations:
- Next task: Task 2 — Safe TAR and DZI validator (do not start)
```

Stop after the report.

---

# Task 2 — Safe TAR and DZI validator

Do not start until Task 1 is reviewed.

Future outcome: validate archive headers, paths, entry types, file counts, extracted bytes, fixed package layout, DZI XML and JPEG signatures without importing assets.

---

# Task 3 — Database lifecycle and asynchronous importer

Do not start until Task 2 is reviewed.

Future outcome: add explicit `prepared_package` ingest mode, `queued_import`/`importing` states, migration, canonical asset staging and background import job.

---

# Task 4 — Prepared upload API and end-to-end synthetic test

Do not start until Task 3 is reviewed.

Future outcome: reserve a package upload, reuse tus, verify length/hash, queue import, reach `ready_private` and load the existing private preview.

---

# Task 5 — Single-copy publication

Do not start until Task 4 is reviewed.

Future outcome: publish canonical DZI assets without duplicating the complete tile tree, with safe unpublish, delete and restore behavior.