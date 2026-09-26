# Open-source registration integration

PathLab runs registration in the dedicated `alignment-worker`. The viewer
continues serving original tiles while immutable engine candidates are built.
No engine writes a warped whole-slide pyramid.

## Engines and pinned sources

| Engine | Pinned source | Runtime policy |
| --- | --- | --- |
| PathLab native | `piecewise-affine-components-v12` | Baseline and fallback |
| HISAlign 0.2.1 | `c56d1eb1a295aec00bf34c05e0274e2fd79fdaf5` | Direct OD, KAZE, similarity and optical-flow adapter; no pickle loading |
| VALIS 1.2.0 | `325828c1dec444e6bb672a78e875537436dd3c20` | Separate optional image; unavailable unless its ARM64 build and native-host smoke pass |

The HISAlign archive SHA-256 is
`db866088a81e53816b591b7915dc1c205deb9512ef5a23a7545a6767fb7e3f6b`.
Its selected array-registration path does not use Torch, torchvision,
SimpleITK, or KFB. `scikit-image==0.26.0` is required because the pinned
HISAlign source calls `SimilarityTransform.from_estimate`, which is absent in
0.25.2. The adapter stores a compressed NumPy coordinate model and always
loads it with pickle disabled.

VALIS remains isolated because its Java/Bio-Formats and native dependencies
can fail independently on ARM64. A VALIS build failure does not affect
HISAlign, the native engine, ingestion, tiles, or the viewer.

## Candidate and promotion boundary

An administrator starts a bakeoff without replacing active alignment. Each
slide/anchor/engine run records the comparison version, source hashes,
settings digest, runtime, artifact hash, evidence, and failure reason. A
candidate is promoted explicitly and creates a normal immutable registration
revision. Re-running one engine appends another candidate rather than changing
earlier evidence.

Every upstream dense transform is sampled only on detected tissue and
converted to paired non-folded triangles. Forward and reverse navigation use
the same vertex correspondence. Cells outside accepted triangles are
unsupported, so the viewer suspends synchronization there.

## Resource and deployment boundary

The alignment worker is the only service allowed to claim `align` and
`align_benchmark` jobs. A queued alignment drains ordinary heavy work; ordinary
workers wait while alignment is active. The container is limited to 8 GiB and
1.75 CPUs, while the child process tree is limited to 7 GiB and 45 minutes.
Timeout, cancellation, stale comparison input, and memory excess terminate the
complete process group on Linux.

`PATHLAB_ALIGNMENT_ENABLED`, `PATHLAB_ALIGNMENT_HISALIGN_ENABLED`, and
`PATHLAB_ALIGNMENT_VALIS_ENABLED` default to false. Enabling an engine exposes
it for benchmark candidates; it does not make the engine an automatic default.

## License and claim boundary

VALIS includes its MIT license in `deploy/third_party`. The pinned
HISAlign `pyproject.toml` declares MIT and its README links to `LICENSE`, but
that commit does not contain the referenced license file. Keep HISAlign builds
private until the missing upstream license text is resolved for distribution.

Flow-cycle error, tissue overlap, and feature inliers are engineering checks.
They do not establish anatomical accuracy. Promotion remains an administrator
choice until independent landmarks pass the frozen acceptance thresholds.
Broad tissue compatibility is an architecture goal, and claims stay limited
to independently validated tissue/stain combinations.
