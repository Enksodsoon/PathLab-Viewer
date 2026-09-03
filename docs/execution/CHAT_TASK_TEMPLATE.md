# Fresh-Chat Task Template

Use this template to start one task in a new chat. Replace the bracketed values, but do not paste the complete production plan into the chat.

```text
Execute PathLab execution task [TASK_ID] from
docs/execution/[PHASE_FILE].md.

Work in the PathLab Viewer repository. Read, in order:
1. docs/execution/README.md
2. only the [TASK_ID] card in docs/execution/[PHASE_FILE].md
3. only the card's Read first contracts
4. the current source and tests in the declared Change surface

Before editing or running evidence, verify every task ID/result in `Depends on`
against current origin/main and separately verify every external prerequisite
named by the card. Record their immutable receipts and the exact starting commit.
Use an isolated worktree and a codex/[task-id]-[slug] branch. Preserve unrelated
work.

Complete the card's full scope, tests, evidence, documentation, and rollback.
Use the Delivery State Ledger literally. Do not claim protected checks, merge,
deployment, pilot, qualification, or activation without direct receipts. Do not
lower frozen gates. Keep TRACE-SIM outside production. If the task reaches a
Stop/hand off condition, stop safely. Report the work status and blockers
independently; report PARTIAL, NEGATIVE, or NOT_EVALUABLE only when an
evaluation or gate actually ran. Never invent a workaround.

At the end, provide the structured handoff from
docs/execution/CHAT_TASK_TEMPLATE.md and identify only tasks directly unlocked.
```

## Required start record

```yaml
task_id: [TASK_ID]
task_title: replace with card title
repository: PathLab-Viewer
starting_default_branch_commit: full-sha
branch: codex/[task-id]-slug
worktree: absolute-path
dependency_receipts:
  - task_id: prerequisite-id
    required_state_or_result: MERGED-or-SUCCESS-as-declared-by-card
    observed_work_status: NOT_STARTED | IN_PROGRESS | WAITING_EVIDENCE | BLOCKED | DONE
    observed_lifecycle_state: PLANNED | IMPLEMENTED | CHECKED_LOCAL | CHECKED_PROTECTED | MERGED | DEPLOYED | PILOT_VALIDATED | PRODUCTION_QUALIFIED | ACTIVATED | ACTIVATION_SUSPENDED
    observed_gate_execution: NOT_APPLICABLE | NOT_STARTED | RUNNING | COMPLETE
    observed_gate_result: null | SUCCESS | PARTIAL | NEGATIVE | NOT_EVALUABLE
    evidence_validity: CURRENT
    subject_fingerprint: immutable-subject-hash
    commit_or_receipt: immutable-reference
external_prerequisite_receipts:
  - prerequisite_id: stable-local-label
    declared_kind: exact-card-kind
    required_disposition: exact-card-requires-value-verbatim
    observed_disposition: exact-observed-disposition-or-UNAVAILABLE
    accountable_party: exact-card-accountable-value
    declared_validity_rule: exact-card-validity-value
    evidence_validity: CURRENT | STALE | INVALIDATED | EXPIRED
    declared_evidence_type: exact-card-evidence-value
    subject_fingerprint: immutable-subject-hash
    receipt_or_artifact: immutable-reference
    expires_at: iso-8601-or-null
read_set:
  - docs/execution/README.md
  - exact task card
  - directly referenced contracts
out_of_scope:
  - copied from task card
```

If a task dependency is absent, stale, or only `IMPLEMENTED`/`CHECKED_LOCAL`, or if a required external-prerequisite receipt is unavailable, stale, expired, mismatched, or lacks its accountable party, do not start downstream work. Return a dependency handoff with work status `BLOCKED`, lifecycle state `PLANNED`, gate execution `NOT_STARTED`, and gate result `null`. Never use `NOT_EVALUABLE` merely because a prerequisite prevented the evaluation from running.

## Required completion handoff

```yaml
task_id: [TASK_ID]
work_status: NOT_STARTED | IN_PROGRESS | WAITING_EVIDENCE | BLOCKED | DONE
lifecycle_state: PLANNED | IMPLEMENTED | CHECKED_LOCAL | CHECKED_PROTECTED | MERGED | DEPLOYED | PILOT_VALIDATED | PRODUCTION_QUALIFIED | ACTIVATED | ACTIVATION_SUSPENDED
gate_execution: NOT_APPLICABLE | NOT_STARTED | RUNNING | COMPLETE
gate_result: null | SUCCESS | PARTIAL | NEGATIVE | NOT_EVALUABLE
evidence_validity: NOT_APPLICABLE | CURRENT | STALE | INVALIDATED | EXPIRED
subject_fingerprint: immutable-subject-hash-or-null
selected_deployment: exact-release-host-selection-receipt-or-null
receipt_cursor: immutable-cursor-or-null
next_audit_at: iso-8601-or-null
starting_commit: full-sha
implementation_commit: full-sha-or-null
pull_request: url-or-null
merged_commit: full-sha-or-null
contexts_changed:
  - bounded-context
files_changed:
  - repository-relative-path
migrations:
  - revision-or-none
schemas:
  - schema-id-and-version-or-none
checks:
  - command: exact command
    result: PASS | FAIL | NOT_RUN
    evidence: immutable-log-or-local-summary
receipts_or_artifacts:
  - immutable-path-hash-or-run-id
external_prerequisite_receipts:
  - prerequisite_id: stable-local-label
    declared_kind: exact-card-kind
    required_disposition: exact-card-requires-value-verbatim
    observed_disposition: exact-observed-disposition
    accountable_party: exact-card-accountable-value
    declared_validity_rule: exact-card-validity-value
    evidence_validity: CURRENT | STALE | INVALIDATED | EXPIRED
    declared_evidence_type: exact-card-evidence-value
    subject_fingerprint: immutable-subject-hash
    receipt_or_artifact: immutable-reference
    expires_at: iso-8601-or-null
security_privacy_rights_review: concise-result
resource_and_zero_cash_review: concise-result
rollback: exact rollback path
unresolved_blockers:
  - blocker-or-none
unlocked_tasks:
  - task-id-only-if-all-dependencies-now-satisfied
```

## Context-minimizing handoff rules

- Link immutable commits, pull requests, test runs, receipts, and artifacts; do not paste long logs.
- List exact commands and terminal results, but summarize output unless a failure message is necessary.
- Name files changed, not every file inspected.
- Record decisions only when an accepted ADR or task split changed the plan.
- A downstream chat should reload source from Git rather than rely on the prior chat's prose description.
- A campaign launch handoff records process identity, manifest hash, receipt cursor, health probes, and next audit time. It never reports `SUCCESS` before terminal closure.
- Work status, lifecycle state, gate execution/result, evidence validity, subject fingerprint and selected deployment are independent axes. Never infer one from another.
- External-prerequisite receipts never substitute for task receipts, and a prose assertion of availability, authority, rights, capacity or approval is not a receipt.
- If work is not merged, `unlocked_tasks` must be empty unless a card explicitly permits a coordinated stack.

## Pull-request body core

```markdown
## Execution task

- Task: `[TASK_ID]`
- Starting default-branch commit: `<full sha>`
- Context/authority: `<name>`
- Dependencies verified: `<task ids and immutable references>`
- External prerequisites verified: `<stable labels, dispositions and immutable references>`

## Outcome

<One paragraph matching the task card.>

## Evidence

- Local result: `<result and commands>`
- Protected result: `<run links or pending>`
- Migration/schema: `<ids or none>`
- Security/privacy/rights: `<result>`
- Resource/zero-cash: `<result>`

## Boundaries

- Not established: merge, deployment, pilot, qualification, activation unless separately evidenced
- Explicit exclusions: `<from card>`
- Rollback: `<path>`
```
