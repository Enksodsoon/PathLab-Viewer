# Existing cold initializer-to-final tradeoffs

[The bound audit](cold-stage-audit.json) reuses actual b35 maps and existing pointwise posthoc scores: zero registration reruns, zero new landmark evaluation, and 12 descriptor-bound initializer stages among 48 planned hybrid cold rows. Missing/rejected stage rows remain in the audit. Full recipe comparisons against individual method outputs are separate from initializer-stage comparisons.

Each row below compares final hybrid (left) to its initializer engine output (right), on exactly the same fit-free published landmarks supported by both original-coordinate maps. Deltas use original reference-image-diagonal units; negative is lower error. `median paired delta` is the median of individual landmark error differences, not the difference of two subset medians. Gain/loss counts are final-only/initializer-only support. These are per-pair tradeoffs, not pooled error quantiles or qualified improvement.

| Recipe | pairIndex | Common support | Gained | Lost | Median paired delta | Common-set p95 delta |
|---|---:|---:|---:|---:|---:|---:|
| native-valis | 3 | 7 | 16 | 2 | 0.00017810201 | -0.00051548261 |
| native-wsireg | 4 | 28 | 33 | 1 | 0.043955468 | 0.077362714 |
| valis-rigid-wsireg | 4 | 57 | 11 | 2 | -0.00088134116 | -0.0044013935 |
| native-valis | 4 | 29 | 39 | 0 | -0.0038833977 | -0.0016810428 |
| native-wsireg | 6 | 39 | 8 | 18 | -0.017850626 | -0.03853447 |
| native-valis | 6 | 39 | 8 | 18 | -0.019748717 | -0.03818517 |
| native-wsireg | 8 | 27 | 6 | 20 | -0.0036872318 | -0.010674894 |
| native-valis | 9 | 11 | 5 | 19 | -0.00019852016 | 0.0010917569 |
| native-wsireg | 10 | 32 | 8 | 3 | -7.7841333e-05 | -0.00029259103 |
| valis-rigid-wsireg | 10 | 32 | 6 | 2 | -0.0020172311 | -0.0017434716 |
| native-valis | 10 | 32 | 8 | 3 | -0.00074704576 | -0.0011293917 |
| native-valis | 11 | 48 | 20 | 0 | -0.00020053128 | -9.8987543e-05 |

Native->VALIS had lower median paired delta in 5/6 measured rows and lower common-set p95 in 5/6; Native->wsireg in 3/4 and 3/4; VALIS-rigid->wsireg in 2/2 and 2/2. Individual rows show lost support and worsened errors too. The affine projection is scored only within initializer-supported cells; the complete initializer piecewise map was not applied to the residual warp. Residual-frame accuracy is NULL because its warped input frame is not original source coordinates. Uncalibrated error, missing anatomical review and development reuse prevent qualification. Fast/Accurate winners remain NULL.
