# First and repeated invocation results

Frozen registration source: `9eab3edeeedded8b2fca9c0521c88cdec388e0cc`. These are engineering observations; qualification is false and Fast/Accurate winners are null.

**Negative challenges:** VALIS pair ordinal15 and wsireg ordinal13 were accepted on both calls. These four negative maps require independent review. Accepted-map counts in the table include those negatives.

**Warm stage comparison:** none of the96 planned stage comparisons is measured. The24 available initializer artifacts are plain-JPEG payloads lacking the explicit geometry proof required by the warm scorer;72 are unavailable. Aggregate zero-support/coverage values are unmeasured denominator placeholders, not measured initializer performance. Do not compare those values against final-map coverage. Earlier producer-bound cold stage scores remain separate.

First invocation and same-contained-process repeat are separate observations. Times below cover measured invocation wall time, excluding input admission; accepted-only timing is also shown so rejection-heavy medians are not mistaken for useful-map speed.

| Recipe | Call | Planned | Executed | Unknown execution | Measured time | Missing receipt/result | Not executed | Registration rejects | Other failures | Accepted maps | All-time median/p95 s | Accepted-time median/p95 s | Supported/947 | Coverage | Relative TRE median/p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|---|
| native-overview-v6 | 1 | 16 | 16 | 0 | 16 | 0 | 0 | 4 | 0 | 12 | 1.3905/2.3985 | 1.2735/2.4797 | 360/947 | 38.01% | 0.0075042/0.0344415 |
| native-overview-v6 | 2 | 16 | 16 | 0 | 16 | 0 | 0 | 4 | 0 | 12 | 1.1795/2.30825 | 1.1565/2.36765 | 360/947 | 38.01% | 0.0075042/0.0344415 |
| valis-1.2.0 | 1 | 16 | 16 | 0 | 16 | 0 | 0 | 11 | 0 | 5 | 139/229.723 | 175.219/197.447 | 130/947 | 13.73% | 0.00333947/0.0139059 |
| valis-1.2.0 | 2 | 16 | 16 | 0 | 16 | 0 | 0 | 11 | 0 | 5 | 142.133/220.629 | 161.906/197.331 | 130/947 | 13.73% | 0.00333947/0.0139059 |
| wsireg-0.3.10 | 1 | 16 | 16 | 0 | 16 | 0 | 0 | 11 | 0 | 5 | 26.383/29.7425 | 26.391/27.059 | 165/947 | 17.42% | 0.00611691/0.0402231 |
| wsireg-0.3.10 | 2 | 16 | 16 | 0 | 16 | 0 | 0 | 11 | 0 | 5 | 8.547/11.4727 | 8.578/9.0662 | 165/947 | 17.42% | 0.00611691/0.0402231 |
| hisalign-0.2.1 | 1 | 16 | 16 | 0 | 16 | 0 | 0 | 12 | 0 | 4 | 9.9845/12.5462 | 9.859/10.818 | 114/947 | 12.04% | 0.00805125/0.0263981 |
| hisalign-0.2.1 | 2 | 16 | 16 | 0 | 16 | 0 | 0 | 12 | 0 | 4 | 8.719/10.254 | 8.836/10.0549 | 114/947 | 12.04% | 0.00805125/0.0263981 |
| deeperhistreg-classical | 1 | 16 | 16 | 0 | 16 | 0 | 0 | 15 | 0 | 1 | 4.2345/5.566 | 5.359/5.359 | 34/947 | 3.59% | 0.0527324/0.0924704 |
| deeperhistreg-classical | 2 | 16 | 16 | 0 | 16 | 0 | 0 | 15 | 0 | 1 | 0.922/1.41825 | 2.25/2.25 | 34/947 | 3.59% | 0.0527324/0.0924704 |
| deeperhistreg-learned | 1 | 16 | 3 | 13 | 3 | 13 | 0 | 0 | 2 | 1 | 16.782/17.3013 | 16.359/16.359 | 35/947 | 3.70% | 0.00316602/0.00890105 |
| deeperhistreg-learned | 2 | 16 | 3 | 0 | 3 | 0 | 13 | 0 | 2 | 1 | 14.531/14.5589 | 13.36/13.36 | 35/947 | 3.70% | 0.00316602/0.00890105 |
| native-wsireg | 1 | 16 | 16 | 0 | 16 | 0 | 0 | 12 | 0 | 4 | 28.062/31.8365 | 28.5545/28.7242 | 181/947 | 19.11% | 0.00736645/0.0890017 |
| native-wsireg | 2 | 16 | 16 | 0 | 16 | 0 | 0 | 12 | 0 | 4 | 9.6565/10.957 | 10.453/10.8285 | 181/947 | 19.11% | 0.00736645/0.0890017 |
| valis-rigid-wsireg | 1 | 16 | 16 | 0 | 16 | 0 | 0 | 14 | 0 | 2 | 149.702/233.32 | 173.476/198.008 | 106/947 | 11.19% | 0.00494616/0.0156998 |
| valis-rigid-wsireg | 2 | 16 | 16 | 0 | 16 | 0 | 0 | 14 | 0 | 2 | 135.188/215.558 | 153.851/179.846 | 106/947 | 11.19% | 0.00494616/0.0156998 |
| native-valis | 1 | 16 | 16 | 0 | 16 | 0 | 0 | 10 | 0 | 6 | 130.711/180.04 | 144.164/191.649 | 262/947 | 27.67% | 0.00426272/0.0137685 |
| native-valis | 2 | 16 | 16 | 0 | 16 | 0 | 0 | 10 | 0 | 6 | 128.258/173.441 | 134.547/185.137 | 262/947 | 27.67% | 0.00426272/0.0137685 |

Pair memory is sampled once for both calls, not attributed twice or divided between invocations. All numerical variants are retained in observations.json.

| Recipe | Recorded memory scope | Measured pairs | Pair peak RSS/working-set median/p95 bytes | Kernel-reported job peak median/p95 bytes |
|---|---|---:|---|---|
| native-overview-v6 | windows-job-sampled-working-set | 16 | 2.52594e+08/2.64988e+08 | 3.61628e+08/3.71139e+08 |
| valis-1.2.0 | windows-job-sampled-working-set | 16 | 4.71866e+09/5.98576e+09 | 4.84354e+09/6.60714e+09 |
| wsireg-0.3.10 | windows-job-sampled-working-set | 16 | 9.55886e+08/9.63295e+08 | 8.18391e+08/8.49359e+08 |
| hisalign-0.2.1 | windows-job-sampled-working-set | 16 | 1.00574e+09/1.10444e+09 | 1.01879e+09/1.10067e+09 |
| deeperhistreg-classical | windows-job-sampled-working-set | 16 | 4.94252e+08/5.57807e+08 | 6.03085e+08/6.86573e+08 |
| deeperhistreg-learned | windows-job-sampled-working-set | 16 | 6.65535e+09/6.87703e+09 | 7.6553e+09/7.6558e+09 |
| native-wsireg | windows-job-sampled-working-set | 16 | 1.06968e+09/1.08599e+09 | 1.06112e+09/1.07028e+09 |
| valis-rigid-wsireg | windows-job-sampled-working-set | 16 | 4.61287e+09/6.06623e+09 | 4.94265e+09/6.88054e+09 |
| native-valis | windows-job-sampled-working-set | 16 | 4.75207e+09/6.21763e+09 | 4.97873e+09/6.69243e+09 |

The table retains every planned ordinal; measured/accepted/executed counts differ. A child ending without a result and without an atomic started marker has unknown cause and no proven executed invocation. Supervisor wall time is not substituted for invocation wall time. Pair peak memory is measured once per two-call supervisor with its recorded scope; kernel and sampled peaks remain distinct, and configured limits do not imply every observed peak was below the limit.

Per-pair tissue/stain results are in pair-observations.json. They join only after exact pair order, input digests, original JPEG bytes, frame/crop semantics and fit-free ground-truth digest checks. No tissue label is inferred from appearance; the BIRL lesions sample organ remains unspecified. Negative pairs have no published positive landmarks and are not treated as measured zero-error pairs.

Stage contribution stays in the tracked reporter output: original-frame initializer output, affine actually applied on own support, and per-pair identical-common-support deltas. Quantiles across different pairs/support sets are never averaged. Residual warp-frame accuracy, retained-model warmth, decoded-pixel cache warmth, host filesystem cache state, micrometer accuracy, human effort, anatomical review and qualified Fast/Accurate winners remain unverified or null.

Historical b35 cold and fresh-process repeat results remain separate, unchanged evidence. Source/runtime differences prevent attributing comparisons to cache speedup. No new map fitting, engine rerun or readiness promotion is performed by this report. Paired original-pixel visual examples remain private and do not establish anatomical qualification.
