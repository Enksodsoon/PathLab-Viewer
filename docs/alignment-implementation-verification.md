# Alignment repair and workflow verification

Reconciled application checkpoint: `6481133`, on `codex/alignment-usability`,
reconciled with main `c37cf81a1cabc967e3a587eb2610bf95993801ba` through
merge `2e2f99d` in an isolated checkout. The public screening remains bound to
its earlier frozen source `b35d3be3b2ef8933eed969dbf123746042c57640`.
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

- Final frontend source `9dc96ff` (unchanged by subsequent backend-test/security
  receipt commits): 702 tests across 93 files, TypeScript, full ESLint and
  production build passed. Annotation and assessment bundle budgets passed
  against a byte-identical dependency lock and the current main baseline.
- Final full backend at `6481133`: 1,834 passed, 114 skipped, 85% line coverage
  in 983.55 seconds. PostgreSQL and platform/runtime-dependent skips remain
  explicit. Private receipts: `var/alignment-final-backend.xml` and
  `var/alignment-final-backend.log`.
- Global CI Ruff and strict mypy passed on 82 source files. Security egress
  inventory covers 260 backend, 29 frontend and 97 egress files; its 11
  regression tests passed. Asset and dependency validators passed.
- The [final guided browser receipt](alignment-results/ui-navigation-2026-10-04/guided-observations.json)
  records 19 passing journeys across Chromium, Firefox, WebKit and mobile
  Chromium, zero assertion retries, failures or skips. Each exercises keyboard
  slide selection and Sync, one-point save/reload, two-point preview/cancel and
  save/reload, plus an injected preview 503 followed by normal retry with points
  retained. Guided correction never opens Advanced. Original nonuniform synthetic
  derivative tiles visibly render in both panes. All four browsers also open
  eight growing/repeated worker stacks of 2/4/8/12 slides, 32 cases total.
  One WebKit setup attempt used an incorrect local executable path and failed
  before browser launch; it is retained separately, with zero browser samples.
  Active-refinement publication safety remains focused-test evidence, rather than
  a scientific claim from these completed fixture jobs.
- Final capacity contracts at `6481133`: 492 passed, 12 skipped; terminal exit
  zero, receipt `var/alignment-final-capacity.log`. These are contract tests,
  not concurrent production load qualification.

Private test artifacts are retained under ignored `var/` and the disposable
`pathlab-alignment-usability-e2e` temporary directory. Benchmark results and
method qualification are tracked separately in
[the campaign report](alignment-campaign-2026-10-03.md).

## Worker containment and recovery

An ordinary registration failure preserves the active map and permits later
jobs after owned-process cleanup succeeds. A failure to prove cleanup instead
records a durable `checkpointing` job with `ALIGNMENT_CONTAINMENT_LOST`, retains
resource diagnostics, detaches its slide foreign key and exits the worker.
That row blocks alignment admission across worker roles and replicas. Cancellation,
slide deletion and stale-running recovery do not establish safe cleanup.

Operator recovery requires stopping alignment workers, identifying the affected
host and retained job/process diagnostics, and independently proving the owned
processes are gone. If process identity cannot be established, restarting the
affected isolated host/container is the recovery boundary. Preserve the failure
receipt and release the quarantine only after that evidence is recorded through
an authorized operational recovery procedure. There is no automatic retry or
new user-facing recovery endpoint in this change.

## Remaining qualification limits

Post-screening repairs have separate evidence from the frozen baseline above.
The [ordered-pane browser receipt](alignment-results/ui-navigation-2026-10-04/matrix-observations.json)
records 192 supported navigation samples and 48 unsupported fields across four
browsers, with hidden references, reversed navigation, declared unit conversion,
unequal per-axis calibration and rotation. These mathematical fixtures verify
actual OpenSeadragon coordinates and rendered pixels, not anatomical matching.
The mobile run additionally verifies 24 scale-notice/control bounds checks;
desktop receipts explicitly bind the code before the final notice/bar repair.

An [actual Linux x64 stdlib containment receipt](alignment-results/platform-2026-10-04/linux-containment-x64.json)
records four successful completion, root-exit, timeout and cancellation cases.
Each verifies terminal state for two descendants, including a TERM-resistant
grandchild in a new process group, while preserving an unrelated process.
This proves owned-session cleanup on WSL2/Python 3.14.4; it does not verify the
heavy registration runtime or ARM64. Descendants that create another session
require the deployment's cgroup boundary. The owned fixture processes exited;
Ubuntu remains running because an unrelated shell's ownership was uncertain.

Subsequent immutable-input preparation fixes through `b210baa` have 61 focused geometry/input/benchmark
tests and Ruff/mypy evidence. The full backend count above remains bound to
`6481133`; it is not silently relabeled as a run against those later changes.

Registration performance is measured on Windows x64. This host has no available Docker Linux
engine, so Linux ARM64 runtime validation remains pending. PostgreSQL-dependent
checks and optional-runtime skips are not counted as passes. Published screening
landmarks lack physical calibration; local development slide calibration lacks
independent landmarks. Neither substitutes for calibrated, held-out accuracy
evaluation. Supply-chain inventories retain pre-existing release blockers; a
generated inventory does not authorize production activation.
