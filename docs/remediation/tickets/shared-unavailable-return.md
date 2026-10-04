# Return from unavailable shared links

Labels: wayfinder:ticket

The September 28 Antigravity reconciliation revision (SHA-256 ceafbc7455b16b9692cebf6810c89d4f596a2b66237f61a7a8616df9f20ffaf2, line 200, FE-89) identifies a caller missed by the original viewer.error-navigation repair. Unavailable public folders and collections render Retry without an exit. The original repair covers ViewerPage; this finding covers SharedViewerPage separately.

Add a native Go to library link to the existing /admin route. Keep Retry, authorization and invitation contracts. The existing AdminPage authentication boundary handles anonymous visitors. No library data is granted by a public share.

The two new unit cases fail against the original missing-link state and pass after repair; all eleven affected unit cases pass. Final browser qualification passes 32 cases across Chromium, Firefox, WebKit and mobile Chromium, both share types and four viewports (320x740, 768x1024, 900x420, 1584x992). It verifies Retry adds one request, keyboard focus/Enter, a 44px minimum target, viewport containment, real sign-in rendering and reload persistence. Light/dark and reduced-motion configurations are covered. Synthetic API fixtures deny private access; production is untouched.

The initial browser fixture incorrectly assumed one initial request under StrictMode. Preserve that failed run separately; the corrected fixture measures the initial count before Retry. An incidental Windows encoding change was restored from the exact UTF-8 Git blob before final qualification. Independent review of the final four-file diff is clear. Final full frontend passed573 tests across85 files in175.46seconds; lint and production build passed. Immutable distribution/inventory refresh and hosted release gates remain pending. At that local checkpoint, verified production remained c37cf81 and this repair was not deployed.

Evidence: docs/remediation/evidence/shared-unavailable-return.json and docs/remediation/ANTIGRAVITY_V2_RECONCILIATION.md. Local detailed logs remain under var/shared-unavailable-return-*.log.

## Completed local distribution and inventory verification

Implementation51f32a7b captured four graphs/125assets in6.76seconds; standard build6.53seconds emitted matching asset bytes and all three legal files. Receipt checkpoint8e2cc297 and software subject54943c9a preserve all582dependency records,612source/574build components and complete notice bytes. Deterministic software validation, both SPDX validators, Ruff and privacy checks over current tree/new history pass. Inventory regressions passed45cases with one Windows symlink-permission skip. Strict admission still returns expected exit1 for176unreviewed shipped inputs; no rights were inferred. Final independent semantic review is clear. At that local checkpoint, PR310 hosted gates and protected production delivery remained pending.


## Production5069c80 release checkpoint

PR310 repaired unavailable folder/collection return; PR311 added its omitted fixture to hosted CI. Both reviewed heads passed all nine gates before normal protected merges. Fresh main CI37175468040 attempt2 and Security37175468076 passed all nine latest exact-SHA checks. Browser285passed/3skipped includes all32 new cases; matrix855seconds stayed within960seconds. Retain attempt1's existing mobile annotation readiness failure before drawing assertions, unchanged20 focused replays and the one same-SHA failed-job retry. Assertions and timeouts were unchanged. Full-stack executed on attempt1 and GitHub carried its successful result forward:30expected/1skipped/0unexpected/0flaky,929.105seconds,productionTouched=false.

[Protected deployment37177663993](https://github.com/Enksodsoon/PathLab-Viewer/actions/runs/37177663993) succeeded at exact5069c80e6d5ecff079ab806fd7fb084f1d3119a2. Its actual restore reported69tables/106325files/3286131731bytes/schema20260907_0037 and restored database/file integrity. Fresh04:55:45UTC livez/readyz200 and anonymous assessment drafts401 passed. Classroom=true, general annotations=false and admin annotation canary=true inputs were preserved; Study retains its existing disabled gate. [Release receipt](../evidence/production-5069c80-release.json) and [exact-main gates](../evidence/main-5069c80-required-checks.json) record scope.

Fresh released native verification remains pending. The private assessment tab showed Administrator sign in; Windows input stopped because the helper could not confidently identify the current browser URL. Earlier c37cf81 native persistence checks remain separate. No new publication, learner submission, Cancel or access change was automated. Original954source entries/29aggregate subclaims/45campaign findings and all versioned aliases remain unchanged. Specific native action confirmations, human production drag observation, external secret provenance/rotation and OneDrive facts,176accountable software admissions/two exact unshipped source notice gaps and distinct-identity production admission qualification keep the full campaign open.
