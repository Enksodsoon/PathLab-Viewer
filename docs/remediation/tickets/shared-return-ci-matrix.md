# Hosted coverage for unavailable shared links

Labels: wayfinder:ticket

PR310 reviewed head5b4db461 passed all nine campaign gates and merged at48434dd. Its complete local qualification includes32 unavailable-return cases across four engines and four viewports. Hosted browser CI37172958003 passed253 existing cases, but the workflow uses an explicit file list that omitted the new shared-unavailable-return.spec.ts. This is a verification integration gap introduced with the new fixture, not another application defect. The repaired control has not been deployed yet.

Add the new file to that existing explicit matrix. Retain two workers, zero-retry behavior and the16-minute step budget. The previous matrix took13.5minutes; the isolated32-case local matrix took1.6minutes. Actual hosted runtime and the resulting case count must be verified before release. Do not infer this coverage from green checks that omit the fixture.

Application sources and dependencies remain unchanged from PR310. Since the provenance boundary includes ci.yml, refresh the immutable browser receipt and deterministic inventories without narrowing that boundary or changing any rights/admissions. Retain original954 findings/29 aggregate claims and45 application campaign findings. Require all nine fresh reviewed-head/main gates, then protected production delivery and native return-control verification.

## Local completion checkpoint

The actual workflow selector resolves288 tests, including32 unavailable-return cases. Isolated compilation atc8fb6781 captures four graphs/125assets in6.06seconds; existing standard output matches every asset and all three legal files. Receipt67f3e25e and software subjecte1695fe8 preserve all582dependency records,612source/574build components, complete notice bytes and176accountable admission blockers. Deterministic inventory validation, both SPDX validators, privacy/current history and independent semantic review pass. Application files are identical to the PR310 source qualified by573frontend/32newbrowser cases; no additional local application rerun is claimed. Fresh hosted285-case completion and all nine reviewed-head/main gates remain pending. [Structured checkpoint](../evidence/shared-return-ci-matrix.json) separates selector resolution from execution.
