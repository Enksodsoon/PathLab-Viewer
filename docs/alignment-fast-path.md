# Progressive alignment implementation and qualification

The ten-second whole-stack target is not production-qualified. Approximate overview maps describe coarse tissue positioning, not validated anatomical correspondence. The measurements below do not satisfy the production activation gates.

## Implemented path

Stack admission creates foreground jobs with one shared ten-second deadline. A persistent worker reuses 1024-pixel preparation and at most 1,536 spatially distributed ORB descriptors per source. Preparation keys bind the source digest, DZI geometry, full dimensions, preprocessing version, and OpenCV version. The preparation LRU has a 128 MiB array budget; directional pair maps have a 16 MiB Python-object budget. Cache misses, preparation, computation, and queue time are recorded. Source edits and cancellation are checked again before publication.

Sparse correspondences or bounded structural initialization produce explicitly approximate overview cells. The support mesh is limited separately from the feature budget. Exact DZI sampling intervals preserve level-zero coordinates. Failed or late first passes become `needs_refinement`; they never count as aligned.

Foreground jobs precede queued refinement. Running refinement checks foreground admission before child startup and every half second, then terminates the complete child process tree and requeues without deleting published maps. Native component feature and structural batches persist atomically under source hashes, engine version, settings digest, crop geometry, and OpenCV version. Component RGB reads are reused within a byte-bounded 384 MiB job cache. Optional VALIS fallback runs after unresolved native refinement, under the existing bounded child supervisor. HISAlign is absent from the production image pending resolution of its upstream license-file issue.

Best available navigation now uses supported local cells before approximate cells, follows direct maps through anchor chains, and rejects missing maps and cyclic chains. New maps recover linkage automatically; progress-only polling preserves the viewport. Approximate navigation is labeled. Initial fitting respects the same OpenSeadragon zoom constraints as linked panes. Manual corrections bind both source versions; incompatible saved maps cannot outrank a replacement. Registration revisions remain immutable.

The worker records current RSS, process-lifetime peak RSS, Linux startup duration, and available cgroup-v2 current/lifetime-peak memory. Lifetime peaks are not isolated foreground peaks. Browser `pathlab:alignment-applied` events contain actual source/target viewports, application duration, and publication/application timestamps. Server/client timestamps require a qualified clock basis before calculating end-to-end latency. A retained earlier map retains its original evidence; current job timings are separate.

## Development measurements

Local Windows/x64, one OpenCV thread, five cold/warm repetitions. These are compute-only measurements, not stack-acceptance-to-browser latency or ARM64 results.

| Stack | P95 compute seconds | Accepted overview pair runs |
| --- | ---: | ---: |
| Synthetic 2 slides | 0.276 | 10/10 |
| Synthetic 4 slides | 0.493 | 30/30 |
| Synthetic 8 slides | 1.165 | 70/70 |
| Synthetic 12 slides | 1.816 | 110/110 |
| Renal development, 4 slides | 0.344 | 0/30 |
| H&E/P40 development, 2 slides | 0.245 | 0/10 |
| H&E/P40/TTF1 development, 3 slides | 0.709 | 20/20 |

Maximum sampled RSS in these runs was approximately 221 MiB. This does not establish the 512 MiB foreground peak or total-container ceiling. Rejected pairs count against coverage. The successful development overviews have not passed independent landmark accuracy gates.

Detailed receipts: [synthetic](benchmarks/alignment-preview-2026-09-22-synthetic.json), [development](benchmarks/alignment-preview-2026-09-22-development.json).

The September 27 sampling repair applies the unchanged scale and anisotropy gates in level-zero coordinates, including mesh cell area checks. Renal slides used 128- and 256-pixel pyramid sampling intervals; comparing their overview pixels directly incorrectly rejected strong fits. Five cold/warm repetitions now accepted 30/30 renal approximate pairs (four-slide compute p95 0.712 seconds), 0/10 H&E/P40 pairs, and 20/20 H&E/P40/TTF1 approximate pairs (three-slide p95 0.750 seconds). Maximum sampled RSS was 221 MiB. This remains local compute evidence, excludes startup/queue/browser costs, and establishes no independent anatomical accuracy. [Sampling repair receipt](benchmarks/alignment-preview-2026-09-27-sampling.json).

The subsequent thin-tissue fallback retains structures removed by the five-pixel mask opening, preserving density, chroma, component-area, scanner-strip, fit, and overlap gates. The original path runs first; only rejected pairs use cached thin support and a five-pixel coarse Gaussian scale. Preparation accounts for the extra mask in its byte ceiling. Five cold/warm repetitions accepted 30/30 renal, 10/10 H&E/P40, and 20/20 H&E/P40/TTF1 approximate pairs, with whole-stack compute p95 of 0.700, 0.837, and 0.920 seconds respectively. Twenty renal-versus-lung challenges produced zero accepted overviews. These checks do not qualify same-organ wrong-structure rejection or anatomical accuracy. [Development receipt](benchmarks/alignment-preview-2026-09-27-thin-tissue.json), [cross-tissue challenge receipt](benchmarks/alignment-preview-2026-09-27-negative.json).

Reproduce with `PYTHONPATH=server python scripts/benchmark_alignment_preview.py --output receipt.json`. Use `--manifest private-manifest.json` for development derivatives; the script documents its manifest format and omits paths and specimen identities from receipts. Private images and manifests must remain outside the repository.

## Remaining release gates

- Qualify local correspondence after the overview sampling and thin-tissue repairs. Development stacks now produce approximate maps; independently reviewed local accuracy remains unproven. Existing local maps can be retained while difficult regions continue refinement.
- Qualify sparse refinement of uncovered regions. Compatible supported maps now seed up to 64 tissue patches, restricted to coarse support and capped at 1024 pixels / 1,536 ORB descriptors. Unsupported windows shrink up to three times; rejected patches do not trigger whole-slide fallback. Completed patch receipts resume before decoding, while existing local cells remain intact. The development probe retained its approximate map with zero accepted local cells; independent accuracy qualification remains incomplete.
- Guided feature crops now reuse the component engine's white-context padding through shared segmentation. This prevents the whole-slide 92-percent flood guard from discarding valid full-tissue crops, without changing the guard or feature acceptance gates. Native v15 and new patch receipt keys prevent reuse of earlier rejected batches. A full-tissue identity regression passes; the H&E/P40 development probe still accepts zero local cells (2.9 seconds, 312 MiB sampled process-tree RSS).
- Measure cold and warm 2/4/8/12-member stack acceptance, worker startup, queue contention, first map availability, and actual browser application on production ARM64 hardware. Local synthetic timing is insufficient.
- Freeze settings and evaluate a specimen-separated, independently reviewed landmark cohort: median error <=50 micrometers, p95 <=100 micrometers, eligible coverage >=80%, zero confident wrong-structure matches. The reviewed cohort has not been supplied.
- Complete protected CI, dependency/asset receipts, ARM64 container checks, deployment, and authenticated production verification. The local Docker daemon was unavailable during implementation; the ARM64 native smoke job enforces 512 MiB and 1.75 CPUs.
- Shading correction remains disabled: no scanner calibration or controlled development-pair accuracy comparison establishes a benefit. Shape initialization is not evidence of anatomical identity.

Relevant upstream references: [OpenCV robust estimators](https://docs.opencv.org/4.13.0/d9/d0c/group__calib3d.html), [VALIS](https://github.com/MathOnco/valis), [BaSiCPy](https://github.com/peng-lab/BaSiCPy). No new registration dependency was added.
