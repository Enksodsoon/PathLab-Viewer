# Alignment recipe campaign: 2026-10-03

Status: frozen public screening and isolated four-browser application measurements
are complete. Immutable development preparation remains pending. No recipe qualified as a Fast or Accurate winner.
Prior screening receipts are
exploratory because frontend verification ran concurrently. They do not establish
fair runtime comparisons or qualified winners.

The public campaign reached terminal outcomes for 144 cold attempts and 144
fresh-process repeats. A repeat launches a fresh process; it does not measure a
warm worker. The historical development plan requests 488 cold attempts if four
recipes advance; immutable specimen and content deduplication must precede that
phase. Unavailable or resource-failed methods count as attempts, not successes.

## Frozen inputs and implementation

- Engine source: `b35d3be3b2ef8933eed969dbf123746042c57640`.
- Screening: 12 positive and 4 negative ordered pairs, with 947 published,
  fit-free landmarks. SHA256:
  `d8fc10b233149495758c7ff23f15f35ec7ca9dd6cc959301fbb172be5906746a`.
  Pre-crop exploratory manifest: `36a2d83626a74f96c401592cf3edb3dcfa05e6e2071b2bdecd84214b3e36c66a`.
- Historical development draft: 134 requested pairs, provisionally deduplicated
  to 122 ordered pairs. These counts are pending immutable content deduplication.
  SHA256: `7ea93466cc00927c7085bdf299a9bcd4504445bbb220b255c76acb5062b2f952`.
  The historical draft treated per-axis pixel-size values as micrometers.
  The current metadata audit found missing unit declarations on at least one
  source. Immutable preparation must verify original-header units or label
  such values uncalibrated. These pairs have no independent landmarks and
  cannot establish accuracy qualification.
  The private campaign manifest adds only the same explicit verified learned
  research-weight paths/hashes as screening; pair calibration and image pairs
  remain unchanged. Derived manifest SHA256:
  `046bfe5cf6ea45d6e6d175de08fdb62bafcbd6a1c911150aaaa93d5b29e69742`.
- Hardware receipt SHA256:
  `7d1461213e6eb4d373ca8d4d73d9187e6c9eed4a757699204338746b701a4b67`.
  Windows x64, Intel Core i5-12600 (6 cores, 12 logical processors),
  34,110,615,552 bytes installed memory.
- Common isolated runtime: Python 3.12, NumPy 1.26.4, Pillow 12.3.0,
  installed OpenCV headless distribution 4.11.0.86, torch 2.14.1, VALIS 1.2.0, wsireg 0.3.10,
  itk-elastix 0.25.4, HiSAlign 0.2.1 and DeeperHistReg 1.0.1.
  Upstream source pins and research-weight provenance remain in
  [alignment-recipes.md](alignment-recipes.md) and `deploy/alignment-sources.json`.
  A post-run probe of this unchanged runtime reports loaded `cv2` 4.9.0 and
  an additional installed `opencv-contrib-python-headless` 4.9.0.80.
  The baseline fingerprint recorded distribution metadata, which does not
  identify the loaded OpenCV binary. Original receipts remain unchanged;
  future freezes must record both distribution and loaded-module versions.

Neither screening image set supplies valid physical calibration. Its errors are
relative image-diagonal errors, kept separate from micrometers. Calibrated Fast
and Accurate winners therefore cannot be qualified from this screening alone.
Calibration metadata on development slides does not replace independent
landmark ground truth.

The published source snapshots are
[BIRL](https://github.com/Borda/BIRL/tree/f1648b293664e3bea50736280a19b846d60841f1)
and [histology landmarks](https://github.com/Borda/dataset-histology-landmarks/tree/8413e09e1e53b0e6fc101ae9d7b760c47cc20c77).
The source repositories retain Jiri Borovec's BSD-3-Clause license notices.
Screening is a development cohort, not an independently held-out final accuracy
evaluation.
No additional disjoint image-plus-landmark specimens have been admitted. The
pinned histology-landmarks snapshot has images only for lung-lesion_3; annotations
for other specimen sets do not establish accessible paired images. BIRL's ANHIR
instructions require challenge participation for download. This describes admission,
not a claim that free datasets are inaccessible.

Bounded anonymous GET checks on 2026-10-04 verified the
[ACROBAT official catalogue](https://researchdata.se/en/catalogue/dataset/2022-190-1),
metadata/readme, image listing and actual ZIP range responses. Its CC-BY4.0
image archives are freely accessible; per-image pixel calibration is documented
in micrometres at every pyramid level. A 65,557-byte ZIP64 tail decoded all 201
validation entries without downloading image data. The smallest two-image
validation pair occupies 98,312,126 compressed bytes; no full archive checksum
or image content was verified. The [official challenge data page](https://acrobat.grand-challenge.org/data/)
states no training annotations were generated and validation/test target
landmarks are withheld. Checked public CSV prefixes contain moving points and
calibration but blank target coordinates. The current official repository
contains annotation protocols and evaluation code, rather than paired landmark
files. The container-format bundle link returned a disabled-sharing HTML page,
not a ZIP. Thus anonymous calibrated images are actionable, but complete paired
ground truth has not been established by these checks.

The [HyReCo official page](https://ieee-dataport.org/open-access/hyreco-hybrid-re-stained-and-consecutive-histological-serial-sections-cc-sa-40)
explicitly requires login with a free IEEE account for file access; membership
is not required. No account or agreement was created. It lists `HyReCo.zip`,
`HyReCo-Additional-HE.zip` and `HyReCo-Additional-PHH3.zip`, but does not expose
exact download URLs anonymously. The [author paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC10704256/)
describes 0.24 micrometre pixels and paired landmarks; the catalogue documents
CSV world coordinates in millimetres. Dataset terms are CC-BY-SA4.0 in its title
and paper; the catalogue's JSON-LD CC-BY4.0 link is inconsistent and was not
used to relax those terms. Files and calibration have not been independently
verified. Neither a paywall nor a subscription requirement is inferred.

Both described cohorts differ from the current public lung/mouse-kidney
screening sources. That is evidence for candidate cohort independence, not
completed specimen/content deduplication. ACROBAT IDs must be grouped with their
split; HyReCo related serial and re-stained slides must remain in the same case
group. Private bounded access receipts retain URLs, byte ceilings, redirects,
HTTP status, body hashes and ZIP64 offsets. No bulk image download or dataset
admission occurred. Final held-out qualification still requires admitted,
calibrated, disjoint image pairs with complete independent ground truth.
The [bounded access receipt](alignment-results/public-screening-2026-10-03/dataset-access.json)
records the official URLs, response ceilings and hashes without response bodies.

## Frozen public screening results

The [observations](alignment-results/public-screening-2026-10-03/observations.json)
bind the original `b35d3be` source and frozen manifest. Coverage divides observed
supported landmarks by all 947 planned landmarks. The p95 error describes only
the supported subset and is a percentage of the reference image diagonal.
Different recipes support different subsets; this table does not establish a
fair p95 accuracy winner. Micrometer errors remain null because this cohort
lacks declared physical calibration. Cold medians include **all 16 attempted
pairs**, including rejections and resource failures, rather than successes only.

| Recipe | Supported landmarks / 947 | Observed coverage | Supported p95 (% diagonal) | Cold median (s), all 16 | Negative safety/resource eligibility | Expansion |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| native-overview-v6 | 360/947 | 38.01% | 3.44% | 2.83 | Eligible | Unqualified expansion |
| native-wsireg | 181/947 | 19.11% | 8.90% | 31.31 | Eligible | Unqualified expansion |
| native-valis | 175/947 | 18.48% | 1.19% | 137.03 | Eligible | Unqualified expansion |
| hisalign-0.2.1 | 114/947 | 12.04% | 2.64% | 12.08 | Eligible | Unqualified expansion |
| wsireg-0.3.10 | 165/947 | 17.42% | 4.02% | 30.35 | 1 unsafe; 1 repeat unknown; 1 missing reviews | Not selected |
| valis-rigid-wsireg | 106/947 | 11.19% | 1.57% | 156.81 | 2 missing reviews | Not selected |
| valis-1.2.0 | 84/947 | 8.87% | 1.03% | 153.32 | 1 unsafe; 1 repeat unknown; 2 missing reviews | Not selected |
| deeperhistreg-classical | 34/947 | 3.59% | 9.25% | 6.27 | Eligible | Not selected |
| deeperhistreg-learned | 35/947 | 3.70% | 0.89% | 22.44 | 2 missing reviews | Not selected |

Every recipe remains unqualified. Native overview, native-wsireg, native-valis
and HiSAlign advance only for further unqualified development. Classical DHR
supports 34 landmarks (3.59%); its negative safety eligibility alone does not
select it above the four broader-support recipes. VALIS and its wsireg hybrid
also encountered bounded image-size resource failures; learned DHR encountered
bounded memory failures and lacks complete negative review. Native-valis had
one positive image-size failure without losing negative safety eligibility.
No Fast or Accurate preset is activated.

## Actual browser application evidence

The [sanitized browser observations](alignment-results/public-screening-2026-10-03/browser-observations.json)
record 768 measured applications: 16 accepted maps, 12 deterministic supported
cell samples each, in each of four sequential browsers on the campaign host.
Selection uses the smallest and largest supported-cell counts per recipe,
with digest ordering for ties. It does not select accuracy winners. Each browser
retains null latency for 104 rows lacking an accepted supported map and 24 rows
outside this bounded sampling selection.

| Browser | Version | Samples | Per-map p95 range (ms) |
| --- | --- | ---: | ---: |
| Chromium | 151.0.7922.34 | 192 | 14.4–17.4 |
| Firefox | 153.0 | 192 | 11–13 |
| WebKit | 26.5 | 192 | 12–19 |
| Mobile Chromium | 151.0.7922.34 | 192 | 12.4–18.1 |

Measured scope is isolated production coordinate-map lookup, genuine
OpenSeadragon viewport setters, a drawn frame and coordinate readback. Loaded
original nonuniform tissue pixels and captured screenshots were verified.
This excludes React, user input, API/queue, map transfer, initial slide loading
and engine preparation/inference; full foreground and warm-worker latency
remain null. Sparse support, anatomical errors and qualification are unchanged.
These mathematical application checks do not establish anatomical accuracy.

The external measurement-index SHA256 is
`6143bc84634a29da3c74cf21806685cbb0decc0b78037f19ffaa92e7d704a6ca`.
The sanitized artifact binds the campaign report
`06dc0ce316767f1cdb03187443b60f78b9d322ce48bf6e16743c384626b8b4fb`,
frozen manifest, original map and input digests, exact harness/source hashes
and screenshot digests. Reproduction and acceptance limits are documented in
[the harness](../apps/web/scripts/alignment-browser-latency.md). Browser evidence
was collected after engine compute paused, without competing benchmark work.

## Reproduction

Private manifests, derivative images, diagnostics, checkpoints and weight files
are under ignored `var/`; they are excluded from this report. Use the frozen
manifest order and public `pairIndex` (zero-based) to reproduce pair strata.

```powershell
$env:PYTHONPATH = 'server'
$env:PYTHONUNBUFFERED = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:OPENBLAS_NUM_THREADS = '1'
$env:NUMEXPR_NUM_THREADS = '1'
$env:ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS = '1'
& 'var/valis-runtime/Scripts/python.exe' scripts/benchmark_alignment_recipes.py `
  --manifest var/benchmark-inputs/public-screening-crops-frozen.json `
  --output-dir var/benchmark-results/public-screening-final-b35d3be `
  --screening --repeat-runs 1 --timeout-seconds 600 --memory-gib 7 `
  --recipes native,valis,wsireg,hisalign,deeperhistreg-classical,deeperhistreg-learned,native-wsireg,valis-rigid-wsireg,native-valis
```

Run one heavy registration child at a time after other verification completes.
Each recipe has a total 600-second child budget and a configured 7-GiB memory limit.
The frozen Windows supervisor samples the registration child's working set;
its reported peak is not a proven full-descendant-tree memory peak or ceiling.
In-process libraries contribute to that sampled working set, but descendant
containment is a separate deferred verification and repair. Preserve this
baseline scope alongside any later Job Object aggregate committed-memory limit.
Repeats launch genuine fresh processes; only the host filesystem cache may be
warm. They do not establish warm model or warm worker latency. Resuming reuses
matching input/geometry/settings/adapter/runtime digests and preserves original
cold timings; cached receipt retrieval is not a compute repeat.

VALIS rigid-only passed a genuine upstream smoke including its cleanup shim:
73.828 seconds supervised wall time, peak 2,346,340,352 bytes, approximate map.
The separate identity-image nonlinear smoke rejected at 0.038 Dice. Its raw
upstream B-spline chain drifted 343.93 pixels; genuine Transformix and the adapter
agreed within 0.000000593 pixels at 16 sampled points. This demonstrates upstream
optimizer drift for that bounded `nl_reduced` profile, rather than a reproduced
coordinate-conversion defect. It does not qualify nonlinear registration or
change the default rigid/affine screening settings.

The first published moving lung-lesion field had 98.31% raw tissue. The normal
whole-slide mask rejected it as a threshold flood; the existing explicit crop
path retained 99.86% support without lowering thresholds. The corrected manifest
declares anatomical crop provenance on 24 CIMA lesion side occurrences, including
negatives. BIRL whole images and development full-slide inputs stay unchanged.
Corrected screening SHA256:
`d8fc10b233149495758c7ff23f15f35ec7ca9dd6cc959301fbb172be5906746a`.
The corrected first-pair native overview probe completed in 2.906 seconds with
257,708,032-byte peak RSS and 0.531 seconds preparation. It produced an approximate
map supporting 19 of 80 fit-free landmarks (61 unsupported), relative median TRE
0.006369 and p95 0.014189. It remains unqualified.
The native recipe now uses the distinct bounded overview adapter, preserving
legacy `native-v12` compatibility. Earlier receipts are exploratory.

VALIS invokes upstream DISK depth and LightGlue pretrained resources, using the
existing upstream cache during this baseline. Their exact cached-byte/release
provenance is unresolved until the phase pause; this campaign does not establish
weight-free operation or offline resource admission. Official LightGlue and DISK
sources state Apache-2.0 terms, but those statements do not establish the identity
of the present cached files. Explicit byte verification and download prevention
must precede the separate development runtime freeze.

Development expansion is deferred until the DZI-only sampling repair is verified
and separately frozen. A 21912×19876 source selects a 2739×2485 overview at exact
divisor 8; using the original height as the overview coordinate frame instead
of 19880 produces a proven 3-pixel Y drift at an interior sample. The completed
public JPEG receipts keep their frozen geometry/settings and source identity.
Development inputs will instead bind 21 immutable bounded-overview snapshots
and their exact sampling geometry. Preparation timing/memory has separate
receipts. Original-source provenance is verified where available and explicitly
unavailable otherwise; absent renal originals are not treated as verified.
The earlier derived development-manifest hash above is preparation history,
not the future immutable development campaign freeze.

## Review and reporting rules

Kidney/lung negative pairs have anatomically absent counterparts. Review actual
accepted maps and paired original-image QA before binding safety reviews to
each receipt digest. Accepted wrong-structure maps receive `wrongStructure:true`;
correct rejections receive `false`. Errors and unavailable resources remain
failures and do not count as safe rejections.

Expansion follows the frozen `reviewed-safe-expansion/1` policy, independently
approved before resumed comparisons. Exclude accepted wrong-structure negatives
and unresolved negative resource/runtime reviews. If a fresh negative repeat is
accepted but its map is unavailable for review, its repeat safety remains unknown
and the recipe is excluded. Do not infer repeat safety from a cold rejection.
Each screening negative must also have exactly one completed fresh-process
repeat; missing planned repeat receipts exclude advancement. Development runs
remain cold-only.
Positive execution failures stay in the landmark denominator and failure rate;
a per-pair failure does not automatically exclude a whole recipe.
Advance up to four eligible safe recipes by observed coverage, error and supervised
wall time, even when unqualified. If fewer than four remain, expand those available
and report the shortfall. The source benchmark selector output is provisional;
the reported finalists apply this reviewed safety policy. Evaluate selected
recipes on every distinct development pair after immutable content/frame
deduplication, preserving all requested reference choices. The historical draft
contained 122 pairs; the final frozen count remains pending.
Do not convert missing accuracy ground truth into zero errors or qualification.

Cold timing includes child startup, image loading/preparation, adapter work,
cleanup and supervisor overhead. Adapter duration and remaining overhead are
reported separately where available. Upstream stage timestamps do not establish
foreground latency.

After reviews and cache-only reaggregation, reproduce the sanitized projection
without launching registration:

```powershell
& 'var/valis-runtime/Scripts/python.exe' scripts/report_alignment_campaign.py `
  --directory var/benchmark-results/public-screening-final-b35d3be `
  --manifest var/benchmark-inputs/public-screening-crops-frozen.json `
  --memory-scope root_process_sampled_working_set `
  --output-dir docs/alignment-results/public-screening-2026-10-03
```

The reporting-script hash and original engine/input freeze are recorded separately.
Private review flags must match the original frozen manifest and each map digest.

The frozen public report records outcomes, invalid/unsupported landmarks, pair-level
relative errors, cold and fresh-process-repeat runtime distributions, peak
memory and actual stage timestamps. Preparation, queue, browser and warm-worker
latency remain null wherever unmeasured. Compute-only runtime cannot establish
the ten-second foreground target. Automatic and manual-assisted scores remain
separate. Approximate observations do not promote maps to ready.
An example labeled `ready` describes its local engineering map status. Every
paired example must separately state its benchmark qualification and supported
landmark coverage; sparse support does not establish a full-slide map.

Hybrid stage contribution uses the persisted initializer engine-output map in
original coordinates. A separate score projects its existing supported source
cells through the affine actually applied to the warp; it does not imply the
entire piecewise initializer was applied. The warped residual is never scored
directly as original-frame accuracy. Hybrid versus individual-method output
comparisons remain separate from these initializer-stage scores.
Coverage-priority ranking is explicitly distinct from accuracy improvement:
per-individual coverage, median/p95 error and wall-time changes reveal tradeoffs,
with separate Pareto accuracy/runtime flags. These observations do not establish
hybrid adoption evidence.
Full supported-subset percentiles may describe different landmark subsets.
Separate saved-map comparisons therefore report the common supported count,
coverage found only in each map, median paired error delta and both p95 errors
on the same common set. Relative and micrometer errors remain separate. Missing
maps, missing ground truth and empty common support leave error measurements
null; coordinates and landmark identifiers remain private.

All independently reviewed wrong-structure cold maps are counted separately
from the confidence-threshold count. A confidence below 0.5 cannot hide an
accepted false correspondence or permit safe expansion. Unseen accepted-repeat
maps have a separate unknown-safety count. Positive visual uncertainty remains
explicit rather than a zero-wrong-structure conclusion.

The numbered DeeperHistReg classical kidney example (pair index 10) is a failed
error example: 34 of 69 published landmarks are supported, with relative p95
error 9.25 percent of the reference image diagonal. Independent review of the
numbered correspondences confirmed substantial systematic displacement; the
worst displayed errors span approximately 7.3 to 11.0 percent of the diagonal.
Anatomical wrong-structure confidence remains uncertain at this resolution.
This example is unqualified and does not establish successful anatomical
correspondence.

The completed frozen Native overview output supports 360 of 947 eligible
published landmarks. The subsequent support diagnosis will separate missing
component/local evidence, grid/cell exclusions and white anatomical interiors
such as alveolar lumens. That diagnosis uses the existing maps and published
landmarks without fitting or threshold changes; any demonstrated algorithm
repair requires a new version and separate before/after evidence. The frozen
public observations remain unchanged.

Reviewed human correction effort can declare one to three point pairs and a
finite nonnegative elapsed time. Missing measurements remain null; an automatic
cohort has zero measured/zero missing assisted pairs. Automated browser timing
does not measure human effort.

The available campaign platform is Windows x64. Docker's Linux engine is
unavailable on this host, and ARM runtime checks are pending. No cross-platform
registration performance claim follows from Windows receipts.

Qualification retains independently reviewed zero wrong-structure matches,
80-percent usable calibrated coverage, median error at most 50 micrometers and
p95 at most 100 micrometers. Final deployment and clinical qualification are
outside this campaign.
