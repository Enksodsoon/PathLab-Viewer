# Assessment v2 score storage and preflight validation

Labels: wayfinder:decision
Status: candidate; review, protected checks and released qualification pending
Owner: root

## Evidence and affected callers

At current production source ae9b1ac, the v2 compiler accepts finite points beyond the existing AssessmentScoreVersion Numeric(12,3) columns. It also accepts an exponent that cannot be quantized during shared score_item execution. Unlike the repaired v1 compiler, it checks neither quantization nor raw and separately rounded totals across sections. Server preflight, preview and publication all use this compiler; learner finalization and manual grading persist into the existing score columns.

Ten new regressions fail before repair: five compiler cases for oversized items and totals, and five actual HTTP cases for invalid points/preflight/publication. The invalid-string preflight fails in its float metrics calculation even after compilation correctly rejects the draft. Nonfinite metrics and accepted oversized drafts are retained as distinct red outcomes. Ignored receipt: var/remediation-v2-points-red.log.

Signed-in Edge created independent synthetic draft `Codex QA assessment ae9b1ac`, with no course, roster or learners. The editor saved oversized points and rendered its local learner preview; this is not proof of server rejection or score persistence. Correcting to1.25 showed All changes saved and a working answer selection. Reload qualification stopped when Computer Use could not confidently determine the current URL; persistence after that reload is unverified. No publication or feature activation was performed.

## Repair

Apply the existing score precision and maximum to v2 compilation. Bound the quantized raw total and the sum of separately rounded item maxima, and translate decimal failures to ASSESSMENT_POINTS_INVALID. Section information stays unscored. Preflight reports null points metrics when compilation fails rather than parsing an invalid draft again; valid metrics use Decimal consistently with compilation and scoring. The existing frontend contract already permits string/null metrics.

Preserve valid half-up scoring, editable invalid drafts, revision checks, section routing, invitation formats and release policy. No migration, existing learner record rewrite or feature activation.

## Verification

The four directly affected v1/v2 compiler and HTTP modules pass67 cases. The broader local assessment suite passes211 cases with9 skips;220 selected cases were independently collected. Ruff and mypy pass for changed sources. Boundary/half-up positive controls preserve valid maximum and information with unused invalid points. HTTP cases reject preview/publication, retain the original draft/revision, then publish a corrected document as version1. Protected PostgreSQL, browser/fullstack and release checks remain pending.

Review identified accepted Decimal spelling `1__0` crashing float metrics. An actual HTTP regression fails before the follow-up and now returns valid preflight with10 points, successful preview/publication. The four affected modules now pass68 cases. Four PostgreSQL cases use temporary tables with actual ORM score-column types to test the valid maximum, half-up persistence and SQLSTATE22003 overflow; they are explicitly skipped without the isolated database and added to the hosted postgres gate.

Disposable real-backend assessment selection passes5 cases, zero skips/unexpected/flaky outcomes; receipt var/qa296/fullstack.json. This run predates the Decimal-metrics follow-up, which requires refreshed applicable checks. Existing published definitions were not rewritten or independently audited for historical oversized scores; that qualification remains open. No activated Study or physical-device claim.

After the review fix and rebase onto merged Inspector main af2c33f, the full local assessment selection passes212 cases,13 explicit skips and1248 deselected, in19.45seconds. Ruff/mypy pass. A refreshed real-backend selection is running at var/qa296b; no result is claimed until terminal completion.

The refreshed var/qa296b selection completed successfully:5passed,0skipped/unexpected/flaky, in52.17seconds. Independent follow-up review accepted the score/Decimal repair and PostgreSQL probes. The hosted postgres job at prior head8fb16eb completed successfully; actual final-head delivery gates remain required.

Further actual HTTP probes reproduced six preflight shape crashes at that candidate: null sections, section, items, item, options and optional release. Saved editable drafts are allowed by the existing API, but preflight traversed them before guarded compilation. Six additional regressions fail before the shape fix. Traverse only list/dict structures for warnings/metrics; keep the original document for contract validation, and preserve manual release defaults for an absent/null optional release. The drafts and revisions remain unchanged. This expands the same v2 preflight repair batch; renewed review and exact-head checks are required.

The six shape regressions now pass in the full local assessment selection:218passed,13explicit skips,1248deselected,21.55seconds. Ruff/mypy and diff whitespace checks pass. Prior head8fb16eb CI37120800790 completed successfully, including actual PostgreSQL score-column probes; those hosted results predate the shape guards. Final-head review and all delivery gates must be renewed.

Fresh signed-in native Edge navigation through Teaching Studio shows synthetic draft revision7, unpublished version0. Reopening the draft through its dashboard entry loads the saved title, question and corrected1.25points with All changes saved. This qualifies server-backed reopen persistence; the earlier interrupted reload remains unverified.

A follow-up actual HTTP probe confirmed a list-valued question type crashes before validation.22additional regressions fail at a5ee292:20saved-draft HTTP cases and2schema compiler cases using list/object values across type, rating, routing, answer-key and media/mark enums. Additional-media fixtures include a valid primary image so they reach the affected validator. Existing contract codes now handle these invalid values before hashing.39red regressions across this batch; the full expanded assessment selection passes240cases,13explicit skips,1248deselected in26.62seconds. Ruff/mypy/diff checks pass. The accepted review and5real-backend cases at a5ee292 predate these field guards; renewed review and final-head delivery checks remain required.

A new full native browser Refresh completed this continuation and rendered the saved synthetic question,1.25points,selected Option1 and All changes saved. Library navigation succeeded afterward. This supersedes the earlier interrupted reload limitation for this synthetic draft; no publication, learner submission or candidate-release qualification is claimed.

Schema HTTP qualification found preflight selected schemas outside its existing error handler, while duplicate/migration also let schema contract errors escape.18actual HTTP checks cover list/object/unknown schemas across preflight,preview,publication,duplication,migration andimport. Corrected baseline:9crashes and9already structured rejection controls. Initial import422expectation was false:existing404ITEM_NOT_FOUND is retained, with untouched source/destination documents/revisions. Move preflight schema selection into its handler and translate duplicate/migration schema failures to existing422errors.48proven red cases across the batch; final expanded assessment selection258passed,13explicit skips,1248deselected,33.90seconds; Ruff/mypy/diff checks pass.

All nine exact-head gates passed at prior4615c0b, CI37122576036/Security37122576032. Those gates predate the route follow-up and do not substitute for renewed review/checks. Stress began at that prior head:1/5/10/20-session five-minute phases completed with0errors;30minute soak remains running. Library workload source is unchanged by the schema-route repair. Existing published definitions, candidate release and other remaining campaign items stay unqualified.
