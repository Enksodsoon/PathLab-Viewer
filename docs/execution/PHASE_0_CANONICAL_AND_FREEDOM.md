# Phase 0 — Canonical Plan, Software Freedom, Rights, and Supply Chain

Phase 0 makes the accepted destination reviewable on `main` and removes every known legal, asset, dependency, provenance, and offline-build ambiguity before runtime implementation expands. All tasks inherit the global rules in [README](./README.md).

## P0-T01 — Publish the ratified plan as the canonical review

- **Outcome:** Open a planning-and-validation-only pull request from `codex/production-endpoint-wayfinder`, run protected documentation, execution-plan, and public-repository checks, resolve review findings without weakening accepted decisions, and merge the exact accepted plan and its fail-closed validation tooling to `main`.
- **Depends on:** none.
- **Read first:** [Final Production Endpoint](../architecture/FINAL_PRODUCTION_ENDPOINT.md), [Delivery State Ledger](../architecture/DELIVERY_STATE_LEDGER.md), [ADR register](../adr/README.md).
- **Change surface:** planning/architecture documents, execution-plan validator and focused tests, public-repository checker and focused regression tests, GitHub pull-request metadata, and protected checks; no product runtime or deployment surface.
- **Implement:** none; publish, review, and merge only the ratified planning/acceptance documents and their fail-closed repository validation tooling, without product, schema, deployment configuration, or runtime mutation.
- **Prove:** resolve and record the live `codex/production-endpoint-wayfinder` tip and current default-branch tip at execution time rather than trusting a copied planning SHA; prove a clean worktree, validator negative fixtures, valid internal links/tables/ADR sequence, no secret/private-address leak, exact protected-check head, merge receipt, and default-branch commit.
- **Stop/hand off:** do not merge if review changes authority, zero-cash, capacity, clinical, rights, recovery, or activation decisions; open a new decision instead. This task establishes only `PLANNED` on `main`.
- **Unlocks:** `P0-T01A` and every other Phase 0 task, beginning with `P0-T02A`.

## P0-T01A — Audit architecture precedence and supersession

- **Outcome:** Publish a reviewable Architecture Precedence Register that classifies every current or historical planning/architecture document, resolves every contradiction against the ratified destination, and makes the canonical source for each decision unambiguous.
- **Depends on:** `P0-T01` `MERGED`.
- **Read first:** [Final Production Endpoint](../architecture/FINAL_PRODUCTION_ENDPOINT.md), [Production Endpoint Decision Register](../adr/README.md), ADR 0131, [Feature Completion Matrix](../architecture/FEATURE_COMPLETION_MATRIX.md), [Adaptive Viewer Capacity](../architecture/ADAPTIVE_VIEWER_CAPACITY.md), [Password Recovery](../architecture/PASSWORD_RECOVERY.md), [PostgreSQL backup/restore](../architecture/POSTGRES_BACKUP_RESTORE.md), and the complete repository planning/architecture document inventory.
- **Change surface:** architecture precedence/supersession register, explicit status banners and cross-links in affected planning documents, and documentation consistency/link checks; accepted historical ADR text remains append-only.
- **Implement:** assign each document and decision topic one explicit status such as canonical, supporting contract, baseline-only, migration-input-only, or superseded; name the controlling canonical document and accepted ADR for every conflict. The Final Production Endpoint, current accepted ADR register, and current context/qualification/security contracts control over older implementation plans or observations. At minimum, classify `ADAPTIVE_VIEWER_CAPACITY.md`, `PASSWORD_RECOVERY.md`, and `POSTGRES_BACKUP_RESTORE.md` as non-authoritative baseline or migration inputs wherever they conflict with the ratified destination.
- **Prove:** repository-wide document/link and normative-language inventory, exact conflict-to-controller mapping, seeded stale-plan reference detection, zero unresolved contradictory requirement, and independent review of every baseline-only or superseded disposition.
- **Stop/hand off:** do not silently rewrite or delete decision history. A conflict that changes accepted authority, lifecycle, security, privacy, capacity, recovery, zero-cash, or activation semantics requires a named superseding ADR; unresolved precedence is `NOT_EVALUABLE` and blocks Phase 0 closure.
- **Unlocks:** `P0-T12` and downstream use of explicitly classified legacy inputs.

## P0-T02A — Establish copyright and relicensing authority

- **Outcome:** Audit Git history, contributor/file provenance, prior licenses, copied/generated material and accountable ownership for all PathLab-authored code, especially `packages/viewer-ui`, then record a file/contributor disposition ledger suitable for a human legal decision.
- **Depends on:** `P0-T01` `MERGED`.
- **Read first:** ADR 0046, repository history, all package metadata and contribution records.
- **Change surface:** `docs/supply-chain/` authority ledger and evidence references only; license changes wait for an accountable disposition.
- **Implement:** distinguish proven PathLab-authored, third-party, generated, clean-room-required and unresolved files; identify the person authorized to make any relicensing decision.
- **Prove:** `git log --follow`/blame/contributor/file inventory with hashes and source evidence, independently reviewable without relying on Codex's legal conclusion.
- **Stop/hand off:** Codex must not invent copyright ownership or legal certainty. Ambiguity is `NOT_EVALUABLE` and requires isolation or clean-room replacement.
- **Unlocks:** `P0-T02`, `P0-T05A`.

## P0-T02 — Establish root license and notice policy

- **Outcome:** Add the root Apache-2.0 license, repository-wide copyright/notice policy, contribution provenance rules, binary/source notice requirements, and release-bundle placement contract.
- **Depends on:** `P0-T02A` `MERGED`.
- **External prerequisites:** label=P0-T02-RELICENSING-AUTHORITY; kind=HUMAN_AUTHORITY; requires=APPROVED; accountable=copyright-and-relicensing-authority; validity=current-for-the-P0-T02A-authority-ledger-and-proposed-license; evidence=immutable-signed-relicensing-disposition
- **Read first:** ADR 0046, [Feature Completion Matrix](../architecture/FEATURE_COMPLETION_MATRIX.md), repository `README.md`, `CONTRIBUTING.md`, package manifests.
- **Change surface:** root `LICENSE`, `NOTICE`, contribution/release documentation, package metadata, public-repository checks.
- **Implement:** distinguish PathLab-authored code from third-party works; define SPDX identifiers and generated-file treatment; preserve compatible third-party notices without relicensing them.
- **Prove:** license scanner and package metadata agree; source and built distributions contain required license/notice files; public-repository check rejects omissions.
- **Stop/hand off:** unknown ownership or incompatible inbound contribution is `NOT_EVALUABLE`; no legal conclusion may be invented from a package name.
- **Unlocks:** `P0-T05A`, `P0-T06`, `P0-T08`, `P0-T09`.

## P0-T03 — Inventory dependency licenses and provenance

- **Outcome:** Produce the authoritative inventory of every mandatory Python, JavaScript, native, deployment, test, model, font, icon, standard artifact, and build dependency with exact source, version, checksum, license, notice, purpose, and distribution status.
- **Depends on:** `P0-T01` `MERGED`.
- **Read first:** ADRs 0046, 0054, 0080 and 0122; root/package/deploy manifests; [Teacher AI Stack](../architecture/TEACHER_AI_STACK.md); [Zero-Cash Runtime](../architecture/ZERO_CASH_RUNTIME.md).
- **Change surface:** `docs/supply-chain/`, lockfiles only for corrections, release-manifest definitions, dependency-scanning configuration.
- **Implement:** separate runtime-mandatory, build-only, test-only, optional, and excluded inputs; record transitive resolution and redistribution constraints; flag mutable/unverifiable sources.
- **Prove:** inventories reconcile to all lockfiles and imported/bundled binaries; clean install/build reports no unrecorded mandatory package.
- **Stop/hand off:** unresolved or incompatible mandatory input blocks Phase 0; do not classify an online service as free software or an expiring allowance as zero-cash.
- **Unlocks:** `P0-T03A`, `P0-T04`, `P0-T05A`, `P0-T06`, `P0-T08`, `P0-T09`.

## P0-T03A — Admit exact runtime and verification toolchain pins

- **Outcome:** Select and admit exact free, ARM64-capable, offline-verifiable pins for PostgreSQL minor, PgBouncer, Caddy, NATS/JetStream, canonical JSON/signature tooling, SBOM generators/validators, WebAuthn implementation, provenance verification and security/license scanning.
- **Depends on:** `P0-T03` `MERGED`.
- **Read first:** dependency inventory, [Zero-Cash Runtime](../architecture/ZERO_CASH_RUNTIME.md), [Zero-Cash Durability and Security](../architecture/ZERO_CASH_DURABILITY_SECURITY.md), [Production Qualification](../architecture/PRODUCTION_QUALIFICATION.md).
- **Change surface:** supply-chain admission ledger, exact lock/config manifests and non-secret offline smoke fixtures.
- **Implement:** record source, exact version/revision, checksum/signature/provenance, license, ARM64 availability, maintenance status, purpose and mirror path.
- **Prove:** official-source verification, admitted offline validator/smoke tests and rejection of mutable tags or unpinned transitive binaries.
- **Stop/hand off:** unavailable ARM64 artifact, unclear rights, automatic promotion or mandatory paid/hosted verification is `NEGATIVE` or `NOT_EVALUABLE`.
- **Unlocks:** `P0-T06`, `P0-T09`, `P1-T03`, `P1-T14`, `P1-T22`.

## P0-T04 — Remove the unresolved `combine-errors` dependency path

- **Outcome:** Locate every direct or transitive use of `combine-errors`, replace it with an admitted implementation or remove the path, update locks, and preserve observable behavior.
- **Depends on:** `P0-T03` `MERGED`.
- **Read first:** the `P0-T03` inventory and affected package source/tests.
- **Change surface:** affected JavaScript package manifest/lockfile, narrow callers, tests, dependency inventory and notices.
- **Implement:** choose the smallest behavior-preserving replacement with verified license/provenance; avoid unrelated upgrades.
- **Prove:** focused behavior tests, full web build/test/lint relevant to the changed dependency, lockfile audit, absence from resolved graph and offline input set.
- **Stop/hand off:** if callers depend on undocumented edge behavior, write characterization tests first and report `PARTIAL` until equivalence is shown.
- **Unlocks:** `P0-T09`, `P0-T12`.

## P0-T05 — Create the Asset Rights Ledger

- **Outcome:** Inventory every shipped image, icon, font, audio/video object, design source, fixture, screenshot, and derived visual with creator, provenance, license/permission, attribution, content hash, permitted use, privacy class, and release disposition.
- **Depends on:** `P0-T01` `MERGED`.
- **Read first:** ADR 0048, [Feature Completion Matrix](../architecture/FEATURE_COMPLETION_MATRIX.md), web assets/public files, documentation media and test fixtures.
- **Change surface:** `docs/supply-chain/ASSET_RIGHTS_LEDGER.*`, asset-check configuration, contributor guidance.
- **Implement:** make missing, changed-hash, prohibited, PHI-risk, or attribution-incomplete entries release-blocking; distinguish fixtures never shipped from release assets.
- **Prove:** repository scan reconciles every governed extension/path to exactly one ledger entry and detects an injected unknown asset.
- **Stop/hand off:** an unverifiable asset is rejected, not presumed permitted.
- **Unlocks:** `P0-T07`, `P0-T08`, `P0-T12`.

## P0-T05A — Resolve the AGPL shared-viewer release boundary

- **Outcome:** Resolve `packages/viewer-ui/package.json` declaring `AGPL-3.0-or-later`: either perform a fully authorized, evidenced relicensing; keep a deliberately compatible separated work under correct obligations; or clean-room replace/isolate it outside the Apache production artifact while preserving its one current consumer.
- **Depends on:** `P0-T02A` and `P0-T03` `MERGED`.
- **Read first:** authority/dependency ledgers, package source/history/consumer, root licensing policy and release architecture.
- **Change surface:** `packages/viewer-ui`, its consumer, package metadata/build graph, notices/SBOM and focused UI tests.
- **Implement:** choose only the disposition supported by accountable ownership and compatibility evidence; preserve observable viewer behavior and accessibility.
- **Prove:** provenance/license review, package and web builds/tests, release-boundary/SBOM scan and absence of accidental license metadata mismatch.
- **Stop/hand off:** changing the `license` field alone is never relicensing evidence. Unresolved authority blocks Apache release admission.
- **Unlocks:** `P0-T06`, `P0-T08`, `P0-T12`.

## P0-T06 — Generate SPDX and CycloneDX software inventories

- **Outcome:** Generate deterministic SPDX and CycloneDX source/build SBOMs and a human notice bundle from admitted dependency records for every release component and offline kit.
- **Depends on:** `P0-T02`, `P0-T03`, `P0-T03A`, `P0-T04`, and `P0-T05A` `MERGED`.
- **Read first:** Phase 0 license/provenance artifacts and ADR 0080.
- **Change surface:** build scripts, `.github/workflows/`, `docs/supply-chain/`, release artifact manifest.
- **Implement:** retain tool versions, hashes, package relationships, native binaries, model bundles, provider artifacts, and source references; prevent nondeterministic timestamps from changing semantic contents.
- **Prove:** schema validation, repeated generation equivalence, reconciliation against locks/build output, and release failure on missing or mismatched components.
- **Stop/hand off:** an SBOM generator that requires an unmirrored paid/hosted service is not admissible.
- **Unlocks:** `P0-T09`, `P1-T22`.

## P0-T07 — Replace unresolved imagery and derived trade dress

- **Outcome:** Remove or replace the unresolved histology imagery and any visual identity that copies or implies affiliation with another product, then record all replacements in the Asset Rights Ledger.
- **Depends on:** `P0-T05` `MERGED`.
- **Read first:** ADR 0048, the Asset Rights Ledger, baseline-only `apps/web/DESIGN.md`, `apps/web/PRODUCT.md`, brand and asset source files; the Architecture Precedence Register and rights contracts control conflicts.
- **Change surface:** web assets/styles/components, screenshots/docs, visual regression and responsive tests, ledger entries.
- **Implement:** establish an Independent PathLab Identity; preserve accessibility, theme behavior, route function and performance budgets; do not redesign unrelated workflows.
- **Prove:** rights scan, hash reconciliation, light/dark and supported viewport visual checks, accessibility checks, full web build/test, and removal of superseded files from release output.
- **Stop/hand off:** if authorship or permission is uncertain, use newly created rights-clear assets rather than approximate the disputed work.
- **Unlocks:** `P0-T08`, `P0-T12`.

## P0-T08 — Enforce release-wide freedom and rights admission

- **Outcome:** Add a fail-closed policy and automated gate covering source, binary, model, font, icon, imagery, standards fixtures, and build inputs against admitted licenses, provenance, notices, and rights records.
- **Depends on:** `P0-T02`, `P0-T03`, `P0-T03A`, `P0-T05`, `P0-T05A`, `P0-T06`, and `P0-T07` `MERGED`.
- **Read first:** all Phase 0 inventories, [Production Qualification](../architecture/PRODUCTION_QUALIFICATION.md), ADRs 0046, 0048, 0054, 0080, 0122.
- **Change surface:** `scripts/`, protected CI, release-manifest schema, supply-chain documentation.
- **Implement:** allow explicit policy exceptions only as rejected/non-release inputs; require immutable evidence for every shipped artifact and the mandatory software path.
- **Prove:** positive repository/release scan plus seeded negative cases for unknown file, changed hash, incompatible license, missing notice, mutable source, and unadmitted model/tool.
- **Stop/hand off:** a waiver cannot make a mandatory input admissible; replace it or redraw the accepted architecture.
- **Unlocks:** `P0-T12`, `P7-T04`.

## P0-T09 — Freeze the offline build-input and source bundle contract

- **Outcome:** Define the signed, content-addressed provider/package/source/model/tool mirror layout and manifest that an Institution-owned runner can consume with network disabled.
- **Depends on:** `P0-T03`, `P0-T03A`, `P0-T04`, `P0-T05A`, and `P0-T06` `MERGED`.
- **Read first:** [Zero-Cash Runtime](../architecture/ZERO_CASH_RUNTIME.md), [Teacher AI Stack](../architecture/TEACHER_AI_STACK.md), ADR 0080, accepted dependency/SBOM artifacts.
- **Change surface:** `docs/supply-chain/`, release manifest schemas, mirror configuration and verification scripts; not yet the complete runtime installer.
- **Implement:** cover Python wheels/sdists, pnpm store, native ARM64 tools, OpenTofu/provider mirror, recovery tools, model bundles, standards fixtures, signatures and source/notice archives.
- **Prove:** manifest/schema/hash verification and a bounded no-network dependency-resolution rehearsal on an owned runner or a clearly labelled non-certifying fixture.
- **Stop/hand off:** missing owned ARM64 runner makes certification `NOT_EVALUABLE`, but the contract and fixture validation may still be `CHECKED_LOCAL`.
- **Unlocks:** `P1-T14`, `P1-T22`.

## P0-T09A — Close the mandatory-path zero-cash and egress inventory

- **Outcome:** Map every build, install, run, backup, restore, network-identity, model, standards and support path to its license, owned/donated resource, gross cash obligation, allowance expiry/cap and required egress.
- **Depends on:** `P0-T03A`, `P0-T08`, and `P0-T09` `MERGED`.
- **Read first:** [Zero-Cash Durability and Security](../architecture/ZERO_CASH_DURABILITY_SECURITY.md), [Final Production Endpoint](../architecture/FINAL_PRODUCTION_ENDPOINT.md), all admitted-input and rights ledgers.
- **Change surface:** accounting/egress baseline schemas and report, automated endpoint/input reconciliation.
- **Implement:** distinguish gross incremental charge/payment from credits, contributed resources, baseline utilities and Institution labor; project every mandatory allowance for 12 months.
- **Prove:** static endpoint/build-input scan, complete bill-of-inputs reconciliation, zero undeclared hosted dependency and seeded expiring/paid-path rejection.
- **Stop/hand off:** this is not the operated 90-day claim. Any mandatory expiring allowance or projected gross incremental charge is `NEGATIVE`.
- **Unlocks:** `P0-T12`, later zero-cash campaign tooling.

## P0-T10 — Implement evidence schema foundations

- **Outcome:** Add JSON Schema 2020-12 common-envelope definitions, canonical JSON/signature test vectors, schema catalog rules, and validation tooling for the Receipt Schema Registry without yet implementing domain emitters.
- **Depends on:** `P0-T01` and `P0-T02` `MERGED`.
- **Read first:** [Receipt Schema Registry](../architecture/RECEIPT_SCHEMA_REGISTRY.md), [Delivery State Ledger](../architecture/DELIVERY_STATE_LEDGER.md), [Golden Institution Journey](../architecture/GOLDEN_INSTITUTION_JOURNEY.md).
- **Change surface:** `schemas/evidence/`, schema validation scripts/tests, contributor documentation.
- **Implement:** stable schema IDs/versions, shared definitions, privacy exclusions, content-hash references, signature metadata, journey linkage and forward-compatible version policy.
- **Prove:** metaschema validation, canonicalization/signature vectors, invalid privacy/identity/version examples, catalog completeness against the registry.
- **Stop/hand off:** schemas must not claim that a receipt creates domain authority or a lifecycle transition unless the registry explicitly says so.
- **Unlocks:** `P0-T10B`, `P0-T10D`, context receipt foundations in Phases 1–6 and exact-release schema tooling.

## P0-T10A — Reconcile and close evidence-registry coverage

- **Outcome:** Independently reconcile every normative receipt/result reference against the bounded schema-family implementations and emit one exact zero-unresolved-name closure result.
- **Depends on:** `P0-T10B`, `P0-T10C`, `P0-T10D`, `P0-T10E`, and `P0-T10F` `MERGED`.
- **Read first:** Receipt Schema Registry, the schema-family coverage reports from `P0-T10B`–`P0-T10F`, and the evidence-schema references discovered by the repository coverage checker.
- **Change surface:** registry coverage index, compatibility matrix, coverage-checker fixtures and signed reconciliation result only.
- **Implement:** none; run the complete name/path/ID/version/owner/source/disposition/lifecycle-effect reconciliation, preserve the child artifacts unchanged, and route every newly discovered schema implementation to a separate bounded child task.
- **Prove:** zero unresolved normative names, exact repository path/`$id`/semantic-version coverage, positive/adversarial fixture coverage for every registered type, and no alias, generic log line or mutable report substitutes for a schema.
- **Stop/hand off:** any missing, duplicate, ambiguous, unowned or unimplemented type makes closure `NEGATIVE` or `NOT_EVALUABLE`; this parent never patches a child schema in place.
- **Unlocks:** all campaign tooling, `P3-T17`, Phase 5 Edge lifecycle and Phase 7 aggregation only on current `P0-T10A=SUCCESS`.

## P0-T10B — Implement exact-release lifecycle, drift, and cutover evidence schemas

- **Outcome:** Register and implement the bounded exact-release schema family for Candidate Fingerprint, Evidence Impact/Equivalence Result, Deployment Selection Receipt, SQLite Authority Cutover Readiness and SQLite Authority Cutover Result.
- **Depends on:** `P0-T10` `MERGED`.
- **Read first:** Receipt Schema Registry Platform Governance rows, Delivery State Ledger transition/invalidation rules, Production Qualification evidence-decision rules and SQLite-to-PostgreSQL authority-cutover contract.
- **Change surface:** Platform Governance evidence registry rows, `schemas/evidence/` exact-release/cutover types and fixtures, validators and compatibility tests.
- **Implement:** bind complete candidate and selection tuples, exact predecessor/head identity, affected evidence graph and cutover source/target authority; any Deployment Selection Receipt head change invalidates current campaign admission and requires a fresh `P6-T30`, and no equivalence declaration may retain that admission.
- **Prove:** exact tuple equality, changed or `REVERTED` selection head, nominally equivalent selection, missing predecessor, affected/unaffected evidence classification, cutover readiness/result ordering and adversarial schema fixtures.
- **Stop/hand off:** no result may rewrite a lifecycle head, carry campaign admission across a selection-head change or let cutover evidence create PostgreSQL authority before the authoritative commit.
- **Unlocks:** `P0-T10C`, `P0-T10E` and `P0-T10A` reconciliation.

## P0-T10C — Implement typed-gate and campaign-control schemas

- **Outcome:** Register and implement the cohesive campaign-control schema family for typed Gate Result, Campaign Manifest, Campaign Admission, Campaign Start, Campaign Checkpoint and Campaign Closure Result.
- **Depends on:** `P0-T10` and `P0-T10B` `MERGED`.
- **Read first:** Receipt Schema Registry campaign-control contract, Production Qualification decision/campaign rules and Delivery State Ledger.
- **Change surface:** Platform Governance evidence registry rows, `schemas/evidence/` typed-gate/campaign-control types and fixtures, stage/chain validators and compatibility tests.
- **Implement:** separate manifest freeze, admission, start, checkpoints and terminal closure; bind complete candidate/selection heads, stage predecessors, declared timing inputs and cleanup; a changed Deployment Selection Receipt head immediately invalidates admission/start and requires a new `P6-T30`, with zero carried admission or elapsed campaign/soak time under equivalence.
- **Prove:** missing/reordered/duplicate stages, checkpoint gaps, changed/equivalent/reverted selection heads, terminal-result aggregation and positive/adversarial fixtures for every type.
- **Stop/hand off:** `RUNNING` or a checkpoint is never closure, a generic Gate Result never mutates product/domain/lifecycle authority, and no campaign schema may hide a missing interval or selection-head reset.
- **Unlocks:** `P0-T10A` reconciliation and long-running campaign tooling.

## P0-T10D — Implement Edge lifecycle evidence schemas

- **Outcome:** Register and implement the bounded Edge schema family for Node Enrollment, Update, Key Rotation, Retirement and Wipe Receipts.
- **Depends on:** `P0-T10` `MERGED`.
- **Read first:** Receipt Schema Registry Edge rows, Edge Node Profile lifecycle and disconnected-authority rules, Role and Approval Matrix Edge capability enum.
- **Change surface:** Edge evidence registry rows, `schemas/evidence/` lifecycle types/fixtures, signature/key-version validators and compatibility tests.
- **Implement:** bind exact Node/release/lease/key versions and predecessor heads; keep enrollment, update, rotation, retirement and wipe dispositions distinct; require owner authorization and Operator execution where frozen without granting an Edge node Platform authority.
- **Prove:** replay, out-of-order update, wrong Node/release/key, expired lease, retirement-before-wipe, wipe-without-authorization, disconnected trusted-time and schema-evolution fixtures.
- **Stop/hand off:** a Local Acquisition, cleanup result or log line cannot substitute for a Node lifecycle receipt, and wipe evidence cannot claim physical overwrite or recovery of external copies.
- **Unlocks:** `P0-T10A` reconciliation and Phase 5 Edge lifecycle implementation.

## P0-T10E — Implement exact-soak and crypto-expiry timing schemas

- **Outcome:** Register and implement the bounded trusted-time schema family for Exact-Candidate Soak Result and Crypto-Expiry Receipt.
- **Depends on:** `P0-T10` and `P0-T10B` `MERGED`.
- **Read first:** Receipt Schema Registry trusted-time rules, Production Qualification exact-candidate soak inequality, Delivery State Ledger invalidation rules and Zero-Cash durability crypto-expiry contract.
- **Change surface:** Platform/Audit evidence registry rows, `schemas/evidence/` soak/crypto-expiry types and fixtures, trusted-interval validators and compatibility tests.
- **Implement:** bind trusted start/end/coverage intervals, exact candidate fingerprint and Deployment Selection Receipt head for soak, and original backup-generation/epoch/key/deletion trigger plus strict completion deadline for crypto expiry; a selection-head change invalidates all accrued soak time and requires fresh admission.
- **Prove:** exact-boundary/equality, uncovered instant, clock rollback/jump, changed/equivalent/reverted selection head, missing epoch/key destruction, late completion and positive/adversarial fixtures.
- **Stop/hand off:** accelerated time is conformance evidence only, soak requires the real trusted inequality, and crypto-expiry evidence cannot claim physical overwrite or erase a historical receipt.
- **Unlocks:** `P0-T10A` reconciliation, exact-candidate soak tooling and durability lifecycle evidence.

## P0-T10F — Implement zero-cash accounting result schema

- **Outcome:** Register and implement one bounded Zero-Cash Accounting Result schema that distinguishes gross charge/payment, credits, contributed resources, baseline utilities, labor and projected mandatory-path exposure over an exact evidence window.
- **Depends on:** `P0-T09A` and `P0-T10` `MERGED`.
- **Read first:** Receipt Schema Registry accounting rules, Zero-Cash Deployment Contract, Production Qualification zero-cash gate and the `P0-T09A` tariff/currency/tax/allowance model.
- **Change surface:** Platform Governance evidence registry row, `schemas/evidence/` zero-cash type/fixtures, coverage/reconciliation validator and compatibility tests.
- **Implement:** bind exact billing accounts, tariff/currency/tax/allowance inputs, provider-statement coverage intervals, campaign/release/host/workload tuple and separate observed versus projected values; prohibit credit-netting from proving zero gross incremental charge/payment.
- **Prove:** missing/gapped/overlapping statements, delayed statement issuance, nonzero gross charge/payment, credit-only zero net, tariff/currency/tax drift, contributed-resource classification and positive/adversarial fixtures.
- **Stop/hand off:** a free-tier label, forecast alone, absent statement or unpriced mandatory dependency is `NOT_EVALUABLE` or `NEGATIVE`, never zero-cash proof.
- **Unlocks:** `P0-T10A` reconciliation and zero-cash campaign evidence tooling.

## P0-T11 — Freeze security-control and egress baselines

- **Outcome:** Map OWASP ASVS 5.0.0 Level 2 controls to PathLab/rest-server surfaces, create threat/data-flow and N/A evidence rules, and inventory every production/build/backup/restore egress path with a default-deny target.
- **Depends on:** `P0-T01` and `P0-T03` `MERGED`.
- **Read first:** [Production Qualification](../architecture/PRODUCTION_QUALIFICATION.md), security documentation, current routes/deploy scripts/workflows, ADR 0122.
- **Change surface:** `docs/security/`, security test/gate definitions, egress inventory; remediation implementation belongs to the owning later task.
- **Implement:** assign owner/task IDs for every applicable control and finding; classify secret/PHI/private-pixel/answer/telemetry evidence exclusions; define Critical and High handling exactly as qualification requires.
- **Prove:** complete route/component/control reconciliation and seeded undeclared-egress/finding cases.
- **Stop/hand off:** unresolved reachable Critical is `NEGATIVE`; a High without verified mitigation and <=30-day expiry blocks release readiness.
- **Unlocks:** security acceptance in every later phase and `P7-T04`.

## P0-T12 — Close the Phase 0 authority and freedom gate

- **Outcome:** Run an independent Phase 0 audit against the exact default-branch head and emit the task/phase result with every unresolved decision, right, license, provenance, security-baseline, zero-cash, and offline-input item accounted for.
- **Depends on:** `P0-T01A`, `P0-T04`, `P0-T05A`, `P0-T08`, `P0-T09`, `P0-T09A`, `P0-T10A`, and `P0-T11` `MERGED`, with current `P0-T10A=SUCCESS`.
- **Read first:** this phase file, all Phase 0 outputs, [Feature Completion Matrix](../architecture/FEATURE_COMPLETION_MATRIX.md), [Production Qualification](../architecture/PRODUCTION_QUALIFICATION.md).
- **Change surface:** immutable audit report/evidence package and Delivery Lifecycle Receipt; fixes remain separate child tasks.
- **Implement:** none; execute the independent reconciliation and emit only the immutable Phase 0 audit result and adjacent lifecycle evidence, leaving every remediation to a separately scoped task.
- **Prove:** clean rights/dependency/license scans, SBOM reconciliation, offline input verification, schema catalog validation, public-repository safety, and zero unresolved release-blocking item list.
- **Stop/hand off:** any missing evidence is `NOT_EVALUABLE`; any mandatory incompatibility is `NEGATIVE`; incomplete remediation is `PARTIAL`. Do not promote to Phase 1 on prose confidence.
- **Unlocks:** `P1-T01` and all Phase 1 implementation.
