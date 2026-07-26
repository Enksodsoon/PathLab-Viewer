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
