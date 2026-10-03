# Assessment save acknowledgments and optional recovery storage

Labels: wayfinder:decision
Status: confirmed; candidate under qualification

## Evidence and decision

At base2289b45, edit a draft, keep its PATCH pending, then edit again and let both750ms debounce timers expire. Two PATCH calls carry the same revision. The independent reproduction fails with two calls instead of one. Serialize saves within a draft load; after acknowledgment, retain newer edits and send them against the acknowledged revision. Keep the backend optimistic revision contract unchanged.

If IndexedDB recovery lookup rejects with SecurityError while the server draft loads successfully, Promise.all rejects and the editor reports Unable to open draft. The independent storage-denial case fails. Treat recovery-cache reads as optional; preserve actual server-load failures and the Retry control.

The initial boolean pending guard passed40affected tests, but independent review identified a lifecycle regression: changing drafts while a save stalls blocks the next draft. A new deferred-save/navigation reproduction fails. Scope the pending token to a load generation and ignore old-generation completions. The existing Upgrade to sections flow can navigate to a different draft in the same builder component, so this is an affected product caller.

Two initial component hypotheses did not reproduce: newer edits were kept unsaved after an older acknowledgment, and the latest local cache call retained newer edits. Keep both passing cases as regression controls. Independent browser qualification subsequently exposed an intermediate All changes saved render after the first acknowledgment while the latest edit still waited; Firefox, WebKit and mobile Chromium observed only revision1sent at that message. Keep Saving until the acknowledged document is the latest local document. Two initial Chromium cases stopped at module startup (Opening Assessment) before draft actions; retain separately and allow a bounded45second initial-load assertion.

## Limits and follow-up

Cache-write denial, same-revision dirty-cache recovery, import/autosave races and precise HTTP failure feedback remain separate investigations. The first failed production points save has no captured request status and is not attributed to this concurrency finding. No API, database, scoring, publication, permission, feature-gate or dependency changes.

Receipts in ignored var: assessment-save-recovery-red.log, assessment-save-recovery-green.log, assessment-save-recovery-qualified.log, assessment-save-route-red.log, assessment-save-generation-green.log and assessment-save-build.log. Final review, complete qualification and protected release remain required.

Final affected suite passes42tests after the status repair. Eight browser cases pass38.8seconds with zero retries across four projects, including latest-title persistence after reload and local storage denial. Current three changed source/test files pass lint. Renewed independent review has no actionable findings. Complete frontend qualification and protected delivery remain pending.

Complete local frontend run passes535tests across82files in539.23seconds. This run began before the final status adjustment, so it is retained as broader regression evidence rather than exact final-source qualification. The final42affected run, eight browser cases, lint and production build8.69seconds cover the revised source. Fresh hosted exact-head complete checks remain required before merge.

## Required full-stack fixture repair

At44ed2de, CI37137449081 passed eight required contexts but failed fullstack: a generated share public ID began with a hyphen, and the fixture subprocess passed it as an option to argparse. A deterministic direct Node-to-Python red reproduces unrecognized arguments. Pass the end-of-options delimiter before the subject. The same actual caller then reaches the disposable database lookup and rejects a missing synthetic share. The added full-stack regression asserts that lookup error rather than random token selection. No share generator, authorization boundary, capacity control or application API changes. Changed-file lint passes; fresh complete exact-head gates and renewed review remain required. Ignored receipts: var/pr299-fullstack-failure.log, var/fixture-hyphen-red.log and var/fixture-hyphen-green.log.
