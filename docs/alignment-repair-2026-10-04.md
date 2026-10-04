# Post-screening geometry and resource repair

The public screening at source `b35d3be3b2ef8933eed969dbf123746042c57640`
remains frozen. The observations, input manifest, maps and qualification gates
are unchanged. The following findings are post-run diagnostics and development
repairs; they are not new comparative accuracy results.

## Explicit sampled frames

The DZI regression reproduced a three-pixel level-zero Y drift at the rounded
edge: a 21,912 × 19,876 source becomes 2,739 × 2,485 pixels at divisor eight,
covering a padded 21,912 × 19,880 coordinate frame. Engines now receive the
exact power-of-two frame before later image resizing. True source bounds,
per-axis sampling scales, crop origins and physical calibration remain distinct.
Paired polygon clipping retains existing barycentric mapping at partially padded
cells and does not extend support into unobserved pixels. Hybrid initializer
sidecars and final maps use original coordinates; the temporary affine warp
accounts for both crop origins. Requested settings identify queue/resume work;
effective settings identify the actual frames and stages. Remaining time is
execution telemetry and is excluded from method identity.

A separate actual native-overview regression found that mask support projected
both coordinates using the X scale. On identical 512 × 256 pixels, an isotropic
frame retained 300 cells while an anisotropic frame retained only 50. Per-axis
mask projection restores the same supported vertices and 300 cells. Legacy
scalar high-resolution callers and the `native-v12` adapter identity are retained.
New overview outputs, including foreground preview, use `native-overview-v6`
and its new adapter identity. Preparation remains version six.

## Frozen native support diagnosis

[The post-run aggregate artifact](alignment-results/public-screening-2026-10-03/native-support-diagnosis.json)
accounts for all 947 eligible published landmarks using saved maps and masks:
360 are supported; 541 lie in tissue components with accepted cells but outside
the accepted mesh; 23 coincide with enclosed mask background holes; another 23
lie outside the tissue mask or image frame. Reconstructing the deterministic
sparse grid with each saved affine reproduces all twelve saved moving-cell
topologies. Of the 541 in-component losses, 456 lie in candidate cells rejected
by the existing mask-cell checks, and 85 lie outside the paired-mask grid control
hull. Per-axis projection changes zero cells on these public JPEG inputs.

For the first lung pair, the identical saved transform has Dice 0.631171 with
normal support and 0.819364 with thin-tissue support. This explains a support
profile difference between native and optional adapters. It does not establish
an upstream optimizer defect, or justify extending the map beyond observed
evidence. Enclosed background can include legitimate lumens; a mask-hole label
does not establish a clinical anatomical label. No registration or landmark
fitting occurred, and no public support gate was lowered.

## VALIS resources and runtime provenance

On 2026-10-04, official downloads exactly matched the observed cached DISK and
LightGlue weight bytes. The resource ledger now records source commits, byte
hashes and the actual pinned license-file hashes. DISK `depth-save.pth` is
4,375,832 bytes, SHA256 `9c2ee4ded238892dfa51569941372601e35e4a74aa6f84ea80053d2ab1c07abe`,
from commit `8dc6d4d65b47210f629e21ad1fbfb56944b11696`. LightGlue DISK weights
are 47,631,405 bytes, SHA256 `b5b21d47ea24f2c5e501aec9c91b9716e4c8c3429a4dc1e615c133c4c9378335`,
from release `v0.1_arxiv`, commit `c91eb892b799fa607523879d18f9ec4fe76194a5`.
Their licenses permit use under Apache-2.0; registration qualification and
production activation remain separate. See the official
[DISK source](https://github.com/cvlab-epfl/disk/tree/8dc6d4d65b47210f629e21ad1fbfb56944b11696)
and [LightGlue release](https://github.com/cvg/LightGlue/releases/tag/v0.1_arxiv).

Future VALIS admission requires explicit local paths and SHA256 hashes for both
resources. Missing, altered or unadmitted weights are unavailable before model
import. The local loader blocks implicit upstream downloads and restores its
bounded child-local override. Paths stay private; public provenance retains
hashes. This post-run byte verification does not make the original b35 receipts
resource-bound or establish offline admission for those earlier runs.

The common runtime contains two OpenCV distributions with conflicting metadata:
headless 4.11.0.86 and contrib-headless 4.9.0.80, while the loaded module reports
4.9.0. The frozen receipts recorded distribution metadata only. Future runtime
identity includes both distributions and the loaded module version; no packages
were changed during the frozen campaign.

## Immutable development inputs

The preparation interface captures a consistent read-only SQLite backup and all
raw ordered requests before deduplication. Workspace overview PNGs bind encoded
bytes, RGB pixels, true geometry, sampling and calibration. Copied original or
derived regional sources remain available to the actual DZI component path;
generated tile-cache files are excluded from input identity. Their loader
pointers, original bytes, rendering settings and DZI descriptors are bound and
verified. Broken snapshots fail closed instead of falling back to other pixels.
Preparation time, storage admission and contained-process memory are measured
separately. The corrected preparation completed on 2026-10-04; its terminal
counts and provenance are recorded below. The comparative campaign remains held.

Deduplication uses pixel content plus frame, calibration, mask and regional-source
semantics. Every raw request retains a mapping to the resulting pair or an
explicit identical-content self-pair exclusion. The new consistent capture
independently reproduces 134 raw requests and 122 distinct ordered pairs, with
no identical-content self-pair exclusions. All 134 requests retain their mapping.
Physically missing sources and unverified acquisition stages remain distinct.
Physical-size metadata without known units stays uncalibrated;
verified original OpenSlide MPP properties can independently establish
micrometers, as documented by the [OpenSlide API](https://openslide.org/api/python/).
These development pairs have no independent landmarks and cannot qualify an
accuracy winner or replace the missing disjoint final evaluation cohort.


## wsireg Windows failure cleanup

A genuine failed pair retained the upstream elastix filter in completed exception
frames. That filter owned `IterationInfo.1.R0.txt`; Windows sharing violation 32
then replaced the original registration error during strict temporary cleanup.
The adapter projects bounded type/message strings and clears completed upstream
traceback frames before raising the original failure category. No cleanup errors
are ignored and no optimizer or anatomical gate is changed.

The before probe failed with sharing violation at 25.797 seconds. The plain
uninstrumented repeat took 26.578 seconds, retained the original mutual-information
failure (zero of two samples inside the moving buffer), and removed its exact
temporary directory. Sampled contained working set was 943,824,896 bytes and
kernel-reported committed peak was 802,619,392 bytes, with one contained process.
An intermediate instrumented repeat retained inspected frame-local objects and
still locked the log; it is excluded from repair evidence. Private receipts,
source hashes, compute logs and the terminal directory-absence check are retained.
This is an engine/runtime failure, not evidence of a correct anatomical rejection.
The wsireg adapter version changes for this repair; frozen b35 outcomes remain
unchanged.


Storage `source.ome.tif` candidates follow a different preparation path from
explicit OpenSlide pointers. Their existing DZI inventory and 512-pixel tile
geometry are preserved. Copied byte checksums and agreement with the captured
database checksum remain separate from original acquisition-stage verification.
Checksum agreement does not establish that stage.

Read-only checks of all five candidates found single-level, 240-pixel JPEG tiled
OME files recognized by OpenSlide as generic TIFF. Their full file hashes matched
the database and their dimensions matched the declared frames. The existing OME
index builder and bounded native JPEG/512-pixel OpenSlide reads succeeded.
OpenSlide MPP properties were absent; declared OME metadata with recognized units
supplies calibration separately. This header/index substage recorded stable
source stats, but its final queue-delivery harness failed after writing the
artifact; its terminal memory receipt is unavailable. That harness failure is
preserved, rather than reported as a successful supervised registration.

A separate terminal, contained reader diagnostic used the existing regional
reader for all five full image bounds with returned dimensions at most 2048 and
exact power-of-two divisor 16. It took 77.938 seconds; sampled Job working-set
peak was 947,109,888 bytes and kernel committed peak was 925,663,232 bytes under
the 7,516,192,768-byte bound. These are reader diagnostics, not engine registration
or anatomical accuracy results. This full-bounds substage did not independently
capture before/after original-file stat evidence. A small returned low-resolution
tile can decode a much larger level-zero rectangle; these findings do not admit
such files under the 512 MiB foreground boundary.

Preparation can explicitly admit a `verified-openslide-candidate` regional source
using both private probe artifact hashes. It rechecks the copied byte checksum
against the database and probe, exact dimensions, the 512/overlap-1/quality-92
profile, and a fresh native 512-pixel ROI against the earlier pixel checksum.
The loader pointer targets only the verified workspace copy. Original acquisition
stage remains unverified. Admission is limited to the contained heavy refinement
boundary and returned analysis dimensions at most 2048; larger regional requests
fail closed. For candidates without a complete copied pyramid, the existing
thumbnail supplies the immutable overview, avoiding a single-level whole-image
overview decode. No production
reader or OME service decode limit is changed.

Without explicit admission, complete copied DZI pyramids permit regional reads;
partial pyramids explicitly lack admitted regional coverage. Missing overview
levels use a provenance-bound existing thumbnail rather than invented white
pixels. Candidate bytes remain bound even when only derived pixels are used.
Preparation records captured render mode, physically missing files, storage
candidates, and unverified acquisition stages separately. The accepted capture
uses complete copied pyramids for all five candidates; the optional no-tiles
candidate admission path was not needed. The development campaign remains held
until the final source and settings freeze.



Deduplication also includes the verified copied-source byte SHA256 and source
kind, independently of regional reader availability. Different stored candidates
with identical overview pixels remain separate cases; byte-identical candidates
with identical frame, calibration, mask and regional semantics can deduplicate.
Private paths and database slide identities do not enter this content identity.
This binding does not establish the candidate's original acquisition stage.

## Development cold-cache protocol

The optional benchmark `--reset-immutable-regional-cache` protocol requires an
explicit `--immutable-input-root`, zero repeat runs, and the 7 GiB heavy boundary.
Before each uncached serial attempt it validates immutable descriptors, then
removes only unbound generated regional cache files within verified workspace
sources. It refuses symlinks or reparse points in any ancestor or entry. Original
and candidate bytes, overview PNGs, DZI descriptors, admission receipts and bound
copied DZI inventories are preserved. Complete inventory validation precedes any
unlink, and descriptors are verified again afterward. Candidate pointer admission
also requires no preexisting copied tile inventory, preventing derived tiles from
being mistaken for that candidate's generated cache.

Each new receipt records reset wall time, removed file count/bytes and source-kind
counts. Core supervised runtime is separate; reported cold runtime includes reset
plus core runtime. The execution protocol enters the resumable digest, so earlier
receipts without reset cannot masquerade as these cold attempts. Cached receipt
reuse does not reset inputs. The default option remains off for frozen public
compatibility. The precise scope is process-cold with empty generated regional
cache; host filesystem caching is unmeasured and warm-model timing remains null.
Fatal containment loss stops the campaign before another reset or recipe.

The cold protocol subtracts measured input-admission and cache-reset time from
the requested total recipe allowance before child execution. The child grant is
rounded down to whole seconds and recorded separately; requested method settings
retain their stable maximum of 600 seconds. Exhausted allowance produces a
resource-time failure without launching a child and retains the planned pair in
the denominator. Core runtime includes startup, execution and mandatory contained
teardown; separate execution/cleanup durations are unmeasured (`null`), and
mandatory terminal cleanup may extend wall time past the execution allowance.

## Corrected actual candidate inventory

The first immutable preparation attempt stopped at 39.063 seconds before finishing
its first source. Source bytes, declared dimensions and the 512/overlap-1/JPEG
profile agreed with the probes; admission failed because the copied source already
contained a complete DZI pyramid. The earlier planning count of two derivative
files resulted from filtering the inventory and did not establish an empty live
pyramid. The failed receipt, log, source hashes and partial workspace copy remain
preserved as historical evidence.

A complete fresh inventory found 3785, 3658, 2108, 2280 and 2096 tile files in the
five candidate sources. Preparation now gives complete copied pyramids precedence:
all copied tile bytes and their DZI frame are bound, the bounded copied-pyramid
overview is used, and no generated OpenSlide pointer replaces that inventory.
Cold-cache reset preserves these bound tiles. Candidate source copies still must
match the database and probe hashes and pass the fresh header/native-512-pixel
check; this reader evidence does not establish acquisition stage. The no-tiles
heavy-candidate path retains its thumbnail overview and 2048 regional limit.
Preparation storage admission includes the entire fresh derivative inventory,
original/candidate copies, overview reservation and 8 GiB generated-cache budget.

## Accepted immutable preparation

The complete-pyramid repair at source
`c7effc133e1b55e440f0db38dd12b4bf8623ba49` passed 104 focused tests: 22 immutable
input/preparation, 34 benchmark, 23 sampling and 25 reporting tests. Ruff and
the preparation script's mypy check passed. These fixtures cover copied-pyramid
precedence, candidate proof binding, descriptor/tile staleness, preserved bound
tiles during cache reset, geometry and report compatibility. They do not replace
real source verification.

The fresh supervised preparation completed in 231.750 seconds with one contained
process under the 600-second and 7 GiB limits. It copied 7,801,237,010 source bytes
and 503,519,793 derivative bytes across 13,969 derivative files. The resulting
workspace occupied 8,383,882,677 bytes. Storage admission reserved 18,303,977,539
bytes, including the 8 GiB generated-cache budget, within the 24 GiB preparation
budget; the additional 4 GiB free-space reserve also passed. Sampled Windows Job
working-set peak was 443,895,808 bytes; kernel-reported committed peak was
420,597,760 bytes. Captured source/database stats and preparation source hashes
were unchanged across this successful run. The earlier failed 39.063-second
attempt and its partial output remain separate historical artifacts.

All 21 snapshots have verified copied bytes and bound overview geometry/pixels.
Sixteen use explicit verified OpenSlide-original pointers; five retain complete
copied DZI inventories. The five copied storage candidates passed fresh checksum,
header and native 512-pixel reader checks, but their original acquisition stage
remains unverified. There were no physically missing candidate files in this
capture. All 21 sources have positive per-axis calibration: 16 from verified
original OpenSlide MPP properties and five from captured metadata declaring
recognized micrometer units. Calibration does not establish anatomical accuracy.

An independent root check validated all 21 descriptors, bound encoded bytes and
decoded overview RGB pixels in 46.219 seconds; the largest overview side was
3883 pixels. The raw immutable manifest SHA256 is
`5b4a23af97ee9d172312205ff6649b7d1ce5ba22daf65b5b01ba0de287071e01`.
The [sanitized preparation receipt](alignment-results/development-preparation-2026-10-04/preparation.json)
contains aggregate counts, measured resource scope and metadata artifact hashes;
private source paths, identities and pixels remain outside the tracked report.

The completed expansion retained those exact 122 pairs and all raw-request mappings.
The four independently safety-reviewed but unqualified screening recipes are
`native-overview-v6`, `native-wsireg`, `native-valis` and `hisalign-0.2.1`:
488 serial process-cold attempts, no fresh repeats, a total 600-second
pair allowance and 7 GiB contained-memory boundary. The opt-in generated-cache
reset preserves all five bound copied pyramids. Settings use established adapter
defaults with explicit admitted VALIS resource paths/hashes; no case or landmark
tuning occurred. Host filesystem caching and warm-worker timings remain
unmeasured. Source freeze `410b2f48e1ae5834f01d2089b779fca22e2ee8bb`,
loaded runtime/resource admission and terminal source-stat checks are recorded
separately from the public screening freeze. All 488 attempts finished in
15,029.422 seconds: 90 accepted engineering maps and 398 rejected attempts.
All-attempt latency includes early rejections; accepted-map latency is reported
separately in the [sanitized expansion report](alignment-results/development-expanded-2026-10-04/observations.json).

These 122 development pairs have zero independent ground-truth landmark sets.
They can test bounded operational behavior across ordered source pairs, but
cannot qualify Fast or Accurate accuracy winners, prove full-slide anatomical
coverage, or substitute for an admitted disjoint final evaluation cohort.

The landmark evaluator previously selected the local mesh globally, overlooking
points supported by a ready map's own overview. Policy
`pointwise-supported-cells/2` now tries ready-local cells, own overview cells and
an explicitly source/anchor/frame-bound overview fallback for each point. Strict
evaluation excludes both coarse tiers. Finite, invertible, orientation-preserving
cells are required; affine-only navigation and viewport-dependent gap snapping
are outside this conservative accuracy measurement scope. Coarse observations
do not contribute to the ready-local qualification denominator, and map status
is never changed by evaluation.

Separate posthoc analysis of the 144 preserved public cold receipts uses the
original frozen fit-free landmarks and records actual evaluator/reporter/script
bytes plus startup Git HEAD and dirty source state. It verifies receipt metadata,
saved-map and initializer hashes and unchanged original artifacts. Analysis SHA
`0b061f47c011593f40799a886926706b5343933b90ec33c5d824a1bc1c46c055`
adds coarse supported observations: Native→VALIS changes from 175 to 262 of 947
eligible landmarks and VALIS from 84 to 130. Native remains 360. These are
posthoc measurements on the same development specimens, with relative errors;
the original published scores remain preserved and no calibrated winner is
qualified. Map-specific anatomical review is not inferred from landmark flags.

The separate warm protocol plans all 16 frozen public pairs and nine recipes:
144 serial contained children, two invocations per child and 288 explicit
invocation outcomes. Both calls share one absolute 600-second deadline and
7 GiB boundary, including spawn, source-byte admission and image preparation.
Frozen input digests are revalidated inside containment before each invocation.
The requested method settings remain stable; remaining budget is execution
telemetry. Atomic first-result and execution-phase receipts survive a second-call
timeout, while fatal containment loss stops the controller. Cached completed
receipts resume by source/runtime/input/settings/protocol identity; interrupted
attempt artifacts remain private and are counted separately.

The second call is labeled `warm-python-repeat`: decoded-image retention, model
retention and host filesystem cache state are unverified. The protocol does not
reinterpret earlier fresh-process repeats as warm-worker evidence. Genuine
registration trials remain pending a separately reviewed source/settings/runtime
freeze and scheduled resource slot.

Per-recipe actual candidate queue and browser-application timings are feasible
followups but remain unmeasured; saved-map lookups and worker/browser fixture
journeys establish engineering behavior only. Automated correction interactions
can measure an automation task's elapsed time and point count, but cannot supply
human correction effort or anatomical accuracy. Human effort requires actual
reviewed measurements. Final held-out qualification still needs admitted,
disjoint, calibrated image pairs with complete independent reference landmarks:
accessible ACROBAT images lack established public target landmarks, while the
listed HyReCo files require an account and have not been admitted.
