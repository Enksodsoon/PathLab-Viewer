# Task 1 Report: Admin-only Persistence and API

## Status

DONE

Task 1 is implemented in the isolated `codex/admin-annotations` worktree. The
annotation system is private/admin-only, guarded by
`PATHLAB_ANNOTATIONS_ENABLED=false` by default, and no frontend, merge, push,
PR, or deployment work was performed.

## Files changed

- `server/wsi_viewer/annotations.py`
  - Strict Pydantic geometry, style, metadata, mutation, manifest, item, layer,
    import, and result contracts.
  - Finite/bounded coordinate and plain-text validation.
  - Measurements with calibrated and pixel units.
  - Atomic optimistic-concurrency batches, revisions, restore, tombstones,
    bounded purge, and privacy-safe audit details.
  - PathLab JSON, QuPath-compatible GeoJSON, and CSV interchange.
- `server/wsi_viewer/annotation_routes.py`
  - Session-protected reads and CSRF-protected mutations/import under
    `/api/v2/admin/annotations`.
  - Manifest, items, batch, layer CRUD, import/export, revision listing,
    tombstone restore, and historical revision restore routes.
- `server/wsi_viewer/models.py`
  - `AnnotationLayer`, `Annotation`, `AnnotationRevision`, indexes,
    constraints, cascade foreign keys, and `Slide.annotation_version`.
- `migrations/versions/20260726_0009_admin_annotations.py`
  - Additive annotation schema and reversible downgrade.
  - Uses direct slide-column alteration so existing expression indexes,
    search triggers, public IDs, and publication grants survive round trips.
- `server/wsi_viewer/config.py`
  - Default-off `annotations_enabled` setting.
- `server/wsi_viewer/main.py`
  - Private route registration, prefix-aware request limits, and admin-only
    `annotationsEnabled` / `annotationVersion` fields.
- `server/wsi_viewer/request_limits.py`
  - Bounded streaming limiter with longest-prefix and import-suffix limits.
- `server/wsi_viewer/readiness.py`
  - Alembic head `20260726_0009` and required annotation query-index check.
- `tests/backend/test_annotations.py`
  - Focused API, validation, transaction, revision, purge, cascade,
    interchange, OpenAPI, limit, audit, and public-boundary coverage.
- `tests/backend/test_api.py`
  - Declared-length and chunked 256 KiB / 8 MiB limiter coverage while
    preserving existing auth/internal/admin limits.
- `tests/backend/test_database.py`
  - Migration upgrade/downgrade/re-upgrade with existing slide/public ID.
- `tests/backend/test_readiness.py`
  - Previous-head rejection and required annotation-index coverage.
- `tests/backend/test_backup_restore.py`
  - SQLite backup preservation of private annotation state.
- `tests/backend/test_public_hardening.py`
  - Public response and route isolation assertions.
- `tests/backend/test_config.py`
  - Default-off and environment-override coverage.

## TDD RED evidence

Production behavior was added only after focused failures were observed. Key
RED checkpoints included:

- `pytest tests/backend/test_config.py -q`
  - Failed because `Settings.annotations_enabled` did not exist.
- `pytest tests/backend/test_database.py::test_admin_annotation_migration_is_additive_and_round_trips_existing_slides -q`
  - Failed because all three annotation tables were absent.
- `pytest tests/backend/test_readiness.py::test_current_alembic_head_is_ready ... -q`
  - Failed because the runtime still expected migration `20260724_0008`.
- `pytest tests/backend/test_annotations.py::test_feature_flag_session_csrf_and_admin_public_serialization -q`
  - Failed because admin slide JSON lacked `annotationsEnabled`.
- `pytest tests/backend/test_annotations.py::test_manifest_batch_items_validation_and_atomic_conflicts -q`
  - Failed because manifest bounds/calibration/limits and batch/items behavior
    were absent.
- Focused revision, layer, interchange, and OpenAPI tests
  - Failed respectively with missing `404`/`405` routes and missing response
    schemas.
- `pytest tests/backend/test_api.py::test_chunked_annotation_body_limit_stops_at_256_kibibytes -q`
  - Failed with one receive call because the old 64 KiB admin limiter won.
- Strict mutation test
  - Failed because string `"1"` was coerced to integer and committed.
- Layer-purge and audit-privacy tests
  - Failed with 101 expired tombstones retained and missing `durationMs`.

Each checkpoint was followed by the minimal implementation, focused GREEN
execution, and then refactoring under the same passing tests.

## GREEN and final verification evidence

Interpreter:

`C:\Users\enkso\.cache\pathlab-viewer-py312\Scripts\python.exe`

Commands and results:

- `python.exe -m pytest tests/backend/test_annotations.py -q`
  - 9 passed.
- Focused compatibility suite covering annotations, API, database, readiness,
  backup, public hardening, and config
  - Passed.
- `python.exe -m pytest tests/backend -q`
  - Exit 0; 357 collected, 355 passed, 2 intentional skips.
- `python.exe -m ruff check server tests migrations`
  - `All checks passed!`
- `python.exe -m mypy server/wsi_viewer`
  - `Success: no issues found in 24 source files`
- `git diff --check`
  - Exit 0.

The full backend run reports only the pre-existing FastAPI/httpx and Alembic
configuration deprecation warnings.

## Self-review

- Public `/api/v1/public` serialization still follows the old branch and
  remains field-compatible; annotation paths are all under the admin prefix.
- Every annotation read has the existing admin-session dependency. Every
  write, layer mutation, restore, and import has the existing CSRF dependency.
- Disabled mode returns `404 ANNOTATIONS_DISABLED` to authenticated callers.
- Batch preflight validates slide/item versions, duplicate targets, layers,
  active counts, geometry, bounds, and text before changing persisted state.
- Audit payloads contain IDs/counts/duration/result/version/purge data only;
  geometry, labels, notes, tags, and import contents are absent.
- Revision retention is current state plus 25 snapshots; delete tombstones
  expire after 30 days; each successful write purges at most 100.
- Migration testing found and corrected an early SQLite batch-alter approach
  that could have dropped expression indexes/triggers during table rebuild.
  Direct add/drop column now passes the existing migration preservation tests.
- No new service, conversion work, derivative, storage scan, public artifact,
  frontend code, or deployment configuration was introduced.

## Concerns

- No functional concerns remain within Task 1.
- Browser/frontend integration, concurrency benchmarking, 25,000-item
  performance certification, GitHub delivery, and OCI rollout are explicitly
  later tasks and were not claimed here.

## Fix round 1

### Status

DONE

Implementation commit: `d6f8f53bafc053e9a5bbde5b3ff9e59040751323`

### Corrections

- Every annotation mutation now acquires the database write lock before
  reloading and rechecking `baseVersion`. SQLite uses `BEGIN IMMEDIATE`; other
  SQLAlchemy dialects use a row-level `SELECT ... FOR UPDATE`.
- Batch/create/update/delete/restore, historical revision restore, import, and
  layer create/update/delete all use the shared serialized mutation boundary.
  A concurrent loser returns stable `409 ANNOTATION_CONFLICT` with the current
  slide version.
- Historical revision restore checks the active annotation limit before
  reviving a tombstoned item.
- Style and layer inputs use strict finite numeric, integer, and boolean
  scalars, so coercible JSON strings are rejected.
- Layer names are normalized and whitespace-only names are rejected across
  direct mutations and imports.
- GeoJSON polygons with interior rings are rejected as
  `ANNOTATION_IMPORT_INVALID` instead of silently discarding every ring after
  the exterior ring.

### TDD RED evidence

Before production changes, this focused command failed all four new
regressions:

`python.exe -m pytest tests/backend/test_annotations.py::test_concurrent_batches_with_the_same_base_version_allow_one_commit tests/backend/test_annotations.py::test_style_and_layer_mutations_reject_coercible_scalars_and_blank_names tests/backend/test_annotations.py::test_historical_revision_restore_enforces_the_active_annotation_limit tests/backend/test_annotations.py::test_geojson_import_rejects_polygon_interior_rings_before_commit -q`

Observed failures:

- Both real SQLite/WAL sessions committed from `baseVersion=2`.
- A layer mutation with string `sortOrder` returned `201`.
- Historical revision restore exceeded the active limit and returned `200`.
- A GeoJSON polygon with an interior ring imported successfully and returned
  `200`.

### GREEN and final verification evidence

Interpreter:

`C:\Users\enkso\.cache\pathlab-viewer-py312\Scripts\python.exe`

Commands and results:

- The four-test focused RED command above: 4 passed.
- `python.exe -m pytest tests/backend/test_annotations.py -q`
  - 13 passed.
- The real concurrent SQLite/WAL regression repeated 10 consecutive times:
  all 10 passed.
- `python.exe -m pytest -o addopts='' tests/backend -q`
  - 360 passed, 2 intentional skips.
- `python.exe -m ruff check server tests migrations`
  - `All checks passed!`
- `python.exe -m mypy server/wsi_viewer`
  - `Success: no issues found in 24 source files`
- `git diff --check`
  - Exit 0.

### Concerns

- No functional concern remains within fix round 1.
- The race test proves one winner and one stable conflict under real SQLite
  WAL concurrency, but it is not a sustained write-contention benchmark.
- No push, merge, PR, browser/frontend work, OCI deployment, or live
  acceptance was performed or claimed.
