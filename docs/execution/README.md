# Full-Surface Execution Playbook

This directory converts the ratified [Final Production Endpoint](../architecture/FINAL_PRODUCTION_ENDPOINT.md) into dependency-ordered work packages sized for separate Codex chats. It is a delivery map, not proof that any package has been implemented, checked, merged, deployed, piloted, qualified, or activated.

Delivery is tracked in [issue #188 — Implement and qualify the ratified PathLab Full-Surface endpoint](https://github.com/Enksodsoon/PathLab-Viewer/issues/188); the closed ratification decision remains recorded separately in issue #187 and the architecture documents.

## How to use this playbook

1. Select exactly one task whose dependencies are all evidenced as `MERGED` or at the stronger state explicitly required by that task.
2. Start a fresh chat with the task ID and the prompt in [CHAT_TASK_TEMPLATE.md](./CHAT_TASK_TEMPLATE.md).
3. Let that chat read only this file, its one task card, the card's `Read first` contracts, and the source files it actually changes.
4. Use a fresh branch or isolated worktree from the exact prerequisite default-branch commit. One task normally produces one focused pull request.
5. Require the task's local checks, protected checks, migration/runbook updates, and evidence artifacts before merging.
6. Record the handoff using [CHAT_TASK_TEMPLATE.md](./CHAT_TASK_TEMPLATE.md). A later chat must verify the receipt or pull request rather than trusting a prose claim.
7. Select the next newly unblocked task. Do not preload later phases into the current chat.

The phase plans are:

| Phase | Plan | Terminal result |
| --- | --- | --- |
| 0 | [Canonical plan, freedom, rights, and supply chain](./PHASE_0_CANONICAL_AND_FREEDOM.md) | No unresolved authority, license, asset-rights, zero-cash, or destination decision |
| 1 | [Resident runtime and context data plane](./PHASE_1_RESIDENT_FOUNDATION.md) | Clean-host, offline install, upgrade, rollback, containment, key, and foundational recovery evidence |
| 2 | [Trust, governance, operations, and protection](./PHASE_2_TRUST_AND_OPERATIONS.md) | Identity, role, approval, retention, deletion, audit, backup, and restore adversarial gates |
| 3 | [Imaging migration and re-admission](./PHASE_3_IMAGING.md) | Viewer, Library, upload, DZI, shares, annotations, and Desktop compatibility requalified on PostgreSQL |
| 4 | [Learning foundation](./PHASE_4_LEARNING.md) | Catalog, deterministic learning, Teacher Authoring, Live Learning/media, and Assessment gates |
| 5 | [Standards and specialist contexts](./PHASE_5_SPECIALIST_CONTEXTS.md) | Integration, credentials, EQA, Clinical Shadow, Research, and Edge gates |
| 6 | [Portability and complete operations](./PHASE_6_PORTABILITY_AND_RECOVERY.md) | N/N-2 portability, lifecycle, key-loss, ransomware, complete restore, strict expiry-cycle, and >=90-day zero-cash evidence |
| 7 | [Exact-release prequalification](./PHASE_7_PREQUALIFICATION.md) | All 20 parent gates, long-run child receipts, accessibility/client coverage, and the Golden Institution Journey report current `SUCCESS` |
| 8 | [Pilot, qualification, activation, and suspension](./PHASE_8_PRODUCTION.md) | Separately evidenced `PILOT_VALIDATED`, `PRODUCTION_QUALIFIED`, and authorized `ACTIVATED` states |

[TASK_INDEX.md](./TASK_INDEX.md) is the compact task-selection entry point. [TRACEABILITY.md](./TRACEABILITY.md) maps every Feature Completion Matrix row, bounded context, qualification gate, and Golden Journey range to its task packages. [DEPENDENCY_WAVES.md](./DEPENDENCY_WAVES.md) shows safe parallelism and serialization points.

## Task-card contract

Every task card obeys this field contract:

- **Outcome**: the one independently reviewable result the chat must deliver.
- **Depends on**: only stable task IDs or task-ID ranges with the exact required lifecycle state or gate result, plus an explicitly named internal release-bound receipt head or an exact external-prerequisite receipt label declared by this card or a transitive task dependency. A grouped list is valid only when one terminal state/result unambiguously applies to every listed ID. Human authority, rights, hardware, corpus, network, tool, cost/allowance, or other non-task prose must not appear here; put each such condition in an **External prerequisites** field and record its structured receipt in the fresh-chat start record.
- **External prerequisites**: at most one field, required only when the card has a non-task precondition. It names each condition with a unique stable local label, exact required disposition, accountable party, validity rule, and immutable evidence type. `kind` is one of `HUMAN_AUTHORITY`, `RIGHTS`, `HARDWARE`, `DATA_OR_CORPUS`, `NETWORK_IDENTITY`, `TOOL_OR_IMPLEMENTATION`, or `COST_OR_ALLOWANCE`. Write each entry, with no extra keys or trailing syntax, as ``label=<stable-label>; kind=<enumerated-kind>; requires=<exact-disposition>; accountable=<role-or-person>; validity=<rule>; evidence=<immutable-receipt-type>``. Separate multiple entries with exactly ` | `. This field never substitutes for a task dependency.
- **Read first**: the minimum normative contracts needed to avoid loading the complete planning corpus.
- **Change surface**: expected repository areas. The chat must inspect rather than assume exact filenames.
- **Implement**: the bounded mutation, or `none;` followed by the bounded planning, audit, evidence, campaign, deployment, or other non-product-mutation operation.
- **Prove**: local checks and evidence required before the task may claim `CHECKED_LOCAL`; protected checks and merge remain separate.
- **Stop/hand off**: pre-execution conditions that require `BLOCKED`/`NOT_STARTED`, conditions that make an executed evaluation `PARTIAL`, `NEGATIVE`, or `NOT_EVALUABLE`, and explicit exclusions.
- **Unlocks**: downstream tasks that become eligible only after the required receipt is current.

An implementation card's **Implement** field names the source, schema, configuration, runtime, UI, authorization, operations, recovery, and documentation mutation it owns. A non-product-mutation card explicitly excludes product mutation. If ownership remains ambiguous, split or amend the card before work starts.

Task IDs are stable. If a task must be split after implementation begins, retain the parent ID and add alphabetic children such as `P4-T18A`; never renumber later tasks. A split is allowed only when it does not weaken the parent's acceptance criteria or hide an unresolved part.

## One-chat sizing rules

A task should fit one focused implementation chat and one pull request. Split before work when any of these are true:

- more than one authoritative bounded context would gain a new mutation path;
- a schema migration and a destructive or one-way data cutover would occur together;
- backend, frontend, infrastructure, and a large campaign would all need non-mechanical changes;
- independent protocol profiles or independent capacity thresholds would be combined;
- the expected review surface is too large to verify from the task's declared `Read first` set; or
- a wall-clock campaign needs continuing operation after the implementation chat ends.

Long-running evidence is always separated into harness, dry-run, launch, monitoring/audit, and closure tasks. A `RUNNING` process or dashboard is not a successful campaign. Closure requires terminal receipts and the signed report.

## State and evidence rules

Use the [Delivery State Ledger](../architecture/DELIVERY_STATE_LEDGER.md) literally:

```text
PLANNED -> IMPLEMENTED -> CHECKED_LOCAL -> CHECKED_PROTECTED -> MERGED
        -> DEPLOYED -> PILOT_VALIDATED -> PRODUCTION_QUALIFIED -> ACTIVATED
```

- A plan, task card, commit, local test, protected check, merge, deployment, pilot, qualification, and activation are different facts.
- A task chat may report only the last state for which it has direct evidence.
- `SUCCESS`, `PARTIAL`, `NEGATIVE`, and `NOT_EVALUABLE` are gate results, not lifecycle states.
- An absent, stale, expired, or unavailable prerequisite prevents execution: report work status `BLOCKED` and gate execution `NOT_STARTED`, with no gate result. `NOT_EVALUABLE` is valid only after the evaluation actually ran but its frozen method could not produce an evaluable result; incomplete evaluated scope is `PARTIAL`; a frozen invariant breach is `NEGATIVE`.
- No task may lower a threshold or remove an adversarial case after seeing a result.
- Historical, other-host, other-commit, or synthetic evidence cannot qualify the final release except under the signed unchanged-input rule already frozen in Production Qualification.
- Every task that adds a governed mutation also adds its capability check, audit/outbox event, retention/deletion behavior, backup or rebuild classification, failure behavior, tests, and runbook before claiming `IMPLEMENTED`.

## Branch, pull-request, and merge discipline

- Start from current `origin/main` after every dependency is merged. Do not stack a new task on an unmerged sibling unless the task card explicitly declares a coordinated stack.
- Use a `codex/` branch with the task ID, for example `codex/p2-t06-webauthn-step-up`.
- Preserve unrelated user changes and use an isolated worktree when the main checkout is dirty.
- Put the task ID, dependency commit, affected context, migrations, checks, evidence result, exclusions, and rollback in the pull-request body.
- Rebase or merge current `origin/main` before final protected checks when intervening work has landed, then re-run affected checks on the exact head.
- Do not merge a task with unresolved Critical/High authority, privacy, data-loss, license, recovery, or security findings. A documented blocker is a valid handoff; silent scope reduction is not.
- After merge, record the exact default-branch commit. Downstream chats must verify it before starting.

## Global invariants for every task

1. One context owns each authoritative record; no cross-context table reads, foreign keys, or shared write models.
2. Context changes and outbox events commit atomically; JetStream transports but never owns truth.
3. Institution, Principal or Purpose Identity, policy version, Key Version, retention trigger, deletion class, and audit linkage accompany governed mutations. The only nullable-Institution exception is the installation-scoped, one-use bootstrap credential before any Institution exists; its immutable installation/repository/release discriminator, consumption, revocation, and replacement receipt are mandatory.
4. Heavy modes are mutually exclusive on Zero-Cash Production. Resident work and emergency headroom remain protected.
5. New authoritative bytes remain `PENDING_PROTECTION` until independent off-host acknowledgement.
6. The Zero-Cash claim is an observed 90-day, then rolling-12-month result—not a promise of being free forever.
7. Mandatory software paths remain Free Software; required assets, models, tools, and standards artifacts need admitted rights and provenance.
8. Clinical Shadow is read-only, deidentified, non-diagnostic, and creates no patient-care or clinical qualification claim.
9. Teacher AI runs on the teacher device, never publishes or grades directly, and has a deterministic non-model path.
10. TRACE-SIM remains excluded from production qualification and activation. Its activation or removal requires a separate approved task.
11. Accessibility, supported-client behavior, install, upgrade, rollback, retention, deletion, restore, and resource limits are parts of feature completion, not optional cleanup.
12. Production activation is a later two-person decision against one exact deployed and qualified release.
13. Every deletion-bound governed plaintext is envelope-encrypted before persistence under an owning-context, purpose-bound Key Version; full-volume encryption alone is insufficient, and owner tasks prove field/object coverage and crypto-erasure behavior.

## Program-level stop conditions

Stop promotion and report the exact blocker when:

- a dependency is not merged or its evidence has expired;
- source rights, license, model openness, standard artifact rights, or security provenance cannot be established;
- an implementation would create a second authority, cross-context database access, silent dual write, or unsupervised runtime;
- the target hardware, backup target, supported client, independent implementation, qualified reviewer, or accountable approver is unavailable;
- a Zero-Cash mandatory dependency projects a gross incremental charge;
- a frozen privacy, data-protection, resource, capacity, clinical, separation-of-duty, or recovery invariant fails; or
- evidence cannot be bound to the exact release, configuration, host, corpus, operator, and schema version.

Do not compensate by changing the claim. If execution never started, record `BLOCKED`/`NOT_STARTED` and no gate result. If an evaluation ran, record its honest `PARTIAL`, `NEGATIVE`, or `NOT_EVALUABLE` result, repair or redraw the affected decision through an explicit ADR, and re-run only after the new prerequisite is accepted.
