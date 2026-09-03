# Phase 7 — Exact-Release Prequalification

Phase 7 integrates one immutable candidate, proves every mandatory non-pilot gate on one exact tuple, then executes the Golden Institution Journey. Candidate integration, merge and deployment intentionally occur after the Phase 6 harness/controller preflight but before its 90-day campaign begins, so the operated interval starts on the exact candidate. Engineering or historical phase evidence is supporting only unless admitted by the signed unchanged-input rule. All tasks inherit [README](./README.md).

## Journey and gate tooling

## P7-T01 — Implement frozen gate manifests and results

- **Outcome:** Create a runner/controller for immutable threshold/invariant/fault/cleanup manifests and canonical `SUCCESS|PARTIAL|NEGATIVE|NOT_EVALUABLE` results bound to exact candidate fingerprints and evidence custody.
- **Depends on:** `P0-T10A`, `P2-T16A`, `P2-T18A`, `P2-T18B` `MERGED`.
- **Read first:** Production Qualification evidence/result/decision rules and Receipt Schema Registry.
- **Change surface:** qualification schemas/library/CLI/UI/tests.
- **Implement:** sign-before-run, no post-observation edits, terminal result rules, expiry/invalidation, privacy scan and accountable signatures.
- **Prove:** modified threshold/manifest, missing artifact, incomplete workload, failed invariant, wrong candidate and mixed evidence cases yield exact results.
- **Stop/hand off:** gate runner never mutates product authority or Delivery State without a separate lifecycle receipt.
- **Unlocks:** exact gate runs and `P7-T02`.

## P7-T02 — Implement the generic Golden Journey runner

- **Outcome:** Execute a signed manifest as an ordered, idempotent command/receipt chain with predecessor verification, Mode Reservations, declared faults, cleanup obligations, restart/resume and terminal reconciliation.
- **Depends on:** `P7-T01`, `P2-T18A` `MERGED`.
- **Read first:** [Golden Institution Journey](../architecture/GOLDEN_INSTITUTION_JOURNEY.md), Receipt Schema Registry journey types.
- **Change surface:** Platform journey module/CLI/operations UI/tests.
- **Implement:** Add ordered idempotent command dispatch, predecessor and reservation verification, fault boundaries, cursor-based resume, cleanup reconciliation and terminal receipt signing without bypassing context owners.
- **Prove:** missing/duplicate/reordered/changed command, wrong predecessor, stale reservation, runner restart and unregistered receipt all fail closed.
- **Stop/hand off:** console messages/logs/screens cannot stand in for registered receipts.
- **Unlocks:** `P7-T03`–`P7-T07`.

## P7-T03 — Provision rights-cleared fixed actors and fixtures

- **Outcome:** Materialize the exact distinct human/service actors, Role Bindings, synthetic/authorized fixtures, corpora, random seed and trusted-time source required by G00–G38.
- **Depends on:** `P0-T05`, `P2-T27`, `P5-T40`, `P7-T02` `MERGED`.
- **External prerequisites:** label=P7-EXT-GOLDEN-ACTORS; kind=HUMAN_AUTHORITY; requires=ALL_DISTINCT_ACTORS_RESERVED; accountable=Golden Journey Owner; validity=exact G00-G38 manifest and execution window; evidence=signed immutable Actor Reservation Receipt | label=P7-EXT-GOLDEN-FIXTURES; kind=DATA_OR_CORPUS; requires=RIGHTS_PRIVACY_AND_HASHES_APPROVED; accountable=Fixture and Rights Owner; validity=exact fixture roots and execution window; evidence=signed immutable Fixture Admission Receipt | label=P7-EXT-TRUSTED-TIME; kind=TOOL_OR_IMPLEMENTATION; requires=TRUSTED_SOURCE_AVAILABLE_AND_ATTESTED; accountable=Evidence Custody Owner; validity=exact execution window; evidence=signed immutable Trusted Time Source Receipt
- **Read first:** Golden Journey actor/fixture sections, Role Matrix.
- **Change surface:** fixture/provisioning tooling, manifests and rights/privacy tests.
- **Implement:** Add bounded actor/role and fixture provisioning, deterministic seeds, immutable roots and teardown controls for the exact Golden manifest; never import undeclared production secrets or PHI.
- **Prove:** each required human is distinct; all fixture/corpus hashes/rights/privacy classes resolve; no production secret, PHI, private answer or placeholder identity.
- **Stop/hand off:** missing accountable humans, legal fixtures or physical inputs is `NOT_EVALUABLE`.
- **Unlocks:** `P7-T04`–`P7-T08`.

## P7-T04 — Implement and test Golden handlers G00–G14

- **Outcome:** Automate admission/install/bootstrap/roles/policies/integration/Catalog/Authoring/upload/protection/DZI/annotations/Public Release with exact commands, receipts and negative cases.
- **Depends on:** `P7-T02` and `P7-T03` `MERGED`; current terminal `SUCCESS` from `P0-T12`, `P1-T25`, `P2-T27`, `P3-T18`, `P4-T13`, `P5-T09`, and `P5-T40`.
- **Read first:** Golden Journey G00–G14 and registered schemas.
- **Change surface:** journey handlers/fixtures/component integration tests.
- **Implement:** Add bounded G00-G14 handlers that invoke only registered owner commands, verify predecessors and emit exact receipts and negative-case evidence.
- **Prove:** each predecessor/hash/actor/reservation/fault/assertion; stale admission stops all later work.
- **Stop/hand off:** no handler may bypass an owner, protection, approval or receipt.
- **Unlocks:** `P7-T07`, `P7-T08`.

## P7-T05 — Implement and test Golden handlers G15–G25

- **Outcome:** Automate Live/media/deterministic learning/Assessment/grade return/eligibility/Credential lifecycle with exact owner transitions and failures.
- **Depends on:** `P7-T02`, `P7-T03`, `P4-T30`, `P5-T15` `MERGED`.
- **Read first:** Golden Journey G15–G25 and relevant receipt schemas.
- **Change surface:** journey handlers/fixtures/component integration tests.
- **Implement:** Add bounded G15-G25 handlers for exact owner transitions, deterministic faults and receipt checks; exclude TRACE-SIM, AI grading and external authority substitution.
- **Prove:** guest/non-durable, restart/replay, media fallback, clock/lease, external outage/rotation and independent approvals.
- **Stop/hand off:** TRACE-SIM, AI grading, guest evidence or external-system authority is `NEGATIVE`.
- **Unlocks:** `P7-T07`, `P7-T08`.

## P7-T06 — Implement and test Golden handlers G26–G38

- **Outcome:** Automate EQA/Clinical/Research/Edge/Portability/Legal Hold/Deletion/Retention/cold restore/cleanup with exact receipts and faults, including separate Learning Catalog and Research accept/reject results for any Clinical deidentified-snapshot offer plus withdrawal, expiry and deletion propagation.
- **Depends on:** `P7-T02`, `P7-T03`, `P5-T40`, `P6-T21`, `P6-T27` `MERGED`.
- **Read first:** Golden Journey G26–G38 and registered schemas.
- **Change surface:** journey handlers/fixtures/component integration tests.
- **Implement:** Add bounded G26-G38 handlers for owner commands, Clinical offer plus separate destination-owner acceptance/rejection, withdrawal/expiry/deletion propagation, fault injection, portability/recovery and cleanup verification without granting Research or Clinical authority.
- **Prove:** seal, PHI rejection, no writeback/claim, Learning and Research destination accept/reject isolation, revoked/expired/deleted snapshot propagation, runner isolation, lease/replay/conflict, empty-target import, failed owner retry, hold expiry and restore reconciliation.
- **Stop/hand off:** partial deletion, Research activation, clinical claim/writeback or restore-invented truth is `NEGATIVE`.
- **Unlocks:** `P7-T07`, `P7-T08`.

## P7-T07 — Implement declared fault control and cleanup verification

- **Outcome:** Inject only manifest-declared faults at exact boundaries, independently verify recovery, enforce exclusive reservations/process drain and reconcile every temporary-data/deletion/backup obligation.
- **Depends on:** `P7-T04`–`P7-T06` `MERGED`.
- **Read first:** Golden Journey fault and cleanup sections; Production Qualification cross-cutting failures.
- **Change surface:** operator fault tools, cleanup verifier and adversarial tests.
- **Implement:** Add manifest-gated fault controls, exclusive reservation/drain checks, independent recovery verification and exact temporary-data/obligation reconciliation.
- **Prove:** every named class, frozen max duration/recovery, F-MODE conflict, zero surviving mode process/temp workspace and explicit still-open bounded obligations.
- **Stop/hand off:** undeclared chaos, changed threshold or untrustworthy evidence is `NOT_EVALUABLE`.
- **Unlocks:** `P7-T08`, final Journey.

## P7-T08 — Run a non-qualifying full rehearsal

- **Outcome:** Execute G00–G38 on a disposable declared environment to find runner/fixture/receipt/fault/cleanup gaps without producing an exact-release Qualification prerequisite.
- **Depends on:** `P7-T03`–`P7-T07` `MERGED`.
- **External prerequisites:** label=P7-EXT-REHEARSAL-TARGET; kind=HARDWARE; requires=DISPOSABLE_ENVIRONMENT_RESERVED; accountable=Golden Journey Operations Owner; validity=exact rehearsal manifest and window; evidence=signed immutable Rehearsal Target Reservation Receipt | label=P7-EXT-REHEARSAL-OPERATOR; kind=HUMAN_AUTHORITY; requires=PRIMARY_OPERATOR_RESERVED; accountable=Golden Journey Operations Owner; validity=exact rehearsal window; evidence=signed immutable Rehearsal Operator Reservation Receipt
- **Read first:** Golden Journey and task runner runbook.
- **Change surface:** rehearsal evidence/issue backlog only; fixes become separate tasks.
- **Implement:** none; execute G00-G38 on the declared disposable environment, record ordered receipts/gaps and clean it, excluding product or qualification mutation.
- **Prove:** ordered terminal run, deliberate non-qualifying subject label and complete gap/cleanup report.
- **Stop/hand off:** rehearsal success must never be reported as the final Golden result.
- **Unlocks:** `P7-T09`.

## Candidate integration and lifecycle transitions

## P7-T09 — Integrate the proposed release candidate

- **Outcome:** Reconcile all completed feature/operation/remediation work into one final integration branch and immutable proposal manifest without yet claiming that a pre-merge commit is the final deployed candidate.
- **Depends on:** `P2-T18C`, `P6-T21`, `P6-T24A` and `P6-T29` `MERGED`, with current terminal `SUCCESS` from `P5-T40` and `P7-T08`.
- **Read first:** Delivery State Ledger, candidate fingerprinting/invalidation rules.
- **Change surface:** isolated integration worktree/branch, compatibility resolution and proposed-candidate manifest.
- **Implement:** Integrate only the declared completed work into the bounded candidate branch, resolve compatibility without widening feature scope and emit the proposed-candidate manifest.
- **Prove:** clean worktree, complete dependency/migration graph, no unresolved conflict/finding/gap, exact proposed head/tree and complete fingerprint inputs ready for review.
- **Stop/hand off:** dirty/mixed/unmerged/stale inputs or a scope fix means the proposal is not ready; its branch SHA is never called the final frozen default-branch candidate. `P7-T09`–`P7-T11` are one explicitly coordinated unmerged stack in the same isolated worktree/branch; they unlock nothing outside that stack before merge. Operated-window tasks `P6-T30`–`P6-T36` remain pending.
- **Unlocks:** `P7-T10`.

## P7-T10 — Emit the proposed-candidate local-check result

- **Outcome:** Run the complete reproducible local suite against only the proposed integration head and produce `CHECKED_LOCAL` evidence with explicit unavailable native/physical gates.
- **Depends on:** `P7-T09` `IMPLEMENTED` within the declared coordinated integration stack.
- **Read first:** Delivery State `CHECKED_LOCAL`, repository check manifests.
- **Change surface:** checks/evidence only; code fix creates a new candidate.
- **Implement:** none; execute the complete reproducible local check manifest on the proposed head and sign its result, excluding code, dependency or candidate mutation.
- **Prove:** all required Python/web/schema/security/public-repo/migration/offline fixtures; exact command/output hashes and result.
- **Stop/hand off:** a partial suite is `PARTIAL`; another SHA cannot fill a gap, and a changed integration tree restarts this task.
- **Unlocks:** `P7-T11`.

## P7-T11 — Pass protected checks, merge, and freeze the default-branch candidate

- **Outcome:** Run every required protected workflow on the exact proposed head, review and merge it, then freeze the final default-branch source commit/tree, build recipe/inputs and declared build environment that release assembly will consume.
- **Depends on:** `P7-T10` with `SUCCESS`.
- **External prerequisites:** label=P7-EXT-RELEASE-REVIEW; kind=HUMAN_AUTHORITY; requires=REQUIRED_INDEPENDENT_REVIEWERS_AND_MERGER_AUTHORIZED; accountable=Release Governance Owner; validity=exact proposed head and protected-check window; evidence=signed immutable Release Review Authority Receipt | label=P7-EXT-PROTECTED-CHECKS; kind=TOOL_OR_IMPLEMENTATION; requires=REQUIRED_PROTECTED_WORKFLOWS_AVAILABLE; accountable=Repository Policy Owner; validity=exact proposed head and required-check manifest; evidence=signed immutable Protected Workflow Availability Receipt
- **Read first:** Delivery State Ledger and protected branch policy.
- **Change surface:** PR/check/review/merge metadata and immutable final-candidate manifest; fixes restart at `P7-T09`.
- **Implement:** none; run protected checks, perform the reviewed merge and freeze the exact default-branch fingerprint; any source fix restarts the candidate stack.
- **Prove:** exact run IDs/attestations/head, required check set and merge commit/default-branch identity. Use a fast-forward/exact-SHA merge or rerun the complete required local and protected check manifests on the final default-branch SHA before freezing—tree equivalence alone is insufficient. Bind commit/tree, build recipe/inputs/environment, configuration/migrations, profile, host/storage/firmware/cache, PostgreSQL minor/client, OS packages/kernel/filesystem, backup target, network rules, clients/corpora/workload/operators, tools/models/protocols/keys/policies, controllers/evidence schemas/trusted time, the pre-deployment Campaign Contract Template and cost-tariff inputs.
- **Stop/hand off:** stale/skipped/failed checks, a final SHA without complete local/protected results, incomplete source fingerprint or any relevant head/input change means no candidate is frozen.
- **Unlocks:** `P7-T12`.

## P7-T12 — Assemble and deploy the exact immutable release

- **Outcome:** Reproducibly build the signed kit on the owned runner, complete the exact release fingerprint with actual artifact/SBOM/signature/configuration/route digests, verify/install on the declared host, apply expand-only migrations, run isolated synthetic transactions, atomically select it, observe 30 minutes and emit linked deployment-selection and lifecycle receipts.
- **Depends on:** `P2-T18C`, `P2-T26`, `P6-T27` and `P7-T11` `MERGED`, with `P2-T26=SUCCESS`, `P6-T27=SUCCESS`, `P7-T11=SUCCESS`, and current release-bound Backup Freshness State, `Restore Receipt(RESTORED)`, `Approval Receipt(APPROVED)` and `Mode Reservation Receipt(READY)` heads for the exact candidate tuple.
- **External prerequisites:** label=P7-EXT-DEPLOY-RUNNER; kind=HARDWARE; requires=OWNED_RUNNER_RESERVED_AND_ATTESTED; accountable=Release Infrastructure Owner; validity=exact build recipe and assembly window; evidence=signed immutable Build Runner Reservation Receipt | label=P7-EXT-DEPLOY-HOST; kind=HARDWARE; requires=DECLARED_HOST_AND_ROLLBACK_TARGET_RESERVED; accountable=Deployment Operations Owner; validity=exact candidate and deployment window; evidence=signed immutable Deployment Host Reservation Receipt | label=P7-EXT-DEPLOY-OPERATOR; kind=HUMAN_AUTHORITY; requires=PRIMARY_AND_ALTERNATE_OPERATORS_RESERVED; accountable=Deployment Operations Owner; validity=exact deployment and observation window; evidence=signed immutable Deployment Operator Reservation Receipt
- **Read first:** Zero-Cash Runtime release switch, Delivery State `DEPLOYED`.
- **Change surface:** build/deploy/runtime evidence only.
- **Implement:** none; reproducibly build, verify, install, migrate, atomically select and observe the frozen release and emit linked selection/lifecycle receipts, excluding source or post-freeze configuration mutation.
- **Prove:** build recipe/input/environment equality to `P7-T11`, artifact/config/migration/host/target/current-route equality, `DeploymentSelectionReceipt(SELECTED)` atomically linked to the adjacent `DeliveryLifecycleReceipt(DEPLOYED)`, health and off-host acknowledgement before/after, and rollback readiness. Reversion selects the prior release with `DeploymentSelectionReceipt(REVERTED)`; if the current release is active, suspension precedes routing change.
- **Stop/hand off:** this operation is deployment, even if an old document calls the binary switch “activation”; it cannot emit `ACTIVATED`.
- **Unlocks:** campaign admission in `P6-T30`; exact-release gates may begin only after that operated campaign starts.

## P7-T13 — Start the exact-final-candidate 14-day soak

- **Outcome:** Bind and begin the mandatory unchanged 14-day soak inside the 90-day operated campaign, with continuous health/resource/outbox/backup/cost/security/incident evidence and targeted final-candidate reruns.
- **Depends on:** `P2-T18B` `MERGED`, current exact-subject `P6-T30=ACTIVE` and `P7-T12=DEPLOYED`, with the current `DeploymentSelectionReceipt(SELECTED)` head exactly matching the admitted campaign tuple.
- **Read first:** Production Qualification unchanged-input rule.
- **Change surface:** campaign manifest/start/monitoring only.
- **Implement:** none; start the candidate-bound soak, record its trusted start/cursor and monitor exact inputs without product, configuration or selection mutation.
- **Prove:** the campaign and soak share the identical signed tuple and live receipt cursor from start. Because deployment precedes campaign admission, any 14 consecutive valid campaign days qualify while the candidate remains unchanged through later aggregation.
- **Stop/hand off:** any relevant candidate/config/host/tool/model/client change invalidates affected soak evidence. Any `DeploymentSelectionReceipt` head change invalidates that admitted campaign tuple and requires a new campaign admission/start receipt before a new soak; equivalence cannot retain admission or soak days.
- **Unlocks:** `P7-T14` after elapsed time.

## P7-T14 — Close the 14-day soak and affected reruns

- **Outcome:** Reconcile every day, input, alert, incident, targeted rerun and any signed equivalence declaration into a terminal exact-candidate result.
- **Depends on:** completed `P7-T13` interval with the current `DeploymentSelectionReceipt(SELECTED)` head exactly matching the same active P6-T30 admission tuple.
- **Read first:** Production Qualification evidence model/invalidation.
- **Change surface:** evidence aggregation only.
- **Implement:** none; reconcile trusted soak timestamps, daily coverage, incidents and affected reruns into a terminal result without product, configuration, selection or evidence mutation.
- **Prove:** trusted `soak_end - soak_start >= 14 * 24h` with no uncovered instant; both endpoints lie inside the current P6-T30 window; the complete candidate fingerprint and `DeploymentSelectionReceipt(SELECTED)` head remain unchanged and exactly match that admission for the full interval; every affected gate rerun is terminal.
- **Stop/hand off:** missing day/input/rerun is `PARTIAL` or `NOT_EVALUABLE`; invariant breach is `NEGATIVE`.
- **Unlocks:** prerequisite aggregation after exact gates.

## Exact-release gate tasks

Every gate card below is a separate evidence task. It never implements or repairs product behavior. Each card names its exact task/result prerequisites; external people, physical clients, lawful corpora, targets and statements must also have current immutable reservation or custody evidence. Freeze the gate manifest before execution and bind the full `P7-T12` candidate fingerprint plus the current `DeploymentSelectionReceipt(SELECTED)` head. Missing evidence or resources is `NOT_EVALUABLE`, an incomplete workload is `PARTIAL`, and an invariant breach is `NEGATIVE`. A failure creates a separate remediation task and a new candidate; never edit code, change inputs or lower thresholds inside a gate run.

## P7-G01 — Qualify license, provenance, security, and offline build

- **Outcome:** Emit the exact-release result for every mandatory source, binary, model, standard, font, icon and asset; both SBOMs/notices/source bundle; owned ARM64 no-network build; ASVS 5.0.0 L2 mapping; default-deny egress; and Critical/High policy.
- **Depends on:** `P0-T12`, `P1-T22`, `P5-T40` and `P7-T01` `MERGED`, active `P6-T30` and `P7-T12=DEPLOYED`.
- **External prerequisites:** label=P7-EXT-G01-RIGHTS; kind=RIGHTS; requires=ALL_MANDATORY_ASSETS_MODELS_STANDARDS_AND_FONTS_ADMITTED; accountable=Asset Rights Owner; validity=exact candidate inputs and gate window; evidence=signed immutable Asset Rights Admission Receipt | label=P7-EXT-G01-RUNNER; kind=HARDWARE; requires=OWNED_ARM64_NO_NETWORK_RUNNER_RESERVED; accountable=Release Infrastructure Owner; validity=exact build recipe and gate window; evidence=signed immutable Offline Build Runner Reservation Receipt
- **Read first:** Production Qualification license/provenance/security/offline-build gate, Asset Rights Ledger, supply-chain ledger and Offline Release Kit manifest.
- **Change surface:** frozen gate manifest, independent scans/build logs, sanitized evidence package and result only.
- **Implement:** none; this task evaluates the already-deployed immutable candidate.
- **Prove:** exact rights/source/hash/license/notice/SBOM/build provenance, no-network assembly and verification, egress denial, ASVS mapping, vulnerability reachability and mitigation expiry.
- **Stop/hand off:** any unresolved right, mutable or unavailable input, hosted mandatory build dependency, reachable Critical or unmitigated High prevents `SUCCESS`.
- **Unlocks:** `P7-T15` only with a current `SUCCESS` on the identical candidate fingerprint and deployment-selection head.

## P7-G02 — Qualify runtime, modes, and keys

- **Outcome:** Emit the exact-release result for clean install/upgrade/rollback/reinstall, immutable switching, migrations, SELinux/cgroups/resource-pressure/restart controls, exclusive modes, the complete root/service/purpose/signing-key recovery and rotation matrix, and the lightweight scale-decision/home-cell/context-extraction/relocation contract without implying funded scale or inherited Zero-Cash evidence.
- **Depends on:** `P1-T25`, `P2-T24`, `P2-T26`, `P6-T22`, `P6-T23`, `P6-T24A`, `P6-T26`, `P6-T27`, and `P7-T01` `MERGED`; current exact-subject `P1-T25=SUCCESS`, `P2-T24=SUCCESS`, `P2-T26=SUCCESS`, `P6-T22=SUCCESS`, `P6-T23=SUCCESS`, and `P6-T27=SUCCESS`; active `P6-T30`; and current `P7-T12=DEPLOYED` on the identical candidate fingerprint and deployment-selection head.
- **External prerequisites:** label=P7-EXT-G02-HOST; kind=HARDWARE; requires=EXACT_OL9_ARM64_HOST_AND_RECOVERY_MEDIA_RESERVED; accountable=Runtime Qualification Owner; validity=exact host fingerprint and gate window; evidence=signed immutable Runtime Host Reservation Receipt | label=P7-EXT-G02-CUSTODIANS; kind=HUMAN_AUTHORITY; requires=THREE_DISTINCT_CUSTODIANS_WITH_ALL_TWO_OF_THREE_PAIRS_AVAILABLE; accountable=Institution Key Custody Owner; validity=exact key hierarchy and gate window; evidence=signed immutable Custodian Quorum Reservation Receipt
- **Read first:** Production Qualification runtime/modes/keys/lightweight-scale gate, Zero-Cash Runtime, Zero-Cash Key Management, the merged P6-T24A scale/home-cell contract and the exact host declaration.
- **Change surface:** frozen runtime/key/scale-routing gate manifest, raw observations, signed receipts and result only.
- **Implement:** none; fixes or new key mechanics require separate tasks and a new candidate.
- **Prove:** 2-OCPU/12-GB limits, 80/90/Safety states, resident/emergency headroom, mode drain, restart throttle, AB/AC/BC, one lost share, operator/custodian replacement, host rewrap and retained-data decrypt/verify across rotations; transient versus sustained 69.9/70/90-percent scale signals and hysteresis; exactly one current Institution home-cell route with absent/ambiguous/stale mappings failing closed; per-context extraction without cross-context SQL; and quiesced relocation, pre-switch reversal, one routing-epoch switch, post-switch reconciliation and cache invalidation without dual writes or lost authority.
- **Stop/hand off:** missing physical host/custodians, plaintext exposure, failed recovery pair, concurrent heavy mode, changed runtime input, ambiguous home-cell authority or dual writes is `NOT_EVALUABLE` or `NEGATIVE` as applicable. The lightweight cell remains the qualified default; a funded cell, HA/DR, automatic failover, added capacity or provider spend requires a separate authorized implementation, deployment and qualification and cannot inherit the Zero-Cash claim.
- **Unlocks:** `P7-T15` only with a current `SUCCESS` on the identical candidate fingerprint and deployment-selection head.

## P7-G03 — Qualify Trust roles and Learning Catalog

- **Outcome:** Emit the exact-release result for at least 10,000 Principals, the full Role/Approval Matrix and attacks, learner/minor/recovery behavior, 100 Courses and at least 100,000 Catalog version/enrollment/roster/progress rows.
- **Depends on:** `P2-T27`, `P4-T07`, `P4-T30`, `P7-T01`, and `P7-T03` `MERGED`; current exact-subject `P2-T27=SUCCESS` and `P4-T30=SUCCESS`; active `P6-T30`; and current `P7-T12=DEPLOYED` on the identical candidate fingerprint and deployment-selection head.
- **External prerequisites:** label=P7-EXT-G03-ACTORS; kind=HUMAN_AUTHORITY; requires=DISTINCT_ROLE_AND_APPROVAL_ACTORS_RESERVED; accountable=Trust Qualification Owner; validity=exact actor manifest and gate window; evidence=signed immutable Trust Actor Reservation Receipt | label=P7-EXT-G03-DATA; kind=DATA_OR_CORPUS; requires=TEN_THOUSAND_PRINCIPALS_AND_CATALOG_LOAD_MANIFEST_FROZEN; accountable=Trust and Catalog Data Owner; validity=exact workload roots and gate window; evidence=signed immutable Trust Catalog Workload Receipt
- **Read first:** Production Qualification Trust/Catalog gate, Role and Approval Matrix and Learning Catalog context.
- **Change surface:** frozen identity/Catalog workload, attacks, raw measurements, signed evidence and result only.
- **Implement:** none; fixture defects and product defects are separate remediation tasks.
- **Prove:** every role/incompatibility/self-approval/cross-Institution/step-up/last-owner case, email-optional learner activation/recovery/guardian rules and exact immutable Catalog authority under the full row counts.
- **Stop/hand off:** placeholder actors, incomplete combinations/rows or authority transfer prevents `SUCCESS`.
- **Unlocks:** `P7-T15` only with a current `SUCCESS` on the identical candidate fingerprint and deployment-selection head.

## P7-G04 — Qualify governance, retention, and deletion

- **Outcome:** Emit the exact-release result for every grant/retention trigger, schedule, Legal Hold, subject export and fail-closed Deletion Saga across every owner and copy class, including cryptographic-erasure and backup obligations.
- **Depends on:** `P2-T14`, `P2-T27`, `P5-T40`, `P6-T21`, and `P7-T01` `MERGED`; current exact-subject `P2-T27=SUCCESS`, `P5-T40=SUCCESS`, and `P6-T21=SUCCESS`; active `P6-T30`; and current `P7-T12=DEPLOYED` on the identical candidate fingerprint and deployment-selection head.
- **External prerequisites:** label=P7-EXT-G04-AUTHORITY; kind=HUMAN_AUTHORITY; requires=DISTINCT_HOLD_DELETION_AND_POLICY_ACTORS_RESERVED; accountable=Governance Qualification Owner; validity=exact owner matrix and gate window; evidence=signed immutable Governance Actor Reservation Receipt
- **Read first:** Production Qualification governance/deletion gate, Governed Product Workflows retention ceilings, owner deletion adapters and Field Encryption Policy.
- **Change surface:** frozen deletion/hold/export manifest, owner receipt reconciliation, privacy evidence and result only.
- **Implement:** none; an absent owner adapter is a blocker, not work hidden inside this gate.
- **Prove:** expiry/withdrawal/hold conflicts, failed owner and retry, records/projections/indexes/exports/derivatives/credentials/public-copy warnings, per-purpose/object key destruction and truthful deduplicated-backup semantics.
- **Stop/hand off:** one missing owner receipt, surviving undeclared plaintext, indefinite hold or false physical-erasure claim prevents `SUCCESS`.
- **Unlocks:** `P7-T15` only with a current `SUCCESS` on the identical candidate fingerprint and deployment-selection head.

## P7-G05 — Qualify Viewer, Library, and Imaging

- **Outcome:** Emit the exact-release result for the maximum-admitted actual corpus, source/upload/adversarial validation, static DZI, Library/Trash, shares/releases, 25,000-object/50-MB annotations, calibration, restore and route behavior.
- **Depends on:** `P3-T18`, `P6-T24`, `P7-T01`, and `P7-T03` `MERGED`; current exact-subject `P3-T18=SUCCESS` and `P6-T24=SUCCESS`; active `P6-T30`; and current `P7-T12=DEPLOYED` on the identical candidate fingerprint and deployment-selection head.
- **External prerequisites:** label=P7-EXT-G05-CORPUS; kind=DATA_OR_CORPUS; requires=ACTUAL_MAXIMUM_ADMITTED_GOVERNED_CORPUS_FROZEN; accountable=Imaging Data Owner; validity=exact content root and gate window; evidence=signed immutable Imaging Corpus Admission Receipt | label=P7-EXT-G05-CLIENTS; kind=HARDWARE; requires=SUPPORTED_PHYSICAL_VIEWER_CLIENTS_RESERVED; accountable=Supported Client Matrix Owner; validity=exact device fingerprints and gate window; evidence=signed immutable Viewer Client Reservation Receipt
- **Read first:** Production Qualification Imaging gate, Imaging Control context, Storage Admission Ledger and P7-G20 client/accessibility contract.
- **Change surface:** frozen Imaging workload/adversarial corpus, browser/host measurements, receipts and result only.
- **Implement:** none; missing format, route, restore or accessibility behavior becomes remediation.
- **Prove:** resume/corruption/bomb/storage pressure, protected source before authority, immutable DZI/manifests, search/folders/collections/saved views/Trash, Restricted/Public authorization, annotation scale/conflict/privacy and restart/migration/restore hash equality.
- **Stop/hand off:** synthetic-only client proof, incomplete actual corpus, dynamic-decode fallback, source-authority breach or public privacy leak prevents `SUCCESS`.
- **Unlocks:** `P7-T15` only with this gate and `P7-G20` current `SUCCESS` on the identical candidate fingerprint and deployment-selection head.

## P7-G06 — Qualify Teacher Authoring and local AI

- **Outcome:** Emit the exact-release result for each admitted physical device tier over at least 300 representative tasks and two independent reviewers, including the complete quality, resource, offline, integrity and deterministic-template boundary.
- **Depends on:** `P4-T13`, `P5-T40`, `P7-T01`, and `P7-T03` `MERGED`; current exact-subject `P4-T13=SUCCESS` and `P5-T40=SUCCESS`; active `P6-T30`; and current `P7-T12=DEPLOYED` on the identical candidate fingerprint and deployment-selection head.
- **External prerequisites:** label=P7-EXT-G06-REVIEWERS; kind=HUMAN_AUTHORITY; requires=TWO_QUALIFIED_INDEPENDENT_REVIEWERS_RESERVED; accountable=Teacher AI Qualification Owner; validity=exact task corpus and gate window; evidence=signed immutable AI Reviewer Reservation Receipt | label=P7-EXT-G06-DEVICES; kind=HARDWARE; requires=EVERY_ADMITTED_DEVICE_TIER_RESERVED; accountable=Teacher AI Device Owner; validity=exact hardware software fingerprints and gate window; evidence=signed immutable AI Device Reservation Receipt | label=P7-EXT-G06-CORPUS; kind=DATA_OR_CORPUS; requires=FROZEN_300_TASK_CORPUS_AVAILABLE; accountable=Teacher AI Corpus Owner; validity=exact corpus root and gate window; evidence=signed immutable AI Corpus Admission Receipt
- **Read first:** Production Qualification Teacher AI gate, Teacher AI Stack and Teacher Authoring context.
- **Change surface:** frozen reviewer/device/model corpus, raw measurements, signed reviews and result only.
- **Implement:** none; model, runtime or UI changes create a new bundle/candidate and gate run.
- **Prove:** quality/source/refusal/no-publish/no-grade, bundle download/memory/latency/100-request soak/airplane reload/zero egress/corruption/rollback/cache eviction/injection and complete no-model authoring.
- **Stop/hand off:** missing reviewer/device/corpus/right, one critical error, remote inference or TRACE-SIM participation prevents `SUCCESS`.
- **Unlocks:** `P7-T15` only with this gate and `P7-G20` current `SUCCESS` on the identical candidate fingerprint and deployment-selection head.

## P7-G07 — Qualify Live Learning

- **Outcome:** Emit the exact-release result for one Instructor plus 1,200 learners over 60 minutes and six DZI slides, including synchronized ephemeral traffic, durable interactions, reconnect/restart, convergence and the guest/non-durable boundary.
- **Depends on:** `P4-T20B`, `P4-T30`, `P7-T01`, and `P7-T03` `MERGED`; current exact-subject `P4-T20B=SUCCESS` and `P4-T30=SUCCESS`; active `P6-T30`; and current `P7-T12=DEPLOYED` on the identical candidate fingerprint and deployment-selection head.
- **External prerequisites:** label=P7-EXT-G07-LOAD; kind=HARDWARE; requires=TWELVE_HUNDRED_CLIENT_LOAD_FLEET_RESERVED; accountable=Live Learning Qualification Owner; validity=exact client/load-generator fingerprints and campaign window; evidence=signed immutable Live Load Reservation Receipt | label=P7-EXT-G07-NETWORK; kind=NETWORK_IDENTITY; requires=DECLARED_NETWORK_PATH_RESERVED_AND_INSTRUMENTED; accountable=Institution Network Owner; validity=exact topology and campaign window; evidence=signed immutable Live Network Path Receipt
- **Read first:** Production Qualification Live Learning gate, Live Learning context and frozen phase campaign manifests.
- **Change surface:** exact-release load/browser/host observations, signed receipts, cleanup and result only.
- **Implement:** none; harness/product fixes require a separate task and a new run.
- **Prove:** frozen pointer/viewport rates, six all-response prompts, 20-percent questions, 10-percent reconnect, process restart, final convergence, submitted workspace evidence, Attendance Intervals, guest absence and resource/latency/error distributions.
- **Stop/hand off:** fewer participants/minutes/slides, missing physical-client evidence, retained ephemeral behavior or accepted-data loss prevents `SUCCESS`.
- **Unlocks:** `P7-T15` only with this gate and `P7-G20` current `SUCCESS` on the identical candidate fingerprint and deployment-selection head.

## P7-G08 — Qualify Teacher Broadcast and Media Fallback

- **Outcome:** Emit the exact-release result for one Instructor broadcasting client-encoded VP8/Opus 540p to 100 receive-only viewers for 60 minutes through direct and TURN paths, followed by Galene failure and synchronized slides/text fallback.
- **Depends on:** `P4-T19`, `P4-T20B`, `P7-T01`, and `P7-T03` `MERGED`; current exact-subject `P4-T20B=SUCCESS`; active `P6-T30`; and current `P7-T12=DEPLOYED` on the identical candidate fingerprint and deployment-selection head.
- **External prerequisites:** label=P7-EXT-G08-RECEIVERS; kind=HARDWARE; requires=ONE_HUNDRED_RECEIVE_CLIENTS_RESERVED; accountable=Broadcast Qualification Owner; validity=exact client fingerprints and campaign window; evidence=signed immutable Broadcast Receiver Reservation Receipt | label=P7-EXT-G08-NETWORK; kind=NETWORK_IDENTITY; requires=DIRECT_AND_TURN_PATHS_RESERVED_AND_ATTESTED; accountable=Institution Network Owner; validity=exact Galene TURN topology and campaign window; evidence=signed immutable Broadcast Network Path Receipt
- **Read first:** Production Qualification Teacher Broadcast gate, accepted Galene/TURN topology and frozen network/browser manifest.
- **Change surface:** exact-release media/network/browser/host evidence, fault receipts, cleanup and result only.
- **Implement:** none; topology, token or fallback changes require remediation and a new candidate.
- **Prove:** token/role/Institution isolation, direct and relay behavior, reconnect, bounded bandwidth/CPU/RAM/errors, no recording/transcoding and automatic fallback without durable Live loss.
- **Stop/hand off:** fewer viewers/minutes, virtual-only receivers, unqualified or paid mandatory relay capacity, cloud-media fallback or manual substitution prevents `SUCCESS`.
- **Unlocks:** `P7-T15` only with this gate and `P7-G20` current `SUCCESS` on the identical candidate fingerprint and deployment-selection head.

## P7-G09A — Start the exact-release Assessment gate

- **Outcome:** Admit and start the frozen 300-learner x 100-item x 120-minute exact-release Assessment campaign with all nine response contracts, actors, clients, faults and observers bound to immutable cursors.
- **Depends on:** `P4-T29C`, `P4-T30`, `P7-T01`, and `P7-T03` `MERGED`; current exact-subject `P4-T29C=SUCCESS` and `P4-T30=SUCCESS`; active `P6-T30`; and current `P7-T12=DEPLOYED` on the identical candidate fingerprint and deployment-selection head.
- **External prerequisites:** label=P7-EXT-G09-CORPUS; kind=DATA_OR_CORPUS; requires=THREE_HUNDRED_LEARNER_ONE_HUNDRED_ITEM_WORKLOAD_FROZEN; accountable=Assessment Qualification Owner; validity=exact actor item and response roots through closure; evidence=signed immutable Assessment Workload Admission Receipt | label=P7-EXT-G09-CLIENTS; kind=HARDWARE; requires=THREE_HUNDRED_CLIENT_CAPACITY_RESERVED; accountable=Assessment Load Owner; validity=exact load topology and 120-minute window; evidence=signed immutable Assessment Client Reservation Receipt | label=P7-EXT-G09-OPERATOR; kind=HUMAN_AUTHORITY; requires=PRIMARY_AND_ALTERNATE_OPERATORS_RESERVED; accountable=Assessment Qualification Owner; validity=exact start monitor and closure window; evidence=signed immutable Assessment Operator Reservation Receipt
- **Read first:** Production Qualification Assessment gate, the frozen exact-release manifest and campaign start runbook.
- **Change surface:** gate admission/start receipts and process identities only.
- **Implement:** none; this task starts evidence collection and cannot repair the candidate.
- **Prove:** full participant/item/contract/client admission, exact candidate/manifest/selection equality, active observers and forward receipt movement.
- **Stop/hand off:** missing participant/client/item/operator, drift or partial admission is `NOT_EVALUABLE`; a start remains `RUNNING`, never `SUCCESS`.
- **Unlocks:** `P7-G09B`.

## P7-G09B — Monitor the exact-release Assessment gate

- **Outcome:** Observe the same campaign through its full interval using immutable cursors while executing the frozen revision, disconnect, restart, device-transfer, deadline and final-minute submission schedule.
- **Depends on:** active `P7-G09A` with unchanged candidate, manifest and `DeploymentSelectionReceipt(SELECTED)` head.
- **Read first:** latest receipt cursor, fault schedule, resource summary and only open incidents.
- **Change surface:** monitoring/fault/incident evidence only.
- **Implement:** none; a product or harness fix invalidates the run.
- **Prove:** live worker/resource/receipt progress, revisions at least every 30 seconds, 10-percent disconnect, process restart, authorized transfer and every final-60-second submission.
- **Stop/hand off:** a stopped worker, cursor gap, changed/`REVERTED` deployment selection, missing interval or changed input follows the frozen invalidation rule; never restart history silently.
- **Unlocks:** `P7-G09` after 120 complete minutes and terminal workload evidence.

## P7-G09 — Close the exact-release Assessment gate

- **Outcome:** Reconcile the complete campaign into one terminal Assessment result covering all nine response contracts, zero accepted-data loss, scoring/moderation/high-stakes change/appeal and the no-AI/no-surveillance boundary.
- **Depends on:** completed `P7-G09A` and `P7-G09B` with unchanged candidate, manifest and deployment-selection head.
- **Read first:** terminal receipt range, frozen manifest and Production Qualification Assessment gate.
- **Change surface:** signed evidence aggregation, cleanup and result only.
- **Implement:** none; closure cannot modify candidate, thresholds or evidence.
- **Prove:** exact counts/duration, response/revision/submission reconciliation, final-minute burst, deterministic/manual scoring, independent moderation, 30-day Appeal contract, cleanup and full fingerprint equality.
- **Stop/hand off:** incomplete workload is `PARTIAL`, missing trustworthy evidence is `NOT_EVALUABLE`, and accepted-data/authority/privacy breach is `NEGATIVE`.
- **Unlocks:** `P7-T15` only with this gate and `P7-G20` current `SUCCESS` on the identical candidate fingerprint and deployment-selection head.

## P7-G10 — Qualify learning and credential interoperability

- **Outcome:** Emit the exact-release result for every frozen LTI/Advantage, OneRoster, QTI, CASE, Open Badges, CLR and optional Caliper profile using official/adversarial and two-independent-implementation fixtures at all independent workload thresholds.
- **Depends on:** `P5-T09`, `P5-T15`, `P5-T40`, `P7-T01`, and `P7-T03` `MERGED`; current exact-subject `P5-T09=SUCCESS`, `P5-T15=SUCCESS`, and `P5-T40=SUCCESS`; active `P6-T30`; and current `P7-T12=DEPLOYED` on the identical candidate fingerprint and deployment-selection head.
- **External prerequisites:** label=P7-EXT-G10-RIGHTS; kind=RIGHTS; requires=ALL_OFFICIAL_AND_REFERENCE_ARTIFACT_RIGHTS_ADMITTED; accountable=Interoperability Rights Owner; validity=exact profile corpus and gate window; evidence=signed immutable Standards Rights Admission Receipt | label=P7-EXT-G10-CORPUS; kind=DATA_OR_CORPUS; requires=OFFICIAL_REFERENCE_AND_ADVERSARIAL_CORPORA_FROZEN; accountable=Interoperability Corpus Owner; validity=exact corpus roots and gate window; evidence=signed immutable Standards Corpus Admission Receipt | label=P7-EXT-G10-TOOLS; kind=TOOL_OR_IMPLEMENTATION; requires=TWO_INDEPENDENT_IMPLEMENTATIONS_PER_CLAIM_AVAILABLE; accountable=Interoperability Qualification Owner; validity=exact tool versions configurations and gate window; evidence=signed immutable Independent Tool Reservation Receipt
- **Read first:** Production Qualification interoperability gate, Learning and Credential Interoperability and admitted standards-corpus manifests.
- **Change surface:** exact-release protocol harness/evidence, independent-tool outputs, privacy scan and result only.
- **Implement:** none; protocol or mapping fixes require a separate task and candidate.
- **Prove:** at least 100,000 roster rows, 10,000 QTI Items and 10,000 Credentials independently; registration/subject binding/mapping/quarantine/outage/retry/replay/rotation/grade return/status/optional delivery and no owner transfer.
- **Stop/hand off:** unavailable lawful corpus/tool, reduced threshold, paid certification dependency or universal/public-Host claim prevents `SUCCESS`.
- **Unlocks:** `P7-T15` only with a current `SUCCESS` on the identical candidate fingerprint and deployment-selection head.

## P7-G11 — Qualify Credential Ledger

- **Outcome:** Emit the exact-release result for at least 10,000 issue/verify/status lifecycle operations, private bounded OB3/CLR, authorized online/offline verification, status-list limits, key rotation, restore, portability custody and deletion-to-revocation.
- **Depends on:** `P5-T15`, `P6-T05`, `P6-T21`, `P7-T01`, and `P7-T03` `MERGED`; current exact-subject `P5-T15=SUCCESS` and `P6-T21=SUCCESS`; active `P6-T30`; and current `P7-T12=DEPLOYED` on the identical candidate fingerprint and deployment-selection head.
- **External prerequisites:** label=P7-EXT-G11-CORPUS; kind=DATA_OR_CORPUS; requires=TEN_THOUSAND_OPERATION_CREDENTIAL_CORPUS_FROZEN; accountable=Credential Qualification Owner; validity=exact definition evidence key and operation roots; evidence=signed immutable Credential Workload Admission Receipt
- **Read first:** Production Qualification Credential Ledger gate, Credential Ledger context and accepted credential/portability schemas.
- **Change surface:** exact-release Ledger workload/adversarial vectors, independent verification outputs, receipts and result only.
- **Implement:** none; serializer, status, grant, key or custody changes require remediation.
- **Prove:** immutable definition/evidence/opaque subject, dual approval/step-up, canonical signature, Verification Grant scope/revocation/expiry, >=131,072-entry `statusSize=1` lists and hostile bounds, supersession/expiry/revocation, private-key absence and custody receipt.
- **Stop/hand off:** public roster/profile, exported issuer key, mutable issuance, stale-as-current offline claim or missing custody/deletion evidence prevents `SUCCESS`.
- **Unlocks:** `P7-T15` only with this gate and `P7-G20` current `SUCCESS` on the identical candidate fingerprint and deployment-selection head.

## P7-G12A — Start the exact-release EQA gate

- **Outcome:** Admit and start one frozen 100-case EQA Round with 300 Institution participants, two collaborating staff each and a complete 120-minute fault/observer schedule.
- **Depends on:** `P5-T20C`, `P5-T40`, `P7-T01`, and `P7-T03` `MERGED`; current exact-subject `P5-T20C=SUCCESS` and `P5-T40=SUCCESS`; active `P6-T30`; and current `P7-T12=DEPLOYED` on the identical candidate fingerprint and deployment-selection head.
- **External prerequisites:** label=P7-EXT-G12-WORKLOAD; kind=DATA_OR_CORPUS; requires=THREE_HUNDRED_INSTITUTION_ONE_HUNDRED_CASE_WORKLOAD_FROZEN; accountable=EQA Qualification Owner; validity=exact participant case and submission roots through closure; evidence=signed immutable EQA Workload Admission Receipt | label=P7-EXT-G12-LOAD; kind=HARDWARE; requires=DECLARED_PARTICIPANT_LOAD_CAPACITY_RESERVED; accountable=EQA Load Owner; validity=exact topology and 120-minute window; evidence=signed immutable EQA Load Reservation Receipt | label=P7-EXT-G12-OPERATORS; kind=HUMAN_AUTHORITY; requires=TWO_DISTINCT_STAFF_ROLES_AND_CAMPAIGN_OPERATORS_RESERVED; accountable=EQA Qualification Owner; validity=exact actor manifest and campaign window; evidence=signed immutable EQA Actor Reservation Receipt
- **Read first:** Production Qualification EQA gate, frozen exact-release EQA manifest and start runbook.
- **Change surface:** gate admission/start receipts and process identities only.
- **Implement:** none; this task starts evidence collection and cannot repair EQA.
- **Prove:** all distinct Institutions/staff/cases/resources/operators admitted, exact tuple equality, observers live and receipt progression begins.
- **Stop/hand off:** a missing or duplicate participant/case/operator, drift or partial admission is `NOT_EVALUABLE`; launch is `RUNNING`, not `SUCCESS`.
- **Unlocks:** `P7-G12B`.

## P7-G12B — Monitor the exact-release EQA gate

- **Outcome:** Observe the full 120-minute Round by immutable cursor while executing five-percent reconnect, restart, revisions and final-minute irreversible-seal cases, followed by scoring/report/appeal work.
- **Depends on:** active `P7-G12A` with unchanged candidate, manifest and `DeploymentSelectionReceipt(SELECTED)` head.
- **Read first:** latest cursor, fault schedule, resource summary and only open incidents.
- **Change surface:** monitoring/fault/incident evidence only.
- **Implement:** none; a product or harness fix invalidates the run.
- **Prove:** live worker/receipt progress, all scheduled faults, 30,000 scoring operations, 300 private reports, 30 appeals and nine/ten suppression boundary.
- **Stop/hand off:** stopped worker, cursor gap, changed/`REVERTED` selection, incomplete interval or changed input follows the frozen invalidation rule.
- **Unlocks:** `P7-G12` after the full workload and cleanup terminate.

## P7-G12 — Close the exact-release EQA gate

- **Outcome:** Reconcile the complete EQA run into one terminal result covering participant isolation, collaborative revision, irreversible seal, deterministic scoring/human adjudication, reports/suppression/appeals, retention, restore and no AI/learner authority.
- **Depends on:** completed `P7-G12A` and `P7-G12B` with unchanged candidate, manifest and deployment-selection head.
- **Read first:** terminal receipt range, frozen manifest and Production Qualification EQA gate.
- **Change surface:** signed evidence aggregation, cleanup and result only.
- **Implement:** none; closure cannot modify candidate, thresholds or evidence.
- **Prove:** exact counts/duration/faults, zero duplicate or reopened seal, private participant reports, human adjudication, restore/deletion/cleanup and full fingerprint equality.
- **Stop/hand off:** incomplete workload is `PARTIAL`, missing trustworthy evidence is `NOT_EVALUABLE`, and isolation/seal/authority breach is `NEGATIVE`.
- **Unlocks:** `P7-T15` only with this gate and `P7-G20` current `SUCCESS` on the identical candidate fingerprint and deployment-selection head.

## P7-G13 — Qualify Clinical and imaging interoperability

- **Outcome:** Emit the exact-release result for at least 100 lawful deidentified cases across frozen FHIR R4, DICOMweb, DICOM WSI/ANN and OME-Zarr profiles, independent tools, adversarial privacy admission, dual review, zero writeback, and separate destination-owner accept/reject/withdraw/expire/delete lifecycles for Learning Catalog and for Research wherever that destination is claimed.
- **Depends on:** `P5-T25B`, `P5-T26`, `P5-T27A`, `P5-T40`, `P7-T01`, and `P7-T03` `MERGED`; current exact-subject `P5-T26=SUCCESS` and `P5-T40=SUCCESS`; active `P6-T30`; and current `P7-T12=DEPLOYED` on the identical candidate fingerprint and deployment-selection head.
- **External prerequisites:** label=P7-EXT-G13-RIGHTS; kind=RIGHTS; requires=CASE_TERMINOLOGY_AND_STANDARD_RIGHTS_ADMITTED; accountable=Clinical Rights Owner; validity=exact corpus terminology and gate window; evidence=signed immutable Clinical Rights Admission Receipt | label=P7-EXT-G13-CORPUS; kind=DATA_OR_CORPUS; requires=ONE_HUNDRED_SYNTHETIC_OR_ATTESTED_DEIDENTIFIED_CASES_FROZEN; accountable=Clinical Data Owner; validity=exact case roots and gate window; evidence=signed immutable Clinical Corpus Admission Receipt | label=P7-EXT-G13-TOOLS; kind=TOOL_OR_IMPLEMENTATION; requires=REQUIRED_TERMINOLOGIES_AND_TWO_INDEPENDENT_TOOLS_AVAILABLE; accountable=Clinical Interoperability Owner; validity=exact versions configurations and gate window; evidence=signed immutable Clinical Tool Reservation Receipt | label=P7-EXT-G13-REVIEWERS; kind=HUMAN_AUTHORITY; requires=TWO_DISTINCT_QUALIFIED_REVIEWERS_RESERVED; accountable=Clinical Privacy Steward; validity=exact case set and gate window; evidence=signed immutable Clinical Reviewer Reservation Receipt | label=P7-EXT-G13-DESTINATIONS; kind=HUMAN_AUTHORITY; requires=LEARNING_ACCEPTOR_AND_RESEARCH_ACCEPTOR_WHERE_CLAIMED_RESERVED; accountable=Cross-context Qualification Owner; validity=exact destination-addressed offers case roots and gate window; evidence=signed immutable Clinical Destination Actor Reservation Receipt
- **Read first:** Production Qualification clinical/imaging gate, Clinical and Imaging Interoperability and admitted corpus/terminology manifests.
- **Change surface:** exact-release clinical protocol/adversarial evidence, independent-tool outputs, privacy review receipts and result only.
- **Implement:** none; validator/profile/export or admission changes require remediation.
- **Prove:** official/reference plus two appropriate implementations per claim; PHI/narrative/OCR/pixel/date/UID/code/geometry/dimension rejection, two-person Clinical admission, immutable destination-addressed offer, separate Learning Catalog accept/reject result, separate Research accept/reject result wherever Research use is claimed, replay and wrong-purpose rejection, withdrawal/expiry/deletion propagation, quarantine destruction and every write method denied without cross-context SQL.
- **Stop/hand off:** missing lawful cases/terminology/tools, repaired-to-pass input, residual identifier, Clinical authorization treated as destination acceptance, a claimed destination without its owner result or any clinical/diagnostic/writeback claim prevents `SUCCESS`.
- **Unlocks:** `P7-T15` only with this gate and `P7-G20` current `SUCCESS` on the identical candidate fingerprint and deployment-selection head.

## P7-G14A — Start the exact-release Research gate

- **Outcome:** Admit and start the frozen signed four-hour Research job at one OCPU, four GB RAM and 20-GB workspace against one read-only Dataset Snapshot and fixed offline Environment Manifest.
- **Depends on:** `P5-T30C`, `P5-T40`, `P7-T01`, and `P7-T03` `MERGED`; current exact-subject `P5-T30C=SUCCESS` and `P5-T40=SUCCESS`; active `P6-T30`; and current `P7-T12=DEPLOYED` on the identical candidate fingerprint and deployment-selection head.
- **External prerequisites:** label=P7-EXT-G14-RUNNER; kind=HARDWARE; requires=ONE_OCPU_FOUR_GB_TWENTY_GB_ISOLATED_RUNNER_RESERVED; accountable=Research Qualification Owner; validity=exact environment and four-hour window; evidence=signed immutable Research Runner Reservation Receipt | label=P7-EXT-G14-DATASET; kind=DATA_OR_CORPUS; requires=READ_ONLY_DATASET_SNAPSHOT_FROZEN; accountable=Research Data Owner; validity=exact snapshot root and run window; evidence=signed immutable Research Dataset Snapshot Receipt | label=P7-EXT-G14-REVIEWERS; kind=HUMAN_AUTHORITY; requires=OPERATOR_AND_ARTIFACT_REVIEWER_RESERVED; accountable=Research Qualification Owner; validity=exact manifest and run through cleanup; evidence=signed immutable Research Actor Reservation Receipt
- **Read first:** Production Qualification Research gate, frozen exact-release Research manifest and start runbook.
- **Change surface:** gate admission/start receipts and process identities only.
- **Implement:** none; this task starts evidence collection and cannot alter the environment or runner.
- **Prove:** exact command/environment/snapshot/quotas/fingerprint, default-deny credentials/egress, active observer and forward receipts.
- **Stop/hand off:** missing lawful snapshot/host/operator, unsigned environment, drift or incomplete isolation is `NOT_EVALUABLE`; start is `RUNNING`, not `SUCCESS`.
- **Unlocks:** `P7-G14B`.

## P7-G14B — Monitor the exact-release Research gate

- **Outcome:** Observe the complete four-hour job through immutable cursors while executing the frozen quota, idle, escape, credential, egress, checkpoint/restart and reproduction boundaries.
- **Depends on:** active `P7-G14A` with unchanged candidate, manifest and `DeploymentSelectionReceipt(SELECTED)` head.
- **Read first:** latest cursor, quota/fault schedule, resource summary and only open incidents.
- **Change surface:** monitoring/fault/incident evidence only.
- **Implement:** none; a product, environment or harness fix invalidates the run.
- **Prove:** live CPU/RAM/disk/wall/process/receipt progress, responsive resident plane, no shell/install/credential/egress/escape, exact restart and deterministic output.
- **Stop/hand off:** stopped worker, cursor gap, changed/`REVERTED` selection, shortened interval or changed input follows the frozen invalidation rule.
- **Unlocks:** `P7-G14` after four elapsed hours and terminal artifact/cleanup evidence.

## P7-G14 — Close the exact-release Research gate

- **Outcome:** Reconcile the four-hour run into one terminal result covering quota/isolation, restart/reproduction, signed artifact review/admission, workspace cleanup and absence of production-model activation or clinical claims.
- **Depends on:** completed `P7-G14A` and `P7-G14B` with unchanged candidate, manifest and deployment-selection head.
- **Read first:** terminal receipt range, frozen manifest and Production Qualification Research gate.
- **Change surface:** signed evidence aggregation, cleanup and result only.
- **Implement:** none; closure cannot modify candidate, environment, thresholds or evidence.
- **Prove:** exact elapsed/resource limits, zero escape/egress/credential breach, identical output hashes, signed-only admission, complete cleanup and full fingerprint equality.
- **Stop/hand off:** shortened/incomplete work is `PARTIAL`, missing trustworthy evidence is `NOT_EVALUABLE`, and isolation/authority breach is `NEGATIVE`.
- **Unlocks:** `P7-T15` only with this gate and `P7-G20` current `SUCCESS` on the identical candidate fingerprint and deployment-selection head.

## P7-G15A — Start the exact-release Edge disconnect

- **Outcome:** Admit 100 physical current-through-N-minus-two Edge nodes and begin the frozen seven-day disconnected interval with exact identities, leases, recovery copies, snapshots, workload and observers.
- **Depends on:** `P5-T39E`, `P5-T40`, `P7-T01`, and `P7-T03` `MERGED`; current exact-subject `P5-T39E=SUCCESS` and `P5-T40=SUCCESS`; active `P6-T30`; and current `P7-T12=DEPLOYED` on the identical candidate fingerprint and deployment-selection head.
- **External prerequisites:** label=P7-EXT-G15-FLEET; kind=HARDWARE; requires=ONE_HUNDRED_PHYSICAL_N_N_MINUS_1_N_MINUS_2_NODES_AND_RECOVERY_MEDIA_RESERVED; accountable=Edge Qualification Owner; validity=exact node-set fingerprints and complete disconnect-drain window; evidence=signed immutable Edge Fleet Reservation Receipt | label=P7-EXT-G15-OPERATORS; kind=HUMAN_AUTHORITY; requires=PRIMARY_ALTERNATE_AND_OBSERVERS_RESERVED; accountable=Edge Qualification Owner; validity=exact manifest and complete disconnect-drain window; evidence=signed immutable Edge Operator Reservation Receipt
- **Read first:** Production Qualification Edge gate, Edge Node Profile and exact-release disconnect manifest/runbook.
- **Change surface:** fleet admission/disconnect start receipts and node/process identities only.
- **Implement:** none; node, Platform or harness changes invalidate the run.
- **Prove:** all physical node/hardware/release/key/lease/media/workload identities, no Platform connectivity, active observers and forward local receipt movement.
- **Stop/hand off:** a missing/virtual/unadmitted node, incomplete recovery copy, required spend, drift or connectivity is `NOT_EVALUABLE` or `NEGATIVE`; start is `RUNNING`.
- **Unlocks:** `P7-G15B`.

## P7-G15B — Monitor the seven-day Edge disconnect

- **Outcome:** Preserve low-context cursor-based evidence across seven complete elapsed days while nodes accumulate the frozen one-million-event/50-GB workload and execute declared lease/clock/key/restart/update/revoke cases.
- **Depends on:** active `P7-G15A` with unchanged candidate, manifest and `DeploymentSelectionReceipt(SELECTED)` head.
- **Read first:** latest node/campaign cursors, health summary, fault schedule and only open incidents.
- **Change surface:** monitoring/fault/incident evidence only.
- **Implement:** none; a node, Platform or harness fix invalidates affected evidence.
- **Prove:** continuous trusted time, live node activity, bounds/leases/recovery copies, exact workload growth, scheduled offline faults and zero silent reconnect.
- **Stop/hand off:** dashboard state without node/receipt movement, a missing interval/node or changed/`REVERTED` selection follows the frozen invalidation rule.
- **Unlocks:** `P7-G15C` only after at least seven complete disconnected days and the full frozen backlog.

## P7-G15C — Start exact-release Edge reconnect and drain

- **Outcome:** Reconnect the identical 100-node fleet, freeze drain roots/cursors and start N/N-1/N-2 upcast/transfer/owner-decision/cleanup under at most ten control synchronizations and two byte transfers.
- **Depends on:** completed valid `P7-G15B` with unchanged candidate, workload, manifest and deployment-selection head.
- **External prerequisites:** label=P7-EXT-EDGE-FLEET; kind=HARDWARE; requires=IDENTICAL_100_PHYSICAL_NODES_RECONNECTED; accountable=Edge Campaign Owner; validity=exact node-set fingerprint and reconnect/drain window; evidence=signed immutable Edge Fleet Custody Receipt | label=P7-EXT-G15-NETWORK; kind=NETWORK_IDENTITY; requires=DECLARED_RECONNECT_PATH_RESERVED_AND_INSTRUMENTED; accountable=Institution Network Owner; validity=exact topology and drain window; evidence=signed immutable Edge Reconnect Path Receipt
- **Read first:** reconnect/drain manifest, Gateway/owner acceptance contracts and exact cursor inventory.
- **Change surface:** reconnect/drain admission/start evidence only.
- **Implement:** none; this task starts the bounded drain and cannot repair sync behavior.
- **Prove:** all event/object roots and 100 nodes reconcile, concurrency caps are active, owner observers are live and every cursor moves only forward.
- **Stop/hand off:** partial fleet, reset cursor, changed backlog/candidate/selection or unbounded transfer is `NOT_EVALUABLE` or `NEGATIVE`.
- **Unlocks:** `P7-G15D`.

## P7-G15D — Monitor the exact-release Edge drain

- **Outcome:** Observe the full drain for at most 24 hours while injecting the frozen conflict/order/replay/key/restart cases and preserving every owner acceptance/rejection and cleanup receipt.
- **Depends on:** active `P7-G15C` with matching immutable roots, manifest and deployment-selection head.
- **Read first:** latest drain/owner cursors, fault schedule, resource summary and only open incidents.
- **Change surface:** monitoring/fault/incident evidence only.
- **Implement:** none; a Platform/node/harness fix invalidates the run.
- **Prove:** event/object/result progress, concurrency/resource/latency distributions, five-percent conflict handling, no duplicate/loss/silent overwrite/leak/forbidden authority and terminal node/recovery-copy cleanup.
- **Stop/hand off:** failure to drain within 24 hours, cursor gap, changed/`REVERTED` selection or authority/privacy breach follows the frozen disposition.
- **Unlocks:** `P7-G15` after drain and cleanup terminate.

## P7-G15 — Close the exact-release Edge gate

- **Outcome:** Reconcile the full seven-day/100-node/one-million-event/50-GB/24-hour sequence into one terminal result covering enrollment, leases, recovery, updates, conflicts, replay/key/restart, acceptance/rejection, revoke/wipe and Desktop separation.
- **Depends on:** completed `P7-G15A`–`P7-G15D` with unchanged candidate, node-set fingerprint, manifest and deployment-selection head.
- **Read first:** terminal receipt ranges, frozen manifest and Production Qualification Edge gate.
- **Change surface:** signed evidence aggregation, cleanup and result only.
- **Implement:** none; closure cannot modify candidate, fleet, thresholds or evidence.
- **Prove:** every N/N-1/N-2 node/workload/timing/limit/fault/result, zero loss/duplicate/silent overwrite/leak/forbidden authority, terminal cleanup and full fingerprint equality.
- **Stop/hand off:** Desktop/simulation cannot fill a physical-node gap; incomplete workload/timing is `PARTIAL`, missing evidence `NOT_EVALUABLE`, and authority/privacy breach `NEGATIVE`.
- **Unlocks:** `P7-T15` only with this gate and `P7-G20` current `SUCCESS` on the identical candidate fingerprint and deployment-selection head.

## P7-G16 — Qualify Audit and Operations

- **Outcome:** Emit the exact-release result for at least one million chained records/events, source-outbox identity, idempotent projection, signed checkpoints, tamper/gap/replay, bounded diagnostics, notices/incidents/retention and restore without invented domain truth.
- **Depends on:** `P2-T18B`, `P2-T25`, `P5-T40`, and `P7-T01` `MERGED`; current exact-subject `P2-T25=SUCCESS` and `P5-T40=SUCCESS`; active `P6-T30`; and current `P7-T12=DEPLOYED` on the identical candidate fingerprint and deployment-selection head.
- **Read first:** Production Qualification Audit/Operations gate, Audit and Operations context and Receipt Schema Registry.
- **Change surface:** exact-release audit/operations workload, hostile fixtures, restored verification evidence and result only.
- **Implement:** none; projection, observability or notice fixes require remediation.
- **Prove:** partition predecessor/source hashes, checkpoint signatures, missing/duplicate/reordered/tampered source events, local bounded logs/metrics/traces, durable Notice acknowledgement, incident lifecycle, expiry/privacy and authoritative replay boundaries.
- **Stop/hand off:** log/metric substitution for authority, false-green dashboard, evidence secret/private-data leak or incomplete chain prevents `SUCCESS`.
- **Unlocks:** `P7-T15` only with this gate and `P7-G20` current `SUCCESS` on the identical candidate fingerprint and deployment-selection head.

## P7-G17 — Qualify Backup, PITR, and cold recovery

- **Outcome:** Aggregate and independently verify the complete exact-candidate 90-day/two-35-day protection, actual-corpus restore, separate 150-GB evidence, fault/adversary/key/media/replacement-host and 14-day-soak results into one terminal recovery gate.
- **Depends on:** `P6-T36=SUCCESS`, `P7-T01` `MERGED`, `P7-T12=DEPLOYED`, and current `P7-T14=SUCCESS` on the identical full candidate fingerprint and deployment-selection head.
- **Read first:** Production Qualification Backup/PITR/cold-recovery gate, P6 terminal evidence map and Zero-Cash Durability and Security.
- **Change surface:** read-only signed evidence verification/aggregation and gate result only.
- **Implement:** none; missing or failed recovery work cannot be performed or repaired inside aggregation.
- **Prove:** every daily/expiry/fault/restore/adversary/key/media/cost-independent receipt lies inside the valid interval; exact WAL/object/owner/audit hashes reconcile; P6-T34B contributes a distinct encrypted 150-GB Backup Generation manifest, isolated-target `Restore Receipt(RESTORED)`, byte/object/hash reconciliation, and measured end-to-end protection plus restore throughput separate from export/import; all cleanup is terminal. Any equivalence declaration may preserve unaffected historical durability evidence only and never candidate admission.
- **Stop/hand off:** active/incomplete `P6-T30`, a stale or non-success `P6-T36`, mixed candidate/target, missing interval or unclosed recovery obligation prevents `SUCCESS`.
- **Unlocks:** `P7-T15` only with a current `SUCCESS` on the identical candidate fingerprint and deployment-selection head.

## P7-G18 — Qualify Portable Institution Packages

- **Outcome:** Emit the exact-release result for the complete separate 150-GB current/N-1/N-2 export/import/round-trip corpus, empty-target admission, populated-target rejection, owner/hash/policy reconciliation, Credential custody and prohibited-material absence.
- **Depends on:** `P6-T21` `MERGED`, current `P6-T34B=SUCCESS`, `P7-T01` `MERGED`, and `P7-T12=DEPLOYED` on the identical full candidate fingerprint and deployment-selection head.
- **Read first:** Production Qualification Portability gate, Portability contract and terminal P6-T34B manifest/receipts.
- **Change surface:** read-only exact-release portability evidence verification, privacy scan, cleanup and result only.
- **Implement:** none; adapter/import/export fixes require a new candidate and full rerun.
- **Prove:** exact 150 GB, every context/schema/version/root, current/N-1/N-2 original hashes, populated-target immutability, disabled mappings/re-registration/re-enrollment/stricter retention/Legal Hold treatment, custody receipt and zero prohibited secrets/caches/derivatives.
- **Stop/hand off:** partial corpus, primary-headroom substitution, nonempty-target mutation, mixed candidate/storage or incomplete staging cleanup prevents `SUCCESS`.
- **Unlocks:** `P7-T15` only with a current `SUCCESS` on the identical candidate fingerprint and deployment-selection head.

## P7-G19 — Qualify the initial Zero-Cash evidence window

- **Outcome:** Aggregate the completed 90-day interval and every covering provider/invoice statement into a terminal result proving zero gross incremental charge, zero cash payment and zero projected 12-month charge at the frozen load while disclosing contributed resources and labor.
- **Depends on:** `P6-T36=SUCCESS`, `P7-T01` `MERGED`, `P7-T12=DEPLOYED` and current `P7-T14=SUCCESS` for the identical candidate/workload/account/tariff tuple.
- **External prerequisites:** label=P7-EXT-ZERO-CASH-STATEMENTS; kind=COST_OR_ALLOWANCE; requires=IMMUTABLE_STATEMENTS_COVER_EVERY_INSTANT_WITHOUT_GAP; accountable=Institution Finance Owner; validity=exact P6-T30 interval accounts and tariff tuple; evidence=signed immutable Provider Cost Evidence Receipt
- **Read first:** Production Qualification Zero-Cash gate, complete P6-T28/P6-T35/P6-T36 cost evidence and allowance-expiry ledger.
- **Change surface:** read-only statement/tariff/workload reconciliation, signed accounting evidence and result only.
- **Implement:** none; a missing statement or positive charge is not repaired or estimated away inside this task.
- **Prove:** trusted 90-day coverage, every mandatory hardware/software/API/model/standard/support/domain/certificate/connectivity/utility input gross before credits, tariff/tax/currency/allowance caps and deterministic 12-month projection.
- **Stop/hand off:** an unavailable covering statement is `NOT_EVALUABLE`; positive charge/payment/projection or hidden mandatory spend is `NEGATIVE`; never claim “free forever.”
- **Unlocks:** `P7-T15` only with a current `SUCCESS` on the identical candidate fingerprint and deployment-selection head.

## P7-G20 — Qualify accessibility and the Supported Client Matrix across all human workflows

- **Outcome:** Emit one exact-release whole-product result proving every human-facing workflow is discoverable and usable to WCAG 2.2 AA on the complete Supported Client Matrix, including keyboard, screen reader, reflow, contrast, focus, reduced motion, touch/pointer alternatives and failure recovery.
- **Depends on:** `P5-T40`, `P6-T22`, `P7-T01`, and `P7-T03` `MERGED`; current exact-subject `P5-T40=SUCCESS` and `P6-T22=SUCCESS`; active `P6-T30`; and current `P7-T12=DEPLOYED` on the identical candidate fingerprint and deployment-selection head.
- **External prerequisites:** label=P7-EXT-CLIENT-MATRIX; kind=HARDWARE; requires=EVERY_DECLARED_PHYSICAL_CLIENT_AVAILABLE; accountable=Supported Client Matrix Owner; validity=exact client fingerprints and gate window; evidence=signed immutable Physical Client Reservation Receipt | label=P7-EXT-ASSISTIVE-TECH; kind=TOOL_OR_IMPLEMENTATION; requires=EVERY_DECLARED_ASSISTIVE_TECHNOLOGY_AVAILABLE; accountable=Accessibility Gate Owner; validity=exact versions configurations and gate window; evidence=signed immutable Assistive Technology Reservation Receipt | label=P7-EXT-ACCESSIBILITY-REVIEWERS; kind=HUMAN_AUTHORITY; requires=QUALIFIED_REVIEWERS_RESERVED; accountable=Accessibility Gate Owner; validity=complete human-workflow matrix and gate window; evidence=signed immutable Accessibility Reviewer Reservation Receipt
- **Read first:** Production Qualification evidence/decision rules, Supported Client Matrix, Accessibility Gate, P4-T00/P5-T00 route contracts and every context's human workflow inventory.
- **Change surface:** frozen route/state/client/assistive-technology matrix, automated/manual evidence, sanitized recordings or hashes, defects and result only.
- **Implement:** none; a missing route/state or accessibility/client defect requires a separate remediation task and new candidate.
- **Prove:** Platform/Trust/operations, Viewer/Library/shares/annotations, Catalog/learner, Teacher Authoring/local-AI/no-model, Live/Broadcast/fallback, Assessment, Integration/Credential, EQA, Clinical Shadow, Research, Edge and portability/admin workflows; current-through-declared browser/OS/device families; zoom/reflow, keyboard-only, screen readers, reduced motion, errors/offline/reconnect/expiry/revocation and no inaccessible pointer-only path.
- **Stop/hand off:** an untested declared client/assistive technology, inaccessible critical workflow, hidden production route, virtual-only substitution or mixed candidate is `NOT_EVALUABLE`, `PARTIAL` or `NEGATIVE` under the frozen rule.
- **Unlocks:** `P7-T15` only with a current `SUCCESS` on the identical candidate fingerprint and deployment-selection head.

## Prequalification and Golden execution

## P7-T15 — Aggregate all non-pilot prerequisite results

- **Outcome:** Verify `P7-G01`–`P7-G20`, `P7-T14` and every required lifecycle/evidence head are current `SUCCESS` for the complete `P7-T12` candidate fingerprint, whose hash and current `DeploymentSelectionReceipt(SELECTED)` head still identify the release actually routed on the declared host.
- **Depends on:** `P6-T36=SUCCESS`, `P7-T14=SUCCESS`, and every `P7-G01`–`P7-G20` parent gate result complete, current and `SUCCESS`; all child campaign receipts must be terminal inputs to their parent result.
- **Read first:** Production Qualification decision rules, complete `P7-T11`/`P7-T12` candidate fingerprint, Deployment Selection Receipt and every gate result schema.
- **Change surface:** read-only qualification aggregation/evidence.
- **Implement:** none; evaluate exact-subject gate and child-receipt heads and sign the prerequisite aggregate without product, configuration, selection or evidence mutation.
- **Prove:** hash equality across source commit/tree, release artifact/SBOM/signature, configuration/routes/migrations, profile/host/storage/firmware/cache, database/client/kernel/filesystem, backup target/network, clients/corpora/workloads/operators, tools/models/protocols/keys/policies/controllers/evidence schemas/trusted time and cost inputs; verify the current selection head is the same `SELECTED` receipt bound by every gate and route observation.
- **Stop/hand off:** any non-success/stale/mismatch, missing fingerprint field, changed selection head, `REVERTED` selection, route divergence or historical substitution blocks Journey admission and invalidates affected evidence.
- **Unlocks:** `P7-T16`.

## P7-T16 — Freeze and sign the exact Golden Manifest

- **Outcome:** Render all actors, fixtures, commands, reservations, receipts, faults, cleanup, `P7-G01`–`P7-G20` heads, random seed and trusted time into one immutable manifest that binds the complete `P7-T12` candidate fingerprint hash and current `DeploymentSelectionReceipt(SELECTED)` head with zero schema gaps.
- **Depends on:** `P7-T03` and `P7-T07` `MERGED`, with current exact-subject `P7-T15=SUCCESS`.
- **Read first:** Golden Journey immutable manifest and Receipt Registry.
- **Change surface:** manifest/signature/coverage evidence only.
- **Implement:** none; render and sign the exact Golden manifest from immutable inputs without changing actors, fixtures, thresholds, product or deployment selection.
- **Prove:** every G00–G38 input/schema resolves; the complete candidate-fingerprint hash, selected release/route and selection-receipt predecessor/head equal P7-T15; no placeholder, mutable tag, partial tuple or alias.
- **Stop/hand off:** missing/unregistered receipt/result, a changed/`REVERTED` selection head or any candidate-fingerprint mismatch is `NOT_EVALUABLE` or `NEGATIVE` under the frozen rule.
- **Unlocks:** `P7-T17`.

## P7-T17 — Evaluate Journey Admission

- **Outcome:** Compare all prerequisite results/expiry, the complete candidate fingerprint and the live current-deployment projection and emit `JourneyAdmissionReceipt(READY)` only when the current `DeploymentSelectionReceipt(SELECTED)` head/hash, selected release, route and every bound field still equal the P7-T16 manifest.
- **Depends on:** current exact-subject `P7-T16=FROZEN`.
- **Read first:** Golden Journey G00 and Journey Admission schema.
- **Change surface:** admission execution/evidence only.
- **Implement:** none; compare every live prerequisite and selected-route fingerprint to the frozen manifest and emit the admission receipt without product or lifecycle mutation.
- **Prove:** mutate/miss/stale each bound input, candidate-fingerprint field, selection head, selection disposition and upstream route; each mismatch yields `NEGATIVE` or `NOT_EVALUABLE` and no later step starts.
- **Stop/hand off:** READY is evidence only, not a lifecycle transition; any later selection-head change or `REVERTED` disposition invalidates READY and the current P6-T30 admission, requiring a new P6-T30 before re-admission.
- **Unlocks:** `P7-T18`.

## P7-T18 — Start the exact G00–G38 campaign

- **Outcome:** Immediately re-read and bind the still-current `DeploymentSelectionReceipt(SELECTED)` head and complete candidate-fingerprint hash from P7-T17, then begin the ordered logical run and record immutable process/receipt cursors for continuation without conversation memory.
- **Depends on:** `P7-T17=READY` with the current `DeploymentSelectionReceipt(SELECTED)` head exactly matching the admitted campaign tuple.
- **External prerequisites:** label=P7-EXT-GOLDEN-ACTORS; kind=HUMAN_AUTHORITY; requires=ALL_NAMED_PEOPLE_PRESENT_AND_AUTHORIZED; accountable=Golden Journey Owner; validity=exact manifest and full run window; evidence=signed immutable Actor Reservation Receipt | label=P7-EXT-GOLDEN-RESOURCES; kind=HARDWARE; requires=ALL_DECLARED_CLIENTS_HOSTS_TARGETS_AND_MEDIA_RESERVED; accountable=Golden Journey Operations Owner; validity=exact manifest and full run window; evidence=signed immutable Golden Resource Reservation Receipt
- **Read first:** Golden Journey exact steps and campaign runbook.
- **Change surface:** production/pilot-free campaign execution and evidence only.
- **Implement:** none; revalidate admission and start the ordered receipt-driven Golden campaign, excluding product, fixture, threshold, lifecycle or selection mutation.
- **Prove:** start-time selection head/disposition/route and full fingerprint equal the admission/manifest, every predecessor is verified before its command, receipts progress and no undeclared mode/process/input exists.
- **Stop/hand off:** any selection-head change or `REVERTED` disposition invalidates that admitted campaign tuple and this run and requires a new campaign admission/start receipt; route/fingerprint mismatch, fault outside manifest or untrustworthy evidence also invalidates the run. Do not silently restart as the same run or carry admission by equivalence.
- **Unlocks:** `P7-T19`.

## P7-T19 — Monitor and operate the Golden campaign

- **Outcome:** Continue the same run using receipt hashes/cursors, declared human actions and bounded monitoring, re-verifying the bound `DeploymentSelectionReceipt(SELECTED)` head, current route and complete candidate fingerprint before each command and after every fault or recovery boundary.
- **Depends on:** active `P7-T18` run.
- **Read first:** run manifest, last coordination handoff and receipt cursor only.
- **Change surface:** campaign evidence/incident records; fixes require a new candidate/run.
- **Implement:** none; continue the same cursor-bound campaign, execute only declared actions/faults and record incidents without product, fixture, threshold or selection mutation.
- **Prove:** monotonically ordered receipts, unchanged selection head/disposition/route/fingerprint, mode drain, fault recovery and cleanup obligations as the run advances.
- **Stop/hand off:** dashboard RUNNING without receipt/worker progress is incomplete; any selection-head change or `REVERTED` disposition invalidates the run and P6-T30 admission and requires a new P6-T30; route/fingerprint drift or any code/config fix also invalidates the run.
- **Unlocks:** `P7-T20` after G38 terminal evidence.

## P7-T20 — Close the Golden result and Phase 7

- **Outcome:** Reconcile manifest/admission, ordered G00–G38 receipts, every expected negative/fault, resource series, source/event counts, cleanup and final Audit/Delivery heads into `GoldenJourneyResult` and phase result.
- **Depends on:** current exact-subject `P7-T18=COMPLETED` and `P7-T19=COMPLETED`, with the terminal G38 Cleanup/Result Receipt head and unchanged `DeploymentSelectionReceipt(SELECTED)` head exactly matching the admitted campaign tuple.
- **Read first:** Golden Journey terminal/cleanup, Production Qualification.
- **Change surface:** read-only aggregation and signed results.
- **Implement:** none; reconcile immutable manifest/admission/step/fault/cleanup receipts and sign the Golden and phase results without product, configuration, selection or evidence mutation.
- **Prove:** zero gap/duplicate/reorder/unexplained retry/surviving temp/mode/altered fixture; restore workspace deletion; the terminal current selection head/route/fingerprint still equal admission and every step receipt.
- **Stop/hand off:** only current `SUCCESS` on an unchanged `SELECTED` deployment unlocks pilot; a changed/`REVERTED` selection invalidates the result, and Journey success itself is neither pilot, qualification nor activation.
- **Unlocks:** Phase 8 pilot admission.
