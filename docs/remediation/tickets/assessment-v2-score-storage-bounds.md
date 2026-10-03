# Assessment v2 score storage and preflight validation

Labels: wayfinder:decision
Status: candidate; review, protected checks and released qualification pending
Owner: root

## Evidence and affected callers

At current production source ae9b1ac, the v2 compiler accepts finite points beyond the existing AssessmentScoreVersion Numeric(12,3) columns. It also accepts an exponent that cannot be quantized during shared score_item execution. Unlike the repaired v1 compiler, it checks neither quantization nor raw and separately rounded totals across sections. Server preflight, preview and publication all use this compiler; learner finalization and manual grading persist into the existing score columns.

Ten new regressions fail before repair: five compiler cases for oversized items and totals, and five actual HTTP cases for invalid points/preflight/publication. The invalid-string preflight fails in its float metrics calculation even after compilation correctly rejects the draft. Nonfinite metrics and accepted oversized drafts are retained as distinct red outcomes. Ignored receipt: var/remediation-v2-points-red.log.

Signed-in Edge created independent synthetic draft `Codex QA assessment ae9b1ac`, with no course, roster or learners. The editor saved oversized points and rendered its local learner preview; this is not proof of server rejection or score persistence. Correcting to1.25 showed All changes saved and a working answer selection. Reload qualification stopped when Computer Use could not confidently determine the current URL; persistence after that reload is unverified. No publication or feature activation was performed.

## Repair

Apply the existing score precision and maximum to v2 compilation. Bound the quantized raw total and the sum of separately rounded item maxima, and translate decimal failures to ASSESSMENT_POINTS_INVALID. Section information stays unscored. Preflight reports null points metrics when compilation fails rather than parsing an invalid draft again; the existing frontend contract already permits null metrics.

Preserve valid half-up scoring, editable invalid drafts, revision checks, section routing, invitation formats and release policy. No migration, existing learner record rewrite or feature activation.

## Verification

The four directly affected v1/v2 compiler and HTTP modules pass67 cases. The broader local assessment suite passes211 cases with9 skips;220 selected cases were independently collected. Ruff and mypy pass for changed sources. Boundary/half-up positive controls preserve valid maximum and information with unused invalid points. HTTP cases reject preview/publication, retain the original draft/revision, then publish a corrected document as version1. Protected PostgreSQL, browser/fullstack and release checks remain pending.
