# Phase 5 — Standards and Specialist Contexts

Phase 5 completes Integration Gateway, learning/credential interoperability, Credential Ledger, EQA, Clinical Shadow, Research and Edge Federation. Protocol transport never transfers owner authority. External specification/tool/corpus facts must be reverified against official sources when each task starts. All tasks inherit [README](./README.md).

## P5-T00 — Extend route and navigation contracts for specialist contexts

- **Outcome:** Freeze discoverable, role-scoped routes and operational states for integrations, credentials, EQA, Clinical Shadow, Research and Edge without exposing administrative or sensitive surfaces broadly.
- **Depends on:** `P4-T00` `MERGED` and current `P4-T30=SUCCESS`.
- **Read first:** Role Matrix, all Phase 5 context glossaries, current application routes/navigation.
- **Change surface:** versioned IA contract and route/accessibility tests only.
- **Implement:** extend the owner-route registry with role visibility, navigation labels and safe empty/loading/error/offline/revoked states for every Phase 5 human workflow.
- **Prove:** every human action has one owning-context route, safe empty/error/offline state and no authority duplication.
- **Stop/hand off:** route naming that implies certification, clinical care, public credentials or Edge multi-master authority must be corrected before UI implementation.
- **Unlocks:** all Phase 5 UI tasks.

## Integration Gateway and learning standards

## P5-T01 — Scaffold Integration Gateway and registration lifecycle

- **Outcome:** Gateway owns its logical database, role, migrations, outbox, External Registrations, Adapter Credentials, exact profile versions, Exchange Attempts, quarantine and delivery attempts.
- **Depends on:** `P1-T25`, `P2-T27`, `P5-T00`, `P1-T02`, `P1-T04`, `P2-T04` `MERGED` and current `P4-T30=SUCCESS`.
- **Read first:** Integration Gateway context, Learning Interoperability authority section, Receipt Registry Gateway section.
- **Change surface:** Gateway module/migrations/contracts, batch mode/admin UI and tests.
- **Implement:** register/activate/revoke/rotate; inbound proposals and outbound delivery only; bounded retries/terminal abandonment.
- **Prove:** wrong issuer/key/scope/version/Institution, replay, retry/restart, credential rotation and no direct owner-table access.
- **Stop/hand off:** Gateway never owns identity, Catalog, Grade, Credential, Imaging or Clinical truth.
- **Unlocks:** `P5-T01A`, `P5-T02`, Clinical and Edge transport.

## P5-T01A — Implement optional external notification delivery

- **Outcome:** Let Integration Gateway consume authoritative in-app Notice delivery proposals and optionally deliver privacy-minimized copies through manually registered Institution-owned endpoints without becoming notice truth.
- **Depends on:** `P2-T18`, `P5-T00`, and `P5-T01` `MERGED`.
- **Read first:** Audit and Operations notice ownership, Integration Gateway registration/delivery contract and Role Matrix.
- **Change surface:** Gateway notification profile, External Registration/Adapter Credential admin UI, delivery worker/receipts/tests.
- **Implement:** disabled-by-default registration, exact audience/purpose/template fields, bounded retry/expiry/abandonment, credential rotation and remote acknowledgement; no email/SMS provider is mandatory.
- **Prove:** endpoint outage, replay/duplicate, revoked registration/key, forbidden-field/secret/PHI/answer inspection, cross-Institution routing and local-notice independence.
- **Stop/hand off:** external delivery never acknowledges or mutates the authoritative in-app Notice and cannot become a paid mandatory production dependency.
- **Unlocks:** specialist closure and optional Institution notification operation.

## P5-T02 — Implement the rights-cleared standards-corpus framework

- **Outcome:** Implement the common manifest, offline-kit layout, rights/provenance fields, checksum rules, immutable versioning and validator-adapter interface used by each independently admitted standards corpus.
- **Depends on:** `P0-T08`, `P0-T09`, `P0-T09A`, `P5-T01` `MERGED`.
- **Read first:** [Learning Interoperability](../architecture/LEARNING_INTEROPERABILITY.md), [Clinical/Imaging Interoperability](../architecture/CLINICAL_IMAGING_INTEROPERABILITY.md), Production Qualification.
- **Change surface:** offline kit standards bundle, `tests/fixtures/interop/`, validator adapters and supply-chain ledger.
- **Implement:** one typed section per profile with official/reference source, claim/version, license/right, hash, local validation command, independent-tool fixture and expiry/review metadata; no corpus payload is admitted by this framework task.
- **Prove:** empty/missing/unknown/mutable/rights-incomplete sections fail, no-network resolution works and one corpus cannot satisfy another profile.
- **Stop/hand off:** unavailable lawful artifacts or independent implementations are recorded by their child task as `NOT_EVALUABLE`; no paid certification or certification mark.
- **Unlocks:** `P5-T02A`–`P5-T02J`.

## P5-T02A — Admit the LTI 1.3 and Advantage corpus

- **Outcome:** Mirror the exact official LTI Core, Deep Linking, NRPS and AGS artifacts plus adversarial/reference fixtures and two independent appropriate implementations.
- **Depends on:** `P5-T02` `MERGED`.
- **Read first:** Learning Interoperability LTI claim and the standards-corpus framework.
- **Change surface:** offline LTI corpus section, fixtures, validator adapter and provenance ledger.
- **Implement:** exact versions/rights/hashes, OIDC/JWK/message/service examples and no-network validation commands.
- **Prove:** official source, mutable/wrong version, key/message/profile mismatch and both independent fixtures.
- **Stop/hand off:** no dynamic-registration, general-SSO, certification or paid-tool substitution.
- **Unlocks:** `P5-T03`, `P5-T04`–`P5-T04B`.

## P5-T02B — Admit the OneRoster corpus

- **Outcome:** Mirror exact OneRoster REST 1.2 and CSV 1.2.1 artifacts, resource examples, hostile sets and two independent appropriate implementations.
- **Depends on:** `P5-T02` `MERGED`.
- **Read first:** Learning Interoperability OneRoster claim and standards-corpus framework.
- **Change surface:** offline OneRoster corpus section, fixtures, validator adapter and provenance ledger.
- **Implement:** exact versions/rights/hashes, frozen resource/direction subset and atomic cross-file validation inputs.
- **Prove:** wrong version, partial/duplicate/cross-file-invalid/oversized sets and independent fixture agreement.
- **Stop/hand off:** no Provider/write/delete profile or paid certification requirement.
- **Unlocks:** `P5-T05`.

## P5-T02C — Admit the QTI 3.0.1 corpus

- **Outcome:** Mirror exact QTI 3.0.1 artifacts/resources/examples for the declared subset, adversarial packages and two independent appropriate implementations.
- **Depends on:** `P5-T02` `MERGED`.
- **Read first:** Learning Interoperability QTI claim and standards-corpus framework.
- **Change surface:** offline QTI corpus section, fixtures, validator adapter and provenance ledger.
- **Implement:** exact version/rights/hashes and supported Assessment/Section/Item interaction manifest.
- **Prove:** hostile archive/resource/path/executable, unsupported interaction/extension, round-trip fixture and independent validation.
- **Stop/hand off:** no Results Reporting, CAT, PCI or universal-QTI claim.
- **Unlocks:** `P5-T06`.

## P5-T02D — Admit the CASE 1.1 corpus

- **Outcome:** Mirror exact CASE 1.1 read-only framework/document/item/association artifacts, adversarial graphs and two independent appropriate implementations.
- **Depends on:** `P5-T02` `MERGED`.
- **Read first:** Learning Interoperability CASE claim and standards-corpus framework.
- **Change surface:** offline CASE corpus section, fixtures, validator adapter and provenance ledger.
- **Implement:** exact version/rights/hashes, declared read subset and immutable-reference examples.
- **Prove:** unknown extension/version, broken/cyclic association, changed framework and both independent fixtures.
- **Stop/hand off:** no CASE write/edit or universal compatibility claim.
- **Unlocks:** `P5-T07`.

## P5-T02E — Admit the Open Badges 3.0 corpus

- **Outcome:** Mirror exact Open Badges 3.0 contexts/schemas/examples, hostile credentials and two independent verifier fixtures.
- **Depends on:** `P5-T02` `MERGED`.
- **Read first:** Credential Interoperability Open Badges claim and standards-corpus framework.
- **Change surface:** offline Open Badges corpus section, fixtures, validator adapter and provenance ledger.
- **Implement:** exact context/version/rights/hashes, declared proof/status/evidence subset and offline verification inputs.
- **Prove:** context substitution, signature/status/evidence tamper, unknown extension and independent verification.
- **Stop/hand off:** no certification mark, public roster or issuer-key fixture in release artifacts.
- **Unlocks:** `P5-T12`.

## P5-T02F — Admit the CLR 2.0 corpus

- **Outcome:** Mirror exact CLR 2.0 contexts/schemas/examples, hostile documents and two independent verifier fixtures.
- **Depends on:** `P5-T02` `MERGED`.
- **Read first:** Credential Interoperability CLR claim and standards-corpus framework.
- **Change surface:** offline CLR corpus section, fixtures, validator adapter and provenance ledger.
- **Implement:** exact context/version/rights/hashes, declared achievement/evidence/status subset and offline validation inputs.
- **Prove:** nesting/size/context/signature/status tamper, unknown extension and independent verification.
- **Stop/hand off:** no universal CLR or certification claim and no private issuer key.
- **Unlocks:** `P5-T12`.

## P5-T02G — Admit the optional Caliper 1.2 corpus

- **Outcome:** Mirror exact Caliper 1.2 contexts/profiles/examples for the privacy-minimized optional outbound subset and two independent consumer fixtures.
- **Depends on:** `P5-T02` `MERGED`.
- **Read first:** Learning Interoperability Caliper boundary and standards-corpus framework.
- **Change surface:** offline Caliper corpus section, fixtures, validator adapter and provenance ledger.
- **Implement:** exact version/rights/hashes and forbidden-field/minimization fixtures.
- **Prove:** unknown profile/version, sensitive field, oversized event and both independent consumers.
- **Stop/hand off:** Caliper remains disabled and optional; missing corpus cannot break local learning.
- **Unlocks:** `P5-T08`.

## P5-T02H — Admit the FHIR R4 and terminology corpus

- **Outcome:** Mirror the exact executable FHIR R4 shadow profile, deidentified examples, allowed terminology snapshot and two independent client/validator fixtures.
- **Depends on:** `P5-T02` `MERGED`.
- **External prerequisites:** label=EP-P5-FHIR-TERMS; kind=RIGHTS; requires=APPROVED; accountable=Clinical interoperability lead; validity=exact FHIR and terminology versions licenses and hashes remain approved through P5-T26 closure; evidence=SignedFHIRTerminologyRightsReceipt.
- **Read first:** Clinical/Imaging Interoperability FHIR/terminology boundary and standards-corpus framework.
- **Change surface:** offline FHIR/terminology corpus section, fixtures, validator adapter and provenance ledger.
- **Implement:** exact package/version/rights/hashes, allowed resources/codes/references and prohibited identifier/writeback examples.
- **Prove:** unknown code/resource/profile, narrative/identifier/date canaries, reference break and independent validation.
- **Stop/hand off:** unavailable lawful terminology makes clinical conformance `NOT_EVALUABLE`; no source writeback or certification.
- **Unlocks:** `P5-T22`.

## P5-T02I — Admit the DICOM/DICOMweb WSI and ANN corpus

- **Outcome:** Mirror the exact bounded DICOM WSI/ANN and read-only DICOMweb artifacts, confidentiality profiles, adversarial objects and two independent client/validator fixtures.
- **Depends on:** `P5-T02` `MERGED`.
- **External prerequisites:** label=EP-P5-DICOM-TOOLS; kind=TOOL_OR_IMPLEMENTATION; requires=AVAILABLE; accountable=Clinical interoperability lead; validity=exact standard revision validator reader and license hashes remain unchanged through P5-T26 closure; evidence=SignedDICOMToolAdmissionReceipt.
- **Read first:** Clinical/Imaging Interoperability DICOM boundary and standards-corpus framework.
- **Change surface:** offline DICOM/DICOMweb corpus section, fixtures, validator adapters and provenance ledger.
- **Implement:** exact SOP/service/profile/version/rights/hashes, geometry/dimension/UID/time/code policy and read-only request fixtures.
- **Prove:** private/unknown tags, UID/time/code/geometry/frame/pixel/OCR canaries, write attempts and independent validation/reads.
- **Stop/hand off:** paid certification is not required, but unavailable lawful normative inputs make the claim `NOT_EVALUABLE`.
- **Unlocks:** `P5-T23`, `P5-T24`, `P5-T25`.

## P5-T02J — Admit the OME-Zarr corpus

- **Outcome:** Mirror the exact declared OME-Zarr representation/version, metadata/array examples, hostile stores and two independent reader/validator fixtures.
- **Depends on:** `P5-T02` `MERGED`.
- **Read first:** Clinical/Imaging Interoperability OME-Zarr boundary and standards-corpus framework.
- **Change surface:** offline OME-Zarr corpus section, fixtures, validator adapter and provenance ledger.
- **Implement:** exact version/rights/hashes, supported multiscale/metadata subset and privacy-minimized derivative examples.
- **Prove:** malformed dimensions/chunks/metadata, unknown extension, source-identity leak, hash mismatch and independent readers.
- **Stop/hand off:** OME-Zarr remains a bounded derivative/export, not authority or a universal format claim.
- **Unlocks:** `P5-T25A`.

## P5-T03 — Implement LTI 1.3 Core Tool launch

- **Outcome:** Manually registered issuers/clients/deployments launch only through LTI OIDC, mapping `(issuer, client_id, sub)` to an existing Principal/Membership; `deployment_id` authorizes but does not identify.
- **Depends on:** `P2-T06`, `P5-T01`, `P5-T02A` `MERGED`.
- **Read first:** Learning Interoperability LTI/external identity, Governed Workflows identity.
- **Change surface:** Gateway LTI adapter, minimal control ingress, launch/registration UI and tests.
- **Implement:** validate the exact OIDC/JWK/message tuple, map only pre-existing Principal/Membership subjects and persist bounded Gateway exchange/replay evidence without creating identity.
- **Prove:** unknown issuer/client/deployment/key/sub, nonce/state/replay/clock/origin/return target, email change and cross-Institution attacks.
- **Stop/hand off:** no general OIDC SSO, dynamic registration, email join or just-in-time identity creation.
- **Unlocks:** `P5-T04`, `P5-T09`.

## P5-T04 — Implement LTI Deep Linking

- **Outcome:** Exact versioned Lessons, WSI assets, Assessments and Class Sessions can be selected and returned through the frozen LTI Deep Linking profile without changing owner truth.
- **Depends on:** `P5-T02A`, `P5-T03`, `P4-T03`, `P4-T15`, and `P4-T27` `MERGED`.
- **Read first:** Learning Interoperability LTI profile and Gateway receipt schemas.
- **Change surface:** Gateway Deep Linking adapter/selection UI and tests.
- **Implement:** exact target type/version/hash, registered deployment/audience/return URI and signed response with no mutable alias.
- **Prove:** disallowed/stale/wrong-Institution target, return URI/audience/replay/key rotation and unsupported message/profile.
- **Stop/hand off:** selection never publishes or copies Catalog/Imaging/Assessment/Live authority.
- **Unlocks:** `P5-T09`; `P5-T04A` and `P5-T04B` remain independently gated by their own Depends fields.

## P5-T04A — Implement LTI NRPS reconciliation

- **Outcome:** Consume a bounded registered NRPS roster only to reconcile reviewed identity/enrollment proposals against existing Trust/Catalog authority.
- **Depends on:** `P5-T02A`, `P5-T03`, and `P4-T04` `MERGED`.
- **Read first:** Learning Interoperability NRPS profile and Trust/Catalog identity ownership.
- **Change surface:** Gateway NRPS client, reconciliation/mapping UI, proposal adapter and tests.
- **Implement:** paging/limits, opaque external identity mapping, reviewed differences, retry/expiry and no direct owner writes.
- **Prove:** unknown/duplicate subject, roster mismatch, endpoint outage/page loop, replay, withdrawal and cross-Institution mapping.
- **Stop/hand off:** NRPS cannot create Principal, Membership or Enrollment authority.
- **Unlocks:** `P5-T09`.

## P5-T04B — Implement LTI AGS Grade delivery

- **Outcome:** Deliver only an approved immutable local Grade through registered AGS line-item/score endpoints and record remote acknowledgement without changing local Grade truth.
- **Depends on:** `P5-T02A`, `P5-T03`, and `P4-T27` `MERGED`.
- **Read first:** Learning Interoperability AGS profile, Assessment Grade ownership and Gateway delivery receipts.
- **Change surface:** Gateway AGS adapter/delivery worker/status UI and tests.
- **Implement:** exact Grade/evidence/line-item/endpoint binding, bounded retry/terminal abandonment, credential rotation and remote acknowledgement.
- **Prove:** unapproved/changed Grade, wrong learner/line item, endpoint outage/retry/replay, key rotation and conflicting response.
- **Stop/hand off:** AGS cannot create, modify, revoke or roll back local Grade authority.
- **Unlocks:** `P5-T09` and Golden Journey G23.

## P5-T05 — Implement OneRoster Consumer profiles

- **Outcome:** Registered read-only OneRoster REST 1.2 and administrator-controlled atomic CSV 1.2.1 sets create reviewed Catalog proposals for only the frozen resource types.
- **Depends on:** `P4-T04`, `P5-T01`, `P5-T02B` `MERGED`.
- **Read first:** Learning Interoperability OneRoster profile.
- **Change surface:** batch importer, mapping/quarantine UI, Catalog proposal handler and fixtures.
- **Implement:** parse bounded REST pages and atomic CSV sets into immutable reviewed proposals, preserve mapping/rejection evidence and let Catalog alone accept new owner versions.
- **Prove:** >=100,000 rows; partial/duplicate/oversized/cross-file-invalid sets, REST outage, ambiguous identity, replay and disabled import.
- **Stop/hand off:** no OneRoster writes/deletes, email joins or silent Catalog authority transfer.
- **Unlocks:** `P5-T09`.

## P5-T06 — Implement the QTI declared subset

- **Outcome:** Import/export only the frozen QTI 3.0.1 Assessment/Section/Item subset for basic auto-scoreable, hotspot and shared-stimulus interactions into reviewed Assessment proposals.
- **Depends on:** every `P4-T22A`–`P4-T22I`, `P5-T01`, and `P5-T02C` `MERGED`.
- **Read first:** Learning Interoperability QTI profile, Assessment item contracts.
- **Change surface:** batch parser/writer, quarantine/preview UI and fixtures/tests.
- **Implement:** parse and serialize only the declared QTI subset, quarantine executable/unknown content and submit immutable reviewed proposals to Assessment without bypassing item publication.
- **Prove:** >=10,000 items, round trip, manifests/resources/rights, hostile executable/URL/bomb/traversal input, unknown extension and unsupported interaction.
- **Stop/hand off:** essay/native WSI/Results Reporting/CAT/PCI are not flattened or falsely labelled QTI.
- **Unlocks:** `P5-T09`.

## P5-T07 — Implement CASE 1.1 read-only consumption

- **Outcome:** Registered framework packages/documents/items/associations become immutable versioned Catalog references only after review.
- **Depends on:** `P4-T03`, `P5-T01`, `P5-T02D` `MERGED`.
- **Read first:** Learning Interoperability CASE profile.
- **Change surface:** batch CASE adapter, mapping/review UI, Catalog proposals and tests.
- **Implement:** validate packages/documents/items/associations, preserve source/version hashes and submit only reviewed immutable framework-reference proposals to Catalog.
- **Prove:** changed/unknown framework version/extension, unresolved association, endpoint outage, wrong Institution and immutable reference behavior.
- **Stop/hand off:** never edit external frameworks or silently retarget published content.
- **Unlocks:** `P5-T09`.

## P5-T08 — Implement minimized optional Caliper delivery

- **Outcome:** Disabled-by-default Caliper 1.2 emits only approved minimized Session/Reading/Media/Assessment/Tool Use events through Gateway without affecting local state.
- **Depends on:** `P4-T18`, `P4-T27`, `P5-T01`, `P5-T02G` `MERGED`.
- **Read first:** Learning Interoperability Caliper boundary, privacy classifications.
- **Change surface:** outbound adapter, privacy policy UI, bounded delivery queue and tests.
- **Implement:** add disabled-by-default minimized event mapping, bounded queue/retry/expiry, registration revocation and forbidden-field enforcement without coupling local commits to delivery.
- **Prove:** endpoint outage, replay/retry/abandon, revocation, opaque subject, queue cap and forbidden-field inspection.
- **Stop/hand off:** no pixels/coordinates, answers, prompts/free text, clinical data, email or Tool Launch; optional failure cannot roll back local work.
- **Unlocks:** `P5-T09`.

## P5-T09 — Reconcile learning-standards conformance and journey results

- **Outcome:** Reconcile independently closed LTI/Advantage, OneRoster, QTI, CASE and optional-Caliper results plus the closed cross-profile journey into one terminal learning-standards result.
- **Depends on:** current terminal `SUCCESS` from `P5-T09D`, `P5-T09G`, `P5-T09J`, `P5-T09M`, `P5-T09P`, and `P5-T09S` on one immutable interop candidate/manifest tuple.
- **Read first:** all profile closure reports, cross-profile journey report and Production Qualification learning interoperability gate.
- **Change surface:** signed result aggregation and evidence index only.
- **Implement:** none; verify profile/result independence, tuple equality and complete receipt coverage before emitting one parent result.
- **Prove:** independent 100,000-row OneRoster and 10,000-item QTI thresholds, every frozen profile/fault/privacy boundary, cross-owner acceptance and final cleanup reconcile without substitution.
- **Stop/hand off:** any missing, stale, mixed-candidate or non-`SUCCESS` required child prevents parent `SUCCESS`; optional delivery remains implemented but cannot affect local owner truth.
- **Unlocks:** Phase 5 closure and Golden Journey G05–G06/G23 only on current `P5-T09=SUCCESS`.

## P5-T09A — Freeze and dry-run the learning-interoperability harness

- **Outcome:** Freeze separate immutable manifests and receipt cursors for each protocol family plus the cross-profile journey, then run only reduced non-qualifying harness checks.
- **Depends on:** `P5-T03`–`P5-T08`, including `P5-T04A` and `P5-T04B`, `MERGED`.
- **External prerequisites:** label=EP-P5-INTEROP-TOOLS; kind=TOOL_OR_IMPLEMENTATION; requires=AVAILABLE; accountable=Learning interoperability lead; validity=official reference and two independent implementation versions licenses and hashes remain unchanged through P5-T09 closure; evidence=SignedInteropToolAdmissionReceipt | label=EP-P5-INTEROP-CORPUS; kind=DATA_OR_CORPUS; requires=AVAILABLE; accountable=Learning interoperability lead; validity=exact official reference adversarial roster item and journey fixture hashes remain unchanged through P5-T09 closure; evidence=SignedInteropCorpusAdmissionReceipt.
- **Read first:** admitted P5-T02A–P5-T02G manifests and Production Qualification learning interoperability gate.
- **Change surface:** interop harness, per-profile manifests, observers, evidence schemas and runbooks only.
- **Implement:** encode independent profile identities/workloads, cross-profile handoffs, retry/fault schedules, receipt cursors and cleanup; dry-run each adapter interface without emitting conformance.
- **Prove:** every external tool/corpus resolves offline, profile manifests cannot satisfy one another, observers detect drift/gaps and reduced cleanup completes.
- **Stop/hand off:** unresolved tool, corpus, profile, threshold or cleanup ambiguity is `NOT_EVALUABLE` and blocks every launch.
- **Unlocks:** `P5-T09B`, `P5-T09E`, `P5-T09H`, `P5-T09K`, and `P5-T09N`.

## P5-T09B — Start LTI 1.3 and Advantage conformance

- **Outcome:** Admit and start only the frozen LTI Core, Deep Linking, NRPS and AGS profile-family workload with immutable tool/process identities and receipt cursor.
- **Depends on:** `P5-T09A` `MERGED`, its LTI manifest `FROZEN`, and current `EP-P5-INTEROP-TOOLS` and `EP-P5-INTEROP-CORPUS` receipt heads.
- **Read first:** frozen LTI manifest and launch runbook.
- **Change surface:** LTI admission/start evidence only.
- **Implement:** none; start the declared LTI workload and observers without executing any other protocol family.
- **Prove:** exact issuer/client/deployment/tool/fixture tuple, observer liveness and forward receipt movement.
- **Stop/hand off:** partial profile admission or drift is `NOT_EVALUABLE`; start remains `RUNNING`.
- **Unlocks:** `P5-T09C`.

## P5-T09C — Monitor and audit LTI 1.3 and Advantage conformance

- **Outcome:** Execute and observe only the full LTI launch/deep-link/NRPS/AGS official, adversarial and independent-tool matrix.
- **Depends on:** active `P5-T09B` with matching immutable LTI manifest.
- **Read first:** latest LTI cursor, fault schedule and open incidents.
- **Change surface:** LTI observations, faults and incident evidence only.
- **Implement:** none; execute nonce/state/replay/rotation/mapping/outage/retry/grade-return cases and preserve all receipts.
- **Prove:** every frozen LTI profile and negative boundary completes without identity or owner-authority transfer.
- **Stop/hand off:** missing independent-tool coverage, receipt gap or drift follows the frozen disposition.
- **Unlocks:** `P5-T09D` after workload and cleanup terminate.

## P5-T09D — Close LTI 1.3 and Advantage conformance

- **Outcome:** Reconcile the complete LTI family workload into one signed profile-family result.
- **Depends on:** completed `P5-T09B`/`P5-T09C` and unchanged LTI manifest/candidate.
- **Read first:** frozen LTI manifest and terminal receipt range.
- **Change surface:** LTI signed aggregation and cleanup only.
- **Implement:** none; validate complete coverage and emit the terminal LTI result.
- **Prove:** exact workload, all profile outcomes/faults, two independent implementations and terminal cleanup.
- **Stop/hand off:** incomplete workload is `PARTIAL`; missing trustworthy evidence is `NOT_EVALUABLE`.
- **Unlocks:** `P5-T09Q` after all other profile families close.

## P5-T09E — Start OneRoster conformance

- **Outcome:** Admit and start only the frozen REST 1.2 and CSV 1.2.1 OneRoster workload with immutable tool/process identities and receipt cursor.
- **Depends on:** `P5-T09A` `MERGED`, its OneRoster manifest `FROZEN`, and current `EP-P5-INTEROP-TOOLS` and `EP-P5-INTEROP-CORPUS` receipt heads.
- **Read first:** frozen OneRoster manifest and launch runbook.
- **Change surface:** OneRoster admission/start evidence only.
- **Implement:** none; start the declared OneRoster workload and observers without another protocol family.
- **Prove:** exact tools, 100,000-row fixture root, observer liveness and forward receipt movement.
- **Stop/hand off:** partial admission or drift is `NOT_EVALUABLE`; start remains `RUNNING`.
- **Unlocks:** `P5-T09F`.

## P5-T09F — Monitor and audit OneRoster conformance

- **Outcome:** Execute and observe only the full 100,000-row OneRoster REST/CSV official, adversarial and independent-tool workload.
- **Depends on:** active `P5-T09E` with matching immutable OneRoster manifest.
- **Read first:** latest OneRoster cursor, fault schedule and incidents.
- **Change surface:** OneRoster observations, faults and incident evidence only.
- **Implement:** none; execute pagination, atomic-set, duplicate, ambiguity, outage, retry and disabled-import cases.
- **Prove:** exact row count, deterministic proposals, bounded resources and zero silent Catalog authority transfer.
- **Stop/hand off:** reduced row count, receipt gap or drift follows the frozen disposition.
- **Unlocks:** `P5-T09G` after workload and cleanup terminate.

## P5-T09G — Close OneRoster conformance

- **Outcome:** Reconcile the complete independent 100,000-row OneRoster workload into one signed profile result.
- **Depends on:** completed `P5-T09E`/`P5-T09F` and unchanged OneRoster manifest/candidate.
- **Read first:** frozen OneRoster manifest and terminal receipt range.
- **Change surface:** OneRoster signed aggregation and cleanup only.
- **Implement:** none; validate workload, mappings, faults and cleanup and emit the terminal result.
- **Prove:** both transport forms, exact independent threshold, two independent implementations and complete cleanup.
- **Stop/hand off:** incomplete workload is `PARTIAL`; missing trustworthy evidence is `NOT_EVALUABLE`.
- **Unlocks:** `P5-T09Q` after all other profile families close.

## P5-T09H — Start QTI conformance

- **Outcome:** Admit and start only the frozen QTI 3.0.1 declared-subset workload with immutable tool/process identities and receipt cursor.
- **Depends on:** `P5-T09A` `MERGED`, its QTI manifest `FROZEN`, and current `EP-P5-INTEROP-TOOLS` and `EP-P5-INTEROP-CORPUS` receipt heads.
- **Read first:** frozen QTI manifest and launch runbook.
- **Change surface:** QTI admission/start evidence only.
- **Implement:** none; start the declared QTI workload and observers without another protocol family.
- **Prove:** exact tools, 10,000-item fixture root, observer liveness and forward receipt movement.
- **Stop/hand off:** partial admission or drift is `NOT_EVALUABLE`; start remains `RUNNING`.
- **Unlocks:** `P5-T09I`.

## P5-T09I — Monitor and audit QTI conformance

- **Outcome:** Execute and observe only the full 10,000-item QTI official, adversarial, round-trip and independent-tool workload.
- **Depends on:** active `P5-T09H` with matching immutable QTI manifest.
- **Read first:** latest QTI cursor, fault schedule and incidents.
- **Change surface:** QTI observations, faults and incident evidence only.
- **Implement:** none; execute package/resource/right, hostile archive, unsupported interaction and owner-acceptance cases.
- **Prove:** exact item count, declared subset round trip, bounded resources and no unsupported flattening.
- **Stop/hand off:** reduced item count, receipt gap or drift follows the frozen disposition.
- **Unlocks:** `P5-T09J` after workload and cleanup terminate.

## P5-T09J — Close QTI conformance

- **Outcome:** Reconcile the complete independent 10,000-item QTI workload into one signed profile result.
- **Depends on:** completed `P5-T09H`/`P5-T09I` and unchanged QTI manifest/candidate.
- **Read first:** frozen QTI manifest and terminal receipt range.
- **Change surface:** QTI signed aggregation and cleanup only.
- **Implement:** none; validate workload, round trips, faults and cleanup and emit the terminal result.
- **Prove:** exact independent threshold, declared interactions, two independent implementations and complete cleanup.
- **Stop/hand off:** incomplete workload is `PARTIAL`; missing trustworthy evidence is `NOT_EVALUABLE`.
- **Unlocks:** `P5-T09Q` after all other profile families close.

## P5-T09K — Start CASE conformance

- **Outcome:** Admit and start only the frozen CASE 1.1 read-only workload with immutable tool/process identities and receipt cursor.
- **Depends on:** `P5-T09A` `MERGED`, its CASE manifest `FROZEN`, and current `EP-P5-INTEROP-TOOLS` and `EP-P5-INTEROP-CORPUS` receipt heads.
- **Read first:** frozen CASE manifest and launch runbook.
- **Change surface:** CASE admission/start evidence only.
- **Implement:** none; start the declared CASE workload and observers without another protocol family.
- **Prove:** exact tools/framework graph, observer liveness and forward receipt movement.
- **Stop/hand off:** partial admission or drift is `NOT_EVALUABLE`; start remains `RUNNING`.
- **Unlocks:** `P5-T09L`.

## P5-T09L — Monitor and audit CASE conformance

- **Outcome:** Execute and observe only the full CASE official, adversarial and independent-tool graph workload.
- **Depends on:** active `P5-T09K` with matching immutable CASE manifest.
- **Read first:** latest CASE cursor, fault schedule and incidents.
- **Change surface:** CASE observations, faults and incident evidence only.
- **Implement:** none; execute changed/unknown framework, broken/cyclic association, outage and immutable-reference cases.
- **Prove:** declared read-only subset, independent-tool agreement and zero external-framework or Catalog mutation bypass.
- **Stop/hand off:** missing graph coverage, receipt gap or drift follows the frozen disposition.
- **Unlocks:** `P5-T09M` after workload and cleanup terminate.

## P5-T09M — Close CASE conformance

- **Outcome:** Reconcile the complete CASE workload into one signed profile result.
- **Depends on:** completed `P5-T09K`/`P5-T09L` and unchanged CASE manifest/candidate.
- **Read first:** frozen CASE manifest and terminal receipt range.
- **Change surface:** CASE signed aggregation and cleanup only.
- **Implement:** none; validate workload, graph faults and cleanup and emit the terminal result.
- **Prove:** every declared resource/association case, two independent implementations and complete cleanup.
- **Stop/hand off:** incomplete workload is `PARTIAL`; missing trustworthy evidence is `NOT_EVALUABLE`.
- **Unlocks:** `P5-T09Q` after all other profile families close.

## P5-T09N — Start optional Caliper conformance

- **Outcome:** Admit and start only the frozen disabled-by-default privacy-minimized Caliper workload with immutable consumer/process identities and receipt cursor.
- **Depends on:** `P5-T09A` `MERGED`, its Caliper manifest `FROZEN`, and current `EP-P5-INTEROP-TOOLS` and `EP-P5-INTEROP-CORPUS` receipt heads.
- **Read first:** frozen Caliper manifest and launch runbook.
- **Change surface:** Caliper admission/start evidence only.
- **Implement:** none; start the declared optional-delivery workload and observers without another protocol family.
- **Prove:** exact consumers/fixtures, disabled-default state, observer liveness and forward receipt movement.
- **Stop/hand off:** partial admission or drift is `NOT_EVALUABLE`; local learning remains independent.
- **Unlocks:** `P5-T09O`.

## P5-T09O — Monitor and audit optional Caliper conformance

- **Outcome:** Execute and observe only the full minimized Caliper official, adversarial and independent-consumer workload.
- **Depends on:** active `P5-T09N` with matching immutable Caliper manifest.
- **Read first:** latest Caliper cursor, fault schedule and incidents.
- **Change surface:** Caliper observations, faults and incident evidence only.
- **Implement:** none; execute endpoint outage, retry/abandon, revocation, queue-cap and forbidden-field cases.
- **Prove:** only approved minimized profiles leave the Gateway and every failure leaves local work unchanged.
- **Stop/hand off:** sensitive-field emission is `NEGATIVE`; receipt gaps or drift follow the frozen disposition.
- **Unlocks:** `P5-T09P` after workload and cleanup terminate.

## P5-T09P — Close optional Caliper conformance

- **Outcome:** Reconcile the complete Caliper workload into one signed optional-profile result.
- **Depends on:** completed `P5-T09N`/`P5-T09O` and unchanged Caliper manifest/candidate.
- **Read first:** frozen Caliper manifest and terminal receipt range.
- **Change surface:** Caliper signed aggregation and cleanup only.
- **Implement:** none; validate privacy, outage, queue and cleanup evidence and emit the terminal result.
- **Prove:** two independent consumers, forbidden-field absence, local-state independence and complete cleanup.
- **Stop/hand off:** incomplete workload is `PARTIAL`; missing trustworthy evidence is `NOT_EVALUABLE`.
- **Unlocks:** `P5-T09Q` after all other profile families close.

## P5-T09Q — Start the cross-profile learning journey

- **Outcome:** Start one immutable OneRoster/CASE/QTI-to-owner, LTI launch/deep-link, Assessment/AGS and optional-Caliper journey after every independent profile result succeeds.
- **Depends on:** current terminal `SUCCESS` from `P5-T09D`, `P5-T09G`, `P5-T09J`, `P5-T09M`, and `P5-T09P` on the same candidate and current cross-profile manifest head `FROZEN`.
- **Read first:** frozen journey manifest and Golden Journey G05–G06/G23 handoffs.
- **Change surface:** cross-profile admission/start evidence only.
- **Implement:** none; start the ordered owner-handoff journey and observers without rerunning or merging profile claims.
- **Prove:** exact candidate/manifest equality, owner endpoints ready, observers live and receipt progression begins.
- **Stop/hand off:** missing profile success, drift or partial admission is `NOT_EVALUABLE`; start remains `RUNNING`.
- **Unlocks:** `P5-T09R`.

## P5-T09R — Monitor and audit the cross-profile learning journey

- **Outcome:** Observe the full ordered journey through immutable cursors while injecting the frozen outage/retry/replay/rotation/mapping/quarantine/privacy faults.
- **Depends on:** active `P5-T09Q` with matching immutable cross-profile manifest.
- **Read first:** latest journey cursor, fault schedule and open incidents.
- **Change surface:** journey observations, faults and incident evidence only.
- **Implement:** none; execute only the frozen cross-profile handoffs and preserve each owner acceptance/rejection receipt.
- **Prove:** no missing/reordered handoff, no cross-context SQL, no transport-owned truth and no optional-delivery rollback of local work.
- **Stop/hand off:** owner divergence, receipt gap or changed input follows the frozen disposition.
- **Unlocks:** `P5-T09S` after journey and cleanup terminate.

## P5-T09S — Close the cross-profile learning journey

- **Outcome:** Reconcile the complete ordered learning-standards journey into one signed integration result.
- **Depends on:** completed `P5-T09Q`/`P5-T09R` and unchanged journey manifest/candidate.
- **Read first:** frozen journey manifest and terminal receipt range.
- **Change surface:** journey signed aggregation and cleanup only.
- **Implement:** none; validate all owner transitions, faults and cleanup and emit the terminal journey result.
- **Prove:** exact ordered receipts for import, owner acceptance, launch, Assessment, grade delivery and optional telemetry with terminal cleanup.
- **Stop/hand off:** a missing or reordered owner receipt is `NEGATIVE`; incomplete workload is `PARTIAL`; missing trustworthy evidence is `NOT_EVALUABLE`.
- **Unlocks:** parent `P5-T09`.

## Credential Ledger

## P5-T10 — Scaffold Credential Ledger and evidence intake

- **Outcome:** Ledger owns its database, roles, migrations, outbox, issuer/verification Key Version references and immutable eligibility/evidence intake using opaque subjects.
- **Depends on:** `P4-T05`, `P4-T06A`, `P4-T27`, `P5-T00`, `P1-T04`, `P2-T04` `MERGED`.
- **Read first:** Credential Ledger context, Learning Interoperability credential section, Receipt Registry Ledger section.
- **Change surface:** Ledger module in control, migrations/contracts/tests.
- **Implement:** create the owner-local schema/repository/service seams, least-privilege role, transactional outbox, issuer/key references and idempotent eligibility-evidence intake without cross-context reads.
- **Prove:** wrong Institution/definition/subject/evidence, duplicate/stale proposal, database isolation and no Adapter Credential access.
- **Stop/hand off:** Ledger never reads Catalog/Assessment tables.
- **Unlocks:** `P5-T11`–`P5-T15`.

## P5-T11 — Implement dual-authorized issuance decisions

- **Outcome:** Course-completion and Assessment outcomes create immutable Achievement Credentials only after exact independent approvals and current step-up.
- **Depends on:** `P2-T05`, `P5-T10` `MERGED`.
- **Read first:** Role Matrix credential pairs, Credential context.
- **Change surface:** issuance commands/service and Instructor/Assessor/Moderator UI/tests.
- **Implement:** definition/evidence/subject/validity/issuer/hash binding, <=7-year validity and duplicate policy.
- **Prove:** self/material-contributor approval, reused/stale/changed/replayed approval, revoked role and restart.
- **Stop/hand off:** no automatic badge/credential on completion or Grade.
- **Unlocks:** `P5-T12`.

## P5-T12 — Generate signed Open Badges 3.0 and CLR 2.0 documents

- **Outcome:** Produce only the frozen private credential classes as immutable JSON-LD using exact context ordering, RDFC-1.0, SHA-256 and Ed25519 `eddsa-rdfc-2022` Multikey proofs.
- **Depends on:** `P5-T02E`, `P5-T02F`, and `P5-T11` `MERGED`.
- **Read first:** Learning Interoperability credentials, exact frozen context corpus.
- **Change surface:** Ledger serializer/signing, schemas/vectors and offline kit.
- **Implement:** canonicalize the frozen JSON-LD classes, sign only with versioned owner keys, embed bounded evidence/status references and package offline contexts/verifier inputs without private keys.
- **Prove:** golden vectors, reordered/unknown/remote context, unsupported proof/JWT, wrong key/purpose and canonicalization mismatch.
- **Stop/hand off:** no public profile/REST Host/wallet/blockchain/mutable resolver or issuer private-key export.
- **Unlocks:** `P5-T13`, `P5-T14`.

## P5-T13 — Implement Verification Grants, bounded status lists, and offline verification

- **Outcome:** Purpose/audience-bound Verification Grants authorize minimum-disclosure online/local verification; grants revoke/expire audibly, and authorized snapshots check schema, signature, issuer material, validity and bounded status lists using `statusSize=1` and >=131,072 entries.
- **Depends on:** `P5-T12` `MERGED`.
- **Read first:** Credential context verification terms and Production Qualification Ledger gate.
- **Change surface:** Ledger Verification Grant/status/verifier schema/service/API/UI, bitstring library, audit/deletion adapter and adversarial tests.
- **Implement:** exact credential/class/purpose/audience/disclosure/expiry scope, grant issue/revoke/expire, snapshot binding and minimum returned fields; offline results remain as-of.
- **Prove:** absent/revoked/expired/replayed/changed grant, wrong audience/purpose/credential, deletion/retention, undersized/oversized/bomb/out-of-range/noncanonical list, stale snapshot and key/status tamper.
- **Stop/hand off:** offline result is as-of and never claims current network status.
- **Unlocks:** `P5-T14`, `P5-T15`.

## P5-T14 — Implement supersession, expiry, revocation, and rotation

- **Outcome:** Immutable Credentials transition truthfully through active/superseded/expired/revoked states using Administrator-to-independent-Moderator status approvals and bounded old/new verification keys.
- **Depends on:** `P2-T05`, `P5-T11`–`P5-T13` `MERGED`.
- **Read first:** Credential context, Role Matrix status pair, Governed Workflows deletion boundary.
- **Change surface:** Ledger lifecycle/scheduler/status UI and tests.
- **Implement:** append lifecycle transitions, automatic expiry, approved status changes, bounded verification-key overlap and truthful recipient-held-copy notices without rewriting issued documents.
- **Prove:** changed/replayed/stale proposal, automatic expiry, compromised key rotation, restore and recipient-held-copy semantics.
- **Stop/hand off:** never rewrite or claim erasure of an issued external document.
- **Unlocks:** `P5-T15`, deletion/portability.

## P5-T15 — Reconcile the complete Credential Ledger gate

- **Outcome:** Reconcile merged export/custody/deletion behavior and the closed 10,000-operation campaign into one terminal Credential Ledger phase result.
- **Depends on:** `P5-T15A` `MERGED` and current `P5-T15E=SUCCESS` on the identical Credential manifest and phase candidate.
- **Read first:** Credential implementation receipt, campaign closure report, Production Qualification Credential Ledger gate and Receipt Registry.
- **Change surface:** signed result aggregation and evidence index only.
- **Implement:** none; verify implementation/campaign tuple equality and complete custody, deletion, restore, key/status and privacy evidence before emitting the parent result.
- **Prove:** all frozen issuance/online-and-offline verification/supersession/expiry/revocation operations, status-list bounds, rotation, tamper, restore, custody and deletion evidence reconcile.
- **Stop/hand off:** missing or stale implementation/evidence, mixed candidates or non-`SUCCESS` campaign prevents parent `SUCCESS`; Phase 6 portability remains a separate gate.
- **Unlocks:** Phase 5 closure, portability and Golden Journey G24–G25 only on current `P5-T15=SUCCESS`.

## P5-T15A — Implement Credential export, custody, and deletion semantics

- **Outcome:** Provide authenticated minimum-disclosure export and Verification Snapshots, governed custody-transfer proposals and deletion-to-revocation behavior without exporting issuer private keys.
- **Depends on:** `P5-T12`–`P5-T14`, `P2-T14` `MERGED`.
- **Read first:** Credential Ledger context, Governed Workflows deletion/custody boundaries and Receipt Registry.
- **Change surface:** Ledger/Gateway export API/UI/batch, custody commands, deletion adapter, audit/outbox, tests and runbook.
- **Implement:** bind export to Verification Grants and exact audience/purpose; create immutable custody receipts; revoke/status deleted credentials while crypto-erasing owner plaintext and truthfully retaining recipient-held copies.
- **Prove:** wrong audience/purpose, replay, offline/as-of verification, custody accept/reject/retry, Legal Hold, delete/restore, key absence and no public roster/profile.
- **Stop/hand off:** no public resolver, issuer-key export, silent custody, false external erasure or Phase 6 portability claim.
- **Unlocks:** `P5-T15B`.

## P5-T15B — Freeze and dry-run the Credential campaign

- **Outcome:** Freeze the exact 10,000-operation manifest, verifier/corpus/key/status/fault/observer/cleanup hashes and execute a reduced non-qualifying dry run.
- **Depends on:** `P5-T15A` `MERGED`.
- **External prerequisites:** label=EP-P5-CRED-TOOLS; kind=TOOL_OR_IMPLEMENTATION; requires=AVAILABLE; accountable=Credential qualification lead; validity=exact independent verifier versions licenses and hashes remain unchanged through P5-T15 closure; evidence=SignedCredentialVerifierAdmissionReceipt | label=EP-P5-CRED-CORPUS; kind=DATA_OR_CORPUS; requires=AVAILABLE; accountable=Credential qualification lead; validity=exact 10000-operation actor definition evidence and hostile-vector roots remain unchanged through P5-T15 closure; evidence=SignedCredentialCorpusAdmissionReceipt.
- **Read first:** Production Qualification Credential Ledger gate and accepted OB3/CLR/status-list fixtures.
- **Change surface:** credential load/adversarial harness, immutable manifest, dry-run evidence and runbook only.
- **Implement:** encode independent operation counts, online/offline verifiers, status/key/custody/deletion faults, resource observers, receipt cursors and cleanup, then run a reduced rehearsal.
- **Prove:** every actor, operation, verifier, vector, observer, fault and cleanup path resolves without product mutation.
- **Stop/hand off:** unresolved count, verifier, corpus, status-list or cleanup ambiguity is `NOT_EVALUABLE`; dry-run success is not gate success.
- **Unlocks:** `P5-T15C` only on current `P5-T15B=SUCCESS`.

## P5-T15C — Start the 10,000-operation Credential campaign

- **Outcome:** Admit and start the frozen full Credential workload with exact candidate, key/status state, verifier identities, process identities and receipt cursor.
- **Depends on:** current `P5-T15B=SUCCESS`, unchanged Credential Campaign Manifest and phase-candidate fingerprint heads, and current `EP-P5-CRED-TOOLS` and `EP-P5-CRED-CORPUS` receipt heads.
- **External prerequisites:** label=EP-P5-CRED-CAPACITY; kind=HARDWARE; requires=AVAILABLE; accountable=Credential qualification lead; validity=declared load and verifier hosts remain available and unchanged through P5-T15E; evidence=SignedCredentialCapacityAdmissionReceipt | label=EP-P5-CRED-OPERATORS; kind=HUMAN_AUTHORITY; requires=ASSIGNED; accountable=Credential qualification lead; validity=named operators remain assigned through P5-T15E; evidence=SignedCredentialOperatorAssignmentReceipt.
- **Read first:** frozen Credential manifest and launch runbook.
- **Change surface:** campaign admission/start evidence only.
- **Implement:** none; start the immutable workload and observers without product or manifest changes.
- **Prove:** exact tuple equality, full operation admission, verifiers/observers live and forward receipt movement.
- **Stop/hand off:** partial admission, missing capacity/operator or drift is `NOT_EVALUABLE`; start remains `RUNNING`.
- **Unlocks:** `P5-T15D`.

## P5-T15D — Monitor and audit the Credential campaign

- **Outcome:** Observe the complete 10,000-operation workload by receipt cursor while executing frozen online/offline, status, key, tamper, restore, custody, privacy and deletion faults.
- **Depends on:** active `P5-T15C` with matching immutable Credential manifest.
- **Read first:** latest cursor, fault schedule and open incidents.
- **Change surface:** Credential observations, faults and incident evidence only.
- **Implement:** none; execute only the frozen schedule and record operation/resource/receipt progress without changing implementation or thresholds.
- **Prove:** issuance, authenticated/offline verification, supersession, expiry and revocation counts; status-list limits; rotation/tamper/restore/custody/deletion; no private-key export.
- **Stop/hand off:** stopped worker, receipt gap, changed tuple, privacy leak or key export follows the frozen disposition without silent restart.
- **Unlocks:** `P5-T15E` after workload and cleanup terminate.

## P5-T15E — Close the Credential campaign

- **Outcome:** Reconcile the full Credential workload, faults, verifier outputs, receipts and cleanup into one terminal campaign result.
- **Depends on:** completed `P5-T15C`/`P5-T15D` and unchanged Credential manifest/candidate.
- **Read first:** frozen manifest, terminal receipt range and Production Qualification Credential Ledger gate.
- **Change surface:** signed evidence aggregation and cleanup only.
- **Implement:** none; verify exact counts, thresholds, hostile vectors, independent verification and cleanup before emitting the campaign result.
- **Prove:** complete workload and every frozen status/key/privacy/restore/custody/deletion gate with terminal cleanup.
- **Stop/hand off:** incomplete workload is `PARTIAL`; missing trustworthy evidence is `NOT_EVALUABLE`; an invariant breach is `NEGATIVE`.
- **Unlocks:** parent `P5-T15`.

## EQA

## P5-T16 — Scaffold EQA and its exclusive batch mode

- **Outcome:** EQA owns its database, role, migrations, outbox and batch reservation for Schemes, Rounds, Cases, participants, drafts, seals, scoring, reports and appeals.
- **Depends on:** `P1-T17`, `P1-T18`, `P2-T27` `MERGED` and current `P3-T18=SUCCESS`, `P4-T30=SUCCESS`.
- **Read first:** EQA context, Governed Workflows EQA, service cells.
- **Change surface:** EQA module/migrations/contracts/batch mode and tests.
- **Implement:** create the owner-local schema/repository/service seams, transactional outbox and exclusive batch-mode lifecycle for Schemes through Appeals without reusing learner Assessment authority.
- **Prove:** role/database isolation, mode conflict, restart and no Assessment/Catalog authority reuse.
- **Stop/hand off:** EQA participant is an Institution, not a learner.
- **Unlocks:** `P5-T17`–`P5-T20`.

## P5-T17 — Implement Schemes, Rounds, Cases, and participant access

- **Outcome:** EQA Managers build immutable 100-case rounds with Institution participants, exact Imaging/Catalog references, deadlines and private two-staff collaboration.
- **Depends on:** `P2-T10`, `P5-T00`, `P5-T16` `MERGED`.
- **Read first:** EQA context and Role Matrix EQA grants.
- **Change surface:** EQA service/manager+participant UI and tests.
- **Implement:** version immutable Scheme/Round/Case definitions, participant grants and exact Imaging/Catalog references with private two-staff workspaces and bounded deadlines.
- **Prove:** wrong participant/Institution, changed case/asset, late enrollment, direct Clinical reference, authorization and accessibility.
- **Stop/hand off:** EQA consumes only separately authorized Imaging/Catalog versions.
- **Unlocks:** `P5-T18`, `P5-T19`.

## P5-T18 — Implement collaborative drafts and irreversible seal

- **Outcome:** Two participant staff may revise one ordered draft; one named EQA Submitter under current step-up creates one immutable Sealed Submission at/before trusted deadline.
- **Depends on:** `P5-T17` `MERGED`.
- **Read first:** EQA context seal semantics and Role Matrix single-person action.
- **Change surface:** revision/seal service and participant UI/tests.
- **Implement:** append ordered collaborative revisions, enforce named submitter/step-up/deadline and atomically create one irreversible sealed submission with idempotent receipt.
- **Prove:** reconnect/reconcile, restart 30 seconds before deadline, final-minute duplicate, second submitter, clock rollback and post-seal edit.
- **Stop/hand off:** no reopen/replace; correction proceeds only through Appeal.
- **Unlocks:** `P5-T19`.

## P5-T19 — Score, adjudicate, report, suppress, and appeal

- **Outcome:** Named deterministic Scoring Version plus accountable human adjudication creates own-participant reports, suppresses aggregates below ten and accepts 30-day Appeals.
- **Depends on:** `P5-T18` `MERGED`.
- **Read first:** EQA context and Production Qualification EQA gate.
- **Change surface:** scoring/report/appeal service and role-separated UI/tests.
- **Implement:** apply versioned deterministic scoring, preserve accountable adjudication, generate participant-private reports, suppress aggregates below ten and append 30-day Appeal outcomes.
- **Prove:** 30,000 scores, 300 reports, nine/ten threshold, 30 Appeals, cross-participant access, AI attempt, changed seal and expiry.
- **Stop/hand off:** no AI score, Grade, Credential or learner Assessment authority.
- **Unlocks:** `P5-T20`.

## P5-T20 — Freeze and dry-run the EQA engineering campaign

- **Outcome:** Freeze the 300-Institution x two-staff x 100-case x 120-minute manifest, thresholds/faults/observers and execute a reduced non-qualifying lifecycle dry run.
- **Depends on:** `P5-T16`–`P5-T19` `MERGED`.
- **External prerequisites:** label=EP-P5-EQA-CORPUS; kind=DATA_OR_CORPUS; requires=AVAILABLE; accountable=EQA qualification lead; validity=exact 300-Institution two-staff 100-case actor and fixture hashes remain unchanged through P5-T20C; evidence=SignedEQACorpusAdmissionReceipt.
- **Read first:** Production Qualification EQA gate.
- **Change surface:** load/evidence harness, immutable manifest and dry-run evidence only; fixes are separate implementation tasks.
- **Implement:** encode the workload, actors, thresholds, observers, fault schedule, receipt cursors and cleanup, then execute a reduced non-qualifying lifecycle rehearsal.
- **Prove:** every actor/case/fault/observer/receipt/cleanup resolves and representative reconnect/restart/final-minute seal/report/appeal/deletion paths reconcile.
- **Stop/hand off:** dry-run success is not the full campaign result; unresolved fixture/harness ambiguity blocks launch.
- **Unlocks:** `P5-T20A`.

## P5-T20A — Start the full EQA engineering campaign

- **Outcome:** Admit the unchanged phase candidate and begin the full 300 x two x 100 x 120-minute EQA run with immutable start evidence and receipt cursor.
- **Depends on:** current `P5-T20=SUCCESS` with unchanged EQA Campaign Manifest, phase-candidate fingerprint and `EP-P5-EQA-CORPUS` receipt heads.
- **External prerequisites:** label=EP-P5-EQA-CAPACITY; kind=HARDWARE; requires=AVAILABLE; accountable=EQA qualification lead; validity=declared load resources remain available and unchanged through P5-T20C; evidence=SignedEQACapacityAdmissionReceipt | label=EP-P5-EQA-OPERATORS; kind=HUMAN_AUTHORITY; requires=ASSIGNED; accountable=EQA qualification lead; validity=named operators remain assigned through P5-T20C; evidence=SignedEQAOperatorAssignmentReceipt.
- **Read first:** frozen EQA campaign manifest and launch runbook.
- **Change surface:** campaign admission/start evidence only.
- **Implement:** none; admit and start the immutable EQA workload, workers, observers and receipt cursor without product or manifest changes.
- **Prove:** exact tuple/manifest, all workers/observers live, full participants/cases admitted and receipts advance.
- **Stop/hand off:** missing capacity/operator, drift or incomplete admission is `NOT_EVALUABLE`; start is `RUNNING`, never `SUCCESS`.
- **Unlocks:** `P5-T20B`.

## P5-T20B — Monitor the active EQA engineering campaign

- **Outcome:** Observe the full interval by receipt cursor, execute scheduled 5% reconnect/restart/final-minute sealing cases and record incidents without retaining implementation context.
- **Depends on:** active `P5-T20A` with matching immutable manifest.
- **Read first:** latest cursor, fault schedule and only open incidents.
- **Change surface:** campaign observations/fault evidence and incidents only.
- **Implement:** none; observe live receipt/resource progress and execute only the frozen reconnect, restart and final-minute fault schedule.
- **Prove:** live worker/resource/receipt progress, no silent gap/drift and every declared fault at its exact boundary.
- **Stop/hand off:** stopped worker, missing interval or changed input follows the frozen disposition; do not restart history silently.
- **Unlocks:** `P5-T20C` after full elapsed interval/workload.

## P5-T20C — Close the EQA engineering campaign

- **Outcome:** Reconcile the complete 300-Institution x two-staff x 100-case x 120-minute run, revisions/reconnect/restart/seals, 30,000 scores, 300 reports, 30 appeals, retention/deletion/restore and cleanup into one terminal result.
- **Depends on:** completed `P5-T20A`/`P5-T20B` and unchanged manifest/candidate.
- **Read first:** frozen manifest, terminal receipt range and Production Qualification EQA gate.
- **Change surface:** signed evidence aggregation and cleanup only.
- **Implement:** none; reconcile the full immutable workload, faults, reports, appeals, retention/deletion/restore and cleanup into one terminal result.
- **Prove:** full elapsed workload, frozen latency/integrity/resource/privacy thresholds, zero duplicate seal/cross-tenant leak/mutation and all terminal receipts.
- **Stop/hand off:** smaller/incomplete workload is `PARTIAL`; missing trustworthy evidence is `NOT_EVALUABLE`.
- **Unlocks:** Phase 5 closure and Golden Journey G26–G27 only on `SUCCESS`.

## Clinical Shadow and imaging interoperability

## P5-T21 — Scaffold Clinical Shadow, quarantine, and Purpose Grants

- **Outcome:** Clinical owns its database/roles/migrations/outbox, encrypted <=24-hour non-backed-up quarantine, read-only Shadow Records, purpose grants and deidentified snapshot proposals.
- **Depends on:** `P2-T27`, `P5-T00`, `P5-T01` `MERGED` and current `P3-T18=SUCCESS`.
- **Read first:** Clinical Shadow context, Governed Workflows, Clinical Interoperability.
- **Change surface:** Clinical module/migrations/contracts, Gateway clinical batch and admission UI/tests.
- **Implement:** create Clinical's owner-local schema/outbox, encrypted non-backed-up quarantine with hard 24-hour destruction, read-only records, Purpose Grants and deidentified-snapshot proposal seams.
- **Prove:** quarantine backup exclusion/destruction, stricter 24-hour clock, purpose expiry/revocation, no sensitive logs and no writeback credential/path.
- **Stop/hand off:** only synthetic or Institution-attested already-deidentified input; PathLab is not a raw-PHI repair service.
- **Unlocks:** `P5-T22`–`P5-T26`.

## P5-T22 — Implement the executable FHIR R4 shadow profile and client

- **Outcome:** Validate exact closed six-resource Shadow Case Bundles under `pathlab.fhir.shadow.r4#1.0.0` and perform only registered bounded GET/read/search operations.
- **Depends on:** `P5-T02H` and `P5-T21` `MERGED`.
- **Read first:** Clinical Interoperability FHIR sections.
- **Change surface:** frozen FHIR package, Gateway client, Clinical validator and fixtures.
- **Implement:** enforce the closed six-resource profile, local terminology/reference resolution, bounded registered GET/read/search and fail-closed rejection of every write or external traversal.
- **Prove:** wrong R4/profile/canonical/resource/reference/code, narrative/free text, external next link, size/page/timeout and every write-method attempt.
- **Stop/hand off:** no general FHIR server, conversion, writeback, history, bulk export or subscription.
- **Unlocks:** `P5-T26`.

## P5-T23 — Validate bounded DICOM WSI/ANN and confidentiality

- **Outcome:** Admit only the two frozen SOP classes/geometry under a machine-readable confidentiality policy, source-time/UID rules, metadata/OCR/pixel review and two-person decision.
- **Depends on:** `P2-T05`, `P3-T14`, `P5-T02I`, and `P5-T21` `MERGED`.
- **Read first:** Clinical Interoperability DICOM/deidentification sections, Role Matrix clinical pair.
- **Change surface:** DICOM validators/policy/OCR-pattern tools, review UI and adversarial fixtures.
- **Implement:** apply the machine-readable confidentiality policy, metadata/time/UID/code/geometry checks, OCR/pixel review and distinct-person decision while rejecting rather than repairing residual identifiers.
- **Prove:** unknown/private tags, dates/UIDs, OCR/barcode/face/label/pixel canaries, malformed frames/geometry, wrong code/terminology, bomb and same-person approval.
- **Stop/hand off:** any residual/unknown identifying value rejects and destroys; never repair to pass.
- **Unlocks:** `P5-T24`, `P5-T25`, `P5-T26`.

## P5-T24 — Serve complete read-only DICOMweb

- **Outcome:** Same-origin DICOMweb implements every mandatory qualified QIDO-RS/WADO-RS read resource and accurate `OPTIONS` Retrieve Capabilities for admitted objects.
- **Depends on:** `P5-T23` `MERGED`.
- **Read first:** Clinical Interoperability DICOMweb contract.
- **Change surface:** DICOMweb routes/delivery/Caddy/conformance statement and tests.
- **Implement:** expose only the exact same-origin QIDO-RS/WADO-RS search/retrieve resources and truthful Retrieve Capabilities with bounded media/query behavior and method-deny policy.
- **Prove:** two independent user agents, searches/retrieval/metadata/rendered/frame/bulk data, media/query limits, inconsistent capabilities, wrong origin and 405 for all writes.
- **Stop/hand off:** no STOW, DIMSE, UPS, worklist or source writeback.
- **Unlocks:** `P5-T26`.

## P5-T25 — Export bounded DICOM ANN derivatives

- **Outcome:** Imaging/clinical batch creates independently validated bounded DICOM ANN derivatives from exact admitted normalized sources.
- **Depends on:** `P3-T07`, `P3-T14`, `P5-T02I`, and `P5-T23` `MERGED`.
- **Read first:** Clinical Interoperability DICOM ANN section.
- **Change surface:** DICOM ANN exporter, derivative manifests and independent-validator fixtures/tests.
- **Implement:** only frozen ANN SOP class, geometry/content-identification/codes, source references and confidentiality policy.
- **Prove:** missing/mixed/remote source, unsupported geometry/code/content/coordinates, UID/time/privacy canaries and two independent validators/readers.
- **Stop/hand off:** no semantic round trip, private vector, unsupported geometry or source-identity leak claim.
- **Unlocks:** `P5-T26B` after the complete Clinical implementation set merges.

## P5-T25A — Export bounded OME-Zarr derivatives

- **Outcome:** Imaging/clinical batch creates independently validated calibrated uint8 RGB `c,y,x` multiscale OME-Zarr 0.5.2-on-Zarr-v3 derivatives from exact admitted normalized sources.
- **Depends on:** `P3-T07`, `P5-T02J`, and `P5-T23` `MERGED`.
- **Read first:** Clinical Interoperability OME-Zarr section and admitted corpus profile.
- **Change surface:** OME-Zarr exporter, derivative manifests and independent-reader fixtures/tests.
- **Implement:** exact axes/chunks/codecs/multiscales, wire `ome.version="0.5"`, source/calibration hashes and privacy-minimized metadata.
- **Prove:** missing/mixed/remote source, unsupported axes/chunks/codecs/dimensions/metadata, corruption/privacy canaries and two independent readers/validators.
- **Stop/hand off:** no arbitrary OME-Zarr ingest, semantic round trip or authoritative-source substitution.
- **Unlocks:** `P5-T26B` after the complete Clinical implementation set merges.

## P5-T25B — Accept Clinical snapshot proposals in Learning Catalog

- **Outcome:** Learning Catalog separately accepts or rejects an exact Clinical-authorized deidentified snapshot proposal into an immutable purpose-bound learning snapshot version; WSI content is usable only through exact already-protected Imaging asset/version references, without reading Clinical or Imaging owner state.
- **Depends on:** `P3-T06`, `P3-T08`, `P4-T01`, `P4-T03`, `P5-T26A` `MERGED`.
- **Read first:** Clinical Deidentified Snapshot Receipt, Imaging protected-asset reference contract, Catalog immutable-version and proposal-acceptance rules and Golden Journey G29.
- **Change surface:** Clinical-to-Catalog proposal adapter, Catalog educator review/acceptance UI and handler, learning snapshot/version/audit/deletion tests and runbook.
- **Implement:** bind the Clinical admission/snapshot/Purpose Grant/source roots, destination Learning purpose/audience/expiry and every protected Imaging asset/version hash; create Catalog authority only after an explicit current educator acceptance; emit idempotent accept/reject, withdrawal/expiry and deletion-propagation results.
- **Prove:** missing/revoked/expired/changed/wrong-purpose/wrong-Institution snapshot, absent/stale/unprotected Imaging reference, stale reviewer, replay/duplicate, restart, withdrawal/deletion and no cross-context SQL.
- **Stop/hand off:** Clinical authorization and Imaging protection cannot create Catalog truth; acceptance cannot publish a Lesson, create a Public Release or bypass owner review and privacy policy.
- **Unlocks:** `P5-T26B` and Golden Journey G29 learning-use handoff.

## P5-T26 — Reconcile Clinical admission and interoperability results

- **Outcome:** Reconcile the merged Clinical owner workflow and Learning-side acceptance with independently closed FHIR, DICOMweb, DICOM WSI/ANN and OME-Zarr results plus the closed 100-case admission journey into one terminal phase result.
- **Depends on:** `P5-T26A`, `P5-T25B` `MERGED`; current terminal `SUCCESS` from `P5-T26E`, `P5-T26H`, `P5-T26K`, `P5-T26N`, and `P5-T26Q` on one immutable Clinical candidate/manifest tuple.
- **Read first:** all profile closure reports, 100-case journey report, Production Qualification clinical gate and Golden Journey G28–G29.
- **Change surface:** signed result aggregation and evidence index only.
- **Implement:** none; verify implementation/profile/journey tuple equality and complete receipt coverage before emitting one parent result.
- **Prove:** each independent profile/tool result, all 100 admissions/rejections, dual review, PHI/no-writeback faults, destination acceptance, refresh/revoke/delete and cleanup reconcile without substitution.
- **Stop/hand off:** any missing, stale, mixed-candidate or non-`SUCCESS` child prevents parent `SUCCESS`; no diagnostic, patient-care or `CLINICALLY_QUALIFIED` claim follows.
- **Unlocks:** Research inputs, Phase 5 closure and Golden Journey G28–G29 only on current `P5-T26=SUCCESS`.

## P5-T26A — Implement Clinical admission and snapshot lifecycle

- **Outcome:** Clinical Privacy Steward initiation plus independent WSI Reviewer approval admits one immutable Shadow Case Bundle and issues, refreshes, withdraws, expires and deletes purpose-bound deidentified-snapshot proposals.
- **Depends on:** `P2-T05`, `P5-T21`–`P5-T23` `MERGED`.
- **Read first:** Clinical Shadow context, Role Matrix clinical pair, Deidentification Admission and Deidentified Snapshot receipt contracts and Governed Workflows deletion rules.
- **Change surface:** Clinical admission/snapshot command service and UI, Purpose Grant lifecycle, audit/outbox, deletion adapter, tests and runbook.
- **Implement:** bind exact validation/package/profile/source-replacement roots and distinct approvals; create immutable admission/snapshot versions; enforce purpose/audience/residency/expiry; emit owner-addressed proposals; destroy quarantine and crypto-erase/delete owner state on the strict schedule.
- **Prove:** same-person/stale-step-up/changed package, duplicate/replay/restart, wrong destination/purpose, grant refresh/revoke/expiry, Legal Hold boundaries, deletion propagation, quarantine cleanup and no writeback.
- **Stop/hand off:** validation is not admission, Clinical never accepts for a destination, and no residual-PHI package may be repaired into admissibility.
- **Unlocks:** `P5-T25B`, `P5-T26B`, and `P5-T27A` implementation eligibility.

## P5-T26B — Freeze and dry-run the Clinical interoperability harness

- **Outcome:** Freeze separate FHIR, DICOMweb, DICOM WSI/ANN and OME-Zarr manifests plus one 100-case admission-journey manifest, then execute only reduced non-qualifying harness checks.
- **Depends on:** `P5-T21`–`P5-T25B`, `P5-T26A` `MERGED`.
- **External prerequisites:** label=EP-P5-CLIN-RIGHTS; kind=RIGHTS; requires=APPROVED; accountable=Clinical interoperability lead; validity=exact standards terminology case and tool rights remain approved through P5-T26 closure; evidence=SignedClinicalRightsReceipt | label=EP-P5-CLIN-CORPUS; kind=DATA_OR_CORPUS; requires=AVAILABLE; accountable=Clinical Privacy Steward; validity=at least 100 synthetic or Institution-attested already-deidentified case roots and attestations remain unchanged through P5-T26 closure; evidence=SignedClinicalCorpusAdmissionReceipt | label=EP-P5-CLIN-TOOLS; kind=TOOL_OR_IMPLEMENTATION; requires=AVAILABLE; accountable=Clinical interoperability lead; validity=two independent appropriate implementations per claimed profile remain at exact admitted versions and hashes through P5-T26 closure; evidence=SignedClinicalToolAdmissionReceipt | label=EP-P5-CLIN-REVIEWERS; kind=HUMAN_AUTHORITY; requires=ASSIGNED; accountable=Clinical Privacy Steward; validity=distinct accountable Clinical Privacy Steward and WSI Reviewer assignments remain current for every admission through P5-T26 closure; evidence=SignedClinicalReviewerAssignmentReceipt.
- **Read first:** admitted P5-T02H–P5-T02J corpora, Production Qualification clinical gate and Golden Journey G28–G29.
- **Change surface:** Clinical/profile harness, independent manifests, observers, evidence schemas and runbooks only.
- **Implement:** encode per-profile identity, 100-case admission workflow, PHI/no-writeback faults, reviewer independence, receipt cursors and cleanup; dry-run each adapter interface without emitting conformance.
- **Prove:** each corpus/tool/reviewer resolves, profile manifests cannot satisfy one another, PHI canaries are detected and reduced quarantine/destination cleanup completes.
- **Stop/hand off:** any prerequisite not at its required disposition or unresolved profile/reviewer/cleanup semantics is `NOT_EVALUABLE` and blocks launch.
- **Unlocks:** `P5-T26C`, `P5-T26F`, `P5-T26I`, and `P5-T26L`.

## P5-T26C — Start FHIR R4 conformance

- **Outcome:** Admit and start only the frozen FHIR R4 Shadow profile workload with exact corpus/client/validator identities and receipt cursor.
- **Depends on:** current `P5-T26B=SUCCESS`, its FHIR manifest head `FROZEN`, and current `EP-P5-CLIN-RIGHTS`, `EP-P5-CLIN-CORPUS`, and `EP-P5-CLIN-TOOLS` receipt heads.
- **Read first:** frozen FHIR manifest and launch runbook.
- **Change surface:** FHIR admission/start evidence only.
- **Implement:** none; start the FHIR workload and observers without any DICOM or OME-Zarr execution.
- **Prove:** exact profile/corpus/tool tuple, observer liveness and forward receipt movement.
- **Stop/hand off:** partial admission or drift is `NOT_EVALUABLE`; start remains `RUNNING`.
- **Unlocks:** `P5-T26D`.

## P5-T26D — Monitor and audit FHIR R4 conformance

- **Outcome:** Execute and observe only the full closed FHIR profile official, adversarial and two-independent-implementation matrix.
- **Depends on:** active `P5-T26C` with matching immutable FHIR manifest.
- **Read first:** latest FHIR cursor, fault schedule and incidents.
- **Change surface:** FHIR observations, faults and incident evidence only.
- **Implement:** none; execute resource/reference/terminology/narrative/identifier/page/timeout/write-method cases and preserve receipts.
- **Prove:** every closed-profile rule, bounded read operation, independent tool and zero-writeback assertion completes.
- **Stop/hand off:** missing independent coverage, external traversal, writeback, receipt gap or drift follows the frozen disposition.
- **Unlocks:** `P5-T26E` after workload and cleanup terminate.

## P5-T26E — Close FHIR R4 conformance

- **Outcome:** Reconcile the complete FHIR workload into one signed profile result.
- **Depends on:** completed `P5-T26C`/`P5-T26D` and unchanged FHIR manifest/candidate.
- **Read first:** frozen FHIR manifest and terminal receipt range.
- **Change surface:** FHIR signed aggregation and cleanup only.
- **Implement:** none; validate profile coverage, independent outputs, faults and cleanup and emit the terminal result.
- **Prove:** all exact resource/reference/terminology/read-only rules, two independent implementations and terminal cleanup.
- **Stop/hand off:** incomplete workload is `PARTIAL`; missing trustworthy evidence is `NOT_EVALUABLE`; writeback is `NEGATIVE`.
- **Unlocks:** `P5-T26O` after all profiles close.

## P5-T26F — Start DICOMweb conformance

- **Outcome:** Admit and start only the frozen read-only QIDO-RS/WADO-RS and Retrieve Capabilities workload with exact user-agent identities and receipt cursor.
- **Depends on:** current `P5-T26B=SUCCESS`, its DICOMweb manifest head `FROZEN`, and current `EP-P5-CLIN-RIGHTS`, `EP-P5-CLIN-CORPUS`, and `EP-P5-CLIN-TOOLS` receipt heads.
- **Read first:** frozen DICOMweb manifest and launch runbook.
- **Change surface:** DICOMweb admission/start evidence only.
- **Implement:** none; start the DICOMweb workload and observers without DICOM object or OME-Zarr conformance execution.
- **Prove:** exact resource/user-agent/corpus tuple, observer liveness and forward receipt movement.
- **Stop/hand off:** partial admission or drift is `NOT_EVALUABLE`; start remains `RUNNING`.
- **Unlocks:** `P5-T26G`.

## P5-T26G — Monitor and audit DICOMweb conformance

- **Outcome:** Execute and observe only the full read-only search/retrieve/capabilities official, adversarial and two-user-agent matrix.
- **Depends on:** active `P5-T26F` with matching immutable DICOMweb manifest.
- **Read first:** latest DICOMweb cursor, fault schedule and incidents.
- **Change surface:** DICOMweb observations, faults and incident evidence only.
- **Implement:** none; execute query/media/limit/capability/origin/write-method cases and preserve receipts.
- **Prove:** every mandatory resource and response form, accurate capabilities, bounds, independent user agents and all-write denial.
- **Stop/hand off:** inconsistent capability, accepted write, receipt gap or drift follows the frozen disposition.
- **Unlocks:** `P5-T26H` after workload and cleanup terminate.

## P5-T26H — Close DICOMweb conformance

- **Outcome:** Reconcile the complete DICOMweb workload into one signed profile result.
- **Depends on:** completed `P5-T26F`/`P5-T26G` and unchanged DICOMweb manifest/candidate.
- **Read first:** frozen DICOMweb manifest and terminal receipt range.
- **Change surface:** DICOMweb signed aggregation and cleanup only.
- **Implement:** none; validate resource coverage, user-agent outputs, faults and cleanup and emit the terminal result.
- **Prove:** all exact read/capability rules, two independent user agents and terminal cleanup.
- **Stop/hand off:** incomplete workload is `PARTIAL`; missing trustworthy evidence is `NOT_EVALUABLE`; write acceptance is `NEGATIVE`.
- **Unlocks:** `P5-T26O` after all profiles close.

## P5-T26I — Start DICOM WSI and ANN conformance

- **Outcome:** Admit and start only the frozen bounded DICOM WSI/ANN object and confidentiality workload with exact validators/readers and receipt cursor.
- **Depends on:** current `P5-T26B=SUCCESS`, its DICOM-object manifest head `FROZEN`, and current `EP-P5-CLIN-RIGHTS`, `EP-P5-CLIN-CORPUS`, and `EP-P5-CLIN-TOOLS` receipt heads.
- **Read first:** frozen DICOM WSI/ANN manifest and launch runbook.
- **Change surface:** DICOM-object admission/start evidence only.
- **Implement:** none; start the object/geometry/confidentiality workload without FHIR, DICOMweb or OME-Zarr conformance execution.
- **Prove:** exact SOP/profile/corpus/tool tuple, observer liveness and forward receipt movement.
- **Stop/hand off:** partial admission or drift is `NOT_EVALUABLE`; start remains `RUNNING`.
- **Unlocks:** `P5-T26J`.

## P5-T26J — Monitor and audit DICOM WSI and ANN conformance

- **Outcome:** Execute and observe only the full WSI/ANN object, geometry, code, UID/time and metadata/OCR/pixel confidentiality matrix.
- **Depends on:** active `P5-T26I` with matching immutable DICOM-object manifest.
- **Read first:** latest DICOM-object cursor, fault schedule and incidents.
- **Change surface:** DICOM-object observations, faults and incident evidence only.
- **Implement:** none; execute malformed/private/unknown tag, dimension, geometry, UID/time/code and PHI-canary cases and preserve receipts.
- **Prove:** both frozen SOP classes, independent validators/readers, rejection-only privacy boundary and no unsupported semantic flattening.
- **Stop/hand off:** residual PHI, unsupported acceptance, receipt gap or drift follows the frozen disposition.
- **Unlocks:** `P5-T26K` after workload and cleanup terminate.

## P5-T26K — Close DICOM WSI and ANN conformance

- **Outcome:** Reconcile the complete DICOM WSI/ANN workload into one signed profile result.
- **Depends on:** completed `P5-T26I`/`P5-T26J` and unchanged DICOM-object manifest/candidate.
- **Read first:** frozen DICOM-object manifest and terminal receipt range.
- **Change surface:** DICOM-object signed aggregation and cleanup only.
- **Implement:** none; validate SOP/geometry/confidentiality coverage, independent outputs and cleanup and emit the terminal result.
- **Prove:** all exact object and rejection rules, two independent validators/readers and terminal cleanup.
- **Stop/hand off:** incomplete workload is `PARTIAL`; missing trustworthy evidence is `NOT_EVALUABLE`; privacy breach is `NEGATIVE`.
- **Unlocks:** `P5-T26O` after all profiles close.

## P5-T26L — Start OME-Zarr conformance

- **Outcome:** Admit and start only the frozen OME-Zarr 0.5.2-on-Zarr-v3 export/read workload with exact readers/validators and receipt cursor.
- **Depends on:** current `P5-T26B=SUCCESS`, its OME-Zarr manifest head `FROZEN`, and current `EP-P5-CLIN-RIGHTS`, `EP-P5-CLIN-CORPUS`, and `EP-P5-CLIN-TOOLS` receipt heads.
- **Read first:** frozen OME-Zarr manifest and launch runbook.
- **Change surface:** OME-Zarr admission/start evidence only.
- **Implement:** none; start the representation workload without another interoperability profile.
- **Prove:** exact version/axes/chunks/codecs/corpus/tool tuple, observer liveness and forward receipt movement.
- **Stop/hand off:** partial admission or drift is `NOT_EVALUABLE`; start remains `RUNNING`.
- **Unlocks:** `P5-T26M`.

## P5-T26M — Monitor and audit OME-Zarr conformance

- **Outcome:** Execute and observe only the full OME-Zarr metadata/array, hostile-store, privacy and two-independent-reader matrix.
- **Depends on:** active `P5-T26L` with matching immutable OME-Zarr manifest.
- **Read first:** latest OME-Zarr cursor, fault schedule and incidents.
- **Change surface:** OME-Zarr observations, faults and incident evidence only.
- **Implement:** none; execute axes/chunk/codec/dimension/metadata/corruption/source-identity cases and preserve receipts.
- **Prove:** exact wire `ome.version`, calibrated RGB multiscales, independent readers and bounded privacy-minimized output.
- **Stop/hand off:** arbitrary ingest, source identity leak, receipt gap or drift follows the frozen disposition.
- **Unlocks:** `P5-T26N` after workload and cleanup terminate.

## P5-T26N — Close OME-Zarr conformance

- **Outcome:** Reconcile the complete OME-Zarr workload into one signed profile result.
- **Depends on:** completed `P5-T26L`/`P5-T26M` and unchanged OME-Zarr manifest/candidate.
- **Read first:** frozen OME-Zarr manifest and terminal receipt range.
- **Change surface:** OME-Zarr signed aggregation and cleanup only.
- **Implement:** none; validate version/representation/privacy coverage, independent outputs and cleanup and emit the terminal result.
- **Prove:** all exact format/subset rules, two independent readers/validators and terminal cleanup.
- **Stop/hand off:** incomplete workload is `PARTIAL`; missing trustworthy evidence is `NOT_EVALUABLE`; privacy breach is `NEGATIVE`.
- **Unlocks:** `P5-T26O` after all profiles close.

## P5-T26O — Start the 100-case Clinical admission journey

- **Outcome:** Start one immutable 100-case admission, Purpose Grant, destination-acceptance, refresh/revoke/delete and PHI/no-writeback journey after every independent profile succeeds.
- **Depends on:** current terminal `SUCCESS` from `P5-T26E`, `P5-T26H`, `P5-T26K`, and `P5-T26N` on the same candidate; current Clinical journey manifest head `FROZEN`; current `EP-P5-CLIN-RIGHTS`, `EP-P5-CLIN-CORPUS`, `EP-P5-CLIN-TOOLS`, and `EP-P5-CLIN-REVIEWERS` receipt heads.
- **Read first:** frozen Clinical journey manifest and Golden Journey G28–G29.
- **Change surface:** journey admission/start evidence only.
- **Implement:** none; admit the full lawful case/reviewer/destination tuple and start observers without product repair.
- **Prove:** exact 100 cases, distinct reviewers, owner handlers and observers admitted with forward receipt movement.
- **Stop/hand off:** missing case/reviewer/destination, drift or partial admission is `NOT_EVALUABLE`; start remains `RUNNING`.
- **Unlocks:** `P5-T26P`.

## P5-T26P — Monitor and audit the 100-case Clinical admission journey

- **Outcome:** Observe all cases through validation, distinct-person admission, snapshot authorization, Learning/Research destination decisions, refresh/revoke/delete and cleanup while injecting every frozen PHI/no-writeback fault.
- **Depends on:** active `P5-T26O` with matching immutable Clinical journey manifest.
- **Read first:** latest journey cursor, reviewer schedule, fault schedule and open incidents.
- **Change surface:** journey observations, reviewer/fault evidence and incidents only.
- **Implement:** none; execute only the frozen workflow and preserve Clinical, Imaging/Learning and Research owner receipts without cross-context repair.
- **Prove:** 100 complete case paths, distinct approvals, metadata/narrative/OCR/pixel canaries, quarantine ceiling/destruction, destination accept/reject, revocation/deletion and zero writeback.
- **Stop/hand off:** reviewer substitution, residual PHI, writeback, receipt gap or changed tuple follows the frozen disposition.
- **Unlocks:** `P5-T26Q` after all case paths and cleanup terminate.

## P5-T26Q — Close the 100-case Clinical admission journey

- **Outcome:** Reconcile the complete 100-case workflow, adversarial faults, destination receipts and cleanup into one signed journey result.
- **Depends on:** completed `P5-T26O`/`P5-T26P` and unchanged Clinical journey manifest/candidate.
- **Read first:** frozen journey manifest, terminal receipt range and Production Qualification clinical gate.
- **Change surface:** journey signed aggregation and cleanup only.
- **Implement:** none; validate every case/reviewer/owner transition, fault and cleanup and emit the terminal journey result.
- **Prove:** exact source/receipt counts, all privacy/no-writeback/destination/deletion invariants and terminal quarantine/workspace cleanup.
- **Stop/hand off:** incomplete cases are `PARTIAL`; missing trustworthy evidence is `NOT_EVALUABLE`; PHI/writeback/authority breach is `NEGATIVE`.
- **Unlocks:** parent `P5-T26`.

## Research

## P5-T27 — Scaffold Research control authority

- **Outcome:** Research owns Projects, grants, Dataset Snapshots, Environment Manifests, Jobs, quotas and private Artifacts in its logical database with signed-manifest handoff to the runner.
- **Depends on:** `P2-T27`, `P5-T00`, and `P1-T04` `MERGED`; current `P3-T18=SUCCESS`.
- **Read first:** Research context, Governed Workflows Research, Role Matrix.
- **Change surface:** Research control module/migrations/contracts/UI and tests.
- **Implement:** owner-local Project, Purpose Grant, Dataset Snapshot, Environment Manifest, Job, quota and private Artifact schemas, repositories, commands/events, least-privilege role and signed runner handoff.
- **Prove:** wrong purpose/Institution, mutable snapshot, unsigned environment, quota mismatch, no production DB/file grant and annual review.
- **Stop/hand off:** outputs remain private proposals and do not activate a model or clinical claim.
- **Unlocks:** `P5-T27A`, `P5-T28`–`P5-T30`.

## P5-T27A — Admit optional Clinical-derived Research snapshots

- **Outcome:** Let Research accept only a separately authorized deidentified immutable Clinical snapshot proposal under an exact Research Purpose Grant, while preserving Clinical and Research owner boundaries.
- **Depends on:** `P5-T27` `MERGED`; current `P5-T26=SUCCESS` on the exact Clinical snapshot proposal candidate.
- **Read first:** Clinical Shadow snapshot handoff, Research Dataset Snapshot authority and Golden Journey G29–G30.
- **Change surface:** Clinical-to-Research proposal adapter, purpose review UI, receipt/audit/deletion tests.
- **Implement:** exact source snapshot/purpose/audience/residency/expiry/hash binding, Research accept/reject event and no cross-context reads.
- **Prove:** revoked/expired/wrong-purpose/wrong-Institution/changed/duplicate proposal, PHI canary, restart and deletion propagation.
- **Stop/hand off:** Clinical input is optional for general Research operation and never creates a clinical or model-activation claim.
- **Unlocks:** Golden G29–G30 chain and specialist closure.

## P5-T28 — Ratify the native Research isolation profile

- **Outcome:** Select and document exact free/offline Linux isolation primitives, syscall/filesystem/network/namespace policy, signed environment format, checkpoint mechanism and escape test suite for the one-OCPU/4-GB/20-GB/four-hour runner.
- **Depends on:** `P0-T03A`, `P1-T20`, `P5-T27` `MERGED`.
- **Read first:** Research context, service cells, host/runtime threat model.
- **Change surface:** narrow ADR, offline input/pin admission and executable security test specification.
- **Implement:** none; ratify the exact native isolation, syscall/filesystem/network/namespace, signed-environment, checkpoint and escape-test contract before runner implementation.
- **Prove:** official-source/license/ARM64/offline evidence, default-deny threat review and reproducible fixture.
- **Stop/hand off:** implementation cannot start with an unspecified sandbox; no container/hosted service is assumed.
- **Unlocks:** `P5-T29`.

## P5-T29 — Implement isolated noninteractive Research execution

- **Outcome:** Run exactly one signed fixed command against read-only snapshots with hard quotas, no shell/package install/network/production credential, deterministic checkpoint/restart and cleanup.
- **Depends on:** `P1-T17`–`P1-T20`, `P5-T27`, `P5-T28` `MERGED`.
- **Read first:** accepted isolation ADR and Research context.
- **Change surface:** runner entry point/systemd sandbox/cgroups, control protocol, offline environments, artifact review/cleanup UI/tests.
- **Implement:** one noninteractive signed-command runner with read-only inputs, fixed offline environment, hard cgroup/storage/time quotas, default-deny network/credentials, deterministic checkpoint/restart, private output review and terminal cleanup.
- **Prove:** CPU/RAM/disk/wall/idle breaches, filesystem/DB/key/network/package/shell/escape attempts, restart/tampered checkpoint, reproduction and direct publication/activation denial.
- **Stop/hand off:** no interactive notebook/arbitrary package/environment or direct owning-context mutation.
- **Unlocks:** `P5-T30`.

## P5-T30 — Freeze and dry-run the four-hour Research campaign

- **Outcome:** Freeze the exact four-hour, one-OCPU/four-GB/20-GB manifest, environment/snapshot/command/fault/observer/cleanup hashes and execute a reduced non-qualifying end-to-end dry run.
- **Depends on:** `P5-T29` `MERGED`; current `EP-P5-RESEARCH-SNAPSHOT` receipt head bound to the exact Research Campaign Manifest.
- **External prerequisites:** label=EP-P5-RESEARCH-SNAPSHOT; kind=DATA_OR_CORPUS; requires=APPROVED; accountable=Research Purpose Grant owner; validity=exact lawful Dataset Snapshot purpose audience residency expiry and content roots remain current through P5-T30C closure; evidence=SignedResearchDatasetAdmissionReceipt.
- **Read first:** Production Qualification Research gate.
- **Change surface:** campaign harness/manifest/dry-run evidence only; fixes are separate implementation tasks.
- **Implement:** the reproducible four-hour campaign harness, immutable manifest/cursor format, quota and observer probes, fault schedule, deterministic comparison and cleanup verifier; execute only the reduced non-qualifying dry run.
- **Prove:** exact command/environment/snapshot, restart/checkpoint/reproduction, escape/egress/credential/quota attacks, signed review and cleanup paths resolve.
- **Stop/hand off:** dry-run success is not the four-hour result; unresolved isolation/observer/cleanup ambiguity blocks launch.
- **Unlocks:** `P5-T30A`.

## P5-T30A — Start the full four-hour Research campaign

- **Outcome:** Admit the unchanged phase candidate and begin the frozen four-hour Research job with immutable start evidence, process identities and receipt cursor.
- **Depends on:** current `P5-T30=SUCCESS`, unchanged frozen Research Campaign Manifest and phase-candidate fingerprint heads, and current `EP-P5-RESEARCH-SNAPSHOT`, `EP-P5-RESEARCH-HOST`, and `EP-P5-RESEARCH-OPERATOR` receipt heads.
- **External prerequisites:** label=EP-P5-RESEARCH-SNAPSHOT; kind=DATA_OR_CORPUS; requires=APPROVED; accountable=Research Purpose Grant owner; validity=exact lawful Dataset Snapshot purpose audience residency expiry and content roots remain current through P5-T30C closure; evidence=SignedResearchDatasetAdmissionReceipt | label=EP-P5-RESEARCH-HOST; kind=HARDWARE; requires=AVAILABLE; accountable=Research qualification lead; validity=declared one-OCPU four-GB twenty-GB Linux host identity and resource envelope remain unchanged through P5-T30C closure; evidence=SignedResearchHostAdmissionReceipt | label=EP-P5-RESEARCH-OPERATOR; kind=HUMAN_AUTHORITY; requires=ASSIGNED; accountable=Research qualification lead; validity=campaign operator and independent artifact reviewer assignments remain current and separate through P5-T30C closure; evidence=SignedResearchOperatorAssignmentReceipt.
- **Read first:** frozen Research campaign manifest and launch runbook.
- **Change surface:** campaign admission/start evidence only.
- **Implement:** none; admit and start the frozen workload and observers without product, harness, manifest or input repair.
- **Prove:** exact tuple/manifest, quotas/cgroups/egress rules active, observer live and receipts advance.
- **Stop/hand off:** missing host/operator/snapshot, drift or incomplete isolation is `NOT_EVALUABLE`; start is `RUNNING`, never `SUCCESS`.
- **Unlocks:** `P5-T30B`.

## P5-T30B — Monitor the active four-hour Research campaign

- **Outcome:** Observe the full job by receipt cursor, execute declared restart/checkpoint and adversarial boundaries and record incidents without retaining implementation context.
- **Depends on:** active `P5-T30A` with matching immutable manifest.
- **Read first:** latest cursor, fault schedule and only open incidents.
- **Change surface:** campaign observations/fault evidence and incidents only.
- **Implement:** none; follow the frozen fault schedule and append observations/incidents without changing the candidate, manifest, job or evidence history.
- **Prove:** live CPU/RAM/disk/time/process/receipt progress, responsive resident plane, no egress/credential/escape and exact scheduled restart.
- **Stop/hand off:** stopped/wedged worker, missing interval or changed input follows the frozen disposition; do not restart history silently.
- **Unlocks:** `P5-T30C` after four elapsed hours and workload completion.

## P5-T30C — Close the four-hour Research campaign

- **Outcome:** Reconcile four complete elapsed hours, restart/reproduction, signed artifact review and terminal workspace cleanup into one exact phase result.
- **Depends on:** completed `P5-T30A`/`P5-T30B` and unchanged manifest/candidate.
- **Read first:** frozen manifest, terminal receipt range and Production Qualification Research gate.
- **Change surface:** signed evidence aggregation and cleanup only.
- **Implement:** none; reconcile the immutable receipt range and emit the terminal campaign result without product, harness or manifest mutation.
- **Prove:** exact elapsed time/quotas, zero escape/egress/credential, responsive resident plane, identical output hashes, signed-only import and complete cleanup.
- **Stop/hand off:** shortened/incomplete run is `PARTIAL`; missing trustworthy evidence is `NOT_EVALUABLE`.
- **Unlocks:** Phase 5 closure and Golden Journey G30 only on `SUCCESS`.

## Edge Federation

## P5-T31 — Scaffold Platform Edge authority and enrollment

- **Outcome:** Edge owns node enrollment, public identity/key refs, leases, compatibility, checkpoints, conflicts and retirement in its logical database.
- **Depends on:** `P2-T27`, `P5-T00`, `P5-T01`, and `P1-T04` `MERGED`.
- **Read first:** [Edge Node Profile](../architecture/EDGE_NODE_PROFILE.md), Edge context and Role Matrix.
- **Change surface:** Edge platform module/migrations/contracts/admin UI and tests.
- **Implement:** physical enrollment, Ed25519/mTLS identity, <=7-day Node and <=24-hour User leases, N/N-2 protocol and revoke.
- **Prove:** reused/wrong hardware/Institution/release, expired/revoked lease, rotation and clock anomaly.
- **Stop/hand off:** no permanent enrollment, cached password/LMS identity or second Platform authority.
- **Unlocks:** `P5-T32`–`P5-T39`.

## P5-T32 — Build the native offline Edge application and release bundle

- **Outcome:** ARM64 Edge kit installs the bounded acquisition/control/sync/update/wipe processes with only control resident and encrypted single-writer SQLite/local objects.
- **Depends on:** `P0-T09`, `P1-T22`, `P5-T31` `MERGED`.
- **Read first:** Edge Node Profile admitted install/process/data/resource sections.
- **Change surface:** Edge application/package/systemd/release/update tooling and tests.
- **Implement:** native ARM64 install/update bundle, bounded acquisition/control/sync/update/wipe processes, encrypted single-writer SQLite/object layout, service supervision and offline release verification.
- **Prove:** offline clean install, exact process count, filesystem/cgroup/network permissions, no Platform DB, and 2-core/2-GB/16-GB envelope.
- **Stop/hand off:** no node PostgreSQL/JetStream/container/hosted dependency.
- **Unlocks:** `P5-T33`–`P5-T38`.

## P5-T33 — Commit bounded Local Acquisitions

- **Outcome:** One on-demand process streams into quarantine, validates and commits a signed local manifest/ordered ledger/outbox under temporary Edge authority within per-node/platform queue limits.
- **Depends on:** `P5-T32` `MERGED`.
- **Read first:** Edge context acquisition and capacity terms.
- **Change surface:** Edge acquisition/local DB/object/UI and tests.
- **Implement:** bounded quarantine streaming, validation, signed local manifest/ordered ledger/outbox commit, disk/inode admission, restart recovery and explicit release/rejection UI.
- **Prove:** corrupt bytes/WAL, unknown size, disk/inode pressure, restart, 80/90% states, invalid format and 10k-event/2-GB bounds.
- **Stop/hand off:** Local Acquisition is not Platform/Imaging acceptance.
- **Unlocks:** `P5-T34`, `P5-T36`.

## P5-T34 — Protect pending Edge authority with Recovery Copies

- **Outcome:** Pending acquisition becomes locally releasable only after a separate encrypted recovery medium reconciles exact state/object roots and receives a bounded expiry obligation.
- **Depends on:** `P5-T33`, `P1-T11A`, `P2-T19`, `P2-T22`, and `P2-T24` `MERGED`.
- **Read first:** Edge Profile recovery-copy states.
- **Change surface:** Edge recovery tooling/state/UI and tests.
- **Implement:** separate encrypted recovery-medium copy, exact database/object-root reconciliation, release interlock, bounded expiry/removal obligation and recoverable failure states.
- **Prove:** missing/corrupt/wrong-location copy, key loss, restart, accepted/rejected final result, expiry/removal and no source release before proof.
- **Stop/hand off:** no cloud/sync-folder/email/permanent archive assumption.
- **Unlocks:** `P5-T35`, `P5-T38`.

## P5-T35 — Enforce offline snapshots, leases, and trusted time

- **Outcome:** Disconnected nodes read only unexpired approved Catalog/assets and perform only acquisition under current Node/User leases using signed time anchor plus monotonic elapsed time.
- **Depends on:** `P5-T31`–`P5-T34` `MERGED`.
- **Read first:** Edge Profile identity/leases/local retention and authority boundary.
- **Change surface:** Edge control/cache/authorization/UI and tests.
- **Implement:** signed snapshot admission, Node/User lease enforcement, trusted-time continuity, expiry/revocation UI and default-deny offline action matrix.
- **Prove:** seven-day disconnect, 24-hour user expiry, clock rollback/continuity loss, stale policy and forbidden identity/grade/publication/EQA/Clinical/Research actions.
- **Stop/hand off:** cached snapshot is never current Platform truth.
- **Unlocks:** `P5-T36`, `P5-T39`.

## P5-T36 — Transfer signed resumable Sync Batches with N/N-2 upcasting

- **Outcome:** Edge packages ordered signed events/object manifests and resumes mTLS transfer through Gateway within ten control/two byte-transfer concurrency, preserving original/upcast hashes.
- **Depends on:** `P1-T02`, `P5-T01`, `P5-T31`–`P5-T35` `MERGED`.
- **Read first:** Edge context/Profile and Gateway authority.
- **Change surface:** Edge sync, Gateway adapter, batch Edge mode and tests.
- **Implement:** signed ordered event/object batches, original/upcast hash chain, resumable mTLS Gateway transfer, N/N-2 upcasting, checkpoints and ten-control/two-byte-transfer bounds.
- **Prove:** duplicate/delay/reorder/replay/corrupt/interrupted/wrong-version/node, restart/checkpoint and concurrency/queue caps.
- **Stop/hand off:** never synchronize SQLite pages/files or replicate Platform databases.
- **Unlocks:** `P5-T37`.

## P5-T37 — Let owner contexts accept or resolve Edge proposals

- **Outcome:** Each owner accepts/rejects exact proposals; Imaging creates authority only for accepted acquisitions; irreducible conflicts remain governed records until deterministic/authorized resolution.
- **Depends on:** `P5-T36` `MERGED`; current `P3-T18=SUCCESS`.
- **Read first:** Edge context authority partition and Receipt Registry Edge section.
- **Change surface:** Edge platform, Imaging proposal handler, conflict UI/cleanup and tests.
- **Implement:** owner-addressed proposal acceptance/rejection, immutable result receipts, deterministic conflict records/resolution authority, replay idempotency and accepted/rejected cleanup.
- **Prove:** replay/conflict/revoked/wrong-Institution node, partial batch, lost receipt, restart and accepted/rejected cleanup.
- **Stop/hand off:** Gateway/node do not decide shared truth; no last-write-wins.
- **Unlocks:** `P5-T38`, `P5-T39`.

## P5-T38 — Update, rotate, retire, revoke, and wipe Edge nodes

- **Outcome:** Signed offline updates migrate a copy then atomically swap/rollback; node keys rotate; retirement drains pending authority and reports confirmed wipe or truthful `REVOKED_UNCONFIRMED`.
- **Depends on:** `P0-T10A` and `P5-T34`–`P5-T37` `MERGED`.
- **Read first:** Edge Profile update/retirement/wipe, Delivery State rules.
- **Change surface:** Edge update/wipe processes, Platform admin/incident UI and tests.
- **Implement:** signed copy-migrate-verify-swap update/rollback, overlapping key rotation, drain-before-retire, remote revoke and evidence-bounded wipe or `REVOKED_UNCONFIRMED` lifecycle.
- **Prove:** interrupted/corrupt update, disk/migration mismatch, root equality rollback, key overlap/revoke, unreachable/stolen node and cleanup.
- **Stop/hand off:** no flash-remanence or wipe-success claim without evidence.
- **Unlocks:** `P5-T39`.

## P5-T39 — Preserve Desktop compatibility and dry-run the Edge campaign

- **Outcome:** Adapt the existing Desktop profile without calling it Edge, then freeze the 100-physical-node N/N-1/N-2 seven-day disconnect plus one-million-event/50-GB/24-hour-drain manifest and execute a reduced non-qualifying dry run.
- **Depends on:** `P3-T15`, `P5-T31`–`P5-T38` `MERGED`; current `EP-P5-EDGE-FLEET`, `EP-P5-EDGE-MEDIA`, and `EP-P5-EDGE-NETWORK` receipt heads bound to the exact Edge Campaign Manifest.
- **External prerequisites:** label=EP-P5-EDGE-FLEET; kind=HARDWARE; requires=AVAILABLE; accountable=Edge qualification lead; validity=100 owned or donated physical ARM64 nodes with declared N N-1 N-2 allocation and no required spend remain admitted through P5-T39E closure; evidence=SignedEdgeFleetAdmissionReceipt | label=EP-P5-EDGE-MEDIA; kind=HARDWARE; requires=AVAILABLE; accountable=Edge qualification lead; validity=separate recovery media identities capacities and custody remain admitted for every node through P5-T39E closure; evidence=SignedEdgeRecoveryMediaAdmissionReceipt | label=EP-P5-EDGE-NETWORK; kind=NETWORK_IDENTITY; requires=DECLARED; accountable=Edge network authority; validity=disconnect reconnect Gateway routes identities bandwidth and fault controls remain unchanged through P5-T39E closure; evidence=SignedEdgeNetworkAdmissionReceipt.
- **Read first:** Production Qualification Edge gate and Edge Profile conformance.
- **Change surface:** Desktop adapter/tests, Edge campaign harness/manifest and dry-run evidence.
- **Implement:** explicit Desktop-versus-Edge capability identity, fixed fleet/version/workload/fault/observer/cleanup contracts and receipt cursors.
- **Prove:** Desktop regressions, manifest resolution, reduced disconnect/reconnect/drain, ten-control/two-byte envelope, conflicts/order/replay/key/clock/restart/update/revoke/wipe and cleanup.
- **Stop/hand off:** Desktop/simulation cannot replace physical Edge conformance; unavailable fleet or required spend is `NOT_EVALUABLE`/`NEGATIVE`.
- **Unlocks:** `P5-T39A`.

## P5-T39A — Start the 100-node seven-day disconnect

- **Outcome:** Admit 100 declared physical nodes spanning N, N-1 and N-2, verify leases/recovery copies/snapshots and begin the frozen seven-day disconnected interval with immutable start evidence.
- **Depends on:** current `P5-T39=SUCCESS`, unchanged frozen Edge Campaign Manifest and phase-candidate fingerprint heads, and current `EP-P5-EDGE-FLEET`, `EP-P5-EDGE-MEDIA`, `EP-P5-EDGE-NETWORK`, and `EP-P5-EDGE-OPERATORS` receipt heads.
- **External prerequisites:** label=EP-P5-EDGE-FLEET; kind=HARDWARE; requires=AVAILABLE; accountable=Edge qualification lead; validity=100 owned or donated physical ARM64 nodes with declared N N-1 N-2 allocation and no required spend remain admitted through P5-T39E closure; evidence=SignedEdgeFleetAdmissionReceipt | label=EP-P5-EDGE-MEDIA; kind=HARDWARE; requires=AVAILABLE; accountable=Edge qualification lead; validity=separate recovery media identities capacities and custody remain admitted for every node through P5-T39E closure; evidence=SignedEdgeRecoveryMediaAdmissionReceipt | label=EP-P5-EDGE-NETWORK; kind=NETWORK_IDENTITY; requires=DECLARED; accountable=Edge network authority; validity=disconnect reconnect Gateway routes identities bandwidth and fault controls remain unchanged through P5-T39E closure; evidence=SignedEdgeNetworkAdmissionReceipt | label=EP-P5-EDGE-OPERATORS; kind=HUMAN_AUTHORITY; requires=ASSIGNED; accountable=Edge qualification lead; validity=disconnect reconnect monitoring incident and owner-review duties remain assigned with declared separation through P5-T39E closure; evidence=SignedEdgeOperatorAssignmentReceipt.
- **Read first:** frozen Edge campaign manifest and disconnect runbook.
- **Change surface:** campaign admission/start evidence only.
- **Implement:** none; admit and disconnect the frozen physical fleet without product, harness, manifest or fixture repair.
- **Prove:** exact node/hardware/release/key/lease/media/workload tuple, all observers live, no Platform connectivity and receipt progression begins.
- **Stop/hand off:** missing/virtual/unadmitted node, required spend, drift or incomplete recovery-copy protection is `NOT_EVALUABLE`/`NEGATIVE`; start is `RUNNING`.
- **Unlocks:** `P5-T39B`.

## P5-T39B — Monitor the seven-day disconnected interval

- **Outcome:** Maintain low-context receipt-cursor checks across seven complete elapsed days while nodes accumulate the frozen one-million-event/50-GB workload and declared clock/key/restart/update/revoke cases.
- **Depends on:** active `P5-T39A` with matching immutable manifest.
- **Read first:** latest cursor, node health summary, fault schedule and only open incidents.
- **Change surface:** monitoring/fault/incident evidence only.
- **Implement:** none; append frozen-schedule health, workload, fault and incident evidence without changing nodes, candidate, manifest or elapsed history.
- **Prove:** trusted elapsed interval, live node activity, bounds/leases/recovery copies, no silent reconnect/drift and every scheduled offline fault.
- **Stop/hand off:** dashboard status alone is insufficient; stopped node, missing interval, unauthorized connectivity or changed input follows the frozen disposition.
- **Unlocks:** `P5-T39C` after at least `7 * 24h` with no uncovered interval.

## P5-T39C — Start reconnect and bounded Edge drain

- **Outcome:** Reconnect the exact fleet, freeze the drain start/cursors and begin N/N-1/N-2 upcast/transfer/owner-decision/cleanup under at most ten control synchronizations and two byte transfers.
- **Depends on:** completed valid `P5-T39B` and unchanged campaign tuple.
- **Read first:** campaign reconnect/drain manifest, Gateway/owner acceptance contracts.
- **Change surface:** reconnect/drain start and observer evidence only.
- **Implement:** none; reconnect the unchanged fleet and start the bounded drain without resetting cursors or modifying the candidate, workload or manifest.
- **Prove:** exact event/object roots, full 100-node admission, concurrency limits active, observers live and forward receipt movement.
- **Stop/hand off:** a partial fleet, reset cursor, changed workload or unbounded transfer is `NOT_EVALUABLE` or `NEGATIVE`.
- **Unlocks:** `P5-T39D`.

## P5-T39D — Monitor the 24-hour Edge drain

- **Outcome:** Observe the complete drain by immutable cursor, inject the frozen 5% conflicts and hostile order/replay/key/restart cases and preserve owner acceptance/rejection evidence.
- **Depends on:** active `P5-T39C` with matching manifest.
- **Read first:** latest drain cursor, fault schedule and open incidents only.
- **Change surface:** monitoring/fault/incident evidence only.
- **Implement:** none; execute the frozen conflict/adversarial schedule and append drain observations without repair or evidence rewriting.
- **Prove:** event/object/receipt progress, concurrency/resource/latency distributions, conflict handling and no duplicate/loss/silent overwrite/leak/forbidden authority.
- **Stop/hand off:** failure to complete within `24h`, cursor gap, drift or authority/privacy invariant breach follows the frozen disposition.
- **Unlocks:** `P5-T39E` after drain and node cleanup terminate.

## P5-T39E — Close the Edge engineering campaign

- **Outcome:** Reconcile the full seven-day/100-node/one-million-event/50-GB/24-hour sequence, every fault/owner result, node/recovery-copy cleanup and Desktop separation into one terminal result.
- **Depends on:** completed `P5-T39A`–`P5-T39D` and unchanged manifest/candidate.
- **Read first:** frozen manifest, complete receipt range and Production Qualification Edge gate.
- **Change surface:** signed evidence aggregation and cleanup only.
- **Implement:** none; reconcile the immutable seven-day and drain receipt ranges and emit the terminal result without product, harness or manifest mutation.
- **Prove:** all N/N-1/N-2 nodes/workload/timings/limits/faults/results, zero loss/duplicate/silent overwrite/leak/forbidden authority and terminal cleanup.
- **Stop/hand off:** Desktop/simulation cannot fill a physical-node gap; incomplete workload/timing is `PARTIAL`, missing trustworthy evidence `NOT_EVALUABLE`.
- **Unlocks:** Phase 5 closure and Golden Journey G31–G32 only on `SUCCESS`.

## P5-T40 — Close specialist cross-context workflows and deletion

- **Outcome:** Run owner-ordered chains for standards, Credential, EQA, Clinical, Research and Edge and obtain complete per-context retention/deletion/audit/backup evidence with no cross-context SQL or transport-owned truth.
- **Depends on:** `P5-T01A` and `P5-T27A` `MERGED`; current terminal `SUCCESS` from `P5-T09`, `P5-T15`, `P5-T20C`, `P5-T26`, `P5-T30C`, and `P5-T39E` on one unchanged phase-candidate fingerprint. Their dependency chains are the complete Phase 5 implementation set; no unnamed implementation prerequisite may be inferred or waived here.
- **Read first:** Golden Journey G05–G06/G23–G32, Production Qualification specialist gates.
- **Change surface:** cross-context contract/e2e/evidence and deletion adapters only.
- **Implement:** none; execute and reconcile the frozen owner-ordered workflows, retention/deletion/audit/backup receipts and final cleanup without changing product behavior or qualification inputs.
- **Prove:** restart/replay/unavailable owner/wrong purpose at each handoff, retention/Legal Hold/backup obligations, exact source/receipt counts and terminal cleanup.
- **Stop/hand off:** isolated context successes cannot substitute for the ordered closure; early campaign evidence will be rerun if exact-release inputs change.
- **Unlocks:** Phase 6 portability/complete operations and Phase 7 exact-release gates.
