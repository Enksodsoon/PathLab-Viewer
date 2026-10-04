# Hosted coverage for unavailable shared links

Labels: wayfinder:ticket

PR310 reviewed head5b4db461 passed all nine campaign gates and merged at48434dd. Its complete local qualification includes32 unavailable-return cases across four engines and four viewports. Hosted browser CI37172958003 passed253 existing cases, but the workflow uses an explicit file list that omitted the new shared-unavailable-return.spec.ts. This is a verification integration gap introduced with the new fixture, not another application defect. The repaired control has not been deployed yet.

Add the new file to that existing explicit matrix. Retain two workers, zero-retry behavior and the16-minute step budget. The previous matrix took13.5minutes; the isolated32-case local matrix took1.6minutes. Actual hosted runtime and the resulting case count must be verified before release. Do not infer this coverage from green checks that omit the fixture.

Application sources and dependencies remain unchanged from PR310. Since the provenance boundary includes ci.yml, refresh the immutable browser receipt and deterministic inventories without narrowing that boundary or changing any rights/admissions. Retain original954 findings/29 aggregate claims and45 application campaign findings. Require all nine fresh reviewed-head/main gates, then protected production delivery and native return-control verification.
