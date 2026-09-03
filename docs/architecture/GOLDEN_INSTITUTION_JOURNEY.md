# Golden Institution Journey

This is the normative exact-order Full-Surface v1 cross-context campaign. It proves that one immutable candidate can move governed truth through every ratified authority without an isolated feature success concealing a broken handoff. It supplements, and never replaces, each context's capacity, conformance, privacy, recovery and security gate.

The journey may run only after every prerequisite technical and bounded-context gate has current `SUCCESS` evidence for the same release, profile, host, backup target, client matrix and standards corpus. Its own Golden Institution journey gate and the later release/pilot-readiness gate are explicitly excluded from that prerequisite set. The frozen dependency order is: prerequisite gates -> Golden Institution Journey -> supervised limited pilot -> aggregate Qualification Claim -> separate activation. Journey success is qualification evidence only; it does not merge, deploy, pilot, qualify or activate a release.

## Immutable run manifest

Before step `G00`, an Operator renders and signs one `golden-journey-manifest` containing no placeholder or mutable tag. The signed manifest binds:

- release commit and artifact digests, migrations, SBOMs, configuration and Offline Release Kit identity;
- Zero-Cash Production Profile, production host, independent Backup Target, Edge Release Bundles, client matrix and declared resource envelopes;
- Institution, actor, Role Binding, authenticator and Purpose Identity fixture identities below;
- exact LTI, OneRoster, QTI, CASE, Open Badges, CLR and Caliper profiles and corpus hashes;
- Course, Achievement Definition, WSI, annotation, Assessment, EQA, clinical, Research, Edge and portability fixture hashes;
- every Mode Reservation identity and planned start/stop boundary;
- every fault identity, injection trigger, maximum duration and recovery condition;
- trusted-time source, random seed, idempotency keys, expected receipt types and cleanup obligations; and
- the prior successful evidence head for every prerequisite gate.

Changing any bound value creates a new journey run. A retry may reuse a step idempotency key only for the same immutable command hash. Each successful step records the predecessor receipt hash, so omitted, reordered or combined steps fail verification.

## Fixed actors

Every human label below resolves to a different canonical Principal and a different person. No service identity or second Purpose Identity substitutes for a human.

| Actor | Role Binding or status | Journey duty |
| --- | --- | --- |
| `OWN-1` | Owner | Accepts policy and, outside this journey, may approve later activation. |
| `ADM-1` | Administrator | Creates memberships, registrations, Edge enrollment and portability actions. |
| `INS-1` | Instructor | Publishes ordinary learning, teaches the Class Session and initiates the course-completion credential outcome. |
| `TA-1` | Teaching Assistant | Contributes a draft and facilitates the Class Session without publication or grading authority. |
| `ASSR-1` | Assessor | Publishes assessment material, authorizes an Attempt transfer, grades and initiates assessment outcomes. |
| `MOD-1` | Moderator | Independently moderates the high-stakes Grade and credential outcomes. |
| `RES-1` | Researcher | Runs the signed Research Job and proposes its private artifact. |
| `EQA-1` | EQA Manager and named EQA Submitter | Collaborates on and irreversibly seals the EQA submission. |
| `EQA-2` | EQA Manager | Collaborates on the EQA draft but cannot alter it after `EQA-1` seals. |
| `CPS-1` | Clinical Privacy Steward | Reviews quarantine and initiates clinical admission. |
| `WSI-1` | WSI Reviewer | Independently approves clinical admission and initiates anonymous Public Release. |
| `PUB-1` | Publication Officer | Independently approves anonymous Public Release. |
| `AUD-1` | Auditor | Verifies receipts and invariants; performs no mutation or fault injection. |
| `OP-1` | Operator | Installs and operates modes, injects declared infrastructure faults and commands restore; cannot approve product truth. |
| `KEY-1`, `KEY-2` | Different Key Custodians | Perform the two-person root-recovery exercise using different current shares. |
| `LRN-A` | Adult learner with Membership and Purpose Identity | Completes the learning, Class Session and Assessment paths. |
| `LRN-M` | Minor learner with Membership, Purpose Identity and current Processing Grant | Proves the guardian-rule and minimum age-band boundary. |
| `GST-1` | Pseudonymous guest, no Membership | Joins only the non-credit Class Session and must leave no durable learner evidence. |
| `LMS-1` | Independent external implementation | Supplies LTI/OneRoster/QTI/CASE inputs and receives grade/credential-related exchanges. |
| `EQA-EXT-01..10` | Synthetic external EQA Participants | Prove own-report isolation and both sides of the aggregate suppression threshold. |

## Fixed fixtures

| Fixture | Required content and boundary |
| --- | --- |
| `INST-J1` | A new empty Institution with current Residency Policy, Retention Schedule, guardian rule, approved locations and zero pre-existing authoritative product records. |
| `REG-LMS-1` | One inactive External Registration with exact learning profiles, initial adapter key and an intentionally ambiguous external subject fixture. |
| `COURSE-1/V1` | One Course Version containing two Modules and three Lessons, one WSI reference, one Class Session definition and deterministic activity ordering. |
| `ACH-1/V1` | One approved Achievement Definition Version binding `COURSE-1/V1`, its deterministic Completion Evidence rule, permitted Assessment evidence, issuer, validity and minimum Credential Evidence Snapshot. |
| `WSI-GOOD-1` | Synthetic or already-deidentified admitted-format WSI with known byte hash, dimensions and expected DZI manifest. |
| `WSI-BAD-1` | Unsupported/decompression-bomb/traversal variants and metadata/OCR/pixel PHI canaries that must never become authoritative or public. |
| `ANN-1` | One Private Annotation Draft with point, region and text content and a declared Learning audience. |
| `ASSESS-1/V1` | At least one immutable Item Version for each of the nine approved response contracts, fixed random seed, accommodations for `LRN-M`, deterministic scoring and one manual essay. |
| `EQA-ROUND-1` | One Case Version using admitted assets, ten EQA Participants, deterministic Scoring Version, report policy and 30-day appeal window. |
| `CLIN-1` | Synthetic or already-deidentified FHIR Bundle plus DICOM/WSI/ANN package with expected QIDO/WADO and OME-Zarr identities and zero writeback endpoint. |
| `RESEARCH-1` | Read-only Dataset Snapshot, signed offline Python Environment Manifest and deterministic expected output hash. |
| `EDGE-1` | Current-version Edge Node with a pending Local Acquisition and separate Edge Recovery Copy. |
| `EDGE-2` | N-minus-two Edge Node with seven-day leases/backlog, a conflicting proposal and a replayed batch fixture. |
| `PORT-1` | Portable Institution Package destination fixtures: one empty supported target and one populated target that must reject import. |

Fixture generation records source rights, synthetic/deidentified status and exact hashes. No production PHI, private learner answers, real Adapter Credentials, Authentication Credentials, Service Credentials or secret key material enters the evidence package.

## Reservation sequence

Resident services and synchronous WAL protection remain active throughout. Heavy reservations occur only in this order:

| Reservation | Steps | Active mode processes |
| --- | --- | --- |
| `MR-01-INTEGRATION-IN` | `G05-G06` | `pathlab-batch` in learning-import mode |
| `MR-02-IMAGING` | `G09-G13` | `pathlab-batch` in imaging mode plus admitted upload/format tools |
| `MR-03-LIVE` | `G15-G18` | `pathlab-live`; Galene only during `G17` |
| `MR-04-ASSESSMENT` | `G20-G22` | `pathlab-assessment` |
| `MR-05-INTEGRATION-OUT` | `G23` | `pathlab-batch` in exchange-delivery mode |
| `MR-06-CREDENTIAL` | `G24-G25` | `pathlab-batch` in credential/export mode |
| `MR-07-EQA` | `G26-G27` | `pathlab-batch` in EQA mode |
| `MR-08-CLINICAL` | `G28-G29` | `pathlab-batch` in clinical-exchange mode |
| `MR-09-RESEARCH` | `G30` | `pathlab-research-runner` |
| `MR-10-EDGE` | `G31-G32` | `pathlab-batch` in bulk-Edge-sync mode |
| `MR-11-PORTABILITY` | `G33` | `pathlab-batch` in portability mode |
| `MR-12-RECOVERY` | `G37` | isolated restore controller on the replacement host; no production-mode writer |

Each reservation requires a signed READY Mode Readiness Receipt and a terminal drained receipt proving its process count returned to zero. Starting another heavy reservation while one is active is fault `F-MODE-01` and must be rejected without interrupting learner-facing work.

## Exact step and receipt chain

No step starts until `AUD-1` verifies the predecessor receipt hash and all named preconditions. “Receipt” below means an authoritative domain receipt or signed invariant result registered in the [Receipt Schema Registry](./RECEIPT_SCHEMA_REGISTRY.md), never a log line or screen message.

| Step | Actors and exact action | Required receipt or authority transition | Mandatory assertion and scheduled fault |
| --- | --- | --- | --- |
| `G00` | `OP-1` presents the immutable run manifest; `AUD-1` verifies every prerequisite evidence head. | `JourneyAdmissionReceipt(READY)` | Any stale, mismatched or missing gate produces `NOT_EVALUABLE`; no later step runs. |
| `G01` | `OP-1` performs a clean no-network install of the exact Offline Release Kit on the declared host and unlocks the declared Credential Bundles. | `InstallReceipt`, release/configuration hashes and healthy synchronous-WAL receipt | Mutable `latest`, undeclared egress, wrong host or wrong key fails admission. |
| `G02` | On the empty deployment, `OP-1` presents the bootstrap manifest, `KEY-1` and `KEY-2` act only as its named install-time Root Recovery Share Custodians, and `OWN-1` enrolls local WebAuthn; `svc-platform` creates `INST-J1` and its first Owner. `OWN-1` then creates `ADM-1`, and `ADM-1` creates the remaining fixed Memberships and Role Bindings, including current Key Custodian bindings for `KEY-1` and `KEY-2`. | `BootstrapReceipt`, Institution, Membership and Role Binding source events plus audit projections | A second bootstrap, remote bootstrap, cross-Institution identifier, missing person and last-Owner removal attack fail closed. `AUD-1` cannot receive a mutating capability. |
| `G03` | Now acting through current Key Custodian Role Bindings, `KEY-1` and `KEY-2` execute the Role Matrix root-recovery pair while `OP-1` commands recovery. | Dual `ApprovalReceipt` and `RootRecoveryReceipt` | `F-KEY-01`: wrong share then one expired step-up are rejected; the valid AB pair succeeds without exposing root material. |
| `G04` | `ADM-1` configures Residency/Retention policy, guardian rule and the Processing Grant for `LRN-M`; `OWN-1` approves the policy; learner Purpose Identities are created for `LRN-A` and `LRN-M`. | Policy approval receipts, Processing Grant and opaque Purpose Identity references | No date of birth is stored; withdrawal and expired-grant fixtures deny durable learner evidence. |
| `G05` | `ADM-1` activates `REG-LMS-1` after official/reference and independent evidence; `LMS-1` performs an LTI launch. | Registration Activation and Exchange Receipts; External Subject Mapping for the valid tuple | `deployment_id` authorizes the launch but is absent from canonical identity; email changes do not remap the Principal. |
| `G06` | `LMS-1` sends the ambiguous subject, OneRoster roster, QTI items and CASE framework; owning contexts explicitly accept only valid proposals. | Quarantined Exchange for ambiguity; accepted Exchange Receipts; Course/Enrollment/Item/CASE references and original hashes | `F-INT-01`: duplicate/reordered payload and conflicting email remain quarantined; no write/delete call is made to OneRoster. `MR-01` drains. |
| `G07` | `INS-1` publishes `COURSE-1/V1` and initiates `ACH-1/V1`; independent `MOD-1` approves the exact Achievement Definition Version. | Course Version, Lesson versions, Published Learning Provenance, dual Approval Receipt and Achievement Definition Version | Legacy Study owns no parallel Course, roster, Learner Progress Evidence or completion flag; the credential-bearing criteria cannot be self-approved. |
| `G08` | `TA-1` contributes an Authoring Draft; the admitted local model produces a Generation Record; `INS-1` reviews it and publishes a new Lesson version. | Draft, Generation Record, Teacher-Approved Draft and Catalog publication receipts | Model output cannot publish directly; a changed Draft invalidates approval; rejected content starts the exact disposition-based retention clocks. |
| `G09` | Under `MR-02`, `INS-1` uploads `WSI-GOOD-1`; validators compute the source manifest. | Upload/chunk receipts and validated `PENDING_PROTECTION` object state | `F-NET-01`: disconnect at 37 percent and process restart resume by content offset/hash with no duplicate authority. |
| `G10` | `OP-1` withdraws the Backup Target before the authority transition, then restores it after the expected failure. | Failed protection attempt followed by valid off-host Protection Receipt | `F-BACKUP-01`: the asset remains unavailable and `PENDING_PROTECTION`; no asynchronous or local-only fallback is permitted. |
| `G11` | Imaging Control accepts the protected source and produces the immutable static DZI Browser Representation. | Asset Admission Receipt, source/derivative manifests and DZI publication authorization | Counts, dimensions and hashes equal the fixture; no format tool becomes authority. |
| `G12` | `INS-1` and `WSI-1` review `ANN-1` for the Learning audience. | Immutable restricted Annotation Layer Version | Anonymous annotation publication is rejected; private draft identifiers remain traceable without copying mutable data. |
| `G13` | `WSI-1` initiates and `PUB-1` approves the exact anonymous Public Release; an unreconciled legacy share and `WSI-BAD-1` are submitted adversarially. | Dual Approval Receipt, Public Release and Collection Manifest; rejection/quarantine receipts for invalid inputs | `F-INPUT-01`: traversal/bomb and PHI canaries never become public; legacy identifiers alone confer no approval. `MR-02` drains. |
| `G14` | `ADM-1` creates the Cohort and Enrollments and captures the exact Roster Snapshot for learning and Assessment. | Enrollment events and Roster Snapshot hash | `GST-1` is absent; withdrawn and wrong-Institution learners are denied. Retention triggers are not yet reached. |
| `G15` | Under `MR-03`, `INS-1` starts one Class Session from the immutable Course, asset and Roster Snapshots; `LRN-A`, `LRN-M` and `GST-1` join under their permitted identities. | Mode Readiness and Class Session start receipts | Minor Processing Grant is current; guest joins only the non-credit path and obtains no Enrollment or Purpose Identity. |
| `G16` | Participants commit one prompt, poll, submitted question/response and selected workspace action; `LRN-A` keeps a notebook local, then explicitly submits one selection. | Durable Interaction receipts for committed items only | `F-LIVE-01`: restart after commit/before delivery reconstructs from outbox with one semantic result. Presence, pointer, viewport, control, pins, strokes and unsubmitted notebook content leave no durable history. |
| `G17` | Galene starts for one Teacher Broadcast; clients establish direct/TURN behavior; `OP-1` removes the media path. | Media authorization observations and Media Fallback receipt | `F-MEDIA-01`: zero recording/transcoding; slides/text and Durable Interactions continue. A concurrent batch-reservation request triggers `F-MODE-01` and is denied. |
| `G18` | `INS-1` closes the Class Session; validated participation produces Attendance Intervals for members only. | Session close, durable-interaction convergence and Attendance Interval receipts | Reconnect produces no gaps/duplicates. `GST-1` has no retained interaction, attendance claim or conversion path. `MR-03` drains. |
| `G19` | The deterministic learning service evaluates ordered activities for `LRN-A` and `LRN-M`, recording versioned progress and completion. | Learner Progress Evidence versions and immutable Completion Evidence bound to `COURSE-1/V1` | Same accepted inputs and rule version reproduce the same evidence; TRACE-SIM, adaptive sequencing and model inference are absent. |
| `G20` | Under `MR-04`, `ASSR-1` opens `ASSESS-1/V1`; learners receive deterministic randomization and accommodations and answer all nine response contracts. `ASSR-1` transfers `LRN-M` once to a replacement device. | Exam Session, Attempt Leases, one Attempt Device Transfer and ordered Response Revisions | `F-CLOCK-01`: client clock rollback cannot extend a lease/deadline; wrong device and second Attempt are denied. No surveillance capture exists. |
| `G21` | Both learners submit in the final 60 seconds; the Assessment process restarts after a confirmed revision and before sealing. | Submission Receipts and zero-loss reconciliation result | `F-ASSESS-01`: committed revisions survive; local journal alone never claims submission; deadline/lease sealing is server-authoritative. |
| `G22` | `ASSR-1` performs deterministic/manual grading; `ASSR-1` initiates and `MOD-1` independently approves the high-stakes outcome; `LRN-A` opens an Appeal. | Scoring Version result, Grade, dual Approval Receipt and Assessment Appeal | Moderator self-approval and stale step-up are rejected; original Submission Receipt/scoring evidence remains immutable. `MR-04` drains. |
| `G23` | Under `MR-05`, the owning Assessment event requests LTI grade return and Caliper delivery through Gateway. | Grade-return Exchange Receipt; Deferred Exchange then final Delivery Attempt receipt | `F-EXT-01`: `LMS-1` is unavailable for the first attempt; local Grade remains authoritative and Caliper/AGS outage cannot roll it back. Adapter key rotates before retry. `MR-05` drains. |
| `G24` | Under `MR-06`, Catalog evaluates `ACH-1/V1`; `INS-1` initiates the course-completion outcome and `MOD-1` approves. `ASSR-1` separately initiates the Assessment evidence path and `MOD-1` approves without reusing an approval. | Achievement Eligibility Proposal, minimum Credential Evidence Snapshots and two independent outcome Approval Receipts | Definition, subject, evidence and policy hashes are exact; changing any invalidates approval. Ledger independently records Issuance Decisions. |
| `G25` | Credential Ledger issues, verifies offline and exports bounded Open Badges/CLR representations. `ADM-1` then initiates an exact supersession and `MOD-1` independently approves it; Gateway transports only approved exchanges. | Achievement Credentials, supersession Approval Receipt, Credential Status transition, Custody/Exchange Receipts and privacy-minimized verification result | `F-CRED-01`: issuer/status key rotation, replay, self-approval and wrong audience are rejected; Adapter Credentials never enter Ledger. `MR-06` drains. |
| `G26` | Under `MR-07`, `EQA-1` and `EQA-2` collaborate on one participant draft; `EQA-1` alone performs the irreversible seal at the deadline. | Draft revision chain and Sealed Submission | `F-EQA-01`: restart 30 seconds before deadline and a post-seal edit attempt preserve one original sealed package. `MR-07` remains active. |
| `G27` | The named Scoring Version and human adjudication produce participant reports; aggregates for nine and ten contributors are evaluated; one Appeal is lodged. | Scoring/adjudication receipts, own EQA Reports, suppressed-nine result, released-ten aggregate and Appeal | No AI scoring or cross-participant report access. `MR-07` drains. |
| `G28` | Under `MR-08`, Gateway receives `CLIN-1` and the PHI canaries; Clinical Shadow validates the bounded bundle without source writeback. | Exchange Receipt, 24-hour quarantine clock and validation/rejection records | `F-CLIN-01`: metadata/OCR/pixel canaries remain quarantined or rejected; Gateway's 30-day clock cannot extend the clinical 24-hour ceiling. |
| `G29` | `CPS-1` initiates and independent `WSI-1` approves clinical admission; a separately authorized deidentified snapshot is offered to learning/research use. | Dual Approval Receipt, Shadow Case Bundle and purpose-bound deidentified snapshot receipt | Source UIDs/provenance obey the admitted profile, clinical source remains read-only and no diagnostic/patient-care claim is created. `MR-08` drains. |
| `G30` | Under `MR-09`, `RES-1` runs `RESEARCH-1` for the signed manifest and proposes the resulting private artifact to its owning context. | Research Job receipt, resource observations, reproducibility hash and private Research Artifact | `F-RESEARCH-01`: network, package-install, interactive-shell and production-credential attempts fail. Artifact is not activated, published or made clinical. `MR-09` drains and workspace cleanup is recorded. |
| `G31` | `EDGE-1` and `EDGE-2` remain disconnected for the declared seven days; `WSI-1`, under current Node and User Authorization Leases, captures Local Acquisitions, verifies Edge Recovery Copies and reads cached snapshots. | Local acquisition/recovery receipts, lease-expiry observations and queued Sync Batch roots | `F-EDGE-01`: identity administration, grading, Publication, EQA, Clinical and Research attempts fail offline; clock rollback and expired User Lease fail closed. |
| `G32` | Under `MR-10`, nodes reconnect; N-minus-two upcasting preserves originals, replay is rejected, conflict is resolved by the owning context and Imaging Control accepts the valid acquisition. | Exchange, Acceptance and Conflict Resolution Receipts; exact object hashes and node cleanup evidence | Revoked/wrong-Institution Node identity is rejected; Integration Gateway transports but does not accept domain truth. Recovery-copy expiry is scheduled only after final results. `MR-10` drains. |
| `G33` | Under `MR-11`, `ADM-1` exports `PORT-1`, imports into the empty N-minus-two target, round-trips it, then attempts the populated target. | Export/import manifests, owner/schema/hash/policy reconciliation and populated-target rejection | Mappings are disabled, integrations require re-registration, authenticators require re-enrollment, expired data is absent, Legal Hold authority is revalidated and stricter retention wins. No Authentication Credential, Adapter Credential, Service Credential, session, private key, recovery material or cache travels. `MR-11` drains. |
| `G34` | `ADM-1` initiates an expiring Legal Hold and a separate Deletion Saga; `OWN-1` independently approves each exact proposal. `ADM-1` also initiates the required Achievement Credential revocation and `MOD-1` independently approves it. | Legal Hold and deletion Approval Receipts, Legal Hold receipt, Deletion Saga identity with per-context obligation list, and pending credential-status Approval Receipt | Hold/deletion authority, scope and expiry are exact; self-approval is rejected; ordinary backup expiry is unchanged; and the external Public Release download warning is preserved. |
| `G35` | Every owning context removes records, derivatives, indexes, projections, exports and controlled caches and returns its receipt; Credential Ledger consumes the exact approved status proposal and revokes rather than falsely erasing the issued Achievement Credential. | Complete per-context Deletion Receipts, consumed credential-status Approval Receipt, Credential Status transition and Saga completion | `F-DELETE-01`: one context is unavailable on first pass, so Saga remains incomplete; retry completes without losing prior receipts. Guest absence and Edge/local cleanup are asserted. |
| `G36` | The Legal Hold expires under trusted time; its package is deleted separately and all Q106 clocks and backup obligations are checked against their original triggers. | Hold Deletion Receipt and retention-trigger invariant report | No retry, restore, export, appeal or quarantine transition restarted a retention clock. Backup generations continue their independent expiry. |
| `G37` | Under `MR-12`, `OP-1` uses the actual encrypted Backup Generation, Offline Release Kit and `KEY-1`/`KEY-2` quorum on an isolated empty replacement host. | Restore Receipt covering PostgreSQL timelines/LSNs, objects, manifests, keys, outboxes, audit chains and expected deletion state | `F-RESTORE-01`: the production host and its online Service Credentials are unavailable. Latest/five-minute/random targets reconcile; deleted live data is not resurrected beyond declared backup obligations. |
| `G38` | `AUD-1` reconciles every receipt chain, source/event count, authority transition, resource series, fault result and cleanup obligation; `OP-1` removes the isolated restore workspace under policy. | `GoldenJourneyResult` and restore-workspace Deletion Receipt | Any gap, stale evidence, unexplained retry, surviving temporary data, running mode process or altered fixture yields `NEGATIVE` or `NOT_EVALUABLE`, never partial success promoted to pass. |

## Fault schedule invariants

Fault injection is performed only by `OP-1` at the step and boundary named above. Each fault has a pre-recorded start condition, maximum duration, expected fail-closed state and recovery command. `AUD-1` verifies it independently. Undeclared chaos, a changed threshold after observation, or a fault that prevents trustworthy evidence makes the run `NOT_EVALUABLE`.

The run must demonstrate all of these classes at least once in their named step: dependency loss, network interruption, process restart, malicious/unsupported input, clock rollback, key failure and rotation, storage/protection loss, incompatible Mode Reservation, replay/reorder, privilege misuse, deletion dependency loss and production-host loss. Fault recovery never permits asynchronous WAL fallback, local-only object authority, external-system authority, surveillance, AI grading, clinical writeback, or an offline Edge capability expansion.

## Cleanup manifest

`G38` cannot succeed until the signed cleanup report proves:

- all heavy Mode Processes drained to zero and every Mode Reservation closed;
- quarantine, upload fragments, temporary conversion data, provisional journals, Research workspace, restore workspace and evidence staging were removed under their clocks;
- `GST-1` has no Membership, Purpose Identity, Enrollment, Attendance Interval, Attempt, Grade, retained Durable Interaction or credential subject;
- both Edge nodes removed accepted/rejected pending authority, expired caches and eligible Edge Recovery Copies, or recorded a still-open bounded obligation;
- the empty portability target and rejected populated-target staging area were removed without changing the populated Institution;
- every controlled export, projection, derivative and index returned a Deletion Receipt or an explicit still-open backup-expiry obligation;
- the issued Achievement Credential is truthfully revoked/superseded while externally held copies remain outside PathLab's erasure claim;
- the Public Release origin state and irreversible external-download warning are preserved without claiming recall;
- the Legal Hold package was deleted after its independent expiry and ordinary backup rotation was never extended; and
- the actual Backup Generation and disconnected recovery material remain only for their declared unexpired recovery window, with no restored workspace left online.

## Terminal result and handoff

`GoldenJourneyResult=SUCCESS` requires every step, expected negative case, fault recovery, receipt hash and cleanup assertion to pass on the exact bound candidate. `PARTIAL`, `NEGATIVE` and `NOT_EVALUABLE` retain their ordinary meanings and block Full-Surface qualification.

A successful result is handed to the supervised limited pilot as evidence. Only after the pilot and final claim review may `OP-1` initiate and `OWN-1` independently approve a separate Activation Receipt under the Role and Approval Matrix. Neither this document, its manifest, a successful run nor an Auditor signature authorizes activation by itself.
