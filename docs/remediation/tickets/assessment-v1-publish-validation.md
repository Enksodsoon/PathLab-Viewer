# Assessment v1 publication validation

Labels: wayfinder:decision
Status: candidate
Owner: root

## Confirmed defect

PR291 CI logged an AssessmentLearnerQuestion missing-key warning during the 100-question authoring fixture. That fixture uses string options and an array answer key, unlike the declared id/label and answer-key object contracts. The warning alone does not prove an application failure.

Current-code reproduction at f96ead4 proves the v1 compiler accepts the same malformed shapes and exposes string options in the learner manifest. Scoring the compiler-accepted array answer key raises AttributeError: list has no get method. The admin preflight path incorrectly calls the malformed draft publishable. The preview/publish routes share that same compiler. Seven compiler and two actual HTTP regressions fail before repair; retain their red log and the compiler/scoring receipt.

## Repair and compatibility

Validate outer answer-key object shape, choice optionIds as an array of strings, and option objects with nonempty string identifiers and labels at v1 compilation. Retain option/item limits, valid v1 behavior, scoring, release policy and all routes. Draft create/save remains permissive for incomplete authoring; rejected publication leaves its document/revision unchanged, and a correction can publish as version 1. Existing stored definitions, annotations and learner records are not rewritten. No database migration is needed.

Correct the 100-question frontend test fixture to use the actual contract. Preserve its card-count, single-editor, navigator, persistence and preview assertions. Do not add UI tolerance that hides unpublishable data or guess answer identifiers.

## Verification and delivery

63 affected backend checks pass, including all nine regressions, v1 runtime/review and v2 contract/routes/operations/import checks. 22 frontend authoring/runtime checks pass without the missing-key warning. Ruff, scoped mypy, changed-file ESLint, public repository and security baseline checks pass. The source register retains all 954 report aliases and their dispositions; this is an additional campaign finding.

Receipts: assessment-v1-publish-shape-reproduction.json, assessment-v1-publish-red.log, assessment-v1-publish-green.log, assessment-v1-publish-regressions.log and assessment-v1-authoring-validation.log in the ignored local release evidence directory.

Fresh exact-head/main checks, protected production delivery retaining feature settings and applicable released verification remain required. Previously released folder/320px annotation verification, action-time Cancel approval and external secret/OneDrive facts remain open independently.
