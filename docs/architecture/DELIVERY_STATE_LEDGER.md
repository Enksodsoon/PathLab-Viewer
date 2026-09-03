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

- receipt identifier, prior ledger head, event time, issuer type/id, accountable approver or controller, signing-authority type, and signing key identity/version;
- `scope_kind` with exactly one of `REPOSITORY`, `RELEASE`, `INSTALLATION`, or `INSTITUTION`, plus an immutable `scope_subject_id`: exact repository/task/change/commit, immutable release/candidate identity, signed installation/target identity, or Institution/domain subject respectively; release artifact roots become mandatory as soon as assembly exists;
- `institution_id`, which is required and non-null for `INSTITUTION` scope and may be JSON `null` only for the other three scopes; an Institution reference outside Institution scope is contextual and does not confer Institution authority;
- capability or complete-release subject, source state, destination state, and the result being asserted;
- the source commit and every release, artifact, configuration, migration, deployment-profile, host, backup-target, client, and corpus identity required at the current scope/state; not-yet-created outputs are explicitly null/not-applicable and cannot be retrospectively inserted into the signed entry;
- direct links or content hashes for check runs, workload manifests, evidence packages, exceptions, incident records, and rollback material;
- the exact claim, expiry or next-review time, invalidation rules, and a machine-readable list of unresolved blockers; and
- privacy classification and proof that the receipt contains no secret, PHI, private slide pixels, assessment answers, or participant-level telemetry.

Repository-scoped entries verify only against repository governance or protected-check trust roots; release-scoped entries verify only against protected-build or release-controller trust roots; installation-scoped entries verify only against the signed installation manifest's Operator, deployment-controller, or installation-scoped `svc-platform` trust roots; Institution-scoped entries require a current Institution-authorized Principal or Service Principal, applicable human Role Binding and Purpose Identity, policy, and Institution Key Version. Before bootstrap, `institution_id` and all Institution Principal, Role Binding, and Purpose Identity fields are null and cannot be inferred; the separate scoped issuer remains required. Such entries cannot create product-domain authority or satisfy an Institution-scoped transition.

Receipts are hash-chained into Audit and Operations and checkpointed at least daily and at every release, qualification, and activation transition. Sanitized verification copies may omit sensitive infrastructure identifiers while preserving hashes and signatures.

## Transition rules

1. Every state transition is explicit. A single phrase such as “released to production” may not collapse merge, deployment, qualification, and activation.
2. The ordinary sequence is `PLANNED` -> `IMPLEMENTED` -> `CHECKED_LOCAL` -> `CHECKED_PROTECTED` -> `MERGED` -> `DEPLOYED` -> `PILOT_VALIDATED` -> `PRODUCTION_QUALIFIED` -> `ACTIVATED`.
3. Evidence from an exact immutable subject may satisfy adjacent prerequisites, but each transition still receives its own receipt and accountable issuer.
4. A later-looking state never repairs an absent earlier receipt. Historical, synthetic, other-host, other-commit, or other-profile evidence cannot be combined into a qualification claim. The sole exception is unaffected long-duration durability evidence accompanied by the signed unchanged-input equivalence declaration, exact-candidate soak, and affected reruns required by [Production Qualification](./PRODUCTION_QUALIFICATION.md); imported evidence remains supporting evidence and never changes the receipt subject. Equivalence never retains Campaign Admission/Start, accrued campaign time or accrued soak time across a Deployment Selection Receipt head change; the historical durability evidence may be cited only after a separately admitted fresh run.
5. A failed or invalidated gate appends an invalidation receipt and blocks the affected forward transition. It does not rewrite or delete prior history.
6. Host, storage layout, database major, kernel or filesystem, authority boundary, mandatory dependency, model bundle, standards profile, client matrix, security mitigation, or configuration drift triggers the targeted invalidation rules in the Qualification Claim.
7. Activation requires two distinct currently authorized people. Expiry, invalidation, rollback, or a fail-closed suspension moves the current projection to `ACTIVATION_SUSPENDED`; reactivation requires a new Activation Receipt against current deployment and qualification receipts and returns the projection to `ACTIVATED` without erasing either prior event.
8. TRACE-SIM remains outside production qualification and activation. Its dormant code state cannot be presented as a production capability, and removal or activation requires a separate approved decision.
9. Delivery State is tracked for each exact release tuple; the release currently selected for routing is a separate append-only deployment projection. Every Deployment Selection Receipt head change—including `REVERTED`, re-selection of identical bytes or a nominally equivalent build—unconditionally invalidates the current Campaign Admission/Start and all accrued campaign/soak time and requires a fresh `P6-T30`; no Impact/Equivalence Result can retain that admission. A pre-activation binary rollback never rewrites a lifecycle receipt or invents a backward transition: it appends a Deployment Selection Receipt selecting the prior release and invalidates the replaced tuple's current deployment binding plus every affected pilot, qualification or soak result. An activated rollback appends suspension before routing changes. Historical states remain visible as supporting evidence only, while current validity and selected deployment are reported independently.
10. Task/change lifecycle receipts use `REPOSITORY` scope and stop at `MERGED`. A complete-release chain uses `RELEASE` scope through `MERGED`, crosses to `INSTALLATION` only for `DEPLOYED`, and crosses to `INSTITUTION` only for `PILOT_VALIDATED`, `PRODUCTION_QUALIFIED`, `ACTIVATED`, or `ACTIVATION_SUSPENDED`. Each crossing must bind the exact prior receipt id/hash and unchanged release tuple; it cannot restart, skip, or retrospectively rescope the chain.
11. The one-time Bootstrap Receipt is `INSTALLATION` scoped with `institution_id=null` and names the newly created Institution only as `created_institution_id`. It is not a lifecycle transition. Institution-scoped receipts become possible only after that atomic bootstrap commit and must use the newly established Institution trust root.

## Reporting contract

Status reports name the scope kind/subject, lifecycle state, and latest applicable gate result. They also distinguish current source observations from claims about a branch, default branch, release artifact, deployed host, pilot, qualified profile, or activated Institution. If evidence cannot establish a state, the report stops at the last evidenced state and lists the missing receipt instead of inferring progress.
