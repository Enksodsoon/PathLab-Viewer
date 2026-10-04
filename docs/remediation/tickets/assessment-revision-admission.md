# Assessment revision admission

Labels: wayfinder:ticket

At main9ea88b9, two authenticated draft mutations can both read revision1 and return200/revision2, overwriting one accepted document. Actual HTTP interleaving reproduces save/save, save/import and import/import. A save paused after reading an editable draft also returns200 after another request archives it. Four original-source failures are retained in var/assessment-draft-concurrency-red.log.

Admit existing draft document mutations with one conditional database UPDATE matching draft id, organization, expected revision and draft status. A successful update increments revision once and commits the accepted document. A rejected update rolls back before rechecking current ownership/status and returning the existing conflict response. Capture immutable identity before rollback. Keep the successful request's acknowledged snapshot; no fresh read that could acknowledge another writer. Existing header/body contracts, source eligibility, publication policy and limits remain unchanged.

Callers: PATCH draft authoring/rename and POST import-questions; frontend autosave, manual retry and import all depend on truthful revision admission. Duplicate and migration create new drafts. Archive changes status without replacing document/revision.

Four SQLite cases pass. With existing admin/import controls the focused suite passes22 and skips4 PostgreSQL cases locally because no disposable PostgreSQL URL is supplied. PostgreSQL cases use generated private schemas and are explicitly included in the protected integration job. Ruff and mypy pass. Full backend qualification, renewed independent review, hosted PostgreSQL execution and all nine exact-head gates remain pending.

An initial green run failed one fixture assertion: GET intentionally rejects archived drafts. The corrected assertion checks GET409 and reads the stored archived document through the test database session. Original failure receipt retained. No production fault injection or delivery claim.

Independent review intercepted actual PostgreSQL connection arguments and found that application timeout options override the first fixture's URL search_path. Correct the fixture by merging its generated search_path into the application's connect_args while retaining timeouts. Assert current_schema before create_schema or synthetic writes; dispose all generated-schema engines even on setup failure. Four SQLite cases still pass and four PostgreSQL cases skip locally. Actual PostgreSQL isolation/execution remains a hosted qualification gate.

Dependency: merge this atomic backend repair before delivering PR304 lost acknowledgment reconciliation; then rebase that PR and rerun required checks. Ignored receipts: var/assessment-draft-concurrency-red.log, var/assessment-draft-concurrency-green.log, var/assessment-draft-concurrency-final-focused.log, var/assessment-revision-full-backend.log.

Renewed independent review is clear. Intercepted connection options include both existing timeouts and the isolated search_path; no external database was contacted. Deterministic software validation passes612components while strict releaseAdmission remains BLOCKED; asset ledger16records passes. Original954 report aliases and aggregate claims are unchanged. Full local backend execution remains in progress when this candidate is opened for hosted qualification; it is not merge-ready until all checks finish.


## Verified production delivery at c570116

PR305 merged6331154 and final reviewed PR304 mergedc570116 through normal protections. All nine fresh c570116 main checks passed in CI37157146069/Security37157146107. Protected deployment37158209056 succeeded at exact c570116 with actual database/files restore69tables/106325files/3286131731bytes/schema20260907_0037. Fresh livez/readyz200 and anonymous actual assessment drafts401 passed. Native signed-in synthetic assessment description edit showed All changes saved and persisted after explicit browser Refresh with both questions/2.502points. Refreshed Library opened synthetic B patterned tiles and two saved rectangles with NO CHANGES. No production concurrency/response-loss injection, publication, learner attempt or Cancel/delete was performed. [Release evidence](../evidence/production-c570116-release.json) retains remaining external/approval/admission requirements. The campaign remains open.
