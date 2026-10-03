# Alignment repair and workflow verification

Implementation source: `b35d3be3b2ef8933eed969dbf123746042c57640`, on
`codex/alignment-usability`, reconciled with main `daa101e` in an isolated checkout.
No production activation or deployment was performed.

## Reproduced problems and repairs

- Hidden reference panes prevented approximate siblings from choosing a supported
  initial field. Navigation now initializes from supported image coordinates,
  including a hidden reference, and preserves the field during job polling.
- Refinement blocked correction. Separate regional revisions now allow bounded
  one-point offset and two-point rotation/scale correction during refinement.
  Preview, save and clear check comparison/source versions; cancellation restores
  navigation, and background publication cannot replace a saved correction.
- Self/cyclic anchors and stale source bindings were accepted or misapplied.
  Configuration and navigation now reject those paths; explicit empty anchors
  clear the configuration.
- The benchmark's native adapter used the legacy high-resolution path instead of
  bounded overview/component matching. `native-overview-v6` now identifies that
  method explicitly; legacy `native-v12` retains its identity.
- Published tight lung tissue crops could trigger the whole-slide flood guard.
  Explicit crop provenance selects the existing padded crop-support path, without
  lowering tissue/ambiguity/geometry thresholds or changing image coordinates.

Original slide pixels remain unchanged. Regional corrections are separate from
canonical anchor maps, bounded to supported tissue, and labeled approximations.
Unsupported anatomical counterparts remain unsupported.

## Workflow

The visible workflow is **Slides → Sync → Adjust region**. Slides default to two
panes and support four. A compact status strip expands progress on demand;
Advanced contains engine comparison, legacy three-point correction and the
active-pane display/quality inspector. Reset and maximize remain accessible.
Correction guides pair selection, corresponding points, preview and save/cancel.
Qualified Fast/Accurate presets remain unavailable without qualifying evidence.

## Verification receipts

- Full frontend at UI source `5c0d7f0`: 591 tests across 88 files; TypeScript and
  ESLint passed. Later explicit overview labels/selection were covered by 61
  focused tests, TypeScript and ESLint at `b35d3be`.
- Eight final disposable fullstack alignment scenarios passed across Chromium,
  Firefox, WebKit and mobile Chromium, without retries or skips. Receipts verify
  actual rendered tissue, tile responses, navigation, correction save/reload and
  cancellation, responsive controls and themes. All services were cleaned up;
  the existing application was untouched.
- Backend overview/worker/region/API integration: 113 passed. Engine/recipe/
  benchmark checks: 122 passed, one optional-runtime skip. Engine API: 40 passed.
- Global CI Ruff passed; strict mypy passed on 76 source files.
- The earlier full backend run had 1669 passes, 106 skips and one outdated
  icon-count receipt failure. The expected glyph count was corrected to 156 and
  its regression passed; refreshed asset/security/inventory tests passed 35/35
  before the later overview repair. Subsequent receipts are recorded separately.
- Capacity contracts: 492 passed, 12 skipped. These are contract tests, not an
  actual concurrent production load qualification.

Private test artifacts are retained under ignored `var/` and the disposable
`pathlab-alignment-usability-e2e` temporary directory. Benchmark results and
method qualification are tracked separately in
[the campaign report](alignment-campaign-2026-10-03.md).

## Remaining qualification limits

Windows x64 is the measured platform. This host has no available Docker Linux
engine, so Linux ARM64 runtime validation remains pending. PostgreSQL-dependent
checks and optional-runtime skips are not counted as passes. Published screening
landmarks lack physical calibration; local development slide calibration lacks
independent landmarks. Neither substitutes for calibrated, held-out accuracy
evaluation. Supply-chain inventories retain pre-existing release blockers; a
generated inventory does not authorize production activation.
