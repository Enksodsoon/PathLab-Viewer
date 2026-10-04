# Alignment repair and workflow verification

Integration reconciliation: maintained main
`316d6fc997a2243166e6b43d6e4f11c0e4ed5f7e` was merged locally through
`9c677e8fc3306a454f66916d4f5bf691d66d36b3`. The merged inputs retain maintained
FastAPI, psycopg and TIFF pins, the alignment OpenCV dependency and the bounded
SQLAlchemy constraint. Dependency and software inventories were regenerated
from the merged inputs and validated: 586 dependency records, 617 source
components and 179 shipped dependency inputs, with release admission blocked.
Neither the merge nor earlier receipts establish final QA.
Maintained TIFF 2026.9.20 requires NumPy >=2.1, incompatible with the frozen
research runtime's NumPy 1.26.4. A separate owned maintained API/QA runtime is
ready with a clean `pip check`; the numerical research profile remains
explicitly separate. Its [sanitized admission receipt](alignment-results/runtime-2026-10-04/qa-runtime.json)
records actual OpenCV 4.14.0, NumPy 2.5.2, TIFF 2026.9.20, FastAPI 0.142.1 and
owned loaded native-library hashes. The operational nine-recipe profile uses
the unchanged older research API/worker dependency profile; it does not qualify
the maintained production runtime.

Reconciled frontend checkpoint: `f1b4531c`, on `codex/alignment-usability`,
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
active-pane display/quality inspector. Each pane now exposes a direct 44-pixel
Reset control beside maximize, without opening Advanced.
Correction guides pair selection, corresponding points, preview and save/cancel.
Qualified Fast/Accurate presets remain unavailable without qualifying evidence.

Candidate previews now require affirmative current pair/source/frame proof.
A separately verified Native foreground overview remains available outside a
candidate's supported cells, with an **Approximate overview** label. Strict mode
excludes that fallback; unsupported fields remain unavailable. Polling uses the
fresh sanitized candidate projection, so a removed stale embedded fallback
cannot remain active. The candidate inspection remains unsaved.

## Verification receipts

- Maintained backend at clean `c5b49c8f`: 2,024 passed, 115 skipped and no
  failures in 2,965.51 seconds, with 85% coverage and 236 warnings. The process
  exited successfully. All 1,422 tracked file hashes, installed runtime versions
  and Python binary hashes stayed byte-identical from startup to terminal;
  both receipts have SHA-256
  `d68769ee0e1a142de414fc2b09ca34ca534f5f2ef79c2cc08df62f3ddd5d8dbd`.
  The full log and JUnit receipt are retained as
  `var/alignment-maintained-final-green-backend.log` and `.xml`. Subsequent
  Linux memory-enforcement and keyboard-test edits require their own verification;
  this full-run receipt remains bound to the tested commit.
- Maintained backend at clean `30d1f199`: 2,019 passed, 115 skipped and one
  failure in 1,254.38 seconds, with 85% coverage and 236 warnings. The only
  failure was the maintained inventory test's stale 177 shipped-input assertion;
  independently audited membership has 179. OpenCV is newly bundled and existing
  tzdata now also appears in the backend lock; neither change removes source
  admission blockers. The corrected assertion passes its focused rerun. This
  failed full run is retained as `var/alignment-maintained-final-backend.log`
  and `.xml`; the separate green rerun above supersedes this failed result.
  All 1,422 tracked source-file hashes, runtime versions and Python binary hashes
  were byte-identical at startup and terminal; receipt SHA-256:
  `12ca7333ef24954bfa6d0a1f42417f2ed1f1e3f4c53785b65fd80267ff69a797`.
- The merged frontend's final production/legal build and both fresh-main bundle
  budgets passed. Annotation initial delta is 3,055/5,120 gzip bytes and lazy code
  303,776/307,200 raw bytes. Assessment learner delta is 1,871/15,360 gzip bytes
  against exact `316d6fc` (165,495 current versus 163,624 baseline). All three
  legal copies match their source bytes; actual packaged distribution verifies
  against its compiled graph receipt. The first baseline package-manager location
  check aborted before compilation; it is retained separately from the subsequent
  successful build using byte-verified dependency definitions. Final private
  frontend receipt SHA-256:
  `47fd4ba8dbd0d6e5111e6e5e4c6ce028c1ea5c06f4f1a36a1a2a48858e0fce61`.
- Merged frontend: 731 tests across 93 files passed in 168.14 seconds, with no
  failures or skips. Full ESLint and TypeScript passed; all 345 captured web,
  package and lock files stayed unchanged. The new compiled browser receipt
  binds source `9c677e8f`, four observed graphs and 129 emitted assets; actual
  distribution verification passed and the receipt was copied byte-identically.
  The final legal build and fresh `316d6fc` baseline comparison passed as recorded
  above. A later keyboard-only E2E edit needs a new browser source receipt; the
  captured unit-test and production source bytes remain unchanged.
- CI-scoped Ruff and strict mypy passed again at `c5b49c8f` (84 server files).
  The actual current-tree scanner and complete 278-commit scan from `origin/main`
  passed. Exact package-version contexts are recognized without exempting changed
  hosts, URLs, paths, values or receipt parents; 36 focused tests passed. Seven
  immutable campaign/runtime/kernel/optional-lock reports stayed unchanged.
- The maintained Python wheel and sdist built from a clean Git archive at
  `c5b49c8f`. Both include LICENSE and NOTICE with identical normalized Git
  contents and contain the exact committed third-party notice bundle. The
  packaged Windows checkout line endings are recorded separately. Wheel SHA-256:
  `c456ec184d8db45acd9718b9a8af246e2a5b666d549472fc760ca3dc6797d95e`;
  sdist SHA-256:
  `c8a4c87169d8aec68b36a791e98e02fb1b15656aa67767dd2d80b27fb4cef6f4`.
  An earlier in-place build was deliberately cancelled during traversal of the
  large ignored workspace; its log is retained separately. Both SPDX documents
  passed the hash-pinned checker installed in a separate directory, leaving the
  QA and research environments unchanged.
- Maintained-runtime CI Ruff scope (`server tests migrations`) and all 21
  changed Python scripts pass. Strict mypy passes all 84 server source files.
  An extra all-script Ruff invocation failed on 62 pre-existing findings in
  unrelated demo seeders; that log is retained separately and does not become
  a passing all-script claim.
- Security source inventory at `a42b8fde` passes with 260 backend routes, 29
  frontend routes and 99 egress-bearing files. The two added operational
  scripts account for the increase from 97, under the existing development-tool
  rule. Eleven focused security tests passed; rules were not loosened.
- Optional-image source `90b5f832` constrains VALIS installation to inherited
  backend pins and checks installed dependency consistency. An actual no-install
  pip dry-run would replace maintained NumPy 2.5.2 with 1.26.4 without the
  constraint, then rejects the same request with it. Installed NumPy, TIFF and
  pip versions remained unchanged. Fifty existing deployment tests passed.
  The frozen VALIS lock conflicts with maintained pins; Docker/ARM64 builds
  remain unverified and the isolated research runtime remains separate.
- Source `0ede9b86` fixes an independently reproduced disclosure race: native
  Advanced opened while React state remained stale, so Adjust region could not
  close it. A delayed-native-toggle regression failed, then two focused UI
  tests passed after controlling summary activation directly. Six operational
  Node evidence fixtures and six mocked launcher fixtures passed; TypeScript,
  scoped ESLint and Ruff passed. An independent review additionally passed
  thirteen Python admission/launcher fixtures and six Node fixtures. These are
  source and fixture checks, not real service timings. The preview banner uses
  plain temporary-alignment wording; engine details remain in Advanced.
- Historical `f1b4531c` candidate/reset gate: Chromium passed all four journeys;
  Firefox passed three and failed its ordinary Advanced click. The failed
  receipt is retained. WebKit and mobile had not run at this boundary. The
  complete four-browser gate must run again after reconciliation and the fix.
- Frontend `f1b4531c`: 728 tests across 93 files passed in 139.99 seconds,
  with no failures or skips. Full ESLint, TypeScript, production/legal build and
  both bundle budgets passed. Annotation initial gzip delta is 3,055 bytes
  (limit 5,120); lazy code remains 303,776 bytes (limit 307,200). Assessment
  learner delta is 1,909 bytes (limit 15,360), with the byte-verified reconciled
  main baseline. All 341 tracked/draft web-source hashes remained unchanged.
  Private receipt SHA256:
  `26ecb49352d596938b3f2df109c421f632fd461c8424a72d1a99f88583974f16`.
  Three meaningful regressions first failed for missing restoration observations,
  then passed for candidate Stop, an absent/disposed source handle and regional
  Cancel. The optional read-only `pathlab:alignment-restored` event records each
  requested field separately from the actual OpenSeadragon getter after the
  setter; absent handles or panes not recorded as opened report null. Restoration semantics
  are unchanged. The fresh 16-journey browser run remains pending.
- Post-campaign backend integration recorded 1,962 passes, 114 skips and one
  failure in 1,145.18 seconds, with 85% coverage and 237 warnings. The failed
  security test expected 97 egress-bearing files; the new operational controller
  increased discovery to 98. The validator's route reconciliation and finding
  policy passed. This failed run is retained at
  `var/alignment-post-campaign-backend.log`/`.xml`; it is not a green full-suite
  result. The complete green rerun must follow the final harness-source freeze
  and reviewed inventory expectation. Backend production modules remained
  unchanged during this run; the benchmark-controller exhaustion repair has
  four separate focused passes.
- Frontend `9ad5d73c`: 723 tests across 93 files passed in 147.12 seconds,
  with no failures or skips. Full ESLint, TypeScript, production/legal build and
  both bundle budgets passed. Annotation initial gzip delta is 3,064 bytes
  (limit 5,120); lazy code is 303,776 bytes (limit 307,200). Assessment learner
  delta is 1,869 bytes (limit 15,360), with teacher isolation passing. All 339
  tracked web files were identical at startup and terminal; dependency manifests
  and lock were byte-identical to the reconciled main baseline. Private receipt
  SHA256: `59d48c290ef5973109e08fb4185bd1c014700dca920c1f17d2342e120389a48e`.
  A preceding focused 99-test batch reproduced and repaired direct Reset,
  candidate fallback, stale/missing pair proof, reflected cells, polling and
  restoration failures. Fresh browser acceptance for these additions is pending;
  earlier browser receipts below retain their original scope.
- Backend preview contract `2c0c5e84`: 169 focused integration tests passed,
  including strict current-pair/source/frame admission and verified Native
  foreground fallback. Actual endpoint failures reproduced stale source/anchor
  bindings and stale nested fallback leakage. The response omits unusable child
  fallbacks without altering immutable receipts. Canonical legacy serving,
  promotion and regional contracts remain unchanged. Further fetch-race and
  bounded warm-protocol checks are tracked separately before final integration.
- Eligibility-token repair `35c5decb`: 106 focused backend tests passed after
  reproducing a mixed-fetch race through the real metadata endpoint. Candidate
  tokens now bind normalized case, readiness and trash state alongside source
  content/frame identity. Thus an old manifest cannot match a newly ineligible
  member even when comparison version and slide SHA stay unchanged. Equivalent
  case normalization and cosmetic edits remain compatible. Regional revision
  tokens and canonical storage retain their contracts. Two frontend tests at
  `c4632c30` independently verify mixed-fetch rejection; these are separate from
  the 723-test frontend run above.
- Evaluator and warm-process harness `4d5d74a0`: 122 focused tests passed, plus
  12 independently reviewed warm containment tests. Five actual failures were
  reproduced and repaired before benchmark admission: elapsed settings identity,
  parent admission consuming the budget, spawn excluded from the deadline,
  unbounded input verification, and missing second-invocation start evidence.
  The warm protocol executes twice in one contained child with a shared
  600-second deadline and 7-GiB committed-memory ceiling. First-call receipts
  survive second-call timeout. This verifies the harness, not actual engine
  warm performance. Fresh strict mypy passes all 84 backend source files;
  Ruff passes server, tests and the changed benchmark/seeder scripts.
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
- [Fresh active-regional-label browser acceptance](alignment-results/ui-navigation-2026-10-04/active-regional-observations.json)
  uses application `296af2b4`
  and final scenario `a166af33`: 12/12 journeys passed across Chromium, Firefox,
  WebKit and mobile Chromium, with zero retries, flaky outcomes or skips.
  Each verifies nine supported regional phases and one outside-region overview
  fallback: one/two-point preview, save/reload, cancellation restoration and
  returning inside the bounds. Independent affine calculations agree with actual
  OpenSeadragon coordinates to at most 1.1368683772161603e-13 pixels, below the
  0.01-pixel tolerance. The literal manual label, unsaved-preview qualification
  and control bounds pass; the manual label clears outside the region.
  All layouts also pass eight real-worker stack openings and the large odd-size
  slide fixture. Initial large-fixture application takes 2,407.860 / 3,678.004 /
  3,487.307 / 2,308.396 ms respectively, including queue/preparation/API/page
  application after seeding. These synthetic fixtures provide engineering
  evidence, not anatomical accuracy or production latency qualification.
  An earlier Firefox exact-text locator failed because the preview badge now
  includes a distinct manual-adjustment subtitle. Its trace and preceding
  Chromium passes remain historical; test-only `a166af33` matches the explicit
  unsaved-preview prefix without changing coordinate tolerances or production
  code. All four layouts reran against that exact scenario. Disposable services
  and their edge listeners are gone; original app process identities/start times
  are preserved.
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

Registration performance is measured on Windows x64. A fresh read-only check now finds the Docker Linux engine available. Actual bounded core-image checks on Linux amd64 and emulated ARM64 remain pending; no physical ARM64 performance qualification is claimed. PostgreSQL-dependent
checks and optional-runtime skips are not counted as passes. Published screening
landmarks lack physical calibration; local development slide calibration lacks
independent landmarks. Neither substitutes for calibrated, held-out accuracy
evaluation. Supply-chain inventories retain pre-existing release blockers; a
generated inventory does not authorize production activation.

## Post-integration verification updates

The Linux worker now rejects unreadable RSS for a still-live owned process, instead of counting it as zero. Exit and process-identity checks distinguish an exited member from a live accounting failure. Independent Windows-focused verification records 58 passes and five Linux-only skips; an actual Linux x64 stdlib fixture records seven passing containment/accounting cases. These checks are separate from the earlier full backend run, and full installed Linux-worker verification remains pending the bounded container checks.

The Advanced drawer browser scenario now verifies keyboard Enter to open, Space to close, retained focus, and visible candidate controls. Only its E2E source changed; prior production/unit source bytes remain unchanged. A fresh compiled-distribution receipt and the unchanged 586 dependency records are bound to `7e9f9daf49dea3b0c6e7ed930253336876431736`; ten inventory checks pass. The fresh sixteen browser journeys remain pending.

A capacity-contract rerun recorded 490 passes, twelve skips and two failures. Reproduction proved the Windows fixture deadline prevented its verifier from running. Test-only `2314d42d` adds entry markers, a distinct exhausted-budget case, and sufficient fixture reserve; fifteen focused cases pass and five skip. Production restoration code is unchanged. The complete capacity rerun passes: 493 passed, twelve skipped, zero failures or errors across 505 cases in 169.707 seconds. Receipts `var/alignment-maintained-capacity-repaired.log` and `.xml` bind the repaired test bytes. The failed receipts remain retained.


The first integrated sixteen-journey gate at `2c2032ef` passed all four Chromium cases and three Firefox cases, then stopped on a candidate disclosure assertion. An actual event replay proved the fixture ended its simulated drag outside the browser window: Firefox never received pointer-up, and stale canvas capture intercepted the next summary click. Production drawer and viewer code are unchanged. Test/measurement-only `0fadc482` uses bounded visible-canvas strokes, actual coordinate convergence and in-window release/capture assertions. The focused Firefox journey passes with thirty ordinary keyboard/open/click/close cycles and six released strokes; twelve Node and fifteen independent Python operational checks pass. Failed traces and diagnostics remain retained. A fresh compiled receipt at `a988f5b5` changes exactly three test/measurement source inputs; four graphs, 129 emitted assets and three prebuilt inputs remain identical. The complete refreshed sixteen-journey gate remains pending its inventory/legal bindings.

The refreshed gate at `2fa4658d` passed all four Chromium and all four Firefox journeys, then recorded three WebKit passes and one closed-disclosure visibility assertion failure; mobile was not started. The failed gate is retained as eleven passes, one failure and four unrun cases. Actual event telemetry proved Space closed Advanced with focus retained. Screenshots showed no drawer, native visibility was false, hit testing excluded its contents, and the next ordinary Tab moved outside the closed subtree. Independent plain and controlled disclosures reproduced the WebKit test-framework visibility discrepancy; no production keyboard or CSS defect was established.

Test-only `84e5bb14` replaces that assertion with actual closed state, native visibility, hit exclusion and keyboard exclusion while preserving ordinary reopening and candidate/navigation assertions. The focused actual WebKit journey passes in 34.923965 seconds, with no retry or skip; TypeScript and scoped ESLint pass. Its owned services and processes are closed, original service identities are preserved, and production/unit/package bytes remain unchanged. Existing full frontend evidence remains separately bound to its original execution source.

Compiled receipt `7fc351aa` binds source `84e5bb14`: exactly one of 353 source inputs changes. Four module graphs, 129 emitted assets and three prebuilt inputs remain identical to the previous receipt; every emitted file and byte digest was independently checked. The actual source/distribution validator exits zero. The complete fresh sixteen-journey gate remains pending the refreshed provenance bindings.

The primary-source dependency regeneration retains all 586 records unchanged and binds 208 source receipts to `7fc351aa`; ten focused inventory tests pass. Software provenance refresh and the complete fresh browser gate remain pending.
