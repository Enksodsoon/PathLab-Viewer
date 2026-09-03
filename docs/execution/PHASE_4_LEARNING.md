# Phase 4 — Learning Foundation

Phase 4 creates Learning Catalog, deterministic learning, Teacher Authoring/local AI, Live Learning/media and Assessment as complete governed vertical slices. Persistence/import prerequisites deliberately overlap Phase 3 so the legacy SQLite source is cut over once. All tasks inherit [README](./README.md).

## P4-T00 — Freeze discoverable learning routes and navigation

- **Outcome:** Define stable route names, navigation placement, role visibility, empty/loading/error/offline states and cross-context links for Catalog, Teacher Authoring, Live Learning, Assessment and later specialist surfaces.
- **Depends on:** `P0-T12`, `P2-T03` `MERGED`.
- **Read first:** Feature Completion Matrix, Role Matrix, current `App.tsx`, web product/design docs.
- **Change surface:** versioned information-architecture contract and route/accessibility tests; no feature implementation.
- **Implement:** freeze one owner-route registry with navigation labels, role visibility and required empty/loading/error/offline/revoked states for every Phase 4 surface and reserved Phase 5 extension point.
- **Prove:** every human workflow has one discoverable owner route; no duplicated authority or hidden admin-only production surface; supported-client/reflow/keyboard plan.
- **Stop/hand off:** unresolved authority or navigation collision requires a narrow ADR before parallel frontend work.
- **Unlocks:** all Phase 4 UI tasks and Phase 5 IA extensions.

## Learning Catalog

## P4-T01 — Scaffold Learning Catalog

- **Outcome:** Catalog owns its logical database, roles, migration head, outbox, API/events and deny-by-default commands for Courses, versions, Modules, Lessons, Cohorts, Enrollments, snapshots, progress/completion and achievement definitions.
- **Depends on:** `P1-T25`, `P2-T27`, `P1-T02`, `P1-T04`, `P1-T06`, `P2-T04` `MERGED`.
- **Read first:** Learning Catalog context, Governed Product Workflows learning section, service-cell contract.
- **Change surface:** Phase-1 Catalog module, migrations/contracts/tests.
- **Implement:** create the owner-local schema/repository/service seams, least-privilege database role, transactional outbox and versioned command/event registry without moving legacy authority.
- **Prove:** atomic outbox, N/N-2 compatibility, role/database isolation and no cross-context FKs/reads.
- **Stop/hand off:** legacy Study remains migration input, not parallel authority.
- **Unlocks:** `P4-T02`–`P4-T07`, `P3-T16` prerequisite.

## P4-T02 — Map and import legacy Study state

- **Outcome:** Deterministically split Study packs/courses/invitations/sessions/progress into Catalog-owned and Assessment-owned structures while retaining source hashes, IDs/mappings and unresolved-content quarantine.
- **Depends on:** `P3-T02`, `P4-T01`, `P4-T21` persistence schema `MERGED`.
- **Read first:** current Study routes/contracts/migrations/pages/stores, P3 source inventory, ADR 0095.
- **Change surface:** owner-local importers/mapping schemas, legacy compatibility routes and tests.
- **Implement:** no dual write, no duplicate course/progress truth, exact deterministic rule/version mapping and explicit rejected/unsupported cases.
- **Prove:** complete legacy fixtures, repeat equality, unmappable-content rejection, route/identity/hash parity and rollback-before-cutover.
- **Stop/hand off:** TRACE-SIM remains dormant and excluded; removal or activation needs separate approval.
- **Unlocks:** `P3-T16`, `P4-T03`, `P4-T05`, `P4-T07`.

## P4-T03 — Implement immutable Course and Lesson versions

- **Outcome:** Educators create/publish/archive immutable Course Versions, Modules and Lesson versions with Published Learning Provenance and exact references to Imaging, Live and Assessment versions.
- **Depends on:** `P4-T00`, `P4-T01` `MERGED`; runtime WSI use requires current `P3-T18=SUCCESS`.
- **Read first:** Catalog context, Governed Product Workflows, Role Matrix ordinary publication.
- **Change surface:** Catalog schemas/service/API and authoring/navigation UI/tests.
- **Implement:** drafts/proposals, version-on-edit, archive/supersede, source attribution, permission/audience and content security.
- **Prove:** immutable publication, changed-source invalidation, stale role, wrong Institution/reference, restart and accessibility.
- **Stop/hand off:** references preserve the owning context/version and never copy mutable state.
- **Unlocks:** `P4-T05`, `P4-T06`, Teacher Authoring, Live scheduling.

## P4-T04 — Implement Cohorts, Enrollments, and Roster Snapshots

- **Outcome:** Membership-backed learners enter versioned Cohorts/Enrollments; scheduled activities capture immutable eligible rosters bound to exact events and content.
- **Depends on:** `P2-T09`, `P2-T10`, `P4-T01` `MERGED`.
- **Read first:** Catalog context, Trust learner/minor contracts, Receipt Registry roster result.
- **Change surface:** Catalog schema/service/admin UI/import seam and tests.
- **Implement:** enroll/withdraw/cancel/close, minor grant checks, roster capture, guest exclusion, versioning and retention.
- **Prove:** 10,000 Principals/100,000 rows fixture, concurrent withdrawal/capture, wrong Institution, expired grant, guest absence and deterministic hash.
- **Stop/hand off:** email, LTI launch, join code or presence cannot create identity/Enrollment.
- **Unlocks:** Live, Assessment, `P4-T05`, specialist roster adapters.

## P4-T05 — Implement deterministic progress and completion

- **Outcome:** Exact accepted activities produce versioned Learner Progress Evidence and immutable reproducible Completion Evidence bound to Purpose Identity, Enrollment, Course Version and rule version.
- **Depends on:** `P4-T02`, `P4-T03`, `P4-T04` `MERGED`.
- **Read first:** Catalog context, Governed Product Workflows, Receipt Registry progress/completion result.
- **Change surface:** deterministic evaluator, learner UI, schemas/tests and deletion adapter.
- **Implement:** idempotent accepted-evidence intake, ordered rules, withdrawal/version handling, retention and reproducibility.
- **Prove:** identical inputs/rule produce identical result; restart/duplicate/reorder/stale version/withdrawal/deletion cases.
- **Stop/hand off:** no model inference, adaptive sequencing, Grade or Credential issuance.
- **Unlocks:** `P4-T06`, Phase 5 Credential Ledger.

## P4-T06 — Govern Achievement Definition Versions and completion eligibility

- **Outcome:** Instructor-initiated definitions receive independent Moderator approval; only exact approved versions can yield eligibility proposals from accepted deterministic completion evidence.
- **Depends on:** `P2-T05`, `P4-T03`, `P4-T05` `MERGED`.
- **Read first:** Catalog/Credential contexts, Role Matrix achievement pairs, Receipt Registry.
- **Change surface:** Catalog schema/service/UI, approval integration, event contracts/tests.
- **Implement:** issuer/validity/minimum-evidence policy, source-version hashes, archive/supersede and exact independent approvals.
- **Prove:** self/material-contributor approval, stale step-up, changed criteria/evidence, duplicate/replay and expiry.
- **Stop/hand off:** Catalog proposes eligibility; Credential Ledger independently decides issuance.
- **Unlocks:** `P4-T06A`, Catalog route closure and Phase 5 Credential foundations.

## P4-T06A — Add Assessment-backed achievement eligibility

- **Outcome:** Extend approved Achievement Definition Versions to accept exact governed Assessment/Grade evidence and emit the same owner-bound eligibility proposal without making Catalog own a Grade or Credential.
- **Depends on:** `P4-T06` and `P4-T27` `MERGED`.
- **Read first:** Catalog/Credential contexts, Assessment Grade contract and accepted P4-T06 definition/approval rules.
- **Change surface:** Catalog Assessment-evidence adapter, event contracts, eligibility tests and audit evidence.
- **Implement:** exact assessment/session/item/scoring/Grade hashes, eligibility recomputation/invalidation and no direct Assessment-table access.
- **Prove:** changed/revoked/appealed Grade, stale definition, duplicate/reordered outbox event, cross-Institution evidence and restart.
- **Stop/hand off:** Catalog only proposes eligibility; it cannot score, mutate Grade or issue a Credential.
- **Unlocks:** complete learning closure and Assessment-backed Credential workflows.

## P4-T07 — Complete Catalog routes and scale gate

- **Outcome:** Discoverable educator/learner routes replace legacy Study authority for course discovery, authoring, enrollment, progress/completion and archive with migration-compatible redirects.
- **Depends on:** `P3-T17`, `P4-T02`–`P4-T06` `MERGED`.
- **Read first:** P4-T00 IA, Catalog qualification gate and supported-client contract.
- **Change surface:** Study/Catalog pages/routes/components, API adapters, e2e/load/accessibility evidence.
- **Implement:** replace legacy route authority with Catalog-backed discoverable educator/learner flows, compatible redirects, bounded pagination and explicit recoverable client states.
- **Prove:** 100 Courses, 10,000 Principals, >=100,000 version/enrollment/roster/progress rows, withdrawal/restart/migration, current/N-2 browser and WCAG 2.2 AA.
- **Stop/hand off:** historical default-off Study evidence or synthetic-only UI tests do not qualify the surface.
- **Unlocks:** `P4-T30`, Phase 7 exact rerun.

## Teacher Authoring and local AI

## P4-T08 — Implement deterministic Authoring Templates and draft lifecycle

- **Outcome:** A complete manual/template workflow creates, edits, rejects, abandons and approves Authoring Drafts without a model, with exact disposition/retention/deletion behavior.
- **Depends on:** `P1-T04`, `P4-T00`, `P4-T01`, and `P4-T03` `MERGED`.
- **Read first:** Teacher Authoring context, Governed Product Workflows, Role Matrix single-person approval.
- **Change surface:** Teacher Authoring schema/service/routes/UI, existing authoring store/pages and tests.
- **Implement:** versioned drafts, source references, 90-day/one-year clocks, approval invalidated by edit and owning-context proposal handoff.
- **Prove:** offline/reload/concurrent edit, changed approval, authorization, retention/deletion and accessible no-model flow.
- **Stop/hand off:** templates are the mandatory complete path, not a degraded remote-AI fallback.
- **Unlocks:** `P4-T11`, `P4-T12`.

## P4-T09 — Build rights-cleared SmolLM2 bundles reproducibly

- **Outcome:** Produce exact primary and fallback teacher-only bundles, conversion recipes, hashes, licenses/notices/SBOMs and size/capability manifests on the owned offline runner.
- **Depends on:** `P0-T08`, `P0-T09`, `P0-T09A`, `P1-T22` `MERGED`.
- **Read first:** [Teacher AI Stack](../architecture/TEACHER_AI_STACK.md), Teacher Authoring context, current web model dependencies.
- **Change surface:** model build/mirror scripts, manifests, offline kit, package locks and supply-chain evidence.
- **Implement:** primary WebLLM q4f16 and fallback ONNX q4 only as frozen; resolve current runtime-pin mismatch explicitly; <=1.5-GB bundle contract.
- **Prove:** repeat build identity, offline assembly, license/provenance/size scan, corruption fixtures and no Hub/CDN/runtime fetch.
- **Stop/hand off:** mutable revision, unclear open-weight rights, missing ARM/browser artifact or paid hosted conversion blocks admission.
- **Unlocks:** `P4-T10`.

## P4-T10 — Select capability tier and activate bundles atomically

- **Outcome:** Browser capability probes select only a qualified WebGPU or WASM tier, verify same-origin signed artifacts and atomically retain a last-known-good cache with deterministic fallback.
- **Depends on:** `P4-T09` `MERGED`.
- **Read first:** Teacher AI Stack capability/offline/resource sections, P4-T00 route contract.
- **Change surface:** dedicated teacher route/workers, Cache Storage/OPFS/service worker, Caddy headers and tests.
- **Implement:** isolated COOP/COEP, persistent storage request, interrupted download/update/rollback, cache eviction and bundle status UI.
- **Prove:** airplane reload, corrupt/missing shard, termination at every boundary, unqualified device, eviction and global route isolation.
- **Stop/hand off:** no WebGL, remote inference, CDN/model-hub fetch or global COOP/COEP regression.
- **Unlocks:** `P4-T11`, `P4-T13`.

## P4-T11 — Bound generation, retrieval, and safety

- **Outcome:** Local generation produces only proposals with approved source spans and Generation Records while publication, grading, tool calls, clinical recommendations and privacy leakage fail structurally.
- **Depends on:** `P4-T08`, `P4-T10` `MERGED`.
- **Read first:** Teacher AI Stack quality/safety, Teacher Authoring context.
- **Change surface:** teacher workers, source-span retrieval, safety/output enforcement, provenance storage/UI/tests.
- **Implement:** bounded rewrite/summarize/objective/question/distractor operations, cancellation <=2s, refusal, no unnecessary prompt/source retention.
- **Prove:** prompt injection, invented source IDs, clinical/diagnostic prompt, publish/grade/tool attempts, leakage and deterministic-template continuity.
- **Stop/hand off:** model output never becomes Catalog/Assessment truth.
- **Unlocks:** `P4-T12`, `P4-T13`.

## P4-T12 — Review and hand approved drafts to Learning Catalog

- **Outcome:** Instructor reviews an exact draft/generation/source diff and explicitly submits a versioned Lesson/Course proposal to Learning Catalog; any edit invalidates prior approval.
- **Depends on:** `P2-T07`, `P4-T08`, `P4-T11` `MERGED`.
- **Read first:** Teacher Authoring/Catalog/Assessment ownership and Role Matrix.
- **Change surface:** teacher review UI/service and Catalog proposal commands/tests.
- **Implement:** bind review to the immutable draft/source/generation tuple, invalidate it on any edit and submit only an idempotent owner-addressed Catalog proposal whose acceptance remains Catalog-owned.
- **Prove:** changed/stale/cross-Institution/duplicate proposal, revoked role, model bypass and accessible deterministic fallback.
- **Stop/hand off:** teacher approval does not itself publish an Item/Lesson or score work.
- **Unlocks:** `P4-T12A` and the Catalog Authoring workflow.

## P4-T12A — Hand reviewed drafts to Assessment

- **Outcome:** Map an exact reviewed draft into one of the nine supported Assessment proposal contracts, require explicit Instructor submission and invalidate approval on any draft/source/item-contract change.
- **Depends on:** `P4-T12` and `P4-T22A`–`P4-T22I` `MERGED`.
- **Read first:** Teacher Authoring/Assessment ownership, all nine accepted Item Version contracts and Role Matrix.
- **Change surface:** Teacher-to-Assessment proposal adapter, review UI states, contract fixtures and tests.
- **Implement:** explicit item-kind selection, immutable source/generation/contract hashes and owner-side accept/reject result without direct publication.
- **Prove:** every supported item kind, unsupported/changed/stale/cross-Institution/duplicate proposal, revoked role, model bypass and accessible deterministic fallback.
- **Stop/hand off:** Teacher Authoring cannot publish an Item Version or supply scoring truth.
- **Unlocks:** complete Authoring workflow and `P4-T13`.

## P4-T13 — Reconcile the Teacher AI tier results

- **Outcome:** Reconcile independently closed primary-WebGPU and fallback-WASM campaigns into one terminal Teacher AI phase result without averaging away a tier failure.
- **Depends on:** current terminal `SUCCESS` from `P4-T13E` and `P4-T13I` on the identical Teacher AI manifest and phase candidate.
- **Read first:** both tier closure reports, Teacher AI Stack and Production Qualification Teacher AI gate.
- **Change surface:** signed result aggregation and evidence index only.
- **Implement:** none; aggregate immutable tier receipts, verify tuple equality and emit exactly one `SUCCESS`, `PARTIAL`, `NEGATIVE`, or `NOT_EVALUABLE` parent result.
- **Prove:** both tiers, every reviewer/device/corpus hash, critical-error disposition, resource/offline/integrity result and cleanup receipt reconcile without gaps or substitution.
- **Stop/hand off:** a missing, stale, mixed-candidate or non-`SUCCESS` tier prevents parent `SUCCESS`; never average tiers or lower thresholds.
- **Unlocks:** `P4-T30` and Phase 7 exact rerun only on current `P4-T13=SUCCESS`.

## P4-T13A — Freeze the Teacher AI harness and manifests

- **Outcome:** Build the observation harness and freeze separate primary-WebGPU and fallback-WASM manifests without executing either tier's qualifying workload.
- **Depends on:** `P4-T09`–`P4-T12A` `MERGED`.
- **External prerequisites:** label=EP-P4-AI-RIGHTS; kind=RIGHTS; requires=APPROVED; accountable=Teacher AI qualification lead; validity=exact corpus and bundle rights records remain current through parent closure; evidence=SignedTeacherAIRightsReceipt | label=EP-P4-AI-CORPUS; kind=DATA_OR_CORPUS; requires=AVAILABLE; accountable=Teacher AI qualification lead; validity=exact corpus hash remains unchanged through parent closure; evidence=SignedTeacherAICorpusReceipt | label=EP-P4-AI-REVIEWERS; kind=HUMAN_AUTHORITY; requires=ASSIGNED; accountable=Teacher AI qualification lead; validity=two independent qualified reviewers remain assigned for every reviewed item through tier closure; evidence=SignedReviewerAssignmentReceipt | label=EP-P4-AI-DEVICES; kind=HARDWARE; requires=AVAILABLE; accountable=Teacher AI qualification lead; validity=declared physical device OS browser and bundle tuple remains unchanged through tier closure; evidence=SignedPhysicalDeviceAdmissionReceipt.
- **Read first:** Teacher AI Stack, Production Qualification Teacher AI gate and accepted bundle manifests.
- **Change surface:** reviewer/campaign harness, immutable manifests, evidence schemas and runbooks only.
- **Implement:** encode per-tier corpus identity, reviewer independence, critical-error rules, resource/latency/offline/integrity thresholds, trusted timing, receipt cursors and cleanup obligations.
- **Prove:** manifest-schema validation, reviewer/device/corpus resolution, deterministic fixture replay, observer integrity and no product mutation.
- **Stop/hand off:** any prerequisite not at its required disposition or unresolved threshold/observer/cleanup semantics is `NOT_EVALUABLE` and blocks dry-run.
- **Unlocks:** `P4-T13B` and `P4-T13F`.

## P4-T13B — Dry-run the primary WebGPU tier

- **Outcome:** Execute a reduced non-qualifying primary-WebGPU rehearsal that resolves every reviewer, generation, observer, fault and cleanup path.
- **Depends on:** `P4-T13A` `MERGED` with its primary Campaign Manifest head `FROZEN` and current `EP-P4-AI-RIGHTS`, `EP-P4-AI-CORPUS`, `EP-P4-AI-REVIEWERS`, and `EP-P4-AI-DEVICES` receipt heads.
- **Read first:** frozen primary manifest and dry-run runbook.
- **Change surface:** primary-tier dry-run evidence and incidents only.
- **Implement:** none; exercise reduced review, source/refusal, download, resource, airplane, zero-egress, rollback and injection cases without changing product or manifest.
- **Prove:** every path emits the expected receipt and terminal cleanup; observer or fixture defects are separated from product failures.
- **Stop/hand off:** unresolved harness/fixture ambiguity blocks launch; dry-run success is not tier success.
- **Unlocks:** `P4-T13C` only on current `P4-T13B=SUCCESS`.

## P4-T13C — Start the primary WebGPU campaign

- **Outcome:** Admit the exact primary bundle, corpus, devices and reviewers and start the frozen full campaign with immutable process identities and receipt cursor.
- **Depends on:** current `P4-T13B=SUCCESS`, unchanged primary Campaign Manifest and phase-candidate fingerprint heads, and current `EP-P4-AI-RIGHTS`, `EP-P4-AI-CORPUS`, `EP-P4-AI-REVIEWERS`, and `EP-P4-AI-DEVICES` receipt heads.
- **Read first:** primary launch runbook and frozen manifest.
- **Change surface:** primary admission/start evidence only.
- **Implement:** none; start the declared workload and observers without repairing code or rewriting evidence.
- **Prove:** exact tuple equality, reviewer independence, physical-device identity, observer liveness and forward receipt movement.
- **Stop/hand off:** partial admission, drift or missing actor/device is `NOT_EVALUABLE`; start remains `RUNNING`, never `SUCCESS`.
- **Unlocks:** `P4-T13D`.

## P4-T13D — Monitor and audit the primary WebGPU campaign

- **Outcome:** Observe at least 300 representative tasks with two independent reviews plus the full 60-minute/100-request resource soak and frozen offline/integrity/adversarial schedule.
- **Depends on:** active `P4-T13C` with matching immutable primary manifest and receipt cursor.
- **Read first:** latest cursor, primary fault schedule and only open incidents.
- **Change surface:** primary observations, reviews, fault evidence and incidents only.
- **Implement:** none; record live task/review progress, memory/latency/throughput, airplane/egress, corruption/rollback/eviction and injection evidence.
- **Prove:** no uncovered interval, two distinct reviews per task, all thresholds and scheduled faults, live device activity and complete raw evidence.
- **Stop/hand off:** one critical error is `NEGATIVE`; a stopped device, reviewer gap, changed tuple or missing evidence follows the frozen disposition without silent restart.
- **Unlocks:** `P4-T13E` after workload, soak and cleanup terminate.

## P4-T13E — Close the primary WebGPU campaign

- **Outcome:** Reconcile the complete primary campaign into one signed tier result and terminal device/cache cleanup record.
- **Depends on:** completed `P4-T13C`/`P4-T13D` and unchanged primary manifest/candidate.
- **Read first:** frozen primary manifest, terminal receipt range and Production Qualification Teacher AI gate.
- **Change surface:** primary signed evidence aggregation and cleanup only.
- **Implement:** none; verify counts, independent reviews, threshold distributions, faults and cleanup before emitting the tier result.
- **Prove:** at least 300 tasks, two reviews each, full soak, all resource/offline/integrity/adversarial thresholds and deterministic-template continuity.
- **Stop/hand off:** incomplete workload is `PARTIAL`, missing trustworthy evidence `NOT_EVALUABLE`, and any critical error `NEGATIVE`.
- **Unlocks:** parent `P4-T13` after `P4-T13I` also closes.

## P4-T13F — Dry-run the fallback WASM tier

- **Outcome:** Execute a reduced non-qualifying fallback-WASM rehearsal that resolves every reviewer, generation, observer, fault and cleanup path independently of WebGPU.
- **Depends on:** `P4-T13A` `MERGED` with its fallback Campaign Manifest head `FROZEN` and current `EP-P4-AI-RIGHTS`, `EP-P4-AI-CORPUS`, `EP-P4-AI-REVIEWERS`, and `EP-P4-AI-DEVICES` receipt heads.
- **Read first:** frozen fallback manifest and dry-run runbook.
- **Change surface:** fallback-tier dry-run evidence and incidents only.
- **Implement:** none; exercise reduced review, source/refusal, download, resource, airplane, zero-egress, rollback and injection cases without changing product or manifest.
- **Prove:** every path emits the expected receipt and terminal cleanup on declared low-resource physical clients.
- **Stop/hand off:** unresolved harness/fixture ambiguity blocks launch; WebGPU results cannot substitute for this dry run.
- **Unlocks:** `P4-T13G` only on current `P4-T13F=SUCCESS`.

## P4-T13G — Start the fallback WASM campaign

- **Outcome:** Admit the exact fallback bundle, corpus, low-resource devices and reviewers and start the frozen full campaign with immutable process identities and receipt cursor.
- **Depends on:** current `P4-T13F=SUCCESS`, unchanged fallback Campaign Manifest and phase-candidate fingerprint heads, and current `EP-P4-AI-RIGHTS`, `EP-P4-AI-CORPUS`, `EP-P4-AI-REVIEWERS`, and `EP-P4-AI-DEVICES` receipt heads.
- **Read first:** fallback launch runbook and frozen manifest.
- **Change surface:** fallback admission/start evidence only.
- **Implement:** none; start the declared workload and observers without repair or substitution.
- **Prove:** exact tuple equality, reviewer independence, physical-device identity, observer liveness and forward receipt movement.
- **Stop/hand off:** partial admission, drift, remote inference or primary-tier substitution prevents launch; start remains `RUNNING`.
- **Unlocks:** `P4-T13H`.

## P4-T13H — Monitor and audit the fallback WASM campaign

- **Outcome:** Observe at least 300 representative tasks with two independent reviews plus the full 60-minute/100-request fallback soak and frozen offline/integrity/adversarial schedule.
- **Depends on:** active `P4-T13G` with matching immutable fallback manifest and receipt cursor.
- **Read first:** latest cursor, fallback fault schedule and only open incidents.
- **Change surface:** fallback observations, reviews, fault evidence and incidents only.
- **Implement:** none; record progress, memory/latency/128-token timing, airplane/egress, corruption/rollback/eviction and injection evidence.
- **Prove:** no uncovered interval, two distinct reviews per task, all fallback thresholds and scheduled faults, live physical-device activity and complete raw evidence.
- **Stop/hand off:** one critical error is `NEGATIVE`; a stopped device, reviewer gap, changed tuple or missing evidence follows the frozen disposition.
- **Unlocks:** `P4-T13I` after workload, soak and cleanup terminate.

## P4-T13I — Close the fallback WASM campaign

- **Outcome:** Reconcile the complete fallback campaign into one signed tier result and terminal device/cache cleanup record.
- **Depends on:** completed `P4-T13G`/`P4-T13H` and unchanged fallback manifest/candidate.
- **Read first:** frozen fallback manifest, terminal receipt range and Production Qualification Teacher AI gate.
- **Change surface:** fallback signed evidence aggregation and cleanup only.
- **Implement:** none; verify counts, independent reviews, threshold distributions, faults and cleanup before emitting the tier result.
- **Prove:** at least 300 tasks, two reviews each, full soak, all fallback resource/offline/integrity/adversarial thresholds and deterministic-template continuity.
- **Stop/hand off:** incomplete workload is `PARTIAL`, missing trustworthy evidence `NOT_EVALUABLE`, and any critical error `NEGATIVE`.
- **Unlocks:** parent `P4-T13` after `P4-T13E` also closes.

## Live Learning and Teacher Broadcast

## P4-T14 — Scaffold Live Learning and import legacy Classroom state

- **Outcome:** `pathlab-live` owns its database, role, migration head, outbox and one leased Class Session owner; legacy durable Classroom state maps deterministically while ephemeral state is discarded.
- **Depends on:** `P1-T17`, `P1-T18`, `P4-T01`, `P4-T02`, `P4-T04` `MERGED`.
- **Read first:** Live Learning context, current Classroom migrations/routes/hub/runtime, P3 source inventory.
- **Change surface:** Live module/service/migrations/contracts/importer and tests.
- **Implement:** session/presenter epochs, durable interactions/attendance identities, snapshots and migration mappings; never hold DB connection across SSE.
- **Prove:** atomic outbox, lease takeover, restart post-commit/pre-delivery, import parity and zero persisted ephemeral rows.
- **Stop/hand off:** SSE/presence/viewport state is transport, not authority.
- **Unlocks:** `P3-T16`, `P4-T15`–`P4-T20`.

## P4-T15 — Schedule, admit, start, and close Class Sessions

- **Outcome:** Sessions bind exact Course/content/asset/Roster Snapshot hashes; members/minors/guests join permitted paths under Presenter/Session leases and terminal lifecycle receipts.
- **Depends on:** current `P3-T18=SUCCESS`; `P4-T03`, `P4-T04`, `P4-T14` `MERGED`.
- **Read first:** Live context, Golden Journey G14–G18, Receipt Registry Live section.
- **Change surface:** Live routes/services and teacher/student/invite/roster UI/tests.
- **Implement:** schedule/start/close commands, exact roster/content snapshot binding, member/minor/guest admission, expiring join capability, Presenter/Session leases and terminal lifecycle receipts.
- **Prove:** wrong Institution, withdrawal, expired Processing Grant, reused invite, guest conversion, lease conflict/restart and start/close idempotency.
- **Stop/hand off:** join codes never create/authenticate Memberships; guests remain non-credit/non-durable.
- **Unlocks:** `P4-T16`–`P4-T18`.

## P4-T16 — Move ephemeral synchronization to the leased owner

- **Outcome:** Presence, pointer, viewport, control, temporary pins and teaching strokes synchronize with bounded ordering/fanout/reconnect while leaving no durable behavior history.
- **Depends on:** `P4-T15` `MERGED`.
- **Read first:** Live context, current Classroom hub/presenter/reconnect/overlay code.
- **Change surface:** live hub/protocol/client sync and load/unit tests.
- **Implement:** single-owner epochs, sequence/snapshot/reconnect, slow-consumer shedding and qualified pointer/viewport rates.
- **Prove:** duplicate/delay/reorder, reconnect, process takeover, slow clients, memory/queue caps and database/audit absence.
- **Stop/hand off:** no unbounded queues, participant telemetry archive or durable conversion.
- **Unlocks:** `P4-T18`, `P4-T20`.

## P4-T17 — Commit Durable Interactions and explicit notebook selections

- **Outcome:** Prompts, polls, submitted questions/responses and selected workspace/notebook actions commit once via Live outbox; unsubmitted notebooks remain device-local.
- **Depends on:** `P4-T14`, `P4-T15` `MERGED`.
- **Read first:** Live context, Governed Product Workflows Live section, Receipt Registry.
- **Change surface:** Live schemas/service, Classroom question/notebook UI and tests.
- **Implement:** semantic idempotency, acknowledgement, purpose/roster binding, privacy/retention/deletion and convergence result.
- **Prove:** restart after commit, duplicate/reconnect, offline local notebook, explicit selection, guest durable-write rejection and deletion.
- **Stop/hand off:** never synchronize the entire notebook or persist teaching strokes/control state.
- **Unlocks:** `P4-T18`, deterministic progress inputs, `P4-T20`.

## P4-T18 — Derive attendance and complete Live UI/accessibility

- **Outcome:** Validated member participation yields bounded Attendance Intervals; raw presence/connection/guest state does not; teacher and learner routes expose recoverable states accessibly.
- **Depends on:** `P4-T15`–`P4-T17` `MERGED`.
- **Read first:** Live context and P4-T00 IA.
- **Change surface:** attendance evaluator, Live UI/notifications/accessibility/e2e and deletion adapter.
- **Implement:** derive intervals only from accepted member participation, expose teacher/learner recovery states and implement notification, retention, deletion and accessible route behavior.
- **Prove:** reconnect without gap/duplicate, guest absence, wrong snapshot, withdrawal/restart, client matrix and WCAG 2.2 AA.
- **Stop/hand off:** online status alone is not attendance evidence.
- **Unlocks:** `P4-T19`, `P4-T20`.

## P4-T19A — Ratify the self-hosted TURN topology and authority contract

- **Outcome:** Freeze the exact free/offline relay implementation and version, built-in-versus-separate process decision, public/listen/relay ports, NAT/firewall rules, credential issuer/rotation/expiry, supervision/cgroup limits, bandwidth/resource envelope, zero-cash accounting and failure/fallback behavior used by Teacher Broadcast.
- **Depends on:** `P0-T03A`, `P1-T17`–`P1-T20`, `P4-T18` `MERGED`.
- **External prerequisites:** label=EP-P4-TURN-SOURCE; kind=TOOL_OR_IMPLEMENTATION; requires=AVAILABLE; accountable=Platform Architect; validity=official source license version and ARM64 offline artifact hashes remain unchanged through P4-T19 merge; evidence=SignedTURNImplementationAdmissionReceipt | label=EP-P4-TURN-NETWORK; kind=NETWORK_IDENTITY; requires=DECLARED; accountable=Network Operator; validity=public address NAT firewall and port-allocation tuple remains the target topology through engineering closure; evidence=SignedTURNNetworkTopologyReceipt.
- **Read first:** Galene official TURN documentation, ADRs 0021–0022/0027, Zero-Cash runtime/service cells, threat model and Production Qualification Broadcast gate.
- **Change surface:** narrow TURN/media ADR, port and credential contract, offline-input manifest, systemd/cgroup/network policy specification and executable topology tests.
- **Implement:** select Galene built-in TURN or one exact separately supervised free implementation; assign least-privilege credential authority and rotation overlap; freeze UDP/TCP exposure, relay quotas, allocation lifetime, abuse limits, observation fields and fail-to-slides/text behavior.
- **Prove:** official-source/license/ARM64/offline evidence, no paid or hosted dependency, port/NAT/firewall reachability model, credential replay/expiry/rotation, cgroup/bandwidth saturation and deterministic relay-loss fallback tests.
- **Stop/hand off:** unavailable inputs, unresolved credential owner, unspecified ports/NAT, unbounded relay capacity or required spend is `NOT_EVALUABLE` or `NEGATIVE` as declared; P4-T19 cannot begin.
- **Unlocks:** `P4-T19`.

## P4-T19 — Integrate Galene, the ratified TURN path, and Media Fallback

- **Outcome:** Pinned Galene runs only inside a Teacher Broadcast sub-reservation using short-lived Institution/audience-bound tokens, one client VP8/Opus 540p publisher, receive-only learners and synchronized slides/text fallback.
- **Depends on:** `P1-T17`–`P1-T20`, `P4-T15`, `P4-T18`, `P4-T19A` `MERGED`.
- **Read first:** Live context media section, ADRs 0021–0022/0027, Production Qualification Broadcast gate.
- **Change surface:** Galene offline artifact/unit/config, Live authorization, browser media/fallback UI and tests.
- **Implement:** install the pinned offline media/relay artifacts, hardened supervision/cgroup and exact port policy; issue short-lived role/audience-bound media and relay credentials; enforce one publisher/receive-only viewers and automatic synchronized fallback.
- **Prove:** direct/TURN, wrong role/audience, token replay/expiry, crash/network loss, no recording/transcoding/database, resource/bandwidth caps and conflicting mode request.
- **Stop/hand off:** no cloud SFU/conference/recording fallback.
- **Unlocks:** `P4-T20A`.

## P4-T20 — Run the Live Learning engineering campaign

- **Outcome:** Exact phase candidate completes the 1-Instructor + 1,200-learner, 60-minute, six-DZI Live campaign without media.
- **Depends on:** `P4-T14`–`P4-T18` `MERGED`.
- **External prerequisites:** label=EP-P4-LIVE-FIXTURES; kind=DATA_OR_CORPUS; requires=FROZEN; accountable=Live qualification lead; validity=actor workload DZI and fault-manifest hashes remain unchanged through campaign closure; evidence=SignedLiveFixtureManifestReceipt | label=EP-P4-LIVE-CLIENTS; kind=HARDWARE; requires=AVAILABLE; accountable=Live qualification lead; validity=declared physical client matrix remains available and unchanged through campaign closure; evidence=SignedLiveClientAdmissionReceipt | label=EP-P4-LIVE-NETWORK; kind=NETWORK_IDENTITY; requires=DECLARED; accountable=Network Operator; validity=network and shaping tuple remains unchanged through campaign closure; evidence=SignedLiveNetworkManifestReceipt.
- **Read first:** Production Qualification Live gate and [Adaptive Viewer Capacity](../architecture/ADAPTIVE_VIEWER_CAPACITY.md) as legacy measurement-baseline input only; the [Final Production Endpoint](../architecture/FINAL_PRODUCTION_ENDPOINT.md) and current accepted Live/resource/capacity contracts control any conflict.
- **Change surface:** load/browser/host observer/evidence harness only.
- **Implement:** none; execute the frozen non-media workload, observations, faults and cleanup without repairing product or changing the manifest.
- **Prove:** frozen ephemeral/durable rates, six all-response prompts, 20% questions, 10% reconnect, process restart, final convergence, resource/latency/error distributions and cleanup.
- **Stop/hand off:** partial duration/participants/slides is `PARTIAL`; virtual load does not replace physical-client/a11y proof.
- **Unlocks:** `P4-T20B` and Phase 7 exact rerun.

## P4-T20A — Run the Teacher Broadcast engineering campaign

- **Outcome:** Exact phase candidate completes the separate 1-Instructor + 100 receive-only-viewer, 60-minute 540p VP8/Opus direct/TURN campaign.
- **Depends on:** `P4-T19` `MERGED`.
- **External prerequisites:** label=EP-P4-MEDIA-FIXTURES; kind=DATA_OR_CORPUS; requires=FROZEN; accountable=Broadcast qualification lead; validity=media browser network and fault-manifest hashes remain unchanged through campaign closure; evidence=SignedBroadcastFixtureManifestReceipt | label=EP-P4-MEDIA-CLIENTS; kind=HARDWARE; requires=AVAILABLE; accountable=Broadcast qualification lead; validity=declared physical publisher and receiver sample remains available and unchanged through campaign closure; evidence=SignedBroadcastClientAdmissionReceipt | label=EP-P4-MEDIA-NETWORK; kind=NETWORK_IDENTITY; requires=DECLARED; accountable=Network Operator; validity=direct and ratified relay topology remains unchanged through campaign closure; evidence=SignedBroadcastNetworkManifestReceipt.
- **Read first:** Production Qualification Teacher Broadcast gate and Live media contract.
- **Change surface:** media load/browser/network/host observer/evidence harness only.
- **Implement:** none; execute the frozen direct and ratified relay workloads, observations, token-expiry cases and cleanup without product repair.
- **Prove:** publisher/receiver roles, direct/TURN paths, token expiry, no record/transcode, bounded bandwidth/resources/latency/errors and terminal cleanup.
- **Stop/hand off:** partial duration/viewers or virtual-only client evidence is `PARTIAL`; no cloud media fallback.
- **Unlocks:** `P4-T20B` and Phase 7 exact rerun.

## P4-T20B — Run the combined media-failure and synchronized-fallback repeat

- **Outcome:** Repeat the exact 1-Instructor + 1,200-learner, 60-minute, six-DZI Live workload with exactly 100 receive-only learners on the qualified Galene overlay and the other 1,100 on synchronized slides/text, then inject the declared media failure and prove automatic fallback without durable-state loss or resource-boundary breach.
- **Depends on:** current `P4-T20=SUCCESS` and `P4-T20A=SUCCESS` on the same phase tuple.
- **Read first:** Live/Teacher Broadcast failure contract, both campaign manifests, and [Adaptive Viewer Capacity](../architecture/ADAPTIVE_VIEWER_CAPACITY.md) as legacy measurement-baseline input only; the [Final Production Endpoint](../architecture/FINAL_PRODUCTION_ENDPOINT.md) and current accepted Live/resource/capacity contracts control any conflict.
- **Change surface:** combined fault/evidence execution and cleanup only; fixes are separate tasks.
- **Implement:** none; run the immutable combined workload and fault schedule, preserve receipt cursors and perform terminal media/session cleanup.
- **Prove:** exact 1,200/100/60-minute/six-slide counts, reservation exclusivity, fault timing, fallback convergence for all participants, reconnect/restart, durable interaction equality, resource/error distributions, no record/transcode and complete cleanup.
- **Stop/hand off:** mixed candidates/manifests, a shortened repeat or manual fallback substitution is `PARTIAL` or `NEGATIVE` as applicable.
- **Unlocks:** `P4-T30` and Phase 7 exact rerun.

## Assessment

## P4-T21 — Scaffold Assessment and map legacy assessable state

- **Outcome:** `pathlab-assessment` owns its logical database, roles, migration head, outbox, mode, API/events and import target for legacy Study items/scoring/work.
- **Depends on:** `P1-T17`, `P1-T18`, `P4-T01`, `P4-T04` `MERGED`.
- **Read first:** Assessment context, Governed Product Workflows Assessment, current Study contracts/source inventory.
- **Change surface:** Assessment module/service/migrations/contracts/importer skeleton and tests.
- **Implement:** create the owner-local schema/repository/service seams, least-privilege role, transactional outbox, exclusive mode ingress and deterministic legacy mapping skeleton without creating parallel Grade authority.
- **Prove:** database/capability isolation, atomic outbox, inactive-mode ingress denial, deterministic legacy mapping and no parallel Catalog/Study grade authority.
- **Stop/hand off:** no Grade or Attempt in Catalog/legacy tables.
- **Unlocks:** `P4-T02`, `P3-T16`, `P4-T22`–`P4-T29`.

## P4-T22 — Implement the shared immutable Item Version envelope

- **Outcome:** Implement the versioned Item envelope, content/safety policy, immutable scoring-definition reference, authoring/player dispatch registry and unknown-kind rejection shared by all nine declared response contracts.
- **Depends on:** current `P3-T18=SUCCESS`; `P4-T00`, `P4-T21` `MERGED`.
- **Read first:** Assessment context, Role Matrix ordinary item publication, P3 DZI/calibration contracts.
- **Change surface:** Assessment common item schemas/service, authoring/player registry, fixtures and tests.
- **Implement:** immutable publication/version hashes, accessibility metadata, safe rich content/resources, deterministic validation and no silent kind coercion.
- **Prove:** schema/version/property/security/accessibility, unsafe content/resource, immutable publication, unknown kind and generic response round trip.
- **Stop/hand off:** the envelope does not imply any response kind is implemented; no AI scoring, adaptive testing or default negative marking.
- **Unlocks:** `P4-T22A`–`P4-T22I`.

## P4-T22A — Implement single-choice Items

- **Outcome:** Author, publish, render, save and deterministically score the single-choice contract through the shared immutable envelope.
- **Depends on:** `P4-T22` `MERGED`.
- **Read first:** Assessment single-choice contract and common Item envelope.
- **Change surface:** single-choice schema/validator/authoring/player/scorer fixtures and tests.
- **Implement:** stable option identities, exactly-one selection, accessible grouping/focus and immutable key/scoring reference.
- **Prove:** zero/one/multiple/unknown choices, reorder/version drift, keyboard/screen-reader behavior and response round trip.
- **Stop/hand off:** never coerce multiple choice or free text into this contract.
- **Unlocks:** `P4-T12A` and `P4-T23` only after the complete response-contract set named by those cards is `MERGED`.

## P4-T22B — Implement multiple-choice Items

- **Outcome:** Author, publish, render, save and deterministically score the multiple-choice contract through the shared immutable envelope.
- **Depends on:** `P4-T22` `MERGED`.
- **Read first:** Assessment multiple-choice contract and common Item envelope.
- **Change surface:** multiple-choice schema/validator/authoring/player/scorer fixtures and tests.
- **Implement:** stable option sets, declared min/max selections, accessible grouping and immutable partial-credit policy without default negative marking.
- **Prove:** empty/duplicate/excess/unknown selections, reorder/version drift, keyboard/screen-reader behavior and response round trip.
- **Stop/hand off:** undeclared partial or negative scoring is prohibited.
- **Unlocks:** `P4-T12A` and `P4-T23` only after the complete response-contract set named by those cards is `MERGED`.

## P4-T22C — Implement true/false Items

- **Outcome:** Author, publish, render, save and deterministically score the explicit true/false contract through the shared immutable envelope.
- **Depends on:** `P4-T22` `MERGED`.
- **Read first:** Assessment true/false contract and common Item envelope.
- **Change surface:** true/false schema/authoring/player/scorer fixtures and tests.
- **Implement:** explicit boolean response identity, unanswered state, localization-safe labels and accessible control semantics.
- **Prove:** true/false/unanswered/invalid values, version drift, keyboard/screen-reader behavior and response round trip.
- **Stop/hand off:** boolean labels cannot be inferred from arbitrary single-choice options.
- **Unlocks:** `P4-T12A` and `P4-T23` only after the complete response-contract set named by those cards is `MERGED`.

## P4-T22D — Implement numeric Items

- **Outcome:** Author, publish, render, save and deterministically score bounded numeric responses through the shared immutable envelope.
- **Depends on:** `P4-T22` `MERGED`.
- **Read first:** Assessment numeric contract, locale policy and common Item envelope.
- **Change surface:** numeric schema/parser/authoring/player/scorer fixtures and tests.
- **Implement:** canonical decimal representation, declared unit/tolerance/range policy, locale-aware entry and no floating-point ambiguity.
- **Prove:** boundaries, precision, locale separators, unit mismatch, NaN/infinity/overflow, version drift and response round trip.
- **Stop/hand off:** undeclared unit conversion or tolerance is prohibited.
- **Unlocks:** `P4-T12A` and `P4-T23` only after the complete response-contract set named by those cards is `MERGED`.

## P4-T22E — Implement short-text Items

- **Outcome:** Author, publish, render, save and apply only declared deterministic normalization/exact-match policy to bounded short-text responses.
- **Depends on:** `P4-T22` `MERGED`.
- **Read first:** Assessment short-text contract, Unicode policy and common Item envelope.
- **Change surface:** short-text schema/normalizer/authoring/player/scorer fixtures and tests.
- **Implement:** byte/grapheme limits, frozen Unicode/case/whitespace normalization and explicit manual-review fallback.
- **Prove:** normalization, confusables, directionality, empty/oversized/control content, version drift and response round trip.
- **Stop/hand off:** no semantic/LLM grading or undisclosed fuzzy matching.
- **Unlocks:** `P4-T12A` and `P4-T23` only after the complete response-contract set named by those cards is `MERGED`.

## P4-T22F — Implement essay Items and manual review

- **Outcome:** Author, publish, render and durably submit bounded essay responses for accountable manual scoring under an immutable rubric.
- **Depends on:** `P4-T22` `MERGED`.
- **Read first:** Assessment essay/manual-scoring contract and common Item envelope.
- **Change surface:** essay schema/editor/authoring/player/manual-review fixtures and tests.
- **Implement:** content limits, autosave-safe response contract, accessible editor, immutable rubric and no automatic semantic scoring.
- **Prove:** long/empty/unsafe content, reconnect/revision, rubric version drift, keyboard/screen-reader use and response round trip.
- **Stop/hand off:** no AI essay score, surveillance or hidden authorship inference.
- **Unlocks:** `P4-T12A` and `P4-T23` only after the complete response-contract set named by those cards is `MERGED`.

## P4-T22G — Implement hotspot Items

- **Outcome:** Author, publish, render, save and deterministically score declared hotspot regions against one immutable referenced image.
- **Depends on:** `P4-T22` `MERGED`.
- **Read first:** Assessment hotspot geometry contract and common Item envelope.
- **Change surface:** hotspot schema/geometry/authoring/player/scorer fixtures and tests.
- **Implement:** normalized coordinates, exact image/version/dimensions, bounded regions, keyboard alternative and deterministic containment/overlap rule.
- **Prove:** scale/rotation/boundary/overlap, stale image, malformed geometry, touch/keyboard/screen-reader alternative and response round trip.
- **Stop/hand off:** hotspot is not the native WSI contract and cannot reference mutable pixels.
- **Unlocks:** `P4-T12A` and `P4-T23` only after the complete response-contract set named by those cards is `MERGED`.

## P4-T22H — Implement shared-stimulus Items

- **Outcome:** Author, publish and render immutable shared stimuli referenced by bounded child Items without copying or mutating child scoring authority.
- **Depends on:** `P4-T22` and `P4-T22A`–`P4-T22G` `MERGED`.
- **Read first:** Assessment shared-stimulus composition contract and common Item envelope.
- **Change surface:** stimulus schema/composition/authoring/player fixtures and tests.
- **Implement:** immutable stimulus/child ordering and hashes, safe resources, accessible navigation/context and independent child responses.
- **Prove:** missing/duplicate/cyclic/stale child, changed stimulus, partial load, keyboard/screen-reader flow and complete response round trip.
- **Stop/hand off:** no mutable shared content or implicit cross-item scoring.
- **Unlocks:** `P4-T12A` and `P4-T23` only after the complete response-contract set named by those cards is `MERGED`.

## P4-T22I — Implement native WSI point and region Items

- **Outcome:** Author, publish, render and save calibrated point/region responses against an exact authorized immutable DZI/Source Asset version.
- **Depends on:** current `P3-T18=SUCCESS`; `P4-T22` `MERGED`.
- **Read first:** Assessment native WSI contract, Imaging calibration/DZI contracts and common Item envelope.
- **Change surface:** WSI response schema/geometry/authoring/player/manual-or-deterministic scorer fixtures and tests.
- **Implement:** source/DZI/calibration/version hashes, normalized point/polygon geometry, bounded vertices, accessible non-pointer path and no raw tile authority.
- **Prove:** stale/missing calibration or DZI, zoom/rotation/boundary/malformed geometry, large polygon, keyboard alternative and response round trip.
- **Stop/hand off:** no QTI flattening, dynamic decode fallback or mutable annotation substitution.
- **Unlocks:** `P4-T12A` and `P4-T23` only after the complete response-contract set named by those cards is `MERGED`.

## P4-T23 — Schedule immutable Exam Sessions

- **Outcome:** Exam Sessions freeze items/scoring, roster, content, accommodations, deterministic random seed/order and trusted server deadlines.
- **Depends on:** `P4-T04` and every `P4-T22A`–`P4-T22I` contract `MERGED`.
- **Read first:** Assessment context and Golden Journey G20–G22.
- **Change surface:** Assessment scheduling service/admin UI/snapshot contracts and tests.
- **Implement:** freeze exact item/scoring/roster/content/accommodation versions, trusted deadlines, deterministic seed/order and immutable Exam Session identity before admission.
- **Prove:** changed roster/item/scoring, wrong learner, concurrent scheduling, seed reproduction, privacy/accommodation and clock rollback.
- **Stop/hand off:** client time or mutable live content cannot define the exam.
- **Unlocks:** `P4-T24`, `P4-T25`.

## P4-T24 — Ratify the Provisional Journal cryptographic contract

- **Outcome:** Research and accept a narrow ADR for browser journal encryption, key derivation/storage, device binding, lease/deadline sealing, loss/recovery, migration, privacy and deletion without claiming local authority.
- **Depends on:** `P1-T11A`, `P2-T06`, `P4-T21`, and `P4-T23` `MERGED`.
- **Read first:** Assessment context, ADR 0064, supported-client/offline threat model and browser platform constraints.
- **Change surface:** ADR/design/test-vector specification only.
- **Implement:** none; ratify the exact journal envelope, key lifecycle, device/lease binding, migration and loss/recovery semantics through a reviewed ADR and executable vectors.
- **Prove:** threat review covers stolen storage/session, offline reload, clock rollback, device transfer, key rotation/loss, browser eviction and zero-server-acceptance ambiguity.
- **Stop/hand off:** implementation cannot begin while the key boundary is ambiguous; do not turn local journal possession into submission evidence.
- **Unlocks:** `P4-T25`.

## P4-T25 — Implement Attempt Leases, transfer, and Provisional Journal

- **Outcome:** One device holds a renewable five-minute/<=30-minute Attempt Lease; one staff-authorized transfer changes device binding; disconnected revisions stay encrypted/provisional and seal at earlier deadline/lease expiry.
- **Depends on:** `P4-T23`, `P4-T24` `MERGED`.
- **Read first:** accepted journal ADR, Assessment context, Role Matrix device transfer.
- **Change surface:** Assessment attempt/lease service, browser journal/crypto/player, transfer UI and tests.
- **Implement:** enforce one-device leases and audited transfer, encrypt provisional revisions under the ratified contract, acknowledge owner-accepted revisions idempotently and preserve truthful offline/deadline states.
- **Prove:** stolen/replayed/expired lease, clock rollback, two devices, one-use transfer, offline reload, key loss/rotation, eviction and server-time reconciliation.
- **Stop/hand off:** local or Sealed Journal never means submitted.
- **Unlocks:** `P4-T26`.

## P4-T26 — Reconcile Response Revisions and seal submissions

- **Outcome:** Monotonic revisions replay idempotently; only durable server acceptance under the exact attempt/deadline creates an immutable Submission Receipt.
- **Depends on:** `P4-T25` `MERGED`.
- **Read first:** Assessment context and Receipt Registry Assessment section.
- **Change surface:** revision/submission/reconciliation service and player sync/UI/tests.
- **Implement:** reconcile provisional and confirmed revisions by immutable predecessor/hash, seal against trusted deadlines and create one Submission Receipt only from owner-accepted state.
- **Prove:** revisions >=30-second frequency, 10% disconnect, restart after confirmed revision, duplicate/reorder/conflict, late work, final-minute burst and zero accepted-data loss.
- **Stop/hand off:** UI confirmation, local hash or Sealed Journal cannot substitute for Submission Receipt.
- **Unlocks:** `P4-T27`.

## P4-T27 — Implement deterministic/manual scoring and governed Grades

- **Outcome:** Immutable Scoring Versions drive deterministic/manual evaluation; ordinary Grades and high-stakes Assessor-to-independent-Moderator outcomes preserve source evidence and history.
- **Depends on:** `P2-T05`, `P4-T26` `MERGED`.
- **Read first:** Assessment context, Role Matrix grade pairs, Receipt Registry.
- **Change surface:** scoring/grading/moderation service and staff UI/tests.
- **Implement:** version deterministic/manual scorers and rubrics, retain immutable evidence, enforce independent high-stakes moderation and append corrected Grade versions without rewriting history.
- **Prove:** self/material-contributor moderation, stale step-up, changed scoring/submission, restart/replay, manual essay/region review and no surveillance/AI path.
- **Stop/hand off:** no AI grading, webcam, screen recording or hidden proctoring data.
- **Unlocks:** `P4-T06A`, `P4-T28`, Phase 5 AGS/Credential.

## P4-T28 — Implement Appeals, reports, retention, and accessible assessment UI

- **Outcome:** Learners receive purpose-minimized results/reports, may open a 30-day Appeal, and every item/attempt/revision/submission/grade/report path implements retention, deletion, restore and accessible error/recovery states.
- **Depends on:** `P4-T27`, `P4-T00`, `P2-T14` `MERGED`.
- **Read first:** Assessment context retention, Governed Product Workflows and route IA.
- **Change surface:** appeal/report services/pages/notices, deletion adapter and e2e/a11y tests.
- **Implement:** issue minimized reports, accept immutable-evidence Appeals within 30 days, apply owner retention/hold/deletion/restore rules and expose accessible recovery/error states.
- **Prove:** deadline, wrong learner/Institution, immutable original evidence, held/deleted/restored state, current client matrix and WCAG 2.2 AA.
- **Stop/hand off:** Appeal never reopens or mutates Submission Receipt/scoring evidence.
- **Unlocks:** `P4-T29`.

## P4-T29 — Freeze and dry-run the Assessment engineering campaign

- **Outcome:** Freeze the exact 300-learner x 100-item x 120-minute manifest, all nine contract fixtures, thresholds/fault schedule/observers and execute a reduced non-qualifying end-to-end dry run.
- **Depends on:** `P4-T21`–`P4-T28` `MERGED`.
- **External prerequisites:** label=EP-P4-ASSESS-CORPUS; kind=DATA_OR_CORPUS; requires=AVAILABLE; accountable=Assessment qualification lead; validity=exact 300-learner 100-item nine-contract corpus and actor hashes remain unchanged through P4-T29C; evidence=SignedAssessmentCorpusAdmissionReceipt.
- **Read first:** Production Qualification Assessment gate.
- **Change surface:** load/browser/evidence harness, immutable manifest and dry-run evidence only; fixes become separate implementation tasks.
- **Implement:** encode the exact workload, clients, actors, thresholds, observers, fault schedule, receipt cursors and cleanup, then execute only a reduced non-qualifying rehearsal.
- **Prove:** every actor/item/contract/observer/fault/cleanup resolves; inject representative disconnect/restart/device-transfer/final-minute work and reconcile dry-run receipts.
- **Stop/hand off:** dry-run success is not the engineering campaign result; unresolved harness/fixture ambiguity blocks launch.
- **Unlocks:** `P4-T29A`.

## P4-T29A — Start the full Assessment engineering campaign

- **Outcome:** Admit the frozen exact phase candidate and begin the full 300 x 100 x 120-minute run with immutable start time, process identities and receipt cursor.
- **Depends on:** current `P4-T29=SUCCESS` with unchanged frozen candidate/manifest and `EP-P4-ASSESS-CORPUS` receipt heads.
- **External prerequisites:** label=EP-P4-ASSESS-CAPACITY; kind=HARDWARE; requires=AVAILABLE; accountable=Assessment qualification lead; validity=declared clients and load resources remain available and unchanged through P4-T29C; evidence=SignedAssessmentCapacityAdmissionReceipt | label=EP-P4-ASSESS-OPERATORS; kind=HUMAN_AUTHORITY; requires=ASSIGNED; accountable=Assessment qualification lead; validity=named operators remain assigned through P4-T29C; evidence=SignedAssessmentOperatorAssignmentReceipt.
- **Read first:** frozen Assessment campaign manifest and launch runbook.
- **Change surface:** campaign start/admission evidence only.
- **Implement:** none; admit and start the immutable campaign tuple, observers and receipt cursor without product or manifest changes.
- **Prove:** exact tuple/manifest equality, all workers/observers live, participant/item counts admitted and receipt progression begins.
- **Stop/hand off:** missing capacity/client/operator, drift or incomplete admission is `NOT_EVALUABLE`; launch is `RUNNING`, never `SUCCESS`.
- **Unlocks:** `P4-T29B`.

## P4-T29B — Monitor the active Assessment engineering campaign

- **Outcome:** Observe the full interval through receipt cursors without retaining implementation context, execute scheduled disconnect/restart/device-transfer/final-minute cases and record incidents.
- **Depends on:** active `P4-T29A` with matching immutable manifest.
- **Read first:** latest cursor, campaign manifest, fault schedule and only open incidents.
- **Change surface:** campaign observations/fault evidence and incident records only.
- **Implement:** none; observe receipt/resource progress and execute only the frozen disconnect, restart, transfer and final-minute fault schedule.
- **Prove:** live worker/resource/receipt progress, no silent gap/drift, 10% disconnect and every scheduled fault at its declared boundary.
- **Stop/hand off:** stopped/wedged worker, missing interval or changed input follows the frozen failure/invalidation rule; do not restart history silently.
- **Unlocks:** `P4-T29C` after the full elapsed interval and workload complete.

## P4-T29C — Close the Assessment engineering campaign

- **Outcome:** Reconcile the complete 300 x 100 x 120-minute run, all nine contracts, revisions, disconnect/restart/device transfer/final-60-second submissions, scoring/moderation/appeal and cleanup into one terminal result.
- **Depends on:** completed `P4-T29A`/`P4-T29B` and unchanged manifest/candidate.
- **Read first:** frozen manifest, terminal receipt range and Production Qualification Assessment gate.
- **Change surface:** signed evidence aggregation and cleanup only.
- **Implement:** none; reconcile the immutable receipt range, workload, thresholds, faults, scoring/appeal evidence and cleanup into one terminal result.
- **Prove:** exact elapsed time/workload, frozen save/submission/resource thresholds, zero accepted-data loss/duplicate receipt, complete audit/grade reconciliation and cleanup.
- **Stop/hand off:** smaller/shorter/incomplete run is `PARTIAL`; missing trustworthy evidence is `NOT_EVALUABLE`; do not tune the gate.
- **Unlocks:** `P4-T30` and Phase 7 exact rerun only on `SUCCESS`.

## P4-T30 — Close the complete learning vertical slice

- **Outcome:** Run Catalog publication -> Teacher proposal -> roster -> Imaging reference -> Live/media -> durable progress/completion -> Assessment/grade -> eligibility proposal with ordered owner events, receipts, restart/failure and deletion behavior.
- **Depends on:** `P4-T07`, `P4-T06A` `MERGED`; current terminal `SUCCESS` from `P3-T18`, `P4-T13`, `P4-T20B`, and `P4-T29C` on the identical phase candidate.
- **Read first:** Golden Journey G07–G24, all Phase 4 contexts and Delivery State Ledger.
- **Change surface:** cross-context contract/e2e/evidence package only.
- **Implement:** none; execute the owner-ordered vertical-slice manifest and reconcile immutable events, receipts, faults, deletion and cleanup into one terminal `P4-T30` result.
- **Prove:** exact hashes/snapshots, no cross-context SQL/duplicate authority, outbox replay, role/purpose/retention/deletion/a11y and explicit exclusions.
- **Stop/hand off:** Credential issuance and external standards remain Phase 5; phase result is not final qualification.
- **Unlocks:** Phase 5 standards, Credential, EQA and specialist workflows.
