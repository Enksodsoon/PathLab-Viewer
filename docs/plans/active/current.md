# Active Task — Prepared-Slide Contract Foundation

> Complete Task 1 only. Commit, report and stop. Do not begin Task 2 automatically.

## Goal

Create the canonical `.plslide` v1 JSON Schema, equivalent typed Python manifest validation, and deterministic tiny package fixtures generated entirely during tests.

This task changes no production API, database, worker, storage, deployment or frontend behavior.

## Create

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

Modify only when required:

```text
pyproject.toml
```

Do not modify:

```text
server/wsi_viewer/api.py
server/wsi_viewer/worker.py
server/wsi_viewer/storage.py
server/wsi_viewer/domain.py
server/wsi_viewer/models.py
migrations/
deploy/
apps/web/
```

## Required public interfaces

```python
class PreparedPackageError(ValueError):
    code: str

class PreparedManifest(...):
    ...

def validate_manifest_json(payload: bytes | str) -> PreparedManifest:
    ...

def build_valid_prepared_package(
    destination: Path,
    *,
    overrides: dict[str, object] | None = None,
) -> Path:
    ...
```

Follow existing Pydantic conventions. Manifest JSON field names must match `docs/compatibility/PREPARED_SLIDE_V1.md`.

## Test-first sequence

- [ ] Add a failing test that loads `contracts/prepared-slide-v1.schema.json` and validates the canonical example manifest.
- [ ] Run it and confirm the failure is caused by the missing schema.
- [ ] Implement the smallest complete Draft 2020-12 JSON Schema.
- [ ] Add failing typed-model tests for a valid manifest and stable invalid-manifest behavior.
- [ ] Implement typed models and `validate_manifest_json`.
- [ ] Emit `MANIFEST_INVALID` for malformed or semantically invalid version-1 manifests.
- [ ] Emit `PREPARED_SCHEMA_UNSUPPORTED` for unsupported schema versions.
- [ ] Add a failing test for a deterministic minimal valid package generated in a temporary directory.
- [ ] Implement `build_valid_prepared_package` using generated tiny JPEG bytes, a minimal valid DZI descriptor and POSIX TAR output.
- [ ] Do not commit the generated binary package or tile tree.
- [ ] Add invalid cases for missing required field, unsupported schema, invalid crop, crop outside source bounds, invalid downsample, incomplete physical-scale group, archive flag/path mismatch and DZI path mismatch.
- [ ] Confirm JSON Schema and typed validation agree for all task fixtures.
- [ ] Run focused tests, then full backend checks.
- [ ] Review for placeholders, inconsistent names, unsafe fixture paths and scope creep.
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

- Version 1 schema is machine-readable and canonical.
- Typed validation agrees with schema validation for every task fixture.
- Tiny valid/invalid package fixtures are generated at test runtime.
- No real WSI, generated DZI tree or `.plslide` binary is committed.
- Stable `MANIFEST_INVALID` and `PREPARED_SCHEMA_UNSUPPORTED` codes exist.
- Existing backend tests pass.
- Production behavior is unchanged.

## Required report

```text
TASK RESULT
- Task: Prepared-slide contract foundation
- Branch:
- Commit:
- Files changed:
- Focused tests:
- Full checks:
- Evidence:
- Known limitations:
- Next task: Safe TAR and DZI validator — do not start
```

Stop after the report.