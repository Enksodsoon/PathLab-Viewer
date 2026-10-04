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
Preparation time, storage admission and process-lifetime memory are measured
separately. Real specimen preparation is still pending at this document revision.

Deduplication uses pixel content plus frame, calibration, mask and regional-source
semantics. Every raw request retains a mapping to the resulting pair or an
explicit identical-content self-pair exclusion. Historical 134/122 counts are
not substituted for the new capture. Missing original files remain explicitly
unverified. Physical-size metadata without known units stays uncalibrated;
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
