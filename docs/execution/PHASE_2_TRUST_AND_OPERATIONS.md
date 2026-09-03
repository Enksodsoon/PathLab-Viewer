# Phase 2 — Trust, Governance, Operations, and Data Protection

Phase 2 makes people, services, policies, approvals, audit, deletion, backup and recovery executable before product contexts gain broad authority. Full 90-day durability and exact-release qualification occur later. All tasks inherit [README](./README.md).

## P2-T01 — Migrate public vocabulary to Institution

- **Outcome:** Replace user-facing/API/schema/package use of `Organization` with canonical `Institution` while retaining a bounded internal compatibility mapping for existing `organization_id` data.
- **Depends on:** `P1-T25` `MERGED` with `SUCCESS`.
- **Read first:** [Governed Product Workflows](../architecture/GOVERNED_PRODUCT_WORKFLOWS.md), Trust context, current identity models/routes/UI.
- **Change surface:** Trust schemas/migrations, API contracts, frontend vocabulary, fixtures and compatibility tests.
- **Implement:** one concept and identifier authority; versioned aliases only where migration compatibility requires them; no simultaneous Organization domain.
- **Prove:** old-data migration, API/package schema compatibility, UI text/accessibility and no duplicate authority.
- **Stop/hand off:** do not silently rename external protocol terms whose standard vocabulary is normative.
- **Unlocks:** `P2-T02A`, `P2-T09`, `P2-T11`; post-bootstrap `P2-T03` unlocks only through successful parent `P2-T02`.

## P2-T02 — Integrate and close the one-time governed bootstrap ceremony

- **Outcome:** Integrate the pre-bootstrap identity and WebAuthn primitives into one empty-deployment-only ceremony that atomically creates the first Institution/Principal/Owner Membership/Role Binding/outbox/Bootstrap Receipt after local Operator, recovery-quorum and intended first Owner acts.
- **Depends on:** `P1-T11`, `P1-T12`, `P0-T10`, `P2-T02A`, and `P2-T02B` `MERGED`.
- **Read first:** [Role and Approval Matrix](../architecture/ROLE_APPROVAL_MATRIX.md) bootstrap enforcement model, Receipt Schema Registry Bootstrap Receipt, and the contracts delivered by `P2-T02A` and `P2-T02B`.
- **Change surface:** bootstrap orchestration command/UI, atomic Trust/Platform transaction/outbox seam, Bootstrap Receipt emitter and integration/adversarial tests.
- **Implement:** compose only the bounded genesis and credential primitives; permanently reject after any prior authority/bootstrap state; prohibit remote bootstrap; bind the signed installation manifest, complete recovery-bundle identity, all actors/shares and intended first Owner credential into one immutable proposal.
- **Prove:** happy path plus second/replayed/remote/partial/changed proposal, reused custodian, missing or changed credential, pre-existing object, outbox/receipt/transaction crash boundary and post-bootstrap denial tests.
- **Stop/hand off:** the parent may not recreate identity/WebAuthn primitives, custodians gain no Institution role through bootstrap, and any partial authority without the atomic receipt is `NEGATIVE`.
- **Unlocks:** `P2-T03`, `P2-T07` and all post-bootstrap Institution authority only on current `P2-T02=SUCCESS`.

## P2-T02A — Implement pre-bootstrap identity genesis primitives

- **Outcome:** Implement the bounded Trust aggregate schemas and one atomic genesis command capable of creating exactly one Institution, one human Principal, one Owner Membership and one Owner Role Binding without exposing post-bootstrap administration.
- **Depends on:** `P2-T01`, `P1-T10`, and `P0-T10` `MERGED`.
- **Read first:** Trust context identity invariants, Role and Approval Matrix bootstrap/last-Owner rules and Receipt Schema Registry bootstrap scope contract.
- **Change surface:** Trust genesis schemas/migrations/repository/service primitive, source events, outbox transaction seam and invariant tests.
- **Implement:** empty-state compare-and-commit, canonical identifiers/versions, exact installation-manifest binding and a single-use internal genesis API callable only by `platform.bootstrap.commit`; provide no ordinary Membership/Role Binding mutation route.
- **Prove:** empty genesis, duplicate/concurrent/replayed genesis, partial-row/transaction crash, wrong installation identity, non-Owner binding, extra aggregate and direct external invocation cases.
- **Stop/hand off:** this child creates primitives only; it cannot execute bootstrap, enroll credentials or implement post-bootstrap Membership/Role Binding administration.
- **Unlocks:** `P2-T02B` and parent `P2-T02` integration.

## P2-T02B — Implement pre-bootstrap WebAuthn enrollment primitives

- **Outcome:** Implement a local single-use WebAuthn registration primitive that validates and binds the intended first Owner public credential during the bootstrap transaction without providing post-bootstrap login, authenticator management or step-up.
- **Depends on:** `P2-T02A` `MERGED`.
- **Read first:** Role Matrix bootstrap ceremony, Trust WebAuthn credential contract, ADR 0053 and Receipt Schema Registry Bootstrap Receipt fields/privacy rules.
- **Change surface:** bootstrap credential schema/library, local challenge/attestation verifier, RP/origin configuration seam, transaction integration contract and security tests.
- **Implement:** cryptographic challenge, origin, RP, attestation/public-key and replay verification; bind the pending Principal/genesis proposal and installation identity; store no authenticator secret and expose no remote or reusable registration route.
- **Prove:** wrong origin/RP/challenge/proposal/Principal/installation, replay, duplicate credential, malformed attestation, transaction abort and remote invocation cases.
- **Stop/hand off:** this primitive cannot authenticate a session or satisfy privileged step-up; post-bootstrap credential lifecycle remains exclusively in `P2-T07`.
- **Unlocks:** parent `P2-T02` integration.

## P2-T03 — Implement post-bootstrap Principals, Memberships, and Role Bindings

- **Outcome:** Extend the bootstrap genesis records with post-bootstrap human/service Principal, Institution-scoped Membership and composable versioned Role Binding administration, lifecycle/expiry, incompatibilities and last-Owner protection for every role in the Role Matrix.
- **Depends on:** `P2-T01` and `P2-T02` `MERGED`, with current `P2-T02=SUCCESS`.
- **Read first:** Trust context, [Role and Approval Matrix](../architecture/ROLE_APPROVAL_MATRIX.md), ADRs 0053, 0103–0105.
- **Change surface:** Trust database/migrations/service/API/admin UI/audit/tests.
- **Implement:** reuse the `P2-T02A` aggregate identities and versions; deny by default; enforce Institution/purpose scope, service/human distinction, expiry/revocation, incompatible-role and no-role-composition-for-two-person rules; never expose a second genesis path.
- **Prove:** all role combinations, cross-Institution identifiers, disabled/expired bindings, last Owner, concurrent changes and 10,000-Principal query/load fixture.
- **Stop/hand off:** role names alone never authorize a route or background command.
- **Unlocks:** `P2-T04`, `P2-T05`, `P2-T06`, and every human workflow.

## P2-T04 — Enforce named capabilities on every action path

- **Outcome:** Create a server-side capability resolver and require every mutating API, command, scheduled job, imported proposal and operator action to declare and pass one Role Matrix capability plus Institution, purpose, target and policy checks.
- **Depends on:** `P2-T03` `MERGED`.
- **Read first:** Role Matrix role/service grants; current route/CLI/worker inventory; P0 security control map.
- **Change surface:** authorization middleware/library, all current mutation entry points, capability registry/tests.
- **Implement:** default deny; generate the exact human-capability-to-owner-handler registry frozen in the Role and Approval Matrix; require exactly one owner context, Service Principal, finite handler capability and, where declared, exact operation enum for every mutating human capability; include the Deployment Selection, Credential Custody Transfer and Clinical Snapshot mappings; reject namespace wildcards, unknown enum values, duplicate/unmapped handlers, and route/command/job drift; re-resolve active bindings and service restrictions at commit.
- **Prove:** bidirectional registry-to-role-to-service-to-entry-point reconciliation, including every dual-decision commit and the exact selection/reversion, custody-transfer and snapshot authorize/withdraw/expire/delete handlers; seeded missing, duplicate, stale, wildcard and unknown-operation mappings; wrong Institution/purpose/role/service, expired/revoked binding, and forged client-claim attacks.
- **Stop/hand off:** a broad `admin` bypass or client-only check is `NEGATIVE`.
- **Unlocks:** every governed feature and `P2-T05`.

## P2-T05 — Implement Approval Requests and Dual Authorization

- **Outcome:** Add immutable expiring proposals, independent initiator/approver decisions, exact target/evidence/policy hashes, Approval Receipts and owning-context commit hooks for every dual-authorization pair.
- **Depends on:** `P2-T03`, `P2-T04`, `P2-T07`, and `P0-T10` `MERGED`.
- **Read first:** Role Matrix dual-authorization/incompatibility/expiry sections and Receipt Schema Registry.
- **Change surface:** Trust schemas/migrations/service/API/UI, approval library and adversarial tests.
- **Implement:** two distinct people, current role/binding/step-up, no material contributor or self-approval, proposal invalidation on any bound change, terminal expiry/rejection.
- **Prove:** every matrix pair, composed roles, stale step-up, changed target, policy/key rotation, concurrent approve/revoke and replay.
- **Stop/hand off:** Approval Receipt is evidence; the owning context must still commit its authoritative transition.
- **Unlocks:** legal hold/deletion and all later high-risk workflows.

## P2-T06 — Implement revocable server-side Session Grants

- **Outcome:** Replace or bound current authentication state with opaque, secure HttpOnly, server-side Session Grants carrying Institution/purpose and role-specific idle/absolute expiry, rotation and mass revocation.
- **Depends on:** `P2-T03` and `P2-T04` `MERGED`.
- **Read first:** Trust context, ADR 0063, current auth/security/session code.
- **Change surface:** Trust schema/service, cookies/CSRF/session store, login/logout UI and security tests.
- **Implement:** fixation prevention, rotation on privilege change, device/session inventory, revocation on credential or learner recovery, no bearer JWT authority in browser storage.
- **Prove:** theft/replay/fixation/CSRF, expiry, concurrent revoke, role/Institution change and restart behavior.
- **Stop/hand off:** external LMS launch and persistent browser state cannot satisfy privileged authentication.
- **Unlocks:** `P2-T07`, `P2-T08`, `P2-T09`.

## P2-T07 — Implement post-bootstrap WebAuthn authentication and step-up

- **Outcome:** Extend the bootstrap-only WebAuthn credential primitive with Institution-enrolled authenticator lifecycle, password-plus-WebAuthn privileged login, trusted-server-time step-up ceremonies and exact freshness windows.
- **Depends on:** `P2-T02`, `P2-T03`, `P2-T06` `MERGED`.
- **Read first:** Role Matrix step-up rules, ADR 0053, Trust context.
- **Change surface:** authenticator schemas/service/API/browser UI, RP/network-identity configuration and security tests.
- **Implement:** reuse the `P2-T02B` verifier and credential identity; add assertion/counter verification, authenticator add/remove policy, at least two authenticators or recovery boundary and action-bound step-up without retaining a bootstrap registration bypass.
- **Prove:** wrong origin/RP/challenge, cloned/replayed assertion, stale server time, revoked binding/authenticator, lost authenticator and supported-client/accessibility flows.
- **Stop/hand off:** password, user-presence-only gesture, API token, LTI launch or Edge lease cannot satisfy step-up.
- **Unlocks:** `P2-T05`, `P2-T08`, every sensitive action.

## P2-T08 — Implement recovery codes and two-officer break glass

- **Outcome:** Add sealed hashed single-use Recovery Code Sets and a bounded incident-specific Break-Glass Grant initiated/approved by two distinct authorized officers, with full session revocation and audit.
- **Depends on:** `P2-T05`, `P2-T06`, and `P2-T07` `MERGED`.
- **Read first:** Trust context, Role Matrix, and [Password Recovery](../architecture/PASSWORD_RECOVERY.md) as legacy source-behavior and migration input only; the [Final Production Endpoint](../architecture/FINAL_PRODUCTION_ENDPOINT.md) and current accepted Trust/recovery contracts control any conflict.
- **Change surface:** Trust schemas/routes/UI, incident/audit integration, recovery tests/runbook.
- **Implement:** no email requirement, rate limits, single use, expiry, reason/evidence binding, role narrowing and post-recovery authenticator rotation.
- **Prove:** reuse/brute force/self-approval/wrong Institution/expired grant/concurrent recovery and last-Owner cases.
- **Stop/hand off:** Break glass is not a super-admin account and cannot recover Root Key material.
- **Unlocks:** `P2-T25`.

## P2-T09 — Implement learner identifiers, activation, and recovery

- **Outcome:** Add opaque Institution-scoped Learner Identifiers, single-use Activation Grants, first local credential establishment and staff-issued Recovery Grants that revoke all prior sessions without requiring email.
- **Depends on:** `P2-T01`, `P2-T03`, and `P2-T06` `MERGED`.
- **Read first:** Trust context learner definitions, governed learner workflow, Role Matrix.
- **Change surface:** Trust schemas/API/admin+learner UI, session revocation and lifecycle tests.
- **Implement:** printable/offline-safe issuance, trusted-time expiry, identity-verification record, collision resistance and non-disclosing responses.
- **Prove:** first activation, reuse, expiry, enumeration, wrong Institution, recovery race, old session/device rejection and accessible client flows.
- **Stop/hand off:** email/student number/display name must not become canonical authentication identity.
- **Unlocks:** `P2-T10`, Catalog/Live/Assessment learner tasks.

## P2-T10 — Implement Purpose Identities, guests, and minor boundaries

- **Outcome:** Issue context/purpose-specific opaque identities for durable learner/research/EQA work; implement non-credit pseudonymous Guest Participation and minimum Minor Status handling.
- **Depends on:** `P2-T09` and `P2-T11` `MERGED`.
- **Read first:** Trust context, Governed Product Workflows learners/minors, ADRs 0061–0062 and 0105.
- **Change surface:** Trust schemas/service/API, context identity adapters and isolation tests.
- **Implement:** purpose-bound correlation barriers, no full DOB by default, current Processing Grant/guardian rule prerequisite, no guest conversion or durable evidence.
- **Prove:** cross-purpose correlation/identifier replay, expired/withdrawn grant, wrong Institution, guest durable-write attempts and deletion.
- **Stop/hand off:** a guest never receives Membership, Enrollment, Attempt, Grade, attendance claim or credential subject.
- **Unlocks:** learning, EQA, Clinical and Research identity workflows.

## P2-T11 — Implement Residency, Processing, and Transfer Grants

- **Outcome:** Add versioned Institution Residency Policies, Approved Data Locations, Processing Grants, Transfer Grants, guardian rules, purpose/data-class/effective-period scope and dual policy approval.
- **Depends on:** `P2-T01`, `P2-T03`, `P2-T05` `MERGED`.
- **Read first:** Trust context; ADRs 0023–0030, 0052, 0062; Governed Product Workflows.
- **Change surface:** Trust schemas/service/API/admin UI, location/processing enforcement hooks and tests.
- **Implement:** fail closed on missing/mismatch/expiry/withdrawal; separate processing from role; bind primary, backup, export and external destination.
- **Prove:** jurisdiction/location mismatch, expired/withdrawn grant, minor/guardian variants, transfer without grant and policy-version races.
- **Stop/hand off:** deployment region or network reachability does not establish an Approved Data Location.
- **Unlocks:** `P2-T10`, `P2-T12`, backup/portability/clinical/research workflows.

## P2-T12 — Implement Retention Schedules and Legal Holds

- **Outcome:** Add versioned Institution schedules bounded by product ceilings, trusted lifecycle triggers, deterministic expiry queues, scoped expiring Legal Holds and separate encrypted hold-package behavior.
- **Depends on:** `P2-T05` and `P2-T11` `MERGED`.
- **Read first:** all context retention sections and [Governed Product Workflows](../architecture/GOVERNED_PRODUCT_WORKFLOWS.md) retention/deletion rules.
- **Change surface:** Trust schemas/service/API/UI, shared retention contract, owner adapters and clock tests.
- **Implement:** stricter schedule selection; no retry/restore/export/appeal/quarantine clock reset; ordinary backup rotation never extended by hold.
- **Prove:** every frozen trigger/ceiling, shorter schedule, hold creation/expiry/revocation, clock rollback/uncertainty and hold-package deletion.
- **Stop/hand off:** indefinite or manually restarted retention is `NEGATIVE`.
- **Unlocks:** `P2-T13`, `P2-T14`, every context completion task.

## P2-T13 — Build the governed data inventory and subject export

- **Outcome:** Define each context's authoritative/projection/index/cache/derivative/export/backup classes, owner query contract, retention/legal-hold state and privacy-minimized subject export manifest.
- **Depends on:** `P1-T02`, `P2-T10`, and `P2-T12` `MERGED`.
- **Read first:** Context Map, all context glossaries, Receipt Schema Registry deletion schemas.
- **Change surface:** inventory schemas/library, per-context skeleton adapters, admin/audit tools and completeness tests.
- **Implement:** no cross-context direct queries; owners return signed inventory facts; distinguish external/public-copy limits and backup obligations.
- **Prove:** registry/context reconciliation, missing-owner failure, cross-purpose subject, projection/cache/object references and privacy filtering.
- **Stop/hand off:** inventory is not deletion and must not expose credentials, PHI, private pixels or learner answers.
- **Unlocks:** `P2-T14`, portability exporters.

## P2-T14 — Implement the fail-closed Deletion Saga framework

- **Outcome:** Coordinate an immutable obligation list across every relevant owner, consume per-context Deletion Receipts, retry idempotently, handle credential revocation/public-copy warnings/backup expiry and complete only with all required terminal receipts.
- **Depends on:** `P2-T05`, `P2-T12`, `P2-T13`, and `P0-T10` `MERGED`.
- **Read first:** Governed Product Workflows deletion/Legal Hold, Receipt Schema Registry, Golden Journey G34–G36.
- **Change surface:** Trust coordinator/schema/API/UI, owner deletion command/receipt interface, audit/failure tests.
- **Implement:** immutable scope, owner discovery, unavailable/failed state, exact retry, hold handling, crypto-erasure reference and external-copy disclosures.
- **Prove:** missing/duplicate/failed/unavailable owner, restart at each boundary, stale approval, cache/export/projection/object/credential/public-release obligations and no false completion.
- **Stop/hand off:** context-specific deletion implementation remains in its owning feature task; framework-only result cannot satisfy production deletion gate.
- **Unlocks:** every owning-context deletion adapter and `P2-T25`.

## P2-T15 — Build append-only audit projections and integrity chains

- **Outcome:** Consume context outboxes into partitioned monotonic Audit Records that bind predecessor hash, source identity, canonical payload hash and record hash without becoming domain authority.
- **Depends on:** `P1-T06` and `P1-T07` `MERGED`.
- **Read first:** Audit context, ADR 0077, Receipt Schema Registry.
- **Change surface:** Audit database/migrations/consumer, canonicalization library, query API/tests.
- **Implement:** idempotent projection, gaps/replay/tamper states, partition heads and privacy-minimized views.
- **Prove:** at least fixture-scale chain with duplicate/delay/reorder/missing/malicious events, stream reconstruction, restore/replay and tamper detection.
- **Stop/hand off:** an Audit Record cannot invent or repair source-domain truth.
- **Unlocks:** `P2-T16`, `P2-T18`, all receipt evidence.

## P2-T16 — Sign daily and release audit checkpoints

- **Outcome:** Add purpose-bound Audit Key Versions, scheduled daily and release-bound signed partition-head checkpoints, independent target copy and verification tooling.
- **Depends on:** `P1-T11`, `P2-T15`, and `P2-T19` `MERGED`.
- **Read first:** Audit context, ADR 0077, Receipt Schema Registry.
- **Change surface:** checkpoint schema/service/timer, signing/verification, Backup Target adapter and tests.
- **Implement:** sequence ranges, gaps/result, key version/rotation and immutable content-hash references; no secret evidence.
- **Prove:** daily/release trigger, missed timer, key rotation/loss, target outage, tamper and restore verification.
- **Stop/hand off:** unsigned logs or local-only hashes are not checkpoints.
- **Unlocks:** `P2-T16A`, `P2-T25`, qualification evidence tooling.

## P2-T16A — Implement content-addressed evidence custody and sanitization

- **Outcome:** Store private raw evidence by immutable hash under approved retention/access rules, generate signed sanitized verification packages, preserve raw-to-summary provenance and execute deletion obligations without exposing protected data publicly.
- **Depends on:** `P0-T10A`, `P1-T11`, `P2-T12`, `P2-T15`, and `P2-T16` `MERGED`.
- **Read first:** Production Qualification evidence package, Receipt Registry envelope/privacy rules, Audit context.
- **Change surface:** Audit evidence library/CLI/store adapter, schemas, privacy scanner, signing/verification and deletion tests.
- **Implement:** exact subject/config/host/corpus references, raw/summary hashes, access classifications, signature rotation, public sanitized copy and no mutable-path authority.
- **Prove:** tamper, wrong key/subject, redaction break, replay, secret/PHI/pixel/answer/private-address canaries, retention expiry and deletion.
- **Stop/hand off:** sanitization that severs provenance or leaks protected content is `NEGATIVE`.
- **Unlocks:** `P2-T18A`, every capacity/qualification campaign.

## P2-T17 — Implement bounded local logs, metrics, and traces

- **Outcome:** Provide local operational logs, 30-second OpenMetrics, seven-day raw/13-month five-minute metric aggregates and error/<=1% sampled 24-hour traces with cardinality, privacy and disk caps.
- **Depends on:** `P1-T21` and `P2-T12` `MERGED`.
- **Read first:** Audit context, ADR 0078, P0 evidence privacy rules.
- **Change surface:** observability configuration/libraries, retention jobs, dashboards and pressure/privacy tests.
- **Implement:** no automatic export, secrets/PHI/private pixels/answers/participant telemetry filters, resource/state/service-level signals and scrape/storage budgets.
- **Prove:** retention expiry, high-cardinality/volume attack, disk pressure, restart and seeded sensitive-value rejection.
- **Stop/hand off:** observability cannot become learner analytics or a hidden hosted dependency.
- **Unlocks:** `P2-T18`, all operational/campaign tasks.

## P2-T18 — Implement durable notices, alerts, incidents, and operator UI

- **Outcome:** Add authoritative in-app notices, local Operator Alerts with acknowledgement/escalation, Security Incident Records, a compact operations dashboard and an owner-event seam for later optional external delivery.
- **Depends on:** `P2-T04`, `P2-T15`, and `P2-T17` `MERGED`.
- **Read first:** Audit context, ADR 0051, Role Matrix operator/auditor grants.
- **Change surface:** Audit/Platform schemas/APIs/UI, external-delivery proposal/outbox contract, rules/tests/runbook.
- **Implement:** reason-coded states for backup/mode/resource/key/security/deletion/campaign; acknowledge without erasing source condition; emit but never deliver optional external-notification proposals.
- **Prove:** unavailable proposal consumer, duplicate alerts, acknowledgement/expiry, cross-Institution access, incident closure and accessibility/client checks.
- **Stop/hand off:** a green dashboard is observation, not a gate result or lifecycle transition.
- **Unlocks:** `P2-T18A`, `P2-T25`, `P5-T01A` and pilot operations.

## P2-T18A — Implement Delivery State Ledger and separate legacy status axes

- **Outcome:** Implement append-only adjacent Delivery Lifecycle transitions while keeping work-package status, source capability observations, Git/release location, gate execution/result/validity and clinical-purpose status as independent axes.
- **Depends on:** `P0-T10A`, `P2-T16A`, `P2-T18` `MERGED`.
- **Read first:** Delivery State Ledger, Receipt Schema Registry; current `docs/evidence/capability-registry.json` and validator.
- **Change surface:** Platform/Audit schema/service/API/CLI/admin status UI, legacy registry migration/validator and tests.
- **Implement:** no-skip/prior-head/issuer/subject/invalidation/suspension rules; preserve `BUILT`, `SYNTHETICALLY_VERIFIED`, `PRODUCTION_CERTIFIED` as historical observations without mapping them to new lifecycle states.
- **Prove:** every adjacent/invalid/duplicate/stale transition; a pushed PR/legacy synthetic result/deployment cannot create merge/pilot/qualification/activation.
- **Stop/hand off:** a later receipt never repairs a missing predecessor or mutates product truth.
- **Unlocks:** `P2-T18B`, reliable program reporting and every lifecycle receipt.

## P2-T18B — Fingerprint candidates and enforce drift invalidation

- **Outcome:** Bind evidence to commit/tree/artifacts/build inputs, configuration/migrations, profile, host/storage/firmware/cache, PostgreSQL minor/client, OS packages/kernel/filesystem, backup target, network rules, clients/corpora/workload/operators, tools/models/protocols/keys/policies, controllers/evidence schemas/trusted time, pre-deployment Campaign Contract Template and cost tariff/currency/tax/allowance inputs; compute impact, expire/invalidate affected gates and support only signed unchanged-input equivalence while treating every Deployment Selection Receipt head change as an unconditional campaign-admission reset.
- **Depends on:** `P2-T16A`, `P2-T18A` `MERGED`.
- **Read first:** Production Qualification evidence/decision rules and Delivery State transition rules.
- **Change surface:** qualification/fingerprint library, inventory adapters, invalidation engine/UI and tests.
- **Implement:** exact tuple equality, gate dependency graph, review/expiry and targeted invalidation for ordinary evidence; independently, any Deployment Selection Receipt head change—including `REVERTED`, re-selection of identical bytes or nominal equivalence—invalidates Campaign Admission/Start, stops admitted elapsed time and requires a fresh `P6-T30`; equivalence can preserve only otherwise unaffected historical durability evidence for a separately admitted run; enforce mandatory exact-final-candidate 14-day soak/reruns.
- **Prove:** mutate each bound input and verify expected gate invalidation; change only the selection-receipt head while keeping every tuple field identical and prove admission/start plus elapsed campaign/soak credit are invalidated; broad carry-forward, missing input and silent drift fail.
- **Stop/hand off:** imported long-duration evidence is supporting only and never changes the lifecycle subject; no Impact/Equivalence Result may retain admission or elapsed campaign/soak time across a selection-head change.
- **Unlocks:** `P2-T18C`, long campaigns and exact-release qualification.

## P2-T18C — Implement release activation, suspension, and reactivation control

- **Outcome:** Implement the release-level controller that proposes, rejects, expires, commits, suspends and re-proposes activation against one exact deployed and qualified tuple without collapsing any Delivery State.
- **Depends on:** `P2-T05`, `P2-T07`, `P2-T16A`, `P2-T18A`, and `P2-T18B` `MERGED`.
- **Read first:** Delivery State Ledger, Role Matrix Full-Surface activation pair, Receipt Schema Registry Activation Receipt and Production Qualification decision rules.
- **Change surface:** Platform Governance activation schema/service/API/CLI/admin UI/tests and suspension/reactivation runbook.
- **Implement:** immutable proposal with <=4-hour expiry; distinct human Operator initiation and Owner approval; both WebAuthn step-ups <=5 minutes; exact current deployment/pilot/qualification/evidence/claim/rollback hashes; fail-closed rejection on drift; append-only suspension; and no automatic reactivation.
- **Prove:** same-person, service-account, stale-role, stale-step-up, expired proposal, changed hash, missing predecessor, replay, rollback and every suspension trigger; historical receipts remain immutable.
- **Stop/hand off:** tests and non-production rehearsal cannot emit a real `ACTIVATED` state, and automation or Codex cannot stand in for either human.
- **Unlocks:** exact candidate integration and the later evidence-only `P8-T09` rehearsal.

## P2-T19 — Enroll the independent Backup Target

- **Outcome:** Implement Institution-owned/donated off-host target enrollment with Approved Data Location, physical-independence and capacity declarations, append-only ingest identity, attestation key, freshness state and revocation/replacement workflow.
- **Depends on:** `P2-T04`, `P2-T11`, `P1-T21` `MERGED`.
- **Read first:** [Zero-Cash Durability and Security](../architecture/ZERO_CASH_DURABILITY_SECURITY.md), Audit context, ADRs 0072, 0117–0120.
- **Change surface:** Audit/Trust schemas/API/operator UI, target-side service/configuration and adversarial tests.
- **Implement:** target may read append/grant-scoped data only; production cannot read/prune arbitrary repository data or hold restic decryption credential.
- **Prove:** wrong location/Institution/capacity, same-host target, stale/revoked identity, append-abuse and target outage.
- **Stop/hand off:** a folder or same failure-domain disk is not an independent target.
- **Unlocks:** `P2-T16`, `P2-T20`, `P2-T21`, `P2-T22`.

## P2-T20 — Protect PostgreSQL through synchronous WAL and Barman

- **Outcome:** Configure synchronous off-host WAL acknowledgement, Barman archive/base/block-incremental lifecycle inputs, commit/flush LSN Protection Receipts and hard five-minute data-protection failure behavior.
- **Depends on:** `P1-T03`, `P2-T19`, and `P0-T10` `MERGED`.
- **Read first:** durability protection/lifecycle sections, ADRs 0117–0121, Production Qualification backup gate.
- **Change surface:** PostgreSQL/Barman configuration, target-side services, receipt emitters, health/admission and fault tests.
- **Implement:** `synchronous_commit=on`, `fsync=on`, `full_page_writes=on`; no session downgrade; fail authoritative writes at frozen fault boundary rather than asynchronous fallback.
- **Prove:** network/target/flush/storage/power/process faults, LSN reconciliation, timeline switch, stale/capacity state and unauthorized setting change.
- **Stop/hand off:** hardware flush/power-loss qualification may remain `NOT_EVALUABLE` until exact hardware exists; software must still fail closed.
- **Unlocks:** `P2-T22`, `P2-T23`, authoritative database writes.

## P2-T21 — Protect immutable objects with target-side restic pull

- **Outcome:** Implement short-lived signed hash-addressed grants that let the Backup Target pull each `PENDING_PROTECTION` object into append-only encrypted restic storage and return a durable Protection Receipt.
- **Depends on:** `P1-T09`, `P2-T19`, and `P0-T10` `MERGED`.
- **Read first:** durability object protection/authority sections, Receipt Schema Registry.
- **Change surface:** production grant endpoint, target pull worker/restic config, object state transition, inventory/tests/runbook.
- **Implement:** minimal per-object grant, exact hash/size/expiry/audience, target-side repository credential, acknowledgement/inventory reconciliation and orphan cleanup.
- **Prove:** replay/expiry/wrong hash/range/Institution, interrupted pull, corrupted repo, production credential search, capacity pressure and eventual retry.
- **Stop/hand off:** production must never hold the restic repository/decryption credential or admit local-only object authority.
- **Unlocks:** `P2-T22`, `P2-T23`, `P3-T07`.

## P2-T22 — Automate backup lifecycle and disconnected rotation

- **Outcome:** Implement rolling seven-day PITR plus preceding daily anchor, <=9-day WAL age, daily block-incrementals, proven full-backup margin below 168 hours, >=28-day discrete anchors, day-34 expiry start with every deletion/crypto-expiry/verification receipt completed strictly before age 35 days, append-only epochs and disconnected recovery-media crypto-expiry.
- **Depends on:** `P2-T12`, `P2-T19`, `P2-T20`, and `P2-T21` `MERGED`.
- **Read first:** durability lifecycle/append-only sections, Audit context, ADRs 0118–0121.
- **Change surface:** target timers/policies, epoch-key tooling, lifecycle receipts/alerts/tests/runbook.
- **Implement:** inventory-before-prune, expiry verification, independent recovery-media rotation, capacity forecasting and no Legal Hold extension of ordinary backups.
- **Prove:** accelerated lifecycle fixtures enforce `completed_at < created_at + 35 * 24h` from trusted target receipt time; exact-boundary/equality, missed timer, clock rollback, prune failure, stale/corrupt generation, capacity block and disconnected-key destruction fail.
- **Stop/hand off:** real two-cycle/90-day proof occurs in Phase 6/7; simulation is not qualification.
- **Unlocks:** `P2-T23`, `P2-T26`, Phase 6 lifecycle campaign.

## P2-T23 — Implement PITR and replacement-host restore controller

- **Outcome:** Restore exact PostgreSQL timelines/LSNs, objects/manifests, keys, outboxes and audit chains into an isolated empty host; reconcile latest/five-minute/random targets and securely delete the workspace.
- **Depends on:** `P1-T22`, `P2-T20`, `P2-T21`, and `P2-T22` `MERGED`.
- **Read first:** durability restore section, Golden Journey G37–G38, and [PostgreSQL backup/restore](../architecture/POSTGRES_BACKUP_RESTORE.md) as legacy migration/rehearsal input only; [Zero-Cash Durability and Security](../architecture/ZERO_CASH_DURABILITY_SECURITY.md), [Production Qualification](../architecture/PRODUCTION_QUALIFICATION.md), and the [Final Production Endpoint](../architecture/FINAL_PRODUCTION_ENDPOINT.md) control any conflict.
- **Change surface:** restore controller/scripts, manifests/receipts, isolated host units and recovery tests/runbook.
- **Implement:** no production Service Credential dependency; quorum rewrap; schema/migration/tool pin checks; deleted-data and backup-obligation reporting.
- **Prove:** latest/random/five-minute, missing/corrupt WAL/object/key, wrong release/config, replacement host and workspace deletion.
- **Stop/hand off:** no fixed RTO or whole-site-loss promise; actual-corpus/150-GB/long-duration proofs belong to Phase 6/7.
- **Unlocks:** `P2-T24`, `P2-T26`, Phase 6 recovery tasks.

## P2-T24 — Exercise key rotation and Root Recovery paths

- **Outcome:** Prove AB/AC/BC root recovery, loss of one share, custodian/operator replacement, host-loss rewrap, purpose/service/signing/audit/backup-attestation key rotation across retained data and post-incident obligations.
- **Depends on:** `P1-T10`, `P1-T11`, `P1-T11A`, `P1-T12`, `P2-T05`, `P2-T16`, and `P2-T23` `MERGED`.
- **External prerequisites:** label=P2-T24-RECOVERY-ACTORS; kind=HUMAN_AUTHORITY; requires=NAMED_OPERATOR_AND_THREE_CURRENT_CUSTODIANS_WITH_EACH_DISTINCT_PAIR_AVAILABLE; accountable=Root-Recovery-Governance-Owner; validity=exact-recovery-bundle-key-versions-retained-data-and-campaign-window; evidence=immutable-signed-Root-Recovery-Actor-Reservation-Receipt
- **Read first:** Zero-Cash Key Management, Role Matrix root-recovery pair, Production Qualification runtime/key gate.
- **Change surface:** campaign harness/evidence and fixes as separate child tasks.
- **Implement:** none; execute the immutable recovery/rotation campaign without product mutation: the named Operator commands but supplies no share, two distinct current Key Custodians execute each admitted pair, and secrets remain outside evidence.
- **Prove:** all AB/AC/BC pairs, wrong/replayed/retired share, stale step-up, unavailable custodian, compromised purpose/service/signing/audit/backup-attestation key rotation, retained-data decrypt/verify and terminal Root Recovery/evidence receipts.
- **Stop/hand off:** any plaintext leak or failed authorized pair is `NEGATIVE`.
- **Unlocks:** `P2-T26`, Phase 6 key-loss campaign.

## P2-T25 — Run Trust, governance, deletion, audit, and operations adversarial gates

- **Outcome:** Execute exact-head campaigns covering 10,000 Principals, all role/approval combinations, learner/minor/guest lifecycle, policies/grants, retention/hold/export/deletion, Delivery State and activation-controller attacks, one-million audit records, bounded observability, alerts and incidents.
- **Depends on:** `P2-T08`, `P2-T10`, `P2-T14`, `P2-T16`, `P2-T18`, and `P2-T18C` `MERGED`.
- **External prerequisites:** label=P2-T25-OWNER-DELETION-FIXTURES; kind=DATA_OR_CORPUS; requires=AVAILABLE; accountable=Trust-and-Governance-test-owner; validity=complete-and-current-for-the-exact-phase-candidate; evidence=content-addressed-owner-deletion-fixture-manifest
- **Read first:** Production Qualification trust/governance/audit gates, Role Matrix, Governed Product Workflows.
- **Change surface:** manifests/harness/evidence; failures create separate implementation tasks.
- **Implement:** none; execute only the immutable Trust/governance/deletion/audit/operations campaign, preserve its exact subject and terminal evidence, and route every discovered correction to a new task.
- **Prove:** cross-Institution/privilege/self-approval/replay/restart/clock/pressure/tamper/orphan cases, terminal receipts and cleanup.
- **Stop/hand off:** framework-only context deletion fixtures cannot qualify final product deletion; record their limited scope.
- **Unlocks:** `P2-T27`, domain phases.

## P2-T26 — Run foundational backup and restore adversarial gates

- **Outcome:** Exercise hard five-minute faults, inventory reconciliation, append-identity abuse, corruption, ransomware fixture, storage pressure, key loss and replacement-host restore on representative non-production data.
- **Depends on:** `P2-T22`, `P2-T23`, and `P2-T24` `MERGED`.
- **Read first:** Production Qualification backup gate and cross-cutting failures, durability contract.
- **Change surface:** campaign manifests/harness/evidence only; fixes are child tasks.
- **Implement:** none; execute the frozen foundational protection/restore campaign on representative non-production data, preserve raw-to-summary evidence and cleanup, and do not mutate the candidate during evaluation.
- **Prove:** exact release/config/host/target identities, signed terminal receipts, raw evidence hashes, cleanup and truthful data-protection result.
- **Stop/hand off:** this is not the 90-day, two-cycle, actual-live-corpus, or separate 150-GB qualification campaign.
- **Unlocks:** `P2-T27`, Phase 6.

## P2-T27 — Close the Phase 2 trust and operations gate

- **Outcome:** Independently reconcile every Phase 2 task, migration/schema head, protected check, adversarial result, open finding and deletion/backup limitation into one signed phase result.
- **Depends on:** `P2-T01`–`P2-T24` `MERGED` and current terminal `SUCCESS` from `P2-T25` and `P2-T26` on the same phase candidate.
- **Read first:** this phase, Delivery State Ledger, Production Qualification.
- **Change surface:** phase evidence package/result only.
- **Implement:** none; independently aggregate current Phase 2 implementation and campaign receipts into one signed phase result without changing source, schemas, configuration, or runtime state.
- **Prove:** exact-head/current prerequisites, no stale or mixed evidence, no unresolved Critical/High or authority/privacy/data-loss issue, and complete blocker list.
- **Stop/hand off:** `SUCCESS` establishes a foundation, not production qualification or activation; incomplete owner deletion paths remain explicit downstream obligations.
- **Unlocks:** Phase 3 final implementation and all governed domain feature work.
