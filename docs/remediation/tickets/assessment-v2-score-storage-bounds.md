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
