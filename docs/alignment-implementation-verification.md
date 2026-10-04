# Alignment repair and workflow verification

Reconciled application checkpoint: `296af2b4`, on `codex/alignment-usability`,
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

Later live-loader regressions found two additional causes on larger slides:
zero saved tiles at the selected DZI level yielded an invented white overview,
and a foreground map sampled at 1024 pixels was served stale when validation
recomputed the default 4096-pixel level. Repair `4d027b7` uses the actual bounded
thumbnail/immutable/pyramid frame and pixel identity in foreground preparation,
keeps genuine sparse pyramids with any present tile, and validates the recorded
DZI selection. Changed thumbnail pixels or source descriptors still invalidate
maps. These repairs have 65 focused passing tests, the fresh full backend
pass and the large-slide browser checks recorded below. Warm foreground
requests now include bounded decode/hash preparation, so earlier warm timing
receipts do not establish performance for this source.

Original slide pixels remain unchanged. Regional corrections are separate from
canonical anchor maps, bounded to supported tissue, and labeled approximations.
Unsupported anatomical counterparts remain unsupported.

Repair `296af2b4` displays **Manually adjusted approximation** only after a
supported saved regional transform is actually applied to a pane. Navigating
outside its bounds clears the manual label when the overview takes over or the
field is unsupported. Unsaved previews retain their distinct label. A focused
regression first reproduced the missing label while confirming correct regional
coordinates, then passed after the repair.

## Workflow

The visible workflow is **Slides → Sync → Adjust region**. Slides default to two
panes and support four. A compact status strip expands progress on demand;
Advanced contains engine comparison, legacy three-point correction and the
active-pane display/quality inspector. Reset and maximize remain accessible.
Correction guides pair selection, corresponding points, preview and save/cancel.
Qualified Fast/Accurate presets remain unavailable without qualifying evidence.

## Verification receipts

- Fresh frontend source `296af2b4`: 704 tests across 93 files passed in
  151.00 seconds. Full ESLint, TypeScript, production/legal build and both bundle
  budgets passed. Annotation initial gzip delta is 3,064 bytes (limit 5,120);
  lazy code is 303,776 bytes (limit 307,200). Assessment learner delta is
  1,894 bytes (limit 15,360), with teacher isolation passing. Private QA receipt
  SHA256: `d42363ac12fbb735e50fcba824164f1814f84d03028aa98d6766705d1d8c9101`.
- Earlier frontend source `85980c0` (unchanged by backend commit `922e418`):
  703 tests across 93 files, TypeScript, full ESLint and
  production build passed. Annotation and assessment bundle budgets passed
  against a byte-identical dependency lock and the current main baseline.
  Annotation initial gzip delta is 3,066 bytes (limit 5,120); lazy code is
  303,776 bytes (limit 307,200). Assessment learner delta is 1,869 bytes
  (limit 15,360), with teacher isolation passing. Private QA receipt SHA256:
  `d582d1fcf136f9282accb18e208a5fc2cb12d77909c0f707339af259f9e00f2c`.
- Earlier full backend at `6481133`: 1,834 passed, 114 skipped, 85% line coverage
  in 983.55 seconds. PostgreSQL and platform/runtime-dependent skips remain
  explicit. Private receipts: `var/alignment-final-backend.xml` and
  `var/alignment-final-backend.log`.
- Fresh full backend at `b08a2a7`: 1,874 passed, 114 skipped, 85% line coverage
  in 1,000.98 seconds, terminal exit zero. Private receipts:
  `var/alignment-final-repaired-green-backend.xml` and
  `var/alignment-final-repaired-green-backend.log`. PostgreSQL and optional
  platform/runtime skips remain explicit.
- Fresh global CI Ruff and strict mypy passed on 83 source files at `922e418`. Security egress
  inventory covers 260 backend, 29 frontend and 97 egress files; its 11
  regression tests passed. Asset and dependency validators passed.
- The [earlier guided browser receipt](alignment-results/ui-navigation-2026-10-04/guided-observations.json)
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
- The [fresh post-repair browser receipt](alignment-results/ui-navigation-2026-10-04/post-basis-large-odd-observations.json)
  records 12/12 journeys across Chromium, Firefox,
  WebKit and mobile Chromium, zero retries, flaky tests or skips. Each layout
  verifies guided correction with the actual preview `basisVersion` in the save
  request, eight growing/repeated real-worker stacks and a 5,003 × 4,009 DZI
  fixture. Actual foreground frames are 626 × 502 analysis pixels, padded
  5,008 × 4,016 coordinates, divisor eight and level ten. Forward/reverse
  coordinates, loaded tile responses and two nonuniform main canvases pass.
  Measured initial application is 2,644.653 ms / 3,683.943 ms / 3,273.910 ms /
  3,056.263 ms respectively. This engineering measurement includes worker queue,
  preparation, API, page and initial viewport application after fixture seeding;
  it excludes seed construction and establishes no anatomical or production
  qualification. The first Chromium run failed a new global status locator
  because both panes correctly displayed the same approximation label after
  reverse navigation. Test-only `f2030cd5` scopes each pane; that failed trace is
  retained outside the twelve terminal passes. Disposable services are gone;
  original app services retain their process identities and start times.
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

Subsequent input, live-loader and correction fixes have focused regression
evidence. The first full run at `922e418` recorded 1,872 passes, 114 skips,
one failed legacy loader mock and 85% coverage in 1,299.84 seconds. Its failed
receipt remains `var/alignment-final-repaired-backend.log`/`.xml`. Test-only
commit `b08a2a7` replaces that outdated mock and verifies explicit 1024/default
4096 bounds, preserved geometry and pyramid preference in two focused passes.
The complete backend rerun at `b08a2a7` passed as recorded above; the earlier
full count remains bound to `6481133`. Fresh browser acceptance above covers
the preview-basis contract and the large odd-dimension real-worker fixture.

One-point saves require the preview's `basisVersion`: an intervening automatic
map change that alters its rotation/scale returns `REGION_PREVIEW_CHANGED` before
writing a revision. The UI retains the marks and requests a fresh preview.
One-point offset correction preserves the newest applicable saved regional
rotation/scale, including reverse navigation, before considering a canonical
basis. These paths have 114 focused backend passes; the frontend contract is
included in the fresh 704-test suite.

Registration performance is measured on Windows x64. This host has no available Docker Linux
engine, so Linux ARM64 runtime validation remains pending. PostgreSQL-dependent
checks and optional-runtime skips are not counted as passes. Published screening
landmarks lack physical calibration; local development slide calibration lacks
independent landmarks. Neither substitutes for calibrated, held-out accuracy
evaluation. Supply-chain inventories retain pre-existing release blockers; a
generated inventory does not authorize production activation.
