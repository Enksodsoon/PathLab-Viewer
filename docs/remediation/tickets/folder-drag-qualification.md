# Native folder moves and dialog Escape

Labels: wayfinder:decision
Status: merged; protected release pending

## Evidence and repair

The approved campaign requires end-to-end coverage for folder drag/drop and its accessible Move fallback. Previous component and Move checks did not exercise native folder drag against the backend.

On release source 68e0a038, native Chromium dragging a root folder onto another folder produced no PATCH; the browser command stalled at mouse release. Starting a drag inserts the top-level target into the list and moves the folder targets. A minimal native stable-row fixture drops successfully, while equivalent row insertion reproduces the stall. Keep the top-level target out of the list's flow and center its label over the folder section header. The actual folder target then receives the drop, the real API acknowledges parentId with 200, and reload preserves the hierarchy.

That native scenario also exposed Escape leaving the Move dialog open because the navigator's document handler prevents the native dialog cancel. Yield when an open dialog owns the key event, or another control has prevented it. Native cancellation closes the dialog while retaining the navigator.

WebKit's native transfer drops the custom folder MIME type: a minimal fixture delivers text/plain but strips application/x-pathlab-folder-id from dragover and drop. The application consequently rejects the gesture before receiving drop. Use the ID of the active drag already started in this tree when custom data is absent, clearing it on drop and dragend. External text never supplies a folder identity. Existing cycle guards and protected API authorization still apply. This fixes native WebKit nesting and top-level return against the actual backend.

Chromium, Firefox and WebKit full-stack scenarios pass native nesting, reload, blocked descendant drag, omission of that descendant from Move choices, modal Escape, native top-level drop, and accessible Move in both directions with reload. Mobile Chromium also passes the accessible Move, dialog Escape and reload path on its disposable stack. Focused folder/library unit checks pass49tests, including discarded custom data, external text rejection and gesture cleanup. TypeScript, changed-file lint and production build pass. Retain original failures and native traces separately; no production learner or source slide is touched by these tests.

## Release boundary

PR288 head a4dc5b356ea8ff645979fdaf520cafd428ae5b30 passed eight of nine delivery checks, including1350 backend,490 frontend,144 PostgreSQL and233 browser tests. Its Linux real full-stack run37096356564 failed the new folder scenario at the first native move with no PATCH acknowledgment;24 other scenarios passed, one skipped and two dependent security scenarios did not run. This contradicts extending the Windows local qualification to Linux. Do not merge, call the gesture repaired everywhere, or rerun without stronger evidence. The original job did not retain its attached trace. Add always-retained synthetic full-stack reports/artifacts and bounded native event output, preserving the failing gesture and product implementation for diagnosis.

Production 68e0a038 shipped successfully through protected run37093695257 after all nine required checks passed. Restore verified69tables/106325files and public health returns200. Fresh signed-in synthetic annotation edits survive reload. These folder/modal repairs are subsequent unmerged work and require fresh review, exact-head/main checks, protected delivery and live qualification.

Receipts are in the follow-up worktree's ignored var/remediation-evidence: folder-drag-native-trace, native-drag-driver-probe.log, native-drag-reflow-probe.log, folder-drag-layout-fixed-chromium, folder-drag-escape-fixed-chromium, folder-drag-top-level-chromium, native-webkit-types-probe.cjs, native-webkit-drop-data-probe.cjs and folder-drag-local-identity-webkit. The first two instrumented runs retained their timeout failures. One subsequent WebKit attempt stopped in setup because a global Create locator ambiguously matched the closing dialog; the test now scopes Create to its command bar. No severity or global zero-bug claim is inferred.

## Retained Linux diagnosis and gesture correction

Diagnostic head f8bf0bb retained CI37097769206's terminal failure:24 passed,1 failed,1 skipped,2 dependent scenarios not run. Eight other delivery checks passed. Its native drag event receipt is empty. Trace input shows source hover/down at(206,9), then target hover at(206,360); the drawer scrolls between held-pointer actions before any dragstart. This supports initiating the native gesture before target actionability can scroll away the source. It does not establish an additional product defect or a Playwright driver defect. Linux qualification remains pending at the corrected test head.

A separate populated-drawer probe with12 preceding root folders reproduced the top-level return helper moving to y=-159, outside the viewport. Scrolling that target into view with native held-pointer hover corrects the helper; real backend nesting, native return, cycle guards, Escape and Move/reload passed locally in Chromium, Firefox, WebKit and mobile Chromium (Move only). Promote the populated fixture and corrected top-level helper; start nesting with a physical12px pointer movement before target hover. No synthetic drag/drop dispatch or mocked server acknowledgment is introduced. Two additional edge-scroll probes passed without reproducing the Linux first-move failure; retain that limitation.

Independent authenticated production68e0a03 failure-path check: the disposable B slide retained an unsaved title after offline Save reported Failed to fetch, displayed SAVED after reconnection, and preserved the title after full reload. Tab networking was restored and the separate paused upload tab was untouched. Receipt: production-68e0a03-offline-save-recovery.json in the release evidence directory.

The corrected canonical populated-drawer scenario now passes all four local targets: native Chromium, Firefox, WebKit and mobile Chromium accessible Move. Changed-file ESLint and security baseline validator pass. These local receipts do not replace the new Linux CI gate.

## Verified Linux result and merge

Corrected head b9f40bd passed all nine delivery checks. Retained Linux fullstack37099639768 passed27 cases,skipped1,and reported no failures. PR288 merged as c1ab7f7ad414325f298193d5411a8d747b929f43. The earlier first-move failure is historical evidence; the corrected native gesture succeeds on Linux. Exact-main CI37100724086/Security37100724053 are running; production remains68e0a038 until protected deployment and live verification.

## Protected delivery update - 2026-10-03

This repair is included in production `bd69848` after all nine exact-main checks passed and protected deployment 37107676115 succeeded. See [release evidence and open checks](remaining-campaign-closure.md#protected-delivery-update---2026-10-03). Relevant signed-in repair verification remains open; earlier pending statements retain historical states.
