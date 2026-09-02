# Delivery State Ledger

The Delivery State Ledger prevents a plan, code change, test result, deployment, or pilot from being reported as production activation. It is an append-only projection of signed receipts registered in the [Receipt Schema Registry](./RECEIPT_SCHEMA_REGISTRY.md); the owning source remains the repository, protected-check system, release host, qualification evidence package, or activation controller named by each receipt.

## Canonical lifecycle states

| State | Minimum receipt | What the state does not establish |
| --- | --- | --- |
| `PLANNED` | Accepted ADR and versioned acceptance contract | implementation, test, merge, deployment, qualification, or activation |
| `IMPLEMENTED` | Commit and artifact hashes plus migrations, schemas, runbooks, and a completed vertical-slice checklist | a passing check or inclusion in a protected branch |
| `CHECKED_LOCAL` | Reproducible local-check manifest and `SUCCESS`, `PARTIAL`, `NEGATIVE`, or `NOT_EVALUABLE` result bound to the implementation commit | protected CI, merge, deployment, target-host behavior, or qualification |
| `CHECKED_PROTECTED` | Required protected-check run identifiers, exact commit, immutable logs or attestations, and aggregate result | merge, deployment, target-host behavior, or qualification |
| `MERGED` | Protected default-branch commit and merge receipt | release assembly, deployment, qualification, or activation |
| `DEPLOYED` | Immutable release digest, configuration digest, migration head, target identity, deployment time, health evidence, and rollback target | pilot success, capacity, recovery, standards conformance, or activation |
| `PILOT_VALIDATED` | Approved pilot manifest, participant and data boundary, incident review, expiry, and accountable signatures | full production qualification or activation |
| `PRODUCTION_QUALIFIED` | One current exact-release Qualification Claim whose mandatory gates all report `SUCCESS` for the named profile, host, backup target, and client matrix | deployment elsewhere, clinical use, or activation |
| `ACTIVATED` | Two-person Activation Receipt naming the deployed qualified release, accepted claims, evidence heads, review date, and rollback target | a permanent claim; expiry, configuration drift, or evidence invalidation can suspend it |
| `ACTIVATION_SUSPENDED` | Invalidation or suspension receipt naming the prior Activation Receipt, trigger, effective time, affected claims, safe operating state, and remediation/requalification requirement | active production authority or automatic reactivation; the historical activation remains auditable |

`CLINICALLY_QUALIFIED` is an independent purpose-specific status, not the next lifecycle state. It requires a separately approved clinical purpose, data and safety boundary, evidence package, expiry, and accountable clinical authority. Base Clinical Shadow interoperability, a production-qualified non-clinical release, or an activated teaching deployment cannot imply it.

## Gate result vocabulary

Every check or qualification gate reports exactly one result:

- `SUCCESS`: every frozen threshold and invariant passed on the exact subject, including cleanup and recovery.
- `PARTIAL`: useful evidence exists, but at least one required part is incomplete or stale.
- `NEGATIVE`: a frozen threshold or invariant failed.
- `NOT_EVALUABLE`: required data, rights, hardware, endpoint, operator, or evidence was unavailable.

A lifecycle state and a gate result answer different questions. For example, a deployed release may have a `NEGATIVE` capacity result; this remains `DEPLOYED` and is not `PRODUCTION_QUALIFIED`.

## Receipt envelope

Every ledger entry uses a versioned schema and contains:

- receipt identifier, prior ledger head, event time, issuer, accountable approver or approvers, and signature Key Version;
- Institution, capability or complete-release scope, source state, destination state, and the result being asserted;
- source commit, immutable release and artifact digests, configuration and migration digests, deployment profile, host and backup-target identities, and applicable client/corpus identifiers;
- direct links or content hashes for check runs, workload manifests, evidence packages, exceptions, incident records, and rollback material;
- the exact claim, expiry or next-review time, invalidation rules, and a machine-readable list of unresolved blockers; and
- privacy classification and proof that the receipt contains no secret, PHI, private slide pixels, assessment answers, or participant-level telemetry.

Receipts are hash-chained into Audit and Operations and checkpointed at least daily and at every release, qualification, and activation transition. Sanitized verification copies may omit sensitive infrastructure identifiers while preserving hashes and signatures.

## Transition rules

1. Every state transition is explicit. A single phrase such as “released to production” may not collapse merge, deployment, qualification, and activation.
2. The ordinary sequence is `PLANNED` -> `IMPLEMENTED` -> `CHECKED_LOCAL` -> `CHECKED_PROTECTED` -> `MERGED` -> `DEPLOYED` -> `PILOT_VALIDATED` -> `PRODUCTION_QUALIFIED` -> `ACTIVATED`.
3. Evidence from an exact immutable subject may satisfy adjacent prerequisites, but each transition still receives its own receipt and accountable issuer.
4. A later-looking state never repairs an absent earlier receipt. Historical, synthetic, other-host, other-commit, or other-profile evidence cannot be combined into a qualification claim. The sole exception is unaffected long-duration durability evidence accompanied by the signed unchanged-input equivalence declaration, exact-candidate soak, and affected reruns required by [Production Qualification](./PRODUCTION_QUALIFICATION.md); imported evidence remains supporting evidence and never changes the receipt subject.
5. A failed or invalidated gate appends an invalidation receipt and blocks the affected forward transition. It does not rewrite or delete prior history.
6. Host, storage layout, database major, kernel or filesystem, authority boundary, mandatory dependency, model bundle, standards profile, client matrix, security mitigation, or configuration drift triggers the targeted invalidation rules in the Qualification Claim.
7. Activation requires two distinct currently authorized people. Expiry, invalidation, rollback, or a fail-closed suspension moves the current projection to `ACTIVATION_SUSPENDED`; reactivation requires a new Activation Receipt against current deployment and qualification receipts and returns the projection to `ACTIVATED` without erasing either prior event.
8. TRACE-SIM remains outside production qualification and activation. Its dormant code state cannot be presented as a production capability, and removal or activation requires a separate approved decision.

## Reporting contract

Status reports name both the lifecycle state and the latest applicable gate result. They also distinguish current source observations from claims about a branch, default branch, release artifact, deployed host, pilot, qualified profile, or activated Institution. If evidence cannot establish a state, the report stops at the last evidenced state and lists the missing receipt instead of inferring progress.
