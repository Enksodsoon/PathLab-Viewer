# Assessment local recovery after failed saves

Labels: wayfinder:decision
Status: confirmed; separate candidate under qualification

## Current-code evidence and decision

At base44ed2de, a failed PATCH leaves the locally cached edited document at the unchanged server revision. Reload picks the server because recovery only checks cached.revision > server.revision. An independent component reproduction loses the locally retained title. Recover divergent cached documents when their revision equals the server revision; continue rejecting older cached revisions. Preserve optimistic If-Match and the existing higher-cache behavior. No local metadata or API contract changes.

The initial storage-write component control passed before any fix: successful server acknowledgments still occur when cache writes reject. It does not establish error containment. An independent native-browser fixture denying IndexedDB records two unhandled page errors during one successful save. Contain both local writes, scope failure notices to the active draft load, and display Local recovery unavailable. Keep this tab open until changes are saved. Server save status remains separate and accurate. Rejected initial recovery reads also show that notice.

## Qualification

Initial recovery red fails; two subsequent controls (server acknowledgment with write rejection and older-cache exclusion) pass. After equal-revision recovery,45affected tests pass and four zero-retry browser cases pass26.7seconds across four projects using actual IndexedDB: firstPATCH503, reload local title, second If-Match1, acknowledged revision2 and reload without another save. First build fails TypeScript narrowing of a closure-written test variable; corrected assertion reads the recorded cache call. Build9.82seconds passes. The write-error browser red records two Synthetic recovery denied page errors. Final affected and eight-browser qualification after error containment is pending.

After error containment, all eight browser cases pass39.9seconds with zero retries across four projects, including the visible recovery-unavailable notice and no unhandled page errors. Current build6.50seconds and lint pass. Three older authoring cases failed because their cache mock returned undefined rather than the actual Promise<void> contract. Correct that stub to resolve undefined; retain the failure log and rerun the final affected suite. Renewed review and complete hosted checks remain required.

## Limits

This does not identify the historical failed production save's HTTP cause, establish a complete offline workflow, qualify cache write ordering/transaction aborts, or repair import/autosave races. The server's newer revision remains authoritative. Parent PR299 must complete exact-head checks and merge before this candidate is rebased and released. Strict software admission and external security facts remain unresolved.

Ignored receipts: assessment-local-recovery-red.log, assessment-local-recovery-green.log, assessment-local-recovery-browser.log, assessment-recovery-write-red.log, assessment-local-recovery-build.log, assessment-local-recovery-build-qualified.log, assessment-local-recovery-final-tests.log and assessment-local-recovery-final-browser.log.

Final corrected affected suite:45passed61.35seconds. Eight zero-retry browser cases39.9seconds and build6.50seconds pass. Renewed independent review reports no actionable findings. Complete hosted qualification and protected delivery remain required.

Complete final-source frontend qualification passed538tests across83files262.47seconds. Asset-rights validator passes16ADMITTED; deterministic software validator passes612components with strict BLOCKED admission unchanged. No accountable software rights granted. The later import-boundary reproduction was not part of this collected suite and is a separate candidate.
