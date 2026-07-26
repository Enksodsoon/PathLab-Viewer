# Admin Annotation System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or `superpowers:executing-plans`. Follow TDD:
> every production behavior begins with a focused failing test.

**Goal:** Build the approved full manual, persistent, admin-only annotation workspace.

**Architecture:** Keep OpenSeadragon and all public delivery contracts unchanged. Add a
lazy private SVG annotation engine and bounded FastAPI/SQLite persistence behind a
default-off feature flag.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, SQLite WAL, Alembic, React 19, TypeScript,
OpenSeadragon 6, SVG, Web Worker, IndexedDB, `polygon-clipping@0.15.7`, `rbush@4.0.1`.

## Global Constraints

- Annotation UI and code load only for authenticated `/admin/preview/:slideId`.
- `/s`, `/f`, and `/c` expose no controls, data, requests, imports, or public API.
- Existing auth, CSRF, storage, conversion, publication, sharing, tile delivery, OSD
  networking, theme, and responsive contracts remain compatible.
- `PATHLAB_ANNOTATIONS_ENABLED=false` by default; no merge or deployment in this plan.
- No new runtime service, conversion work, derivative file, storage scan, or public artifact.
- Current plus 25 revisions; 30-day trash; purge at most 100 expired tombstones per write.
- Save after 750 ms; at most 50 operations; 256 KiB batch; 8 MiB import.
- Limits: 25,000 active annotations, 100 layers, 8,192 vertices/shape, 250,000
  vertices/import, 2,000 mounted SVG shapes, 5,000 cached shapes, 5 MiB IndexedDB drafts.
- Annotation failure must fail open to a usable viewer and preserve dirty local edits.

---

### Task 1: Admin-only persistence and API

**Files:**
- Create `server/wsi_viewer/annotations.py` for validation, measurements, transactions,
  revision/trash policy, and PathLab/GeoJSON/CSV interchange.
- Create `server/wsi_viewer/annotation_routes.py` for the private API.
- Create `migrations/versions/20260726_0009_admin_annotations.py`.
- Modify models, settings, request limits, app registration, readiness, admin slide JSON,
  and backend database/API/backup/public-hardening tests.

**Interfaces:**
- Add `AnnotationLayer`, `Annotation`, `AnnotationRevision`, and
  `Slide.annotation_version`.
- Add `AdminSlide.annotationsEnabled` and `AdminSlide.annotationVersion`; public slide JSON
  remains byte-for-byte field-compatible.
- Register `/api/v2/admin/annotations/slides/{slide_id}/manifest`,
  `/items`, `/batch`, `/layers`, `/import`, and `/export`, plus item revision/restore
  endpoints.
- Define strict Pydantic geometry, style, metadata, mutation, manifest, and result models.
- Batch operations use client UUID `mutationId` and integer `baseVersion`; any conflict
  rejects the transaction with `409 ANNOTATION_CONFLICT`.

**Acceptance:**
- Session required for every read; CSRF required for every mutation/import.
- Disabled feature returns `404 ANNOTATIONS_DISABLED`.
- Prefix-aware body limiter preserves existing limits and applies 256 KiB/8 MiB annotation
  limits without unbounded buffering.
- Validated coordinates are finite and in slide bounds; text is plain and bounded; unknown
  fields/geometries and active-count/vertex/layer overflows reject before commit.
- Revision creation/pruning, restore-as-new-revision, 30-day tombstones, bounded purge,
  audit privacy, cascade deletion, import/export, and migration round-trip are tested.
- Existing public endpoint responses and viewer routes have no annotation field or route.

### Task 2: Frontend annotation engine and durable client state

**Files:**
- Add an `apps/web/src/annotations/` module containing versioned types, API client,
  geometry/measurement helpers, spatial index, editing store, autosave/conflict logic,
  IndexedDB drafts, interchange adapters, and boolean Web Worker.
- Modify frontend dependencies and lockfile with exact pinned versions.
- Add focused unit tests under `apps/web/src/test/`.

**Interfaces:**
- Mirror backend `AnnotationGeometry`, `AnnotationRecord`, `AnnotationLayer`,
  `AnnotationMutation`, `AnnotationManifest`, and `AnnotationBatchResult`.
- Expose a framework-neutral store used by the later React workspace.
- Expose attach/detach overlay lifecycle, tool commands, selection, history, layer/filter,
  measurement, autosave status, import preview, and export APIs.

**Acceptance:**
- Implement every approved tool and editing/boolean operation against image-pixel geometry.
- Boolean work runs in a worker and terminates at two seconds without mutating the source.
- Spatial rendering obeys 2,000 mounted/5,000 cached caps and produces density fallback.
- Measurements handle anisotropic `nm`/`µm`/`mm` calibration and explicit uncalibrated units.
- Autosave debounces 750 ms, batches at 50, retries with backoff, flushes on request, and
  presents conflict choices.
- IndexedDB preserves dirty data until acknowledgement/discard and enforces the 5 MiB,
  seven-day policy.
- PathLab JSON round-trips losslessly; GeoJSON mapping and CSV measurements use literal,
  independently checked fixtures.

### Task 3: Canvas Focus workspace and private viewer integration

**Files:**
- Add focused toolbar, overlay, inspector, list/layers, save status, error boundary, and
  responsive workspace components/styles under `apps/web/src/annotations/`.
- Modify `OpenSeadragonViewer` with an optional attachment callback returning cleanup.
- Modify private `ViewerPage` flow to lazy-load the workspace only when `slideId` and the
  feature flag are present.
- Add component tests and `apps/web/e2e/annotation-responsive.spec.ts`.

**Interfaces:**
- Keep the existing `ViewerHandle` unchanged.
- The attachment callback receives the live OSD viewer and must return cleanup invoked
  before OSD destroy or source replacement.
- Public rendering follows the old branch and cannot reference annotation APIs/components.

**Acceptance:**
- Implement approved Focus desktop layout and ≤760 px dock/sheet layout with Canvas Focus
  tokens, 44 px touch targets, dark/light/system support, reduced motion, accessible names,
  focus restoration, and shortcuts.
- Create, edit, style, layer, measure, search, zoom-to, save, reload, restore, import, and
  export workflows work with mouse, touch, and keyboard.
- Annotation initialization/render/save failures restore pan/zoom and retain drafts.
- Public viewer tests prove zero annotation UI, fetches, payload fields, and lazy chunk load.

### Task 4: Stability, compatibility, and delivery verification

**Files:**
- Add annotation architecture/operations documentation and focused performance/security
  contracts.
- Update deployment examples only with the default-off feature flag.
- Modify CI commands only where needed to run new tests and bundle-budget checks.

**Acceptance:**
- Run full backend suite, Ruff, mypy, full frontend Vitest, ESLint, TypeScript build,
  production build, Playwright Chromium/Firefox/WebKit/mobile Chromium, worker tests,
  deploy-config tests, Compose validation, security audit, and `git diff --check`.
- Verify migration upgrade → downgrade → upgrade with existing annotation rows and
  backup/restore preservation.
- Verify concurrent annotation reads during a 50-op save do not produce SQLite lock errors.
- Verify public initial gzip delta ≤5 KiB and lazy annotation chunk ≤300 KiB.
- Benchmark a 25,000-annotation synthetic slide, verify indexed query plans, and record
  results without claiming live multi-user or physical-device acceptance.
- Commit logical backend, engine, workspace, and QA changes; push one `codex/` branch and
  open a protected PR. Do not merge or deploy.
