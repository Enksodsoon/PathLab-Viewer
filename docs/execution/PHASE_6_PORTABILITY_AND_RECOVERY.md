# Phase 6 — Portability and Complete Operations

Phase 6 makes every context portable, proves supported-version round trips, closes complete lifecycle/recovery behavior and operates the irreducible 90-day durability/zero-cash window. It never treats the separate 150-GB portability corpus as the live governed allowance of the 150-GB primary volume. All tasks inherit [README](./README.md).

## Portable Institution Package

## P6-T01 — Freeze the Portable Institution Package contract

- **Outcome:** Define versioned signed Institution-encrypted manifest/section/object schemas, canonical JSONL rules, identifiers, upcasters, content roots, resumability, empty-target admission, reconciliation and prohibited contents.
- **Depends on:** `P5-T40`, `P1-T02`, `P0-T10` `MERGED`.
- **Read first:** [Portability](../architecture/PORTABILITY.md), Final Endpoint compatibility section, Receipt Registry portability section.
- **Change surface:** `schemas/portability/`, evidence schemas/fixtures and contract tests.
- **Implement:** context-neutral section boundaries; credential custody artifacts; disabled mappings; re-registration/re-enrollment; stricter retention; Legal Hold revalidation; no secrets/caches/rebuildable derivatives.
- **Prove:** canonicalization/signature/encryption/version/size/path/bomb/collision fixtures and registry coverage.
- **Stop/hand off:** any section without one owner/schema or any credential/private-key ambiguity blocks adapters.
- **Unlocks:** `P6-T02`–`P6-T15`.

Every owner adapter below implements deterministic canonical export, import/upcast, object inventory, retention/Legal Hold handling, owner-command/outbox application and reconciliation. Direct foreign-table writes and database dumps are prohibited.

## P6-T02 — Implement the Platform Governance portability adapter

- **Outcome:** Export Institution profile, release history and historical qualification/activation provenance without transferring current deployment selection, activation authority or controller state.
- **Depends on:** `P6-T01`, `P2-T16A`, `P1-T23`, `P2-T18A`, `P2-T18B`, `P2-T18C` and `P5-T40` `MERGED`.
- **Read first:** Portability, Delivery State Ledger, Receipt Registry and activation-control contracts.
- **Change surface:** Platform Governance section schema, exporter/importer/upcaster, owner commands/outbox, fixtures and reconciliation tests.
- **Implement:** Preserve immutable historical receipt/fingerprint references and profile policy versions; import them as provenance only, with the target's deployment selection and activation controller initialized independently.
- **Prove:** N/N-1/N-2 reads, repeated-export equality, round trip, interruption/resume, missing/duplicate/malformed records, exact hashes and an adversarial package that attempts to select, activate or reactivate a release.
- **Stop/hand off:** Any imported value that can make a release current or active, any unknown owner, cross-context write or history/hash mismatch blocks merge.
- **Unlocks:** `P6-T16` only after this adapter and its evidence fixtures are `MERGED`.

## P6-T03 — Implement the Trust portability adapter

- **Outcome:** Export Principals, Memberships, Role Bindings, policies, grants and Purpose Identity references while excluding Authentication Credentials, sessions, recovery material and authenticators.
- **Depends on:** `P6-T01`, `P2-T16A` and `P2-T27` `MERGED`.
- **Read first:** Portability identity exclusions, Trust authority/credential custody and Institution isolation contracts.
- **Change surface:** Trust section schema, exporter/importer/upcaster, re-enrollment commands, fixtures and reconciliation tests.
- **Implement:** Recreate owner-held identity/authorization records through Trust commands with original policy/version/expiry provenance; require fresh credential/authenticator enrollment at the target.
- **Prove:** N/N-1/N-2 reads, deterministic export, round trip, restart/resume, expired/revoked grant, wrong-Institution reference, duplicate principal and prohibited secret/session/authenticator fixtures with exact record roots.
- **Stop/hand off:** Credential material, recovery authority, a live session, silently extended grant or cross-Institution authority in the package is `NEGATIVE` and blocks merge.
- **Unlocks:** `P6-T16` only after this adapter and its evidence fixtures are `MERGED`.

## P6-T04 — Implement the Learning Catalog portability adapter

- **Outcome:** Export Course Versions, Modules/Lessons, Cohorts/Enrollments, roster snapshots, durable progress/completion evidence and Achievement Definition Versions.
- **Depends on:** `P6-T01`, `P2-T16A` and `P4-T30` `MERGED`, with current `P4-T30=SUCCESS`.
- **Read first:** Portability, Catalog authority/versioning, roster snapshot and achievement eligibility contracts.
- **Change surface:** Catalog section schema, exporter/importer/upcaster, owner commands/outbox, object inventory, fixtures and reconciliation tests.
- **Implement:** Preserve immutable definition/roster/version references and durable learner evidence while applying target retention/Legal Hold rules through Catalog-owned commands.
- **Prove:** N/N-1/N-2 reads, repeated-export equality, full and empty Catalog round trips, interruption/resume, missing version, duplicate enrollment, stale roster, deletion/hold and exact record/object/root fixtures.
- **Stop/hand off:** Mutable reconstruction of an immutable snapshot, missing definition provenance, foreign-table write or completion/eligibility mismatch blocks merge.
- **Unlocks:** `P6-T16` only after this adapter and its evidence fixtures are `MERGED`.

## P6-T05 — Implement the Credential Ledger portability adapter

- **Outcome:** Export Credential Documents, evidence/definition snapshots, status/history and custody records without issuer/status private keys and without restarting validity.
- **Depends on:** `P6-T01`, `P2-T16A` and current terminal `P5-T15=SUCCESS` on the merged Phase 5 closure tuple.
- **Read first:** Portability credential custody, Credential Ledger validity/revocation and key-rotation contracts.
- **Change surface:** Credential section schema, exporter/importer/upcaster, custody commands, fixtures and reconciliation tests.
- **Implement:** Preserve original issue/not-before/expiry/status timestamps and immutable verification evidence; import target-verifiable custody/history while requiring separately admitted signing/status authority.
- **Prove:** N/N-1/N-2 reads, deterministic export, round trip, resume, expired/revoked/tampered document, missing definition, duplicate status, prohibited-key scans and exact document/evidence/status roots.
- **Stop/hand off:** Any issuer/status private key, extended/restarted validity, rewritten issued document or unverifiable custody transition is `NEGATIVE` and blocks merge.
- **Unlocks:** `P6-T16` only after this adapter and its evidence fixtures are `MERGED`.

## P6-T06 — Implement the Audit portability adapter

- **Outcome:** Export applicable signed checkpoints and verification provenance without making imported history replayable source truth or exposing protected raw evidence.
- **Depends on:** `P6-T01`, `P2-T16`, `P2-T16A`, `P2-T18A` and `P5-T40` `MERGED`.
- **Read first:** audit-chain, content-addressed evidence custody/sanitization, Delivery State Ledger and Portability contracts.
- **Change surface:** Audit section schema, exporter/importer/upcaster, provenance index, fixtures and verification/reconciliation tests.
- **Implement:** Carry signed checkpoint/content-root references and sanitized custody metadata as immutable historical provenance; establish a distinct target audit-chain origin for all import actions.
- **Prove:** N/N-1/N-2 verification, repeated-export equality, interruption/resume, tampered/missing/duplicate checkpoint, protected-field scan, target-origin separation and exact checkpoint/evidence roots.
- **Stop/hand off:** Raw protected evidence, signing/decryption secrets, imported mutable authority, unverifiable chain boundary or use of history as target source truth blocks merge.
- **Unlocks:** `P6-T16` only after this adapter and its evidence fixtures are `MERGED`.

## P6-T07 — Implement the Integration Gateway portability adapter

- **Outcome:** Export registration and mapping records in a disabled state, exclude Adapter Credentials and require destination re-registration before any outbound action.
- **Depends on:** `P6-T01`, `P2-T16A` and current terminal `P5-T09=SUCCESS` on the merged Phase 5 closure tuple.
- **Read first:** Portability disabled-mapping rule, Gateway authority and standards-adapter credential contracts.
- **Change surface:** Integration section schema, exporter/importer/upcaster, disabled-registration commands, fixtures and reconciliation tests.
- **Implement:** Preserve versioned mapping/provenance records and owner references, force every imported connector/mapping disabled, and expose explicit destination admission/re-registration work.
- **Prove:** N/N-1/N-2 reads, deterministic export, resume/round trip, wrong mapping, duplicate registration, credential/endpoint-secret scans and zero outbound traffic before fresh admission.
- **Stop/hand off:** An exported Adapter Credential, enabled connector/mapping, implicit endpoint trust, transport-owned truth or foreign-table write is `NEGATIVE` and blocks merge.
- **Unlocks:** `P6-T16` only after this adapter and its evidence fixtures are `MERGED`.

## P6-T08 — Implement the Imaging portability adapter

- **Outcome:** Export admitted originals/manifests, non-rebuildable annotations/artifacts and governed publication state while excluding caches and deterministic derivatives.
- **Depends on:** `P6-T01`, `P2-T16A` and `P3-T18` `MERGED`, with current `P3-T18=SUCCESS`.
- **Read first:** Portability object rules, Imaging object/annotation/publication authority and retention/deletion contracts.
- **Change surface:** Imaging section/object schemas, exporter/importer/upcaster, object staging/inventory, owner commands/outbox, fixtures and reconciliation tests.
- **Implement:** Preserve source/object/coordinate/publication provenance and exact content roots; regenerate only declared deterministic derivatives after target admission.
- **Prove:** N/N-1/N-2 reads, repeated byte/root identity, full round trip, interrupted object resume, missing/duplicate/corrupt/bomb/path object, private/public state, deletion/hold and exact pixel/annotation/object reconciliation.
- **Stop/hand off:** Missing lawful provenance, leaked restricted object, cache/derivative treated as authority, coordinate drift or object/hash mismatch blocks merge.
- **Unlocks:** `P6-T16` only after this adapter and its evidence fixtures are `MERGED`.

## P6-T09 — Implement the Live Learning portability adapter

- **Outcome:** Export Durable Interactions and Attendance with immutable snapshots while excluding presence, pointers/viewports, strokes, unsubmitted notebooks and all ephemeral session state.
- **Depends on:** `P6-T01` and `P2-T16A` `MERGED`, plus current exact-subject `P4-T20B=SUCCESS` and `P4-T30=SUCCESS` for the same Phase 4 closure tuple.
- **Read first:** Portability, Live durable-versus-ephemeral state, attendance authority and synchronized fallback contracts.
- **Change surface:** Live section schema, exporter/importer/upcaster, owner commands/outbox, fixtures and reconciliation tests.
- **Implement:** Preserve durable interaction/attendance event order, immutable snapshot references and accepted owner receipts; rebuild no transient collaboration state.
- **Prove:** N/N-1/N-2 reads, deterministic export, round trip/resume, reconnect/replay/order/duplicate cases, missing snapshot, deletion/retention and explicit absence of every ephemeral field.
- **Stop/hand off:** Presence or device-local/unsubmitted state in the package, reconstructed attendance, order loss, duplicate acceptance or cross-context write blocks merge.
- **Unlocks:** `P6-T16` only after this adapter and its evidence fixtures are `MERGED`.

## P6-T10 — Implement the Teacher Authoring portability adapter

- **Outcome:** Export retained drafts, Generation Records, approvals and provenance while excluding model caches, weights not licensed to travel and inference temporaries.
- **Depends on:** `P6-T01`, `P2-T16A` and `P4-T13` `MERGED`, with current `P4-T13=SUCCESS`.
- **Read first:** Portability, Teacher proposal/approval authority, model provenance/rights and retention contracts.
- **Change surface:** Teacher Authoring section schema, exporter/importer/upcaster, owner commands/outbox, fixtures and reconciliation tests.
- **Implement:** Preserve retained draft/revision/approval/source hashes and generation disclosures; force unavailable destination model assets into an explicit disabled/reacquisition state.
- **Prove:** N/N-1/N-2 reads, deterministic export, round trip/resume, missing source/model, rejected draft, duplicate approval, rights/secret/cache scans, deletion/hold and exact revision/provenance roots.
- **Stop/hand off:** Unlicensed asset transfer, model/API credential, cache/temp payload, approval mutation or silent model substitution blocks merge.
- **Unlocks:** `P6-T16` only after this adapter and its evidence fixtures are `MERGED`.

## P6-T11 — Implement the Assessment portability adapter

- **Outcome:** Export immutable items/sessions, accepted revisions/submissions, Grades and Appeals while excluding Provisional Journals and device-local state.
- **Depends on:** `P6-T01` and `P2-T16A` `MERGED`, plus current exact-subject `P4-T29C=SUCCESS` and `P4-T30=SUCCESS` for the same Phase 4 closure tuple.
- **Read first:** Portability, Assessment immutable session/submission, accepted-revision, grading and appeal contracts.
- **Change surface:** Assessment section schema, exporter/importer/upcaster, owner commands/outbox, fixtures and reconciliation tests.
- **Implement:** Preserve frozen item/session versions, accepted submission revision, grading basis and appeal history; never promote provisional/device-local records during import.
- **Prove:** N/N-1/N-2 reads, deterministic export, round trip/resume, late/duplicate/replayed revision, absent item version, grade/appeal history, prohibited provisional-state scans and exact receipt roots.
- **Stop/hand off:** Mutable item/session history, provisional journal treated as submission, grade recalculation, appeal loss or ownership/hash mismatch blocks merge.
- **Unlocks:** `P6-T16` only after this adapter and its evidence fixtures are `MERGED`.

## P6-T12 — Implement the Clinical Shadow portability adapter

- **Outcome:** Export only admitted deidentified, purpose-authorized and residency-compatible snapshots/provenance; exclude source credentials, writeback authority, PHI and expired/revoked cases.
- **Depends on:** `P6-T01`, `P2-T16A` and current terminal `P5-T26=SUCCESS` on the merged Phase 5 closure tuple.
- **Read first:** Portability Clinical exclusions, Purpose Grant, deidentification/residency, quarantine and no-writeback contracts.
- **Change surface:** Clinical section/object schemas, exporter/importer/upcaster, destination-admission commands, fixtures and reconciliation tests.
- **Implement:** Revalidate destination purpose/residency/retention before admission, retain immutable approvals/provenance, and quarantine rather than silently import any incompatible case.
- **Prove:** N/N-1/N-2 reads, deterministic export, round trip/resume, metadata/narrative/OCR/pixel PHI canaries, expired/revoked purpose, wrong residency, duplicate case and exact admitted/quarantined/object roots.
- **Stop/hand off:** PHI, source/writeback credential, expired authority, bypassed destination review, cross-residency admission or provenance/hash mismatch is `NEGATIVE` and blocks merge.
- **Unlocks:** `P6-T16` only after this adapter and its evidence fixtures are `MERGED`.

## P6-T13 — Implement the Research portability adapter

- **Outcome:** Export Projects, immutable Dataset/Environment manifests and admitted Artifacts while excluding active workspaces, credentials, processes and package caches.
- **Depends on:** `P6-T01` and `P2-T16A` `MERGED`, plus current terminal `P5-T30C=SUCCESS` on the merged Phase 5 closure tuple.
- **Read first:** Portability, Research snapshot/environment/artifact admission, isolation/egress and cleanup contracts.
- **Change surface:** Research section/object schemas, exporter/importer/upcaster, owner commands/outbox, fixtures and reconciliation tests.
- **Implement:** Preserve immutable dataset/environment/command/artifact hashes and signed review provenance; require destination reconstruction/admission instead of moving a live workspace.
- **Prove:** N/N-1/N-2 reads, deterministic export, round trip/resume, missing dataset/environment, corrupt artifact, credential/cache/process scans, retention/deletion and reproducible exact artifact roots.
- **Stop/hand off:** Workspace or credential leakage, mutable environment substitution, unsigned artifact admission, egress expansion or hash/reproduction mismatch blocks merge.
- **Unlocks:** `P6-T16` only after this adapter and its evidence fixtures are `MERGED`.

## P6-T14 — Implement the EQA portability adapter

- **Outcome:** Export Schemes/Rounds/Cases, sealed submissions, adjudication, reports and Appeals while preserving participant isolation and seal history.
- **Depends on:** `P6-T01` and `P2-T16A` `MERGED`, plus current terminal `P5-T20C=SUCCESS` on the merged Phase 5 closure tuple.
- **Read first:** Portability, EQA participant isolation, sealing/adjudication/report/appeal and retention contracts.
- **Change surface:** EQA section/object schemas, exporter/importer/upcaster, owner commands/outbox, fixtures and reconciliation tests.
- **Implement:** Preserve immutable round/case versions, sealed accepted submission roots, adjudication/report/appeal provenance and per-participant visibility through owner admission.
- **Prove:** N/N-1/N-2 reads, deterministic export, round trip/resume, final-minute/duplicate/replayed seal, cross-participant probes, missing case version, deletion/hold and exact submission/report roots.
- **Stop/hand off:** Broken participant isolation, unsealed mutation, recomputed authoritative score/report, appeal loss or ownership/hash mismatch blocks merge.
- **Unlocks:** `P6-T16` only after this adapter and its evidence fixtures are `MERGED`.

## P6-T15 — Implement the Edge Federation portability adapter

- **Outcome:** Export Platform-held enrollment, acceptance and conflict history while excluding node private keys, pending local authority, recovery secrets and caches; require re-enrollment wherever keys do not travel.
- **Depends on:** `P6-T01` and `P2-T16A` `MERGED`, plus current terminal `P5-T39E=SUCCESS` on the merged Phase 5 closure tuple.
- **Read first:** Portability, Edge lease/enrollment/acceptance/conflict, disconnected authority and key-custody contracts.
- **Change surface:** Edge section schema, exporter/importer/upcaster, re-enrollment/owner commands, fixtures and reconciliation tests.
- **Implement:** Preserve Platform-accepted event/object roots, owner decisions, lease/revocation/update history and conflict provenance; quarantine pending node-local work until a separately authorized reconnect.
- **Prove:** N/N-1/N-2 reads, deterministic export, round trip/resume, replay/order/conflict/revoked-node cases, node-key/recovery-secret/cache scans, deletion obligations and exact accepted-history roots.
- **Stop/hand off:** Node private/recovery key, pending local authority promoted as accepted, silent conflict overwrite, lease extension or history/hash mismatch is `NEGATIVE` and blocks merge.
- **Unlocks:** `P6-T16` only after this adapter and its evidence fixtures are `MERGED`.

## P6-T16 — Coordinate a consistent resumable export

- **Outcome:** Freeze one cross-context snapshot boundary, run owner exporters, stage within admitted capacity, reconcile counts/bytes/roots and sign/encrypt only the complete package.
- **Depends on:** `P6-T02`–`P6-T15` `MERGED`.
- **Read first:** Portability, owner adapter shared rules, Mode Reservation and storage admission contracts.
- **Change surface:** Platform batch portability mode, CLI/admin UI, storage accounting, manifests/tests.
- **Implement:** Add bounded exporter orchestration, resumable cursors, cross-owner inventory reconciliation, post-reconciliation signing/encryption and allowlisted abort cleanup without mutating source-domain authority.
- **Prove:** interrupted/repeated export, changing owner state, insufficient capacity, missing section/object, signature-before-complete attempt and deterministic root.
- **Stop/hand off:** stale/mixed snapshot or unknown size/headroom is `NO_GO`; no partial package is presented as export success.
- **Unlocks:** `P6-T17`.

## P6-T17 — Implement dry-run and atomic empty-target import

- **Outcome:** Verify/decrypt/upcast/reconcile without writes, then import only into a new/empty Institution through owner commands/outboxes with all-or-quarantined failure behavior.
- **Depends on:** `P6-T16` `MERGED`.
- **Read first:** Portability import gates, Trust/bootstrap rules.
- **Change surface:** Platform import coordinator, owner command clients, CLI/UI/tests.
- **Implement:** identity maps, stricter policy/retention, Legal Hold revalidation, mappings disabled, integration/authenticator re-admission and terminal Import Receipt.
- **Prove:** populated target, ID collision, partial owner outage, wrong key/signature/version, retry/restart and no half-authoritative target.
- **Stop/hand off:** v1 never merges into a populated Institution.
- **Unlocks:** `P6-T18`, `P6-T21`.

## P6-T18 — Prove N/N-1/N-2 round-trip compatibility

- **Outcome:** Export/import/round-trip complete representative packages across current and two prior contract versions while preserving originals and owner/schema/record/object/policy hashes.
- **Depends on:** `P6-T17` `MERGED`.
- **Read first:** compatibility/upcaster contract and Portability.
- **Change surface:** versioned fixtures, compatibility/reconciliation harness and evidence.
- **Implement:** none; execute the compatibility harness against N/N-1/N-2 fixtures, compare exact artifact sets and write signed evidence without product or schema mutation.
- **Prove:** all supported directions, unknown future/older version rejection, original payload/hash retention and no silent defaulting.
- **Stop/hand off:** reduce no compatibility window to make a test pass; unresolved ambiguity is `NEGATIVE`.
- **Unlocks:** `P6-T19`.

## P6-T19 — Generate the separate rights-cleared 150-GB corpus

- **Outcome:** Produce a deterministic non-PHI, non-secret, representative complete-context portability/restore-throughput corpus with immutable generator inputs and content/section roots.
- **Depends on:** `P0-T05` and `P6-T18` `MERGED`.
- **External prerequisites:** label=P6-EXT-150GB-STORAGE; kind=HARDWARE; requires=CAPACITY_QUALIFIED_AND_RESERVED; accountable=Institution Infrastructure Owner; validity=exact corpus manifest and campaign window; evidence=signed immutable Storage Capacity Reservation Receipt
- **Read first:** Production Qualification Portability/Backup gates and Asset Rights Ledger.
- **Change surface:** synthetic corpus generator/manifests and rights/privacy checks.
- **Implement:** Add the deterministic rights-cleared 150-GB corpus generator, frozen seed/content-root manifest, representative context distribution and namespace-bounded cleanup tooling.
- **Prove:** repeated byte/root identity, complete context mix, exact 150-GB accounting and zero credentials/production data/private material.
- **Stop/hand off:** missing rights, capacity storage or reproducibility is `NOT_EVALUABLE`.
- **Unlocks:** `P6-T20`.

## P6-T20 — Rehearse the 150-GB portability throughput campaign

- **Outcome:** Run a non-qualifying full-size rehearsal that exports/imports into empty current, N-1 and N-2 Institutions, reconciles/round-trips, rejects a populated target and cleans all staging on capacity-qualified storage.
- **Depends on:** `P6-T02`–`P6-T19` `MERGED`, including current `P6-T18=SUCCESS`.
- **External prerequisites:** label=P6-EXT-150GB-STORAGE; kind=HARDWARE; requires=CAPACITY_QUALIFIED_AND_RESERVED; accountable=Institution Infrastructure Owner; validity=exact corpus manifest and rehearsal window; evidence=signed immutable Storage Capacity Reservation Receipt
- **Read first:** Production Qualification Portability gate.
- **Change surface:** campaign/evidence only; fixes are child tasks.
- **Implement:** none; execute the full 150-GB export/import/round-trip rehearsal with interruption, resume, exact reconciliation and campaign-namespace cleanup, excluding product mutation.
- **Prove:** schemas/owners/hashes/policies/non-rebuildables/credential custody, mappings/authenticators/integrations/retention behavior, resource/time series and cleanup.
- **Stop/hand off:** never run this by consuming primary production headroom or call it the live 150-GB allowance; the qualifying run must repeat inside the 90-day interval in `P6-T34B`.
- **Unlocks:** `P6-T21`, campaign-controller admission and the later in-window run.

## P6-T21 — Expire and delete portability staging

- **Outcome:** Successful, rejected, interrupted, dry-run and populated-target staging areas reach exact retention/deletion dispositions with receipts and no target mutation.
- **Depends on:** `P6-T17`, `P6-T20`, `P2-T14` `MERGED`.
- **Read first:** Portability and Deletion Saga contracts.
- **Change surface:** portability cleanup worker/deletion adapter/tests/evidence.
- **Implement:** Add the bounded expiry scheduler, deletion saga, orphan/scratch cleanup, idempotent retry ledger and lifecycle receipts; delete only exact allowlisted generation/object namespaces.
- **Prove:** plaintext/ciphertext/object/index/temp cleanup, restart/idempotency, hold/backup obligations and rejected populated target unchanged.
- **Stop/hand off:** surviving undeclared plaintext or temp authority is `NEGATIVE`.
- **Unlocks:** `P6-T36`.

## Release, migration, and network-identity operations

## P6-T22 — Qualify complete N/N-2 install, upgrade, migration, and rollback support

- **Outcome:** Exercise complete product Offline Release Kits, expand-only migrations, isolated candidate checks, atomic deployment switch and binary rollback from current-through-N-2 supported releases.
- **Depends on:** `P1-T22`, `P1-T23`, `P3-T17`, `P5-T40` `MERGED`.
- **External prerequisites:** label=P6-EXT-RELEASE-HOST; kind=HARDWARE; requires=SUPPORTED_N_N_MINUS_1_N_MINUS_2_TARGETS_RESERVED; accountable=Release Infrastructure Owner; validity=exact kit hashes and qualification window; evidence=signed immutable Release Host Reservation Receipt
- **Read first:** Zero-Cash Runtime deployment-switch mechanics, Delivery State Ledger, all migration heads.
- **Change surface:** release/support harness, runbooks and evidence; fixes are child tasks.
- **Implement:** none; execute the exact-kit install, upgrade, migration, observation and rollback matrix and sign evidence, excluding product, migration or deployment-selection mutation.
- **Prove:** no-network clean install/reinstall, old/new readers, wrong/corrupt kit, interruption at each boundary, 30-minute observation and rollback without reversing schema.
- **Stop/hand off:** the binary switch emits deployment evidence, never `ACTIVATED`.
- **Unlocks:** `P6-T27`, Phase 7 release freeze.

## P6-T23 — Recover the Institution-supplied network identity

- **Outcome:** Prove public-ACME or internal-CA DNS/certificate state can be renewed and recovered after host loss without requiring one provider, DuckDNS, a paid domain or network service.
- **Depends on:** `P1-T14`, `P1-T22` and `P2-T11` `MERGED`.
- **External prerequisites:** label=P6-EXT-NETWORK-IDENTITY; kind=NETWORK_IDENTITY; requires=INSTITUTION_PATH_SELECTED_AND_RESERVED; accountable=Institution Network Identity Owner; validity=current identity contract and recovery window; evidence=signed immutable Network Identity Path Receipt
- **Read first:** ADR 0052 and Zero-Cash Runtime network boundary.
- **Change surface:** Caddy/install/recovery configuration, runbook and evidence.
- **Implement:** Add provider-neutral DNS/certificate export, reseed, rotation and revocation hooks bounded to the Institution-selected network-identity contract.
- **Prove:** expiry/renewal, lost host/key, restored trust path, offline/internal route and zero mandatory provider/cost assumption.
- **Stop/hand off:** unavailable Institution network identity is `NOT_EVALUABLE` for that deployment.
- **Unlocks:** `P6-T27`, Phase 7 deployment.

## Capacity, durability, and recovery

## P6-T24 — Measure the maximum admitted live governed corpus

- **Outcome:** Freeze the actual maximum corpus that fits the 150-GB raw encrypted primary volume after database/WAL/index/object/staging/derivative/deletion/restore-workspace/35-day-growth and >=20% safety terms.
- **Depends on:** `P1-T09`, `P2-T22` and the exact complete-context closure `P5-T40` `MERGED`.
- **External prerequisites:** label=P6-EXT-ACTUAL-CORPUS-HOST; kind=DATA_OR_CORPUS; requires=ACTUAL_GOVERNED_CORPUS_SNAPSHOT_FROZEN; accountable=Institution Data Owner; validity=exact snapshot root and measurement window; evidence=signed immutable Governed Corpus Snapshot Receipt | label=P6-EXT-PRIMARY-VOLUME; kind=HARDWARE; requires=150GB_RAW_VOLUME_RESERVED_AND_INSTRUMENTED; accountable=Institution Infrastructure Owner; validity=exact host and measurement window; evidence=signed immutable Primary Volume Reservation Receipt
- **Read first:** Zero-Cash Durability capacity equations, Production Qualification backup/imaging gates.
- **Change surface:** storage-accounting workload/evidence only; fixes are child tasks.
- **Implement:** none; measure every frozen storage term and admission trigger against the actual governed corpus and emit signed evidence without provisioning, purchase, topology or product mutation.
- **Prove:** worst-case bounded terms, inode/free-space/growth measurements, dynamic admission behavior and exact corpus manifest.
- **Stop/hand off:** any unknown/unbounded term is `NOT_EVALUABLE`; 150 GB is raw volume, not source-object allowance.
- **Unlocks:** `P6-T24A`, `P6-T25`.

## P6-T24A — Implement the scale-decision, home-cell, and context-extraction contract

- **Outcome:** Turn the funded scalability ladder into an executable decision record: keep the lightweight Zero-Cash cell as the default, trigger review at sustained >=70% of any frozen capacity envelope, prefer measured vertical relief first, assign each Institution to exactly one authoritative home cell, and define funded rebalancing/context extraction without automatic spend or duplicated authority.
- **Depends on:** `P1-T02`, `P1-T05`, `P1-T07`, `P1-T19`, `P5-T40`, `P6-T18` and `P6-T24` `MERGED`, with current `P6-T24=SUCCESS`.
- **Read first:** Final Production Endpoint funded scalability ladder, Context Map authority rules, Portability, Adaptive Viewer Capacity only as legacy measurement input, and current Zero-Cash limits.
- **Change surface:** Scale Decision and Institution Home Cell Assignment schemas/controllers/reports/UI, capacity-window and routing logic, context-extraction/rebalancing contracts/fixtures and runbook.
- **Implement:** per-resource sustained-window/hysteresis rules; admit/throttle/shed outcomes; measured vertical options; versioned `Institution -> home_cell` assignment and authoritative routing that fail closed on absent, ambiguous or stale mappings; an accountable, signed relocation plan that quiesces writes, exports/imports through owners, reconciles, switches one routing epoch and provides bounded reversal without dual writes; funded-resilience criteria based on measured RTO/RPO and outage/loss tolerance, failure-domain independence, restore evidence, operational staffing, cost and separate authorization.
- **Prove:** transient versus sustained 69.9/70/90% CPU/RAM/pool/disk/inode/network modes; concurrent/stale/unknown home-cell routing; an Institution move, interrupted move, pre-switch reversal, post-switch reconciliation and cache invalidation; owner extraction/replay without cross-context SQL, dual writes or lost authority; no automatic procurement, provider creation, deployment mutation or rebalance.
- **Stop/hand off:** a routing ambiguity or possible dual authority is `NEGATIVE`. This task establishes recommendation/routing/extraction readiness only; funded cells, replication, HA/DR, automatic failover, unlimited scale and any zero-cash guarantee for larger profiles require separate funding, deployment, qualification and accountable activation.
- **Unlocks:** `P7-T09`, `P6-T30` and `P7-G02` only after `P6-T24A` is `MERGED`; an authorized funded implementation may consume the decision record but is not created by it.

## P6-T25 — Rehearse restoration of the actual maximum-admitted corpus

- **Outcome:** Before campaign admission, rehearse latest/five-minute/one-hour/random retained PITR and full object/context/audit/outbox/deletion reconciliation from an actual encrypted Backup Generation into isolated storage.
- **Depends on:** `P2-T23` and `P6-T24` `MERGED`, with current release-bound Protection Receipt and Backup Generation manifest heads.
- **External prerequisites:** label=P6-EXT-RESTORE-TARGET; kind=HARDWARE; requires=ISOLATED_TARGET_RESERVED_AND_CAPACITY_QUALIFIED; accountable=Backup and Restore Owner; validity=selected generation heads and rehearsal window; evidence=signed immutable Restore Target Reservation Receipt
- **Read first:** Production Qualification backup gate and Golden Journey G37.
- **Change surface:** restore campaign/evidence only.
- **Implement:** none; execute the PITR/full-object rehearsal on the isolated target, reconcile every declared owner/state/hash and clean only the restore workspace, excluding product mutation.
- **Prove:** exact timelines/LSNs/manifests/keys/owners/receipts, deleted-state obligations, target-only material and restore-workspace deletion.
- **Stop/hand off:** synthetic or separate 150-GB throughput corpus cannot substitute, and this preflight does not replace the qualifying in-window execution in `P6-T34A`.
- **Unlocks:** `P6-T27`, `P6-T29` and the later in-window run.

## P6-T26 — Implement disconnected recovery epochs and crypto-expiry

- **Outcome:** Create independently stored recovery generations with random epoch DEKs, external two-of-three shares, bounded rotation and irreversible expiry confirmed by at least two stores plus negative decrypt.
- **Depends on:** `P2-T22` and `P2-T24` `MERGED`.
- **External prerequisites:** label=P6-EXT-RECOVERY-MEDIA; kind=HARDWARE; requires=MEDIA_PRESENT_AND_DISCONNECTED; accountable=Institution Key Custody Owner; validity=exact key epoch and lifecycle window; evidence=signed immutable Recovery Media Inventory Receipt | label=P6-EXT-RECOVERY-KEEPERS; kind=HUMAN_AUTHORITY; requires=TWO_OF_THREE_QUORUM_RESERVED; accountable=Institution Key Custody Owner; validity=exact key epoch and recovery or destruction ceremony; evidence=signed immutable Keeper Quorum Reservation Receipt
- **Read first:** Zero-Cash Durability append-only/disconnected rotation and key-management contracts.
- **Change surface:** target/recovery-media tooling, key manifests, lifecycle receipts/tests/runbook.
- **Implement:** Add per-generation random key epochs, threshold-share custody/revocation, auditable destruction, negative-decrypt verification and fail-closed retry semantics.
- **Prove:** refresh/disconnect/reattach/recover, lost medium/share, all wraps destroyed, late/replayed share and negative decrypt.
- **Stop/hand off:** medium must not self-unlock; Root Key must not derive expired epoch key; missing independent erasure evidence blocks expiry.
- **Unlocks:** `P6-T27`, `P6-T32`, `P6-T33`.

## P6-T27 — Rehearse ransomware, append-abuse, corruption, and cold-host recovery

- **Outcome:** Before campaign admission, show compromised production/ingest identities cannot read/overwrite/delete/prune/unlock prior generations, then rehearse recovery on an empty replacement host from kit/state/quorum/target/network-identity material.
- **Depends on:** `P6-T22`, `P6-T23`, `P6-T25`, `P6-T26` `MERGED`.
- **External prerequisites:** label=P6-EXT-REPLACEMENT-HOST; kind=HARDWARE; requires=EMPTY_SUPPORTED_HOST_RESERVED; accountable=Recovery Operations Owner; validity=exact kit and rehearsal window; evidence=signed immutable Replacement Host Reservation Receipt | label=P6-EXT-RECOVERY-OPERATORS; kind=HUMAN_AUTHORITY; requires=PRIMARY_AND_ALTERNATE_RESERVED; accountable=Recovery Operations Owner; validity=exact scenario and rehearsal window; evidence=signed immutable Recovery Operator Reservation Receipt
- **Read first:** Production Qualification backup/cross-cutting faults.
- **Change surface:** security/recovery campaign/evidence only.
- **Implement:** none; execute the ransomware, abuse, corruption and empty-replacement-host recovery rehearsal, reconcile exact authority/data and destroy drill credentials without product mutation.
- **Prove:** nonce/replay/hash/rate/quota/garbage abuse, previous generation survival, AB/AC/BC, one lost share, new host-key rewrap, exact restore and cleanup.
- **Stop/hand off:** any production repository credential or pair failure is `NEGATIVE`; no fixed RTO/HA claim; qualifying replacement-host/repository-adversary and key/custodian/media drills repeat in `P6-T34C` and `P6-T34D` during the operated interval.
- **Unlocks:** `P6-T29` and the later in-window drills.

## P6-T28 — Implement complete zero-cash accounting and projection

- **Outcome:** Record every PathLab-specific hosting/software/API/model/standard/support/hardware/domain/certificate/connectivity/utility obligation gross before credits, with allowance caps/expiry and 12-month projected incremental charge; disclose contributed resources/labor separately.
- **Depends on:** `P0-T09A`, `P1-T22`, `P1-T23`, `P2-T22`, `P5-T40`, `P6-T20`, `P6-T21`, `P6-T22`, `P6-T23` and `P6-T24` `MERGED`.
- **External prerequisites:** label=P6-EXT-COST-SOURCES; kind=COST_OR_ALLOWANCE; requires=ALL_ACCOUNTS_TARIFFS_ALLOWANCES_AND_STATEMENT_SOURCES_ACCESSIBLE; accountable=Institution Finance Owner; validity=exact accounts and frozen projection timestamp; evidence=signed immutable Cost Source Inventory Receipt
- **Read first:** Zero-Cash Durability accounting/claim limits, Production Qualification Zero-Cash gate.
- **Change surface:** Audit/cost schemas, operator UI/CLI/report/tests.
- **Implement:** freeze provider rate cards/tariffs, currency and tax treatment, allowance caps/reset/expiry, billing-account/source identities, statement availability lag and deterministic 12-month projection method with every workload assumption.
- **Prove:** every mandatory input/path reconciles; credits cannot zero gross charge; missing/expiring/positive-overage/paid-certification cases fail; repeated calculation from the same statements/tariffs yields the same result.
- **Stop/hand off:** no “free forever” or permanent allowance statement.
- **Unlocks:** `P6-T30`, `P6-T35`.

## P6-T29 — Build the operated-campaign controller

- **Outcome:** Freeze signed daily checkpoints, input/candidate drift, primary/alternate operators, fault schedule, receipt cursor, live worker/activity checks, pause/failure semantics and signed unchanged-input equivalence rules in a pre-deployment Campaign Contract Template.
- **Depends on:** `P2-T16`, `P2-T16A`, `P2-T18A`, `P2-T18B`, `P6-T20`, `P6-T21`, and `P6-T25`–`P6-T28` `MERGED`.
- **Read first:** Production Qualification evidence/decision rules and Delivery State Ledger.
- **Change surface:** campaign controller/dashboard/evidence schemas/tests/runbook.
- **Implement:** Add deterministic campaign start/resume, signed checkpoints and heartbeats, lease takeover, monotonic elapsed-time accounting, terminal-state publication and allowlisted cleanup without changing release selection.
- **Prove:** killed/wedged worker, missing receipt/day/operator, clock gap, changed input, stale evidence and false-green dashboard fixtures.
- **Stop/hand off:** `RUNNING` is not success; no historical result carries without exact signed equivalence and final-candidate soak.
- **Unlocks:** exact candidate integration in `P7-T09`; the campaign cannot start until that candidate is merged and deployed. The template hash enters the candidate fingerprint, while the later run manifest references both without circular hashing.

## P6-T30 — Admit and start the 90-day durability/zero-cash campaign

- **Outcome:** Bind the exact already-deployed release fingerprint and current deployment-selection receipt head to the declared host, primary volume, independent target, storage/network/cache properties, key topology, exact workload, cost boundary, billing cycles/sources, operators, fault/restore schedule and evidence schemas, then emit the registered campaign start receipt.
- **Depends on:** `P6-T24`, `P6-T24A`, and `P6-T25`–`P6-T29` `MERGED`; current exact-subject `P7-T12=DEPLOYED` with its atomically linked current `DeploymentSelectionReceipt(SELECTED)` and `DeliveryLifecycleReceipt(DEPLOYED)` for the identical tuple.
- **External prerequisites:** label=P6-EXT-CAMPAIGN-OPERATIONS; kind=HUMAN_AUTHORITY; requires=PRIMARY_AND_ALTERNATE_OPERATORS_RESERVED; accountable=Campaign Operations Owner; validity=exact admitted tuple and entire declared 90-day window; evidence=signed immutable Campaign Operator Reservation Receipt | label=P6-EXT-CAMPAIGN-RESOURCES; kind=HARDWARE; requires=HOST_PRIMARY_VOLUME_INDEPENDENT_TARGET_AND_DRILL_TARGETS_RESERVED; accountable=Institution Infrastructure Owner; validity=exact admitted tuple and entire declared 90-day window; evidence=signed immutable Campaign Resource Reservation Receipt | label=P6-EXT-CAMPAIGN-NETWORK; kind=NETWORK_IDENTITY; requires=DECLARED_ROUTE_DNS_CERTIFICATE_AND_CONNECTIVITY_PATH_RESERVED; accountable=Institution Network Owner; validity=exact admitted tuple and entire declared 90-day window; evidence=signed immutable Campaign Network Path Receipt | label=P6-EXT-CAMPAIGN-WORKLOAD; kind=DATA_OR_CORPUS; requires=EXACT_WORKLOAD_AND_CORPUS_ROOTS_FROZEN_AND_AVAILABLE; accountable=Campaign Data Owner; validity=exact admitted tuple and entire declared 90-day window; evidence=signed immutable Campaign Workload Admission Receipt | label=P6-EXT-CAMPAIGN-COST; kind=COST_OR_ALLOWANCE; requires=ALL_BILLING_SOURCES_AND_COVERING_STATEMENTS_COMMITTED; accountable=Institution Finance Owner; validity=exact accounts and full campaign coverage interval; evidence=signed immutable Campaign Cost Evidence Plan Receipt
- **Read first:** Production Qualification backup/zero-cash gates.
- **Change surface:** immutable Campaign Run Manifest/start evidence only.
- **Implement:** none; verify prerequisite receipt heads, freeze the exact release-selection-resource tuple, sign admission/start receipts and start monitoring without source, configuration, deployment-selection or product mutation.
- **Prove:** the run manifest records the full `P7-T12` release fingerprint plus deployment-selection and lifecycle receipt IDs/hashes, and references the frozen `P6-T29` template as a separate non-circular input; the selected route, host and fingerprint are current/equal at admission and start; both distinct sequential 35-day cycles and every `P6-T34`–`P6-T34D` drill are scheduled to finish inside the declared >=90-day window; actual worker/receipt progression begins.
- **Stop/hand off:** a missing/mismatched/reverted selection head, operator, hardware declaration, independent target, accounting source, covering-billing plan, expiry path, in-window drill slot or evidence custody is `NOT_EVALUABLE` and no start receipt is emitted.
- **Unlocks:** `P6-T31`, `P6-T32`, `P6-T34`, `P6-T34A`, `P6-T34B`, `P6-T34C`, `P6-T34D` and concurrent exact-candidate soak `P7-T13`.

## P6-T31 — Monitor and audit the active campaign

- **Outcome:** Maintain daily signed checks of WAL/object protection, capacity, costs, worker CPU/activity, receipts, alerts, incidents, key/target state, the current `P7-T12` fingerprint/deployment-selection head and scheduled fault/restore work without retaining a chat context.
- **Depends on:** active `P6-T30`.
- **Read first:** operated-campaign runbook and automation policy.
- **Change surface:** heartbeat automation/status evidence and incident/remediation tasks only.
- **Implement:** none; poll liveness, resource and receipt-cursor progress, record incidents and drift, and perform only pre-authorized operational recovery without product or deployment-selection mutation.
- **Prove:** monotonic receipt/day sequence, live progress, current selection/lifecycle receipt linkage, no silent gaps/drift, and actionable notifications only on change/failure/completion/user need.
- **Stop/hand off:** a global continuity loss restarts the full affected window. Any `DeploymentSelectionReceipt` head change, including a `REVERTED` or nominally equivalent build, immediately invalidates the current P6-T30 admission and requires a new P6-T30 before admitted time can accrue. A signed Impact/Equivalence Result may preserve only unaffected historical durability evidence for a separately admitted run; it can never retain admission, affected gate results or soak days. Never close or restart history silently outside the frozen rule.
- **Unlocks:** scheduled cycle closures and `P6-T35` only after full duration.

## P6-T32 — Close the first complete 35-day expiry cycle

- **Outcome:** Reconcile one generation created inside the operated window through logical expiry, prune/reclamation, repository verification, quorum crypto-expiry, negative decrypt and terminal receipts strictly before age 35 days.
- **Depends on:** active `P6-T30` and `P6-T26` `MERGED`, with a current campaign-bound `CampaignCheckpointReceipt` head covering every instant through the cycle.
- **Read first:** backup lifecycle contract and campaign manifest.
- **Change surface:** read-only evidence review/closure.
- **Implement:** none; close active-retention, protection, crypto-expiry and deletion evidence from immutable campaign receipts, excluding product or release mutation.
- **Prove:** `window_start <= created_at < completed_at <= window_end` and `completed_at < created_at + 35 * 24h` using trusted target receipt time; execute expiry/prune early enough on lifecycle day 34 to finish before the strict deadline; reconcile dependencies, independent stores/keys and absence of a Legal Hold extension. Equality at the strict 35-day deadline fails; `completed_at == window_end` is allowed only when every other inequality and coverage condition holds.
- **Stop/hand off:** missed or incomplete expiry is `NEGATIVE` and blocks authoritative admission/retention claim.
- **Unlocks:** `P6-T33`.

## P6-T33 — Close the second independent 35-day expiry cycle

- **Outcome:** After the first cycle closes, repeat complete creation-to-expiry evidence with different generation/epoch/share identities and the same strict pre-35-day inequality while the 90-day campaign continues.
- **Depends on:** active `P6-T30` and current `P6-T32=SUCCESS`, with a current campaign-bound `CampaignCheckpointReceipt` head covering every instant through the second cycle.
- **Read first:** the backup lifecycle contract, `Crypto-Expiry Receipt` and `Deletion Receipt` schemas, and the immutable Campaign Run Manifest.
- **Change surface:** evidence review/closure only.
- **Implement:** none; close the second independent crypto-expiry/deletion cycle from immutable campaign receipts and exclude product or release mutation.
- **Prove:** `first.completed_at < second.created_at < second.completed_at <= window_end` and `second.completed_at < second.created_at + 35 * 24h` using trusted receipt time; no reuse of the first generation/epoch/share/proof; all crypto/prune/integrity/deletion receipts independently reconcile and equality at the strict deadline fails.
- **Stop/hand off:** late/reused/missing evidence is `NEGATIVE`.
- **Unlocks:** `P6-T35` when day 90 also completes.

## P6-T34 — Execute the in-window database and protection fault matrix

- **Outcome:** During the operated window, run the declared idle/peak, target/network loss, process/primary restart, slot/capacity pressure, corruption/replay/clock, power/cache-boundary and latest/five-minute/one-hour/random PITR cases, plus primary-operator unavailability and signed alternate-operator takeover, without changing thresholds or evidence inputs.
- **Depends on:** current exact-subject `P6-T30=ACTIVE` and `P6-T27` `MERGED`, with the current immutable Campaign Run Manifest schedule head for the admitted campaign tuple.
- **External prerequisites:** label=P6-EXT-CAMPAIGN-OPERATIONS; kind=HUMAN_AUTHORITY; requires=PRIMARY_AND_ALTERNATE_OPERATORS_RESERVED; accountable=Campaign Operations Owner; validity=exact admitted tuple and declared fault slots; evidence=signed immutable Campaign Operator Reservation Receipt
- **Read first:** Production Qualification cross-cutting failures and backup gate.
- **Change surface:** campaign evidence only; fixes require a new candidate/task and invalidation decision.
- **Implement:** none; execute the frozen fault matrix and alternate-operator takeover, capture signed evidence and clean only campaign namespaces without product mutation.
- **Prove:** trusted receipts show `window_start <= started_at < completed_at <= window_end` and the current deployment-selection head; hard five-minute behavior, acknowledged-write and object-pending invariants, frozen durability settings, protection/inventory/PITR correctness, primary-to-alternate handoff with the alternate executing a declared review/drill, cleanup and signed Fault Injection Results; no 24-hour staffing claim follows.
- **Stop/hand off:** a run outside the declared window/current selection, undeclared chaos or untrustworthy evidence is `NOT_EVALUABLE`; invariant breach is `NEGATIVE`.
- **Unlocks:** `P6-T35` only together with every sibling in-window drill.

## P6-T34A — Execute the in-window maximum-actual-corpus restore

- **Outcome:** During the operated interval, fully restore and hash-reconcile the maximum admitted actual governed corpus from an actual encrypted Backup Generation on isolated capacity-qualified storage.
- **Depends on:** active `P6-T30` and current `P6-T25=SUCCESS`, with the current P6-T30 Campaign Run Manifest schedule and `DeploymentSelectionReceipt(SELECTED)` heads exactly matching the admitted tuple.
- **External prerequisites:** label=P6-EXT-ACTUAL-CORPUS-HOST; kind=DATA_OR_CORPUS; requires=ACTUAL_GOVERNED_CORPUS_SNAPSHOT_FROZEN; accountable=Institution Data Owner; validity=exact snapshot root and drill slot; evidence=signed immutable Governed Corpus Snapshot Receipt | label=P6-EXT-RESTORE-TARGET; kind=HARDWARE; requires=ISOLATED_TARGET_RESERVED_AND_CAPACITY_QUALIFIED; accountable=Backup and Restore Owner; validity=exact Backup Generation and drill slot; evidence=signed immutable Restore Target Reservation Receipt
- **Read first:** Zero-Cash Durability Restore and operating evidence; Production Qualification Backup gate.
- **Change surface:** immutable campaign manifests, raw measurements, signed results and cleanup evidence only.
- **Implement:** none; restore and reconcile the maximum actual governed corpus on the isolated target and clean only the restore workspace, excluding product mutation.
- **Prove:** trusted receipts show `window_start <= started_at < completed_at <= window_end` and the current deployment-selection head; exact timelines/LSNs, every context/outbox/audit/object/manifest/deletion/key state, hashes/resources/timings, no primary-headroom substitution and isolated workspace removal.
- **Stop/hand off:** synthetic/separate throughput data, a run outside the interval/current selection or unqualified storage is `NOT_EVALUABLE`; reconciliation breach is `NEGATIVE`.
- **Unlocks:** `P6-T35` only together with every sibling in-window drill.

## P6-T34B — Execute the in-window separate 150-GB portability/restore campaign

- **Outcome:** During the operated interval, execute the complete separate 150-GB export/import/round-trip and, as a distinct leg, create/protect and restore that full corpus from an encrypted Backup Generation into an isolated empty target on capacity-qualified build/restore storage.
- **Depends on:** active `P6-T30` and current `P6-T20=SUCCESS`, with the current P6-T30 Campaign Run Manifest schedule and `DeploymentSelectionReceipt(SELECTED)` heads exactly matching the admitted tuple.
- **External prerequisites:** label=P6-EXT-150GB-CORPUS; kind=DATA_OR_CORPUS; requires=EXACT_RIGHTS_CLEARED_CORPUS_FROZEN; accountable=Portability Campaign Owner; validity=exact 150-GB manifest root and drill slot; evidence=signed immutable Corpus Admission Receipt | label=P6-EXT-150GB-STORAGE; kind=HARDWARE; requires=CAPACITY_QUALIFIED_BUILD_AND_ISOLATED_RESTORE_TARGETS_RESERVED; accountable=Institution Infrastructure Owner; validity=exact corpus manifest and drill slot; evidence=signed immutable Storage Capacity Reservation Receipt
- **Read first:** Zero-Cash Durability Restore and operating evidence; Production Qualification Portability/Backup gates.
- **Change surface:** immutable fault/recovery manifests, signed results and cleanup evidence only.
- **Implement:** none; execute the portability leg and a separate timed encrypted backup/isolated-restore-throughput leg, reconcile every byte/object/root and clean only campaign namespaces without product mutation.
- **Prove:** trusted receipts show `window_start <= started_at < completed_at <= window_end` and the current deployment-selection head; the portability leg proves current/N-1/N-2 empty-target round trip, populated-target rejection and owner/schema/hash/policy/non-rebuildable reconciliation. The distinct backup/restore leg records the encrypted Backup Generation manifest/root, target-side protection completion, restore into an isolated empty target, a current `Restore Receipt`, byte/object/hash reconciliation, and end-to-end protection plus restore throughput. Both legs record resources/timings, use no primary headroom and remove all staging; export/import alone cannot satisfy restore throughput.
- **Stop/hand off:** treating the corpus as live allowance, a run outside the interval/current selection, partial corpus, missing or partial Backup Generation/Restore Receipt or unqualified storage is `NOT_EVALUABLE`; reconciliation breach is `NEGATIVE`.
- **Unlocks:** `P6-T35` only together with every sibling in-window drill.

## P6-T34C — Execute in-window replacement-host and repository-adversary recovery

- **Outcome:** During the operated interval, recover the actual encrypted generation on an isolated empty replacement host while exercising production-identity ransomware, malicious/replayed pull grants, garbage/quota pressure, receipt replay and corruption.
- **Depends on:** active `P6-T30`, `P6-T22` and `P6-T23` `MERGED`, and current `P6-T27=SUCCESS`, with the current P6-T30 Campaign Run Manifest schedule and `DeploymentSelectionReceipt(SELECTED)` heads exactly matching the admitted tuple.
- **External prerequisites:** label=P6-EXT-REPLACEMENT-HOST; kind=HARDWARE; requires=EMPTY_SUPPORTED_HOST_RESERVED; accountable=Recovery Operations Owner; validity=exact admitted tuple and drill slot; evidence=signed immutable Replacement Host Reservation Receipt | label=P6-EXT-NETWORK-IDENTITY; kind=NETWORK_IDENTITY; requires=RECOVERY_MATERIAL_CURRENT_AND_AVAILABLE; accountable=Institution Network Identity Owner; validity=current identity contract and drill slot; evidence=signed immutable Network Identity Recovery Receipt
- **Read first:** Zero-Cash Durability authority/restore evidence and Production Qualification cross-cutting failures.
- **Change surface:** immutable fault/recovery manifests, signed results and cleanup evidence only.
- **Implement:** none; execute the replacement-host and repository-adversary recovery drill, reconcile exact authority/data and destroy drill credentials without product mutation.
- **Prove:** trusted receipts show `window_start <= started_at < completed_at <= window_end` and the current deployment-selection head; kit, encrypted infrastructure state, quorum rewrap, network identity, context databases, outboxes, audit chains and object manifests; prior generations survive; production holds no target maintenance/decryption authority.
- **Stop/hand off:** use of the original host, synthetic generation, a run outside the interval/current selection, missing governed authority or undeclared egress is `NOT_EVALUABLE`; lost acknowledged truth or repository boundary breach is `NEGATIVE`.
- **Unlocks:** `P6-T35` only together with every sibling in-window drill.

## P6-T34D — Execute in-window key, custodian, and disconnected-media lifecycle drills

- **Outcome:** During the operated interval, execute signing-key rotation, old/new-key recovery, one-custodian loss, AB/AC/BC quorum, disconnected-generation refresh/disconnection/reattachment/verification/recovery, lost-medium handling and on-time epoch-key crypto-expiry.
- **Depends on:** active `P6-T30` and `P6-T26` `MERGED`, and current `P6-T27=SUCCESS`, with the current P6-T30 Campaign Run Manifest schedule and `DeploymentSelectionReceipt(SELECTED)` heads exactly matching the admitted tuple.
- **External prerequisites:** label=P6-EXT-RECOVERY-MEDIA; kind=HARDWARE; requires=MEDIA_PRESENT_AND_DISCONNECTED; accountable=Institution Key Custody Owner; validity=exact admitted key epochs and drill slot; evidence=signed immutable Recovery Media Inventory Receipt | label=P6-EXT-RECOVERY-KEEPERS; kind=HUMAN_AUTHORITY; requires=TWO_OF_THREE_QUORUM_RESERVED; accountable=Institution Key Custody Owner; validity=exact admitted key epochs and drill slot; evidence=signed immutable Keeper Quorum Reservation Receipt
- **Read first:** Zero-Cash Durability disconnected rotation and Root Recovery Quorum contracts.
- **Change surface:** immutable key/media drill manifests, signed receipts and negative-decrypt evidence only.
- **Implement:** none; execute the frozen key, custodian and disconnected-media lifecycle drills and record negative-decrypt evidence without product mutation.
- **Prove:** trusted receipts show `window_start <= started_at < completed_at <= window_end` and the current deployment-selection head; media never self-unlocks; lost share/medium does not break permitted recovery; epoch destruction completes with `completed_at < created_at + 35 * 24h` and expired material cannot decrypt after all required stores acknowledge destruction; receipt/signature history remains verifiable.
- **Stop/hand off:** a run outside the interval/current selection is `NOT_EVALUABLE`; reusable-root derivation, equality/overrun at the strict expiry deadline, late/replayed share acceptance, failed quorum pair or incomplete independent expiry evidence is `NEGATIVE`.
- **Unlocks:** `P6-T35` only together with every sibling in-window drill.

## P6-T35 — Close the full 90-day and initial zero-cash windows

- **Outcome:** After 90 consecutive valid days and after every invoice/provider statement covering that interval becomes available, aggregate daily evidence, two cycles, every in-window fault/recovery/actual-corpus/150-GB/key/media drill, exact-candidate soak, incidents and gross cost/projection into terminal results.
- **Depends on:** current exact-subject `P6-T30=COMPLETED`, with completed `P6-T31`, `P6-T32`, `P6-T33`, `P6-T34`, `P6-T34A`, `P6-T34B`, `P6-T34C`, `P6-T34D` and `P6-T28`; current `P7-T14=SUCCESS`; and current `P7-T12` `DeploymentSelectionReceipt(SELECTED)`/`DeliveryLifecycleReceipt(DEPLOYED)` heads exactly matching the completed admitted campaign tuple.
- **External prerequisites:** label=P6-EXT-COVERING-STATEMENTS; kind=COST_OR_ALLOWANCE; requires=IMMUTABLE_STATEMENTS_COVER_EVERY_INSTANT_WITHOUT_GAP; accountable=Institution Finance Owner; validity=exact admitted campaign window and billing accounts; evidence=signed immutable Provider Cost Evidence Receipt
- **Read first:** Production Qualification backup and Zero-Cash gate rules.
- **Change surface:** signed evidence aggregation only.
- **Implement:** none; aggregate immutable child receipts, elapsed-time and billing-coverage facts into terminal results without product, selection or evidence mutation.
- **Prove:** trusted `window_end - window_start >= 90 * 24h` with no uncovered interval; every campaign day, cycle, workload and `P6-T34`–`P6-T34D` drill starts and completes inside that interval; the union of immutable provider/invoice `coverage_start..coverage_end` ranges covers every instant of the interval without a billing gap, even when statements are issued after `window_end`; all accounts/rates/taxes/currencies/allowances reconcile; zero gross incremental charge/payment and zero projected charge under frozen load; the terminal fingerprint and current deployment-selection head exactly match that completed admitted campaign tuple. Any selection-head change requires a newly admitted campaign tuple; no Impact/Equivalence chain retains admission.
- **Stop/hand off:** day 90 ends observation but cannot produce `SUCCESS` while any covering statement is unavailable, mutable, unverified or leaves a coverage gap; a missing day, out-of-window drill, incomplete workload, stale selection or unclosed incident is `PARTIAL` or `NOT_EVALUABLE`; positive charge/payment/projection or an invariant breach is `NEGATIVE`.
- **Unlocks:** `P6-T36` and long-duration exact-release gates.

## P6-T36 — Close Phase 6 portability and operations

- **Outcome:** Independently reconcile portability across N/N-1/N-2, the separate 150-GB corpus, actual live corpus, lifecycle, two strictly pre-35-day expiry cycles, key loss, ransomware, upgrade/migration, network identity, cold recovery and full >=90-day zero-cash evidence.
- **Depends on:** `P6-T01`–`P6-T29`, including `P6-T24A`, `MERGED`, with current exact-subject `P6-T20=SUCCESS`, `P6-T21=SUCCESS`, `P6-T22=SUCCESS`, and `P6-T23=SUCCESS`, plus current `P6-T35=SUCCESS` for the same operated-campaign tuple.
- **Read first:** this phase, Delivery State Ledger, Production Qualification.
- **Change surface:** phase evidence/result only.
- **Implement:** none; evaluate and sign the phase result from immutable receipts without product, configuration, deployment-selection or evidence mutation.
- **Prove:** exact subjects, interval/cycle inequalities, current `P7-T12` fingerprint and deployment-selection/lifecycle receipt heads exactly matching the current P6-T30 admission, complete billing coverage and no waived/stale/mixed evidence; complete blocker/invalidation list. A selection-head change requires a new P6-T30 and no equivalence carry-forward may retain admission.
- **Stop/hand off:** long-duration evidence can support but not itself qualify or activate a future candidate. Any non-`SUCCESS` Phase 6 result is still recorded as terminal evidence but unlocks no exact-release gate.
- **Unlocks:** `P7-G17`, `P7-G19` and `P7-T15` only on current `P6-T36=SUCCESS` for the identical candidate fingerprint and deployment-selection head; candidate integration already occurred before campaign admission.
