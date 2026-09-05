# Architecture Precedence Register

This register is the review surface for PathLab planning and architecture
precedence. It classifies the complete `docs/architecture` inventory, preserves
historical material, and names the authority that controls when documents
conflict. Classification does not implement, deploy, qualify, or activate a
capability.

## Precedence rule

Apply the first matching authority below. A lower-ranked document may add
compatible detail, but it cannot change a higher-ranked decision.

1. Accepted ADRs and the [Final Production Endpoint](./FINAL_PRODUCTION_ENDPOINT.md)
   control destination architecture and ratified decisions.
2. Current context, security, qualification, lifecycle, and interoperability
   contracts control compatible detail within their declared boundaries.
3. The execution plan controls task ordering and evidence requirements only.
4. Baseline and migration-input documents describe existing or transitional
   behavior only.
5. Superseded documents and evidence records retain history but create no
   current requirement.

Accepted ADR text is append-only. A change to accepted authority, lifecycle,
security, privacy, capacity, recovery, zero-cash, rights, or activation semantics
requires a named superseding ADR; this register cannot make that change.

## Status vocabulary

| Status | Meaning |
|---|---|
| `CANONICAL` | Ratified destination, decision, acceptance, or lifecycle authority. |
| `SUPPORTING_CONTRACT` | Current detail that is authoritative only where compatible with canonical controllers. |
| `CANONICAL_EXECUTION_PLAN` | Current sequencing and evidence authority; it cannot change architecture decisions. |
| `BASELINE_ONLY` | Observation or contract for the currently implemented product; it is not destination authority. |
| `MIGRATION_INPUT_ONLY` | Transitional implementation input; conflicting topology, security, recovery, or activation language is non-authoritative. |
| `SUPERSEDED` | Retained history with no current normative authority. |
| `EVIDENCE_ONLY` | Receipt or observation that may prove a claim but cannot create one. |
| `NAVIGATION_ONLY` | Index or map that points to authorities without becoming one. |

## Complete architecture inventory

Every file in `docs/architecture` other than this register appears exactly once.

| Document | Status | Controlling canonical source for conflicts |
|---|---|---|
| `docs/architecture/CAPACITY_EVIDENCE_PROTOCOL_V3.md` | `SUPPORTING_CONTRACT` | [Production Qualification](./PRODUCTION_QUALIFICATION.md) and ADR [0132](../adr/0132-qualify-3000-learner-combined-broadcast-with-zero-cash-admission.md); standalone protocol foundation, not measured qualification or activation authority. |
| `docs/architecture/ADAPTIVE_VIEWER_CAPACITY.md` | `BASELINE_ONLY` | [Final Production Endpoint](./FINAL_PRODUCTION_ENDPOINT.md), [Production Qualification](./PRODUCTION_QUALIFICATION.md), ADRs [0066](../adr/0066-require-the-full-1200-participant-classroom-campaign.md), [0067](../adr/0067-require-the-full-300-organization-eqa-campaign.md), and [0128](../adr/0128-qualify-every-context-on-the-exact-release.md) |
| `docs/architecture/ADMIN_ANNOTATIONS.md` | `BASELINE_ONLY` | [Imaging Control context](../contexts/imaging-control/CONTEXT.md), [Role Approval Matrix](./ROLE_APPROVAL_MATRIX.md), ADRs [0076](../adr/0076-version-annotations-under-single-editor-leases.md) and [0111](../adr/0111-readmit-anonymous-shares-and-restrict-annotation-publication.md) |
| `docs/architecture/CLASSROOM_PROTECTED_JOBS.md` | `BASELINE_ONLY` | [Live Learning context](../contexts/live-learning/CONTEXT.md), [Zero-Cash Runtime](./ZERO_CASH_RUNTIME.md), ADRs [0038](../adr/0038-schedule-heavy-work-through-prioritized-mode-reservations.md), [0066](../adr/0066-require-the-full-1200-participant-classroom-campaign.md), and [0110](../adr/0110-separate-durable-live-learning-evidence-from-ephemeral-state.md) |
| `docs/architecture/CLINICAL_IMAGING_INTEROPERABILITY.md` | `SUPPORTING_CONTRACT` | [Final Production Endpoint](./FINAL_PRODUCTION_ENDPOINT.md), ADRs [0084](../adr/0084-freeze-clinical-shadow-on-fhir-r4-4-0-1.md), [0087](../adr/0087-bound-dicom-microscopy-to-calibrated-single-plane-wsi-and-2d-annotations.md), [0090](../adr/0090-admit-only-rights-cleared-clinical-terminologies.md), and [0093](../adr/0093-self-qualify-clinical-interoperability-before-institution-activation.md) |
| `docs/architecture/DELIVERY_STATE_LEDGER.md` | `CANONICAL` | [Final Production Endpoint](./FINAL_PRODUCTION_ENDPOINT.md) and ADRs [0128](../adr/0128-qualify-every-context-on-the-exact-release.md), [0129](../adr/0129-require-one-golden-institution-journey.md), and [0130](../adr/0130-separate-plan-build-deploy-qualification-and-activation.md) |
| `docs/architecture/EDGE_NODE_PROFILE.md` | `SUPPORTING_CONTRACT` | [Final Production Endpoint](./FINAL_PRODUCTION_ENDPOINT.md), ADRs [0019](../adr/0019-partition-edge-and-platform-authority.md), [0020](../adr/0020-bound-edge-offline-operation-with-expiring-leases.md), [0070](../adr/0070-bound-zero-cash-edge-federation-capacity.md), and [0114](../adr/0114-make-edge-own-bounded-desktop-offline-acquisition.md) |
| `docs/architecture/FEATURE_COMPLETION_MATRIX.md` | `CANONICAL` | [Final Production Endpoint](./FINAL_PRODUCTION_ENDPOINT.md), [Delivery State Ledger](./DELIVERY_STATE_LEDGER.md), and ADRs [0126](../adr/0126-require-a-complete-vertical-slice-before-calling-a-feature-complete.md), [0127](../adr/0127-finish-and-requalify-the-entire-ratified-feature-surface.md), and [0131](../adr/0131-make-the-wayfinder-map-and-versioned-plan-canonical.md) |
| `docs/architecture/FINAL_PRODUCTION_ENDPOINT.md` | `CANONICAL` | Accepted [ADR register](../adr/README.md), especially ADR [0131](../adr/0131-make-the-wayfinder-map-and-versioned-plan-canonical.md) |
| `docs/architecture/GOLDEN_INSTITUTION_JOURNEY.md` | `SUPPORTING_CONTRACT` | [Production Qualification](./PRODUCTION_QUALIFICATION.md), [Delivery State Ledger](./DELIVERY_STATE_LEDGER.md), and ADR [0129](../adr/0129-require-one-golden-institution-journey.md) |
| `docs/architecture/GOVERNED_PRODUCT_WORKFLOWS.md` | `SUPPORTING_CONTRACT` | [Final Production Endpoint](./FINAL_PRODUCTION_ENDPOINT.md), [Role Approval Matrix](./ROLE_APPROVAL_MATRIX.md), and ADRs [0103](../adr/0103-use-institution-language-and-composable-governed-roles.md), [0104](../adr/0104-require-two-person-authorization-for-high-risk-decisions.md), and [0107](../adr/0107-coordinate-deletion-through-a-fail-closed-saga.md) |
| `docs/architecture/IDENTITY_GOVERNANCE.md` | `BASELINE_ONLY` | [Trust Governance context](../contexts/trust-governance/CONTEXT.md), [Role Approval Matrix](./ROLE_APPROVAL_MATRIX.md), ADRs [0053](../adr/0053-require-webauthn-for-privileged-memberships.md), [0103](../adr/0103-use-institution-language-and-composable-governed-roles.md), [0104](../adr/0104-require-two-person-authorization-for-high-risk-decisions.md), and [0105](../adr/0105-separate-durable-learners-from-guests-and-minimize-minor-data.md) |
| `docs/architecture/LEARNING_INTEROPERABILITY.md` | `SUPPORTING_CONTRACT` | [Final Production Endpoint](./FINAL_PRODUCTION_ENDPOINT.md), ADRs [0096](../adr/0096-integrate-as-a-manually-registered-lti-tool-only.md) and [0097](../adr/0097-consume-oneroster-without-transferring-catalog-authority.md) |
| `docs/architecture/LIBRARY_DOMAIN.md` | `MIGRATION_INPUT_ONLY` | [Imaging Control context](../contexts/imaging-control/CONTEXT.md), [Governed Product Workflows](./GOVERNED_PRODUCT_WORKFLOWS.md), ADRs [0074](../adr/0074-separate-revocable-restricted-shares-from-public-releases.md), [0075](../adr/0075-publish-folders-and-collections-as-immutable-manifests.md), and [0111](../adr/0111-readmit-anonymous-shares-and-restrict-annotation-publication.md) |
| `docs/architecture/OME_TIFF_PIPELINE.md` | `MIGRATION_INPUT_ONLY` | [Imaging Control context](../contexts/imaging-control/CONTEXT.md), [Clinical Imaging Interoperability](./CLINICAL_IMAGING_INTEROPERABILITY.md), ADRs [0014](../adr/0014-keep-dzi-for-browser-delivery-and-standards-for-exchange.md), [0031](../adr/0031-preserve-imaging-authority-and-evict-rebuildable-bytes.md), and [0111](../adr/0111-readmit-anonymous-shares-and-restrict-annotation-publication.md) |
| `docs/architecture/PASSWORD_RECOVERY.md` | `MIGRATION_INPUT_ONLY` | [Trust Governance context](../contexts/trust-governance/CONTEXT.md), [Role Approval Matrix](./ROLE_APPROVAL_MATRIX.md), ADRs [0053](../adr/0053-require-webauthn-for-privileged-memberships.md), [0103](../adr/0103-use-institution-language-and-composable-governed-roles.md), and [0104](../adr/0104-require-two-person-authorization-for-high-risk-decisions.md) |
| `docs/architecture/PORTABILITY.md` | `SUPPORTING_CONTRACT` | [Final Production Endpoint](./FINAL_PRODUCTION_ENDPOINT.md), ADRs [0059](../adr/0059-use-opentofu-and-native-systemd-as-production-authorities.md), [0083](../adr/0083-export-portable-context-neutral-institution-packages.md), and [0115](../adr/0115-import-portable-packages-only-into-empty-institutions.md) |
| `docs/architecture/POSTGRES_BACKUP_RESTORE.md` | `MIGRATION_INPUT_ONLY` | [Zero-Cash Durability and Security](./ZERO_CASH_DURABILITY_SECURITY.md), [SQLite to PostgreSQL](./SQLITE_TO_POSTGRESQL.md), ADRs [0060](../adr/0060-keep-opentofu-state-encrypted-local-and-single-writer.md), [0082](../adr/0082-cut-sqlite-over-once-without-dual-write.md), and [0119](../adr/0119-combine-append-only-backups-with-disconnected-rotation.md) |
| `docs/architecture/POSTGRES_MIGRATION.md` | `MIGRATION_INPUT_ONLY` | [SQLite to PostgreSQL](./SQLITE_TO_POSTGRESQL.md), ADRs [0034](../adr/0034-use-one-postgresql-cluster-with-context-owned-namespaces.md), [0035](../adr/0035-use-one-logical-database-per-bounded-context.md), and [0082](../adr/0082-cut-sqlite-over-once-without-dual-write.md) |
| `docs/architecture/POSTGRES_RUNTIME_CUTOVER.md` | `MIGRATION_INPUT_ONLY` | [Zero-Cash Runtime](./ZERO_CASH_RUNTIME.md), [SQLite to PostgreSQL](./SQLITE_TO_POSTGRESQL.md), ADRs [0034](../adr/0034-use-one-postgresql-cluster-with-context-owned-namespaces.md), [0035](../adr/0035-use-one-logical-database-per-bounded-context.md), and [0082](../adr/0082-cut-sqlite-over-once-without-dual-write.md) |
| `docs/architecture/PRODUCTION_QUALIFICATION.md` | `CANONICAL` | [Final Production Endpoint](./FINAL_PRODUCTION_ENDPOINT.md), [Delivery State Ledger](./DELIVERY_STATE_LEDGER.md), ADRs [0066](../adr/0066-require-the-full-1200-participant-classroom-campaign.md), [0067](../adr/0067-require-the-full-300-organization-eqa-campaign.md), [0128](../adr/0128-qualify-every-context-on-the-exact-release.md), and [0129](../adr/0129-require-one-golden-institution-journey.md) |
| `docs/architecture/REBUILDABLE_TILE_CACHE.md` | `MIGRATION_INPUT_ONLY` | [Imaging Control context](../contexts/imaging-control/CONTEXT.md), [Zero-Cash Durability and Security](./ZERO_CASH_DURABILITY_SECURITY.md), ADRs [0031](../adr/0031-preserve-imaging-authority-and-evict-rebuildable-bytes.md) and [0043](../adr/0043-require-static-dzi-before-browser-publication.md) |
| `docs/architecture/RECEIPT_SCHEMA_REGISTRY.md` | `CANONICAL` | [Delivery State Ledger](./DELIVERY_STATE_LEDGER.md), [Production Qualification](./PRODUCTION_QUALIFICATION.md), and ADRs [0128](../adr/0128-qualify-every-context-on-the-exact-release.md) and [0130](../adr/0130-separate-plan-build-deploy-qualification-and-activation.md) |
| `docs/architecture/ROLE_APPROVAL_MATRIX.md` | `SUPPORTING_CONTRACT` | [Trust Governance context](../contexts/trust-governance/CONTEXT.md), ADRs [0103](../adr/0103-use-institution-language-and-composable-governed-roles.md), [0104](../adr/0104-require-two-person-authorization-for-high-risk-decisions.md), and [0105](../adr/0105-separate-durable-learners-from-guests-and-minimize-minor-data.md) |
| `docs/architecture/SQLITE_TO_POSTGRESQL.md` | `SUPPORTING_CONTRACT` | [Final Production Endpoint](./FINAL_PRODUCTION_ENDPOINT.md), ADRs [0034](../adr/0034-use-one-postgresql-cluster-with-context-owned-namespaces.md), [0035](../adr/0035-use-one-logical-database-per-bounded-context.md), and [0082](../adr/0082-cut-sqlite-over-once-without-dual-write.md) |
| `docs/architecture/TEACHER_AI_STACK.md` | `SUPPORTING_CONTRACT` | [Teacher Authoring context](../contexts/teacher-authoring/CONTEXT.md), ADRs [0049](../adr/0049-run-teacher-ai-only-on-the-teacher-device.md), [0054](../adr/0054-guarantee-permissively-licensed-open-weight-teacher-ai.md), [0056](../adr/0056-require-an-independent-300-task-ai-quality-gate-per-tier.md), [0057](../adr/0057-cap-teacher-ai-download-memory-and-latency.md), and [0058](../adr/0058-require-offline-integrity-and-zero-egress-ai-evidence.md) |
| `docs/architecture/ZERO_CASH_DURABILITY_SECURITY.md` | `SUPPORTING_CONTRACT` | [Final Production Endpoint](./FINAL_PRODUCTION_ENDPOINT.md), ADRs [0072](../adr/0072-require-an-independent-institution-owned-backup-target.md), [0079](../adr/0079-require-continuous-and-release-bound-restore-evidence.md), [0117](../adr/0117-enforce-synchronous-off-host-protection-before-authority.md), [0118](../adr/0118-bound-backup-lifecycle-and-recovery-horizons.md), [0119](../adr/0119-combine-append-only-backups-with-disconnected-rotation.md), [0120](../adr/0120-separate-backup-keys-privileges-and-recovery-evidence.md), [0121](../adr/0121-require-operated-90-day-durability-qualification.md), and [0122](../adr/0122-qualify-the-durability-supply-chain-and-egress-boundary.md) |
| `docs/architecture/ZERO_CASH_KEY_MANAGEMENT.md` | `SUPPORTING_CONTRACT` | [Final Production Endpoint](./FINAL_PRODUCTION_ENDPOINT.md), ADRs [0033](../adr/0033-use-operator-unlocked-envelope-key-management.md), [0047](../adr/0047-implement-threshold-recovery-with-sops-age-and-systemd-credentials.md), [0073](../adr/0073-encrypt-primary-data-with-luks2-and-purpose-keys.md), and [0120](../adr/0120-separate-backup-keys-privileges-and-recovery-evidence.md) |
| `docs/architecture/ZERO_CASH_RUNTIME.md` | `SUPPORTING_CONTRACT` | [Final Production Endpoint](./FINAL_PRODUCTION_ENDPOINT.md), ADRs [0001](../adr/0001-separate-zero-cash-production-from-funded-scalability.md), [0004](../adr/0004-make-every-planned-context-a-zero-cash-launch-gate.md), [0040](../adr/0040-partition-the-zero-cash-host-with-emergency-headroom.md), [0041](../adr/0041-degrade-modes-before-their-hard-resource-limit.md), [0059](../adr/0059-use-opentofu-and-native-systemd-as-production-authorities.md), and [0116](../adr/0116-qualify-zero-cash-accounting-over-evidence-windows.md) |
| `docs/architecture/ZERO_CASH_SERVICE_CELLS.md` | `SUPPORTING_CONTRACT` | [Zero-Cash Runtime](./ZERO_CASH_RUNTIME.md), ADRs [0038](../adr/0038-schedule-heavy-work-through-prioritized-mode-reservations.md) and [0066](../adr/0066-require-the-full-1200-participant-classroom-campaign.md) |

## Repository planning families

| Path or family | Status | Controller or limitation |
|---|---|---|
| `docs/adr/README.md` and accepted `docs/adr/0001` through `0132` | `CANONICAL` | Accepted decision history; individual ADR supersession metadata controls within the family. |
| `docs/contexts/*/CONTEXT.md` and `CONTEXT-MAP.md` | `SUPPORTING_CONTRACT` | Final Production Endpoint and accepted ADRs control conflicts. |
| `docs/execution/*.md` | `CANONICAL_EXECUTION_PLAN` | Sequencing and evidence only; no architecture or activation override. |
| `docs/superpowers/specs/2026-08-14-pathlab-free-classroom-design.md` and `docs/superpowers/plans/2026-08-14-pathlab-free-classroom.md` | `SUPERSEDED` | Final Production Endpoint, Zero-Cash Runtime, Production Qualification, ADRs 0038, 0066, 0128, and 0129. |
| `docs/classroom/IMPLEMENTATION.md` | `BASELINE_ONLY` | Live Learning context, Final Production Endpoint, and accepted ADRs. |
| `apps/web/DESIGN.md` | `BASELINE_ONLY` | Current UI implementation only; governed workflow, accessibility, rights, and release contracts control destination changes. |
| `README.md`, `docs/PROJECT_GUIDE.md`, and `docs/REPOSITORY_MAP.md` | `NAVIGATION_ONLY` | They may describe current implementation and link authorities; they do not override them. |
| `docs/evidence/**` and generated receipts | `EVIDENCE_ONLY` | Evidence may establish a result only under the governing qualification or task contract. |

## Conflict-to-controller map

| Decision topic | Non-authoritative legacy input | Controlling source |
|---|---|---|
| Production topology, footprint, and service isolation | Free-classroom design, current Compose/systemd observations, protected-job baseline | Final Production Endpoint; Zero-Cash Runtime; ADRs 0001, 0038, 0040, 0041, 0059 |
| Capacity numbers and production claims | Adaptive Viewer Capacity and 1,200/1,500-seat free-classroom targets | Production Qualification; Delivery State Ledger; ADRs 0002, 0006, 0022, 0066, 0128 |
| Workforce identity, roles, and privileged recovery | Single-administrator recovery and first identity slice | Trust Governance context; Role Approval Matrix; ADRs 0053, 0103, 0104, 0105 |
| Persistence ownership and cutover | Single SQLite or single-target PostgreSQL migration assumptions | SQLite to PostgreSQL; ADRs 0034, 0035, 0036, 0082 |
| Imaging, derivatives, shares, and annotations | Current OME-TIFF, library, and private-annotation implementation contracts | Imaging Control context; Clinical Imaging Interoperability; ADRs 0014, 0031, 0074, 0075, 0076, 0111 |
| Cache durability | Current dynamic cache index and LRU metadata | Imaging Control context; Zero-Cash Durability and Security; ADRs 0031 and 0043 |
| Backup, restore, and recovery authority | Program 0B `pg_dump` plus HMAC bundle | Zero-Cash Durability and Security; ADRs 0032, 0072, 0079, 0117–0122 |
| Lifecycle, release, qualification, and activation | “Approved for implementation,” `BUILT`, local tests, or historical campaign targets | Delivery State Ledger; Production Qualification; ADRs 0081, 0126–0130 |
| Zero-cash semantics | Expiring allowance, promotional tier, or unqualified operational observation | Zero-Cash Runtime; ADRs 0001, 0004, 0116, 0121, 0122 |

## Reference rule

A planning document may cite `BASELINE_ONLY`, `MIGRATION_INPUT_ONLY`, or
`SUPERSEDED` material only when the citation is explicitly labeled with that
status or an equivalent word (`baseline`, `migration input`, `legacy`, or
`superseded`) and the nearby text names its controlling canonical source. Modal
language such as “must,” “shall,” “required,” “approved,” or “production
authority” attached to a non-authoritative source without that qualification is
a stale-plan reference and fails repository validation.
