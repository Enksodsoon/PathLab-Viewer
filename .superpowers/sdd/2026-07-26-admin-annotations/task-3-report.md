# Task 3 Report: Canvas Focus workspace and private viewer integration

## Status

Complete. The implementation is committed as
`2bd250fca315ac01d5e5a413a34732188bf24845`
(`feat: add private annotation workspace`).

The annotation workspace remains private-admin-only. Public routes do not render
annotation UI, request annotation APIs, receive annotation payload fields, or load the
lazy annotation module. No push, pull request, merge, OCI deployment, or live
infrastructure change was performed.

## Implemented workspace

- Added a full Canvas Focus annotation workspace with:
  - the complete hand, select, marquee, point, ruler, polyline, angle, rectangle,
    ellipse, polygon, freehand, brush-add, brush-subtract, and text tool surface;
  - selection, multi-selection, move, image-pixel resize, vertex edit, undo/redo,
    duplicate, copy/paste, delete/restore, union/subtract/intersection/split, and
    zoom-to;
  - title, classification, tags, notes, callout text, stroke/fill, width, opacity,
    label visibility, annotation-layer assignment, active drawing layer, layer
    visibility/lock/opacity/reorder/add, calibrated measurements, and calibration
    warnings;
  - search, classification/tag/trash filters, annotation register, live coordinate
    readout, import preview/import, PathLab JSON/GeoJSON/CSV export, and revision
    restore;
  - explicit save/reload, 750 ms autosave integration, honest dirty/saving/error/
    conflict states, conflict reload/save-as-duplicate choices, and local draft
    recovery.
- Added a native SVG OpenSeadragon overlay using image-pixel coordinates and the
  existing RBush render plan:
  - at most 2,000 annotations are mounted and 5,000 cached;
  - high-density views use bounded density cells and the existing zoom prompt;
  - layer visibility/opacity and selection styling are applied without filtering the
    pathology canvas;
  - every handler, subscription, SVG node, and navigation override has explicit
    cleanup.
- Added fail-open boundaries:
  - initialization, dynamic-module, overlay-render, attachment, and save failures keep
    the slide viewer usable;
  - overlay failures restore mouse and keyboard pan/zoom;
  - dirty IndexedDB drafts are retained until acknowledgement or explicit reload.
- Manual reload now rebases the existing autosave controller instead of disposing it.
  A generation token prevents an obsolete in-flight acknowledgement from overwriting
  the newly loaded version.
- Versioned layer/import/revision workflows flush annotation edits first and refuse to
  continue when autosave remains dirty, retrying, conflicted, or failed.

## Viewer and access integration

- `OpenSeadragonViewer` gained one optional attachment callback while the existing
  `ViewerHandle` remains unchanged.
- Attachment cleanup runs before source replacement and before OSD destruction.
  Attachment exceptions restore navigation and cannot block viewer cleanup.
- `ViewerPage` runtime-imports `AnnotationWorkspace` only when all three private
  conditions hold: a private `slideId`, an admin slide response, and
  `annotationsEnabled: true`.
- The public route retains its existing branch and has no static annotation import.
- Annotation loading/failure UI is private-only and does not cover or disable normal
  viewer navigation.

## Design and responsive behavior

The frontend-design guidance was applied as a constrained extension of the existing
Canvas Focus language: the same tokens, compact utilitarian controls, mono data cues,
restrained surfaces, and a single hazard-style focus rail rather than a separate visual
system.

- Desktop uses a left tool strip and object register, top command bar, and right
  inspector.
- At 760 px and below, tools become a horizontal bottom dock and the inspector becomes
  a focus-restoring bottom sheet.
- Interactive mobile controls meet the 44 px target contract.
- Light, dark, and system themes are inherited from the application.
- Reduced-motion rules disable nonessential transitions.
- Tool and command controls have accessible names, live save/operation status, keyboard
  shortcuts, and inspector focus restoration.

No decorative image asset or image generation was needed for this utilitarian,
viewer-first surface.

## Integration fixes found by real build/browser execution

Task 3 was the first code path to load and execute the Task 2 runtime module in a
production browser. Two narrow engine integration defects were fixed:

- `polygon-clipping@0.15.7` exposes its runtime API through the default ESM export, so
  the Boolean core now destructures `union`, `difference`, and `intersection` from that
  default while retaining named type imports.
- The default annotation fetcher now invokes global `fetch` through a wrapper, avoiding
  browser `Illegal invocation` errors caused by retaining bare `window.fetch` as a
  class property.

Playwright can also use an explicit `PLAYWRIGHT_PORT`; this prevents a test run from
silently reusing a Vite server belonging to another worktree.

## TDD evidence

Initial focused component command:

```powershell
pnpm --dir apps/web exec vitest run `
  src/test/annotation-workspace.test.tsx `
  src/test/annotation-overlay.test.ts `
  src/test/viewer.test.tsx
```

- RED before implementation: the private toolbar/workspace and OSD attachment lifecycle
  were missing, and the workspace module could not be resolved.
- The tests were not weakened to bypass the missing behavior.

Reload durability regression:

```powershell
pnpm --dir apps/web exec vitest run src/test/annotation-autosave.test.ts
```

- RED: `autosave.reset is not a function`.
- GREEN after generation-safe rebase support: 10/10.

Final focused result:

```powershell
pnpm --dir apps/web exec vitest run `
  src/test/annotation-autosave.test.ts `
  src/test/annotation-workspace.test.tsx `
  src/test/annotation-overlay.test.ts `
  src/test/viewer.test.tsx
```

- PASS: 4 files, 36 tests.

## Final verification

- `pnpm --filter @pathlab/viewer-web test`
  - PASS: 24 files, 153 tests.
- `pnpm --filter @pathlab/viewer-web lint`
  - PASS with `--max-warnings 0`.
- `pnpm --filter @pathlab/viewer-web exec tsc --noEmit`
  - PASS.
- `pnpm --filter @pathlab/viewer-web build`
  - PASS: TypeScript project build, 4,661 modules transformed, and Vite production
    output.
  - Lazy annotation JavaScript: 105.10 kB raw / 31.35 kB gzip.
  - Lazy annotation CSS: 15.66 kB raw / 3.43 kB gzip.
  - Boolean worker: 27.52 kB raw.
  - `ViewerPage`: 6.23 kB raw / 2.40 kB gzip.
- `PLAYWRIGHT_PORT=5174 pnpm --dir apps/web exec playwright test
  e2e/annotation-responsive.spec.ts`
  - PASS: 16/16 across Chromium, Firefox, WebKit, and mobile Chromium.
  - Covers private desktop create/save, the 760 px dock/sheet and focus restoration,
    44 px targets, light/dark integration, and public zero UI/API/payload/lazy-module
    behavior.
- `pnpm audit --prod --audit-level high`
  - PASS at the requested threshold: zero high and zero critical findings.
  - The same three pre-existing moderate React Router advisories remain.
- `git diff --check` and `git diff --cached --check`
  - PASS; only Git's Windows LF-to-CRLF checkout notices were emitted.

## Scope and evidence limits

- Component and browser tests use deterministic mocked private/public API and DZI
  responses. They are real browser executions, but they are not live OCI acceptance.
- Mobile Chromium viewport/touch-mode behavior was verified; no physical phone or tablet
  was claimed.
- Task 4 still owns full backend/migration/Compose/load/security/delivery verification,
  branch push, and protected pull-request workflow.

## Fix Round 1: durability, complete canvas tools, and stability

Fix Round 1 is complete in
`859694ffa6e267e0a80ef43a2093e1d4c62c099e`
(`fix: harden admin annotation workspace`).

### Critical durability and conflict corrections

- Draft snapshots now include both queued and in-flight mutations. Dirty drafts are
  serialized through one write pipeline, persisted again during unmount, and removed
  only after the matching server acknowledgement or an explicit reload discard.
- Draft write, acknowledgement, and discard operations cannot overtake one another.
  Cross-slide lifecycle refs are reset before a new workspace initializes.
- Save-as-duplicate now rebases its replacement batch on the server-provided
  `currentVersion`; an empty duplicate result also returns that server version.
- The conflict surface is an `aria-modal` focus-trapped alert dialog and restores the
  previously focused control after reload or duplicate resolution.

### Complete annotation behavior

- Brush add/subtract now performs the real worker-backed polygon union/difference
  against the selected closed ROI, preserving the existing atomic preflight and
  single-batch semantics.
- Visible annotation titles/classifications and text callouts render on the canvas.
  Selected geometry exposes real vertex handles and four resize handles; edits are
  committed in image-pixel coordinates.
- `pointercancel` clears construction and handle state without creating or mutating an
  annotation.
- Locked layers are immutable across create, edit, duplicate, paste, Boolean, brush,
  delete, and restore paths, and can never become the active drawing layer.

### Bounded rendering and workflow stability

- The spatial index is loaded once and updated incrementally as records change.
  Viewer animation no longer rebuilds the index or clears/remounts every annotation
  group.
- At the 25,000-object ceiling, density mode mounts no individual shapes, density
  markers remain bounded to 512, normal rendering remains capped at 2,000 mounted
  records, and the object register renders 200 rows at a time with an accessible
  continuation.
- Layer writes are serialized. Reordering normalizes unique `sortOrder` values and
  advances the returned server version between updates. Opacity changes stay local
  during the gesture and commit once.
- Imports reject files over 8 MiB before calling `File.text()`, show a bounded preview,
  and require confirmation. Exports flush pending edits first. Revision history is
  bounded to 25 entries and requires an explicit preview selection before restore.
- Mobile inspector and conflict surfaces trap focus and restore it on close. Browser
  auditing verifies every visible mobile annotation control target at the 44 CSS px
  contract, allowing only sub-pixel browser layout rounding.
- Image coordinates were verified through a rotated viewport transform, and mobile
  browser execution now creates an annotation from an explicit touch pointer.

### Fix-round TDD evidence

The focused regression command was:

```powershell
pnpm --dir apps/web exec vitest run `
  src/test/annotation-autosave.test.ts `
  src/test/annotation-store.test.ts `
  src/test/annotation-measurement-spatial.test.ts `
  src/test/annotation-overlay.test.ts `
  src/test/annotation-workspace-stability.test.tsx
```

- RED exposed missing in-flight recovery, stale duplicate conflict bases, placeholder
  brush behavior, missing canvas labels/handles, 2,000 shapes mounted in density mode,
  repeated overlay/index rebuilds, and all nine workspace stability regressions.
- The first bounded resume run was 40/46, with the remaining failures confined to
  handle assertion shape and deterministic browser-event harness details.
- GREEN: 5/5 files and 46/46 tests.
- A separate locked-layer regression was RED at 17/18 because duplicate could still
  create on a locked layer; it is GREEN at 18/18 after the store-level immutability
  guard.
- The mobile browser audit was RED on two 32×44 layer-order controls; after the
  responsive grid correction it passed with all visible targets at the 44 px
  contract.

### Final verification after Fix Round 1

- `pnpm --dir apps/web test`
  - PASS: 25 files, 168 tests.
- `pnpm --dir apps/web lint`
  - PASS with `--max-warnings 0`.
- `pnpm --dir apps/web exec tsc --noEmit`
  - PASS.
- `pnpm --dir apps/web build`
  - PASS: 4,661 modules transformed.
  - Lazy annotation JavaScript: 115.62 kB raw / 34.31 kB gzip.
  - Lazy annotation CSS: 17.18 kB raw / 3.66 kB gzip.
  - Boolean worker: 27.52 kB raw.
  - `ViewerPage`: 6.23 kB raw / 2.40 kB gzip.
- `PLAYWRIGHT_PORT=5192 pnpm --dir apps/web exec playwright test
  e2e/annotation-responsive.spec.ts`
  - PASS: 16/16 across Chromium, Firefox, WebKit, and mobile Chromium.
  - Includes private create/save, explicit touch creation, exhaustive mobile target
    sizing, modal focus behavior, theme integration, and public-route zero annotation
    UI/API/payload/lazy-module behavior.
- `pnpm audit --prod --audit-level high`
  - PASS at the requested threshold: zero high and zero critical findings.
  - The same three pre-existing moderate advisories remain.
- `git diff --check` and `git diff --cached --check`
  - PASS; only Windows LF-to-CRLF checkout notices were emitted.

No push, pull request, merge, deployment, or infrastructure change was performed.

## Fix Round 2: rapid editing, slide isolation, and bounded persistence

Fix Round 2 is complete and included in the current task commit. It preserves the
private-admin-only boundary and the existing Canvas Focus design language.

### Stability corrections

- Rapid brush strokes against the same ROI now run through a per-target worker
  pipeline. Each stroke reads the latest optimistic geometry, subsequent strokes wait
  for the active worker result, same-target updates coalesce, and a failed worker call
  leaves the local geometry and pending mutation available for retry.
- Workspace async work is generation-scoped. Slide changes replace the layer pipeline,
  clear slide-bound import/revision/opacity/list/coordinate state, and prevent stale
  layer, revision, import, export, reload, and conflict callbacks from mutating the new
  slide. Draft-store read failure remains fail-open for remote annotations.
- Pointer-coordinate updates write directly to the small coordinate output instead of
  setting React workspace state. They no longer clone, filter, or rerender 25,000
  records on every move.
- The object register is a true 200-row window. Next/previous navigation replaces the
  rendered page instead of permanently growing the DOM toward 25,000 rows.

### Touch, drafts, and import limits

- Selected vertex and resize controls now expose semantic button roles, descriptive
  accessible names, compact visible glyphs, and transparent 44×44 screen-pixel hit
  targets. Real touch-pointer vertex editing is covered in component and Playwright
  tests.
- New drafts contain only the base version and recovery mutation journal. Legacy
  snapshot-bearing drafts remain readable, while a one-record edit at the 25,000-object
  ceiling remains below 2 kB and far below the five MiB draft cap.
- Dirty drafts load before the remote manifest so an offline failure can truthfully
  report that the unsaved journal is retained. No acknowledgement or discard occurs
  without server success or explicit reload.
- Import preflight now measures the exact serialized API request, including mutation
  ID, base version, format, layer name, and wrapper fields. An exact eight MiB source
  that overflows after wrapping is rejected before network I/O; a valid near-boundary
  request is accepted.

### Fix-round TDD evidence

The focused regression command was:

```powershell
pnpm --dir apps/web exec vitest run `
  src/test/annotation-store.test.ts `
  src/test/annotation-overlay.test.ts `
  src/test/annotation-drafts.test.ts `
  src/test/annotation-workspace-stability.test.tsx
```

- RED: 35/44 passed and 9 failed for concurrent brush execution, undersized/unlabelled
  handles, missing compact draft builder, permanently growing register pages,
  25,000-record coordinate cloning, stale slide completions, offline draft reporting,
  and serialized import-boundary handling.
- The first implementation run reached 40/44. Remaining failures isolated the
  cross-slide callbacks, offline load order, and a test fixture that was not valid
  PathLab interchange data.
- GREEN: 4/4 files and 44/44 tests.
- The first full-unit run exposed one existing private-viewer regression: IndexedDB
  absence in the test/browser environment blocked remote initialization after draft
  load moved earlier. Draft storage failure was made nonfatal; the targeted viewer
  regression and fresh full suite then passed.

### Final verification after Fix Round 2

- `pnpm test`
  - PASS: 25 files, 175 tests.
- `pnpm lint`
  - PASS with `--max-warnings 0`.
- `pnpm build`
  - PASS: TypeScript project build and 4,661 Vite modules transformed.
  - Lazy annotation JavaScript: 119.19 kB raw / 35.23 kB gzip.
  - Lazy annotation CSS: 17.31 kB raw / 3.68 kB gzip.
  - Boolean worker: 27.52 kB raw.
- `PLAYWRIGHT_PORT=5201 pnpm --dir apps/web exec playwright test
  e2e/annotation-responsive.spec.ts --project=chromium`
  - PASS: 5/5, including an actual touch-pointer drag through a 44×44 vertex target.
- `PLAYWRIGHT_PORT=5202 pnpm test:e2e`
  - PASS: 113 passed, 3 expected skips, 0 failed across Chromium, Firefox, WebKit,
    and mobile Chromium.
- `pnpm audit --prod --audit-level high`
  - PASS at the requested threshold: zero high and zero critical findings.
  - Three pre-existing moderate advisories remain.
- `git diff --check`
  - PASS; only Windows LF-to-CRLF checkout notices were emitted.

No push, pull request, merge, deployment, OCI change, or live-environment acceptance
was performed.
