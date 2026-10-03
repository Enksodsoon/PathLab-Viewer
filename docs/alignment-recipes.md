# Optional registration recipes and private benchmark

The registry accepts `native`, `valis`, `hisalign`, `wsireg`,
`deeperhistreg-classical`, `deeperhistreg-learned`, `native-wsireg`,
`valis-rigid-wsireg`, and `native-valis`. Existing versioned engine names remain
valid. Optional absence is reported; another algorithm is never substituted.
`ALIGNMENT_WSIREG_ENABLED` and `ALIGNMENT_DEEPERHISTREG_ENABLED` default false.

wsireg uses its genuine upstream elastix helper and rigid/affine parameter maps,
with pinned wsireg 0.3.10 and itk-elastix 0.25.4. Its default remains rigid/affine.
The explicit `models: ["rigid", "affine", "nl_reduced"]` profile adds genuine
upstream B-spline refinement. Its inverse evaluates at most 2401 sample points,
using at most 25 Newton steps with finite positive Jacobians, bounded steps and
subpixel cycle checks; it never allocates a full-slide inverse field. This
additional profile needs real dataset validation independently of the default.
DeeperHistReg classical uses upstream SIFT-RANSAC; learned uses upstream
SuperPoint/SuperGlue. These adapters produce affine initial-registration maps;
they do not claim to exercise the entire upstream deformable pipeline.
Learned weights must be explicit local files with matching SHA256 settings
`superpointWeightsPath`, `superpointWeightsSha256`, `superglueWeightsPath`, and
`superglueWeightsSha256`. No adapter downloads weights. Their noncommercial
research license excludes production use. Source archives, licenses and the
observed isolated Python 3.12 profile are recorded under `deploy/`.

Hybrid stages warp temporary analysis images only. The initializer maps original
moving level-zero coordinates into the reference frame; the residual maps that
warped reference frame into the original reference. Final triangles and controls
are composed back into original moving coordinates. Stage receipts include
versions, settings digests, timing, image scales, crop origins and calibration.
Moving calibration becomes reference calibration for the residual stage.
Hybrid adapter v4 preserves one private original-frame initializer map sidecar,
`initializer-coordinate-map.json`, capped at 16 MiB. Final receipts expose its
fixed basename and SHA256 only. The sidecar is copied before temporary workspace
cleanup, including when a later residual stage rejects. Initializer engine-output
support can therefore be scored separately on frozen original-frame landmarks.
The warp applies the initializer's affine projection, not its whole piecewise
support mesh; stage reports must distinguish engine-output accuracy from this
actually applied affine projection. Residual-frame maps are never directly
scored as original-frame maps.
VALIS rigid initialization disables its nonrigid registrar. Pinned VALIS's
rigid-only constructor omits `non_rigid_reg_kwargs`, although successful
`register()` cleanup accesses it unconditionally. Adapter v15 initializes an
empty dict only for rigid-only registration when the attribute is absent,
preserving existing options and measured error evidence. Every recipe shares
one 600-second process-tree deadline, one CPU thread and the existing 7-GiB
ceiling. New analysis images are bounded to 2048 pixels. Adaptive worker retries,
preemption and automatic fallback persist compute already spent.

## Private manifest

```json
{
  "pairs": [{
    "kind": "positive",
    "reference": {"path": "PRIVATE_DERIVATIVE_DIRECTORY", "size": [10000, 8000]},
    "moving": {"path": "OTHER_PRIVATE_DERIVATIVE_DIRECTORY", "size": [10000, 8000]},
    "landmarksFitFree": true,
    "independentlyReviewed": true,
    "landmarks": [{
      "eligible": true,
      "movingPoint": [100, 100], "referencePoint": [105, 110],
      "referenceMicronsPerPixel": [0.25, 0.5], "wrongStructure": false
    }],
    "reviews": {"wsireg": {
      "registrationDigest": "DIGEST_FROM_THE_ACTUAL_RUN_RECEIPT",
      "wrongStructure": false,
      "frontendLatencySeconds": 8.5,
      "frontendLatencyScope": "foreground-open-to-sync",
      "frontendLatencyReviewed": true
    }}
  }],
  "settings": {"wsireg": {
    "referenceMicronsPerPixel": [0.25, 0.5], "movingMicronsPerPixel": [0.25, 0.5]
  }}
}
```

A derivative directory needs existing DZI tiles or `thumbnail.jpg`. For public
landmark datasets the thumbnail can be the bounded image whose original full
size is declared. Uncalibrated observations use `referenceSize` instead of
`referenceMicronsPerPixel`; they report relative TRE separately and cannot meet
micrometer gates. `negative` pairs have no eligible corresponding landmarks and
need a digest-bound independently reviewed wrong-structure flag. A correctly
rejected negative is a valid safety observation.

```powershell
$env:PYTHONPATH = 'server'
& 'PRIVATE_OPTIONAL_RUNTIME/Scripts/python.exe' scripts/benchmark_alignment_recipes.py `
  --manifest PRIVATE.json --output-dir PRIVATE_OUTPUT --screening `
  --recipes native,valis,wsireg,hisalign,deeperhistreg-classical,deeperhistreg-learned,native-wsireg,valis-rigid-wsireg,native-valis
```

Screening requires exactly twelve positive and four negative ordered, unique,
fit-free independently reviewed pairs. Outside screening, `landmarks: []` is
allowed for unscored development probes; no observations means no finalist or
qualified winner. Inputs are hashed from actual derivative bytes and geometry.
Cache keys include engine/adapter versions, settings and runtime packages.
Each pair can override cohort options with `settings: {"wsireg": {...}}` (or its
versioned engine name). Pair `referenceMicronsPerPixel` and
`movingMicronsPerPixel`, or each slide's `micronsPerPixel`, accept two positive
finite values for the declared full-size coordinate frame. Pair calibration
overrides cohort options, reaches both registration and uncalibrated landmark
records, and is included in the receipt digest. Explicit landmark calibration
remains authoritative for evaluation. Manual-assisted positive landmarks stay
in the automatic denominator as unsupported; assisted scores are separate.
Assisted pairs may additionally declare reviewed human correction effort as
`manualCorrectionEffort: {"pointPairs": 2, "elapsedSeconds": 14.5,
"reviewConfirmed": true}`. Point-pair counts must be integers from one to three;
seconds must be finite and nonnegative. Only these fields appear in report rows.
Aggregates report measured/missing assisted-pair counts and point/time totals and
time percentiles. Unmeasured totals and percentiles stay null, including an
automatic-only cohort. Browser automation timings are never human-effort data.
Reviews can be added after a run; a different registration digest invalidates
negative and latency reviews. Resume preserves actual cold timing.

`--repeat-runs 1` executes an additional supervised child. Its timing is separate
from cache reuse: only the host filesystem cache may be warm, and process/model
warmth is not claimed. Queue/browser latency remains null unless separately
measured. Fast needs complete reviewed frontend latency within ten seconds;
compute-only timing cannot select it. Accurate ranks calibrated usable coverage,
then p95 error, then supervised compute time. Benchmark qualification can measure
approximate maps against frozen landmarks without changing their navigation
status; the legacy ready-map evaluator retains its ready-only qualification.
Both gates retain median 50 micrometers, p95 100 micrometers, coverage 80 percent
and zero independently reviewed confident wrong-structure matches.

Public report rows include zero-based `pairIndex` in frozen manifest order and
per-pair landmark metrics without coordinates or maps. Advancement ranks up to
four strongest tested recipes, including zero-coverage rejected recipes when
scored ground truth and fresh negative reviews exist; advancement alone never
qualifies a recipe. Cohorts without negative pairs cannot advance.

Aggregate JSON/Markdown omit identities, paths and landmark coordinates. Private
caches and map artifacts stay in the explicitly chosen output directory, which
must be outside version-controlled files. Production merge, deployment and
clinical qualification are separate operations.
Private `diagnostics/<receipt-digest>.json` files retain upstream exception types
and messages for cold/repeat failures. Cached failures recorded before this
feature cannot recover discarded messages; rerun them with `--no-resume` to
obtain diagnostics. Public reports retain sanitized reason categories only.
