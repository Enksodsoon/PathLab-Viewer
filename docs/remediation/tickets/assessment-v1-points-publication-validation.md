# Assessment v1 points publication validation

Labels: wayfinder:decision
Status: verified affected tests; complete checks pending
Owner: root

## Confirmed defect and current callers

At13948ba invalid/NaN points raise decimal.InvalidOperation rather than AssessmentContractError; admin preflight/preview/publish catch only the contract error. Infinity publishes but score_item quantization raises InvalidOperation. A huge finite exponent publishes but scoring overflows. Existing AssessmentScoreVersion points/maximum_points columns are Numeric(12,3), and submission stores their sums without an earlier capacity check. Information compilation ignores points but scoring parses their unused value before returning zero.

Twelve compiler/HTTP regressions fail before repair. The actual HTTP tests preserve the invalid editable draft, reject preflight/preview/publication, then correct and publish version1. Valid precision boundary and existing half-up rounding are positive controls. Negative Infinity already rejects correctly; do not count it as a new defect.

## Resolution

At the shared v1 compiler reject malformed or nonfinite scored points using ASSESSMENT_POINTS_INVALID. Translate decimal parsing/quantization exceptions into that same contract error. Bound both quantized raw maximum and sum of independently rounded item scores by the existing Numeric(12,3) storage capacity. This is a storage representation constraint, not a guessed assessment policy cap. Information returns its existing zero score before unused-point parsing.

Keep editable drafts, route formats, release/scoring policy, permissions and feature settings. No database migration, existing definition rewrite or learner mutation. The prior option/answer-key repair remains intact.

## Verification and open delivery

Affected eight-module assessment set:77 passed, including v1/v2 runtime/admin/review/contract/operations/import. Ruff and scoped mypy pass. Complete local backend:1356 passed,100 skipped,0 failures/errors in648.968s; existing dependency deprecation warnings are retained separately. New repair needs fresh protected CI, PostgreSQL checks and production delivery. Existing folder/320px live checks and external operator facts remain open.

Receipts in ignored var/remediation-evidence: assessment-points-boundary-reproduction.json (in followup worktree), assessment-points-red.log, assessment-points-green.log, assessment-points-backend.log and XML.
