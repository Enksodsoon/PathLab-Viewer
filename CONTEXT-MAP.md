# Context Map

The navigable decision frontier is [Wayfinder: Ratify the zero-cash Full-Surface production endpoint](https://github.com/Enksodsoon/PathLab-Viewer/issues/187). The complete destination and delivery sequence are defined in [Final Production Endpoint](./docs/architecture/FINAL_PRODUCTION_ENDPOINT.md), with current-to-target coverage in the [Feature Completion Matrix](./docs/architecture/FEATURE_COMPLETION_MATRIX.md), exact gates in [Production Qualification](./docs/architecture/PRODUCTION_QUALIFICATION.md), and non-conflating status transitions in the [Delivery State Ledger](./docs/architecture/DELIVERY_STATE_LEDGER.md). The Zero-Cash physical mapping is defined in [Zero-Cash Service Cells](./docs/architecture/ZERO_CASH_SERVICE_CELLS.md), its host authority in [Zero-Cash Runtime](./docs/architecture/ZERO_CASH_RUNTIME.md), its recovery boundary in [Zero-Cash Key Management](./docs/architecture/ZERO_CASH_KEY_MANAGEMENT.md) and [Zero-Cash Durability and Security](./docs/architecture/ZERO_CASH_DURABILITY_SECURITY.md), its current-data cutover in [SQLite to PostgreSQL](./docs/architecture/SQLITE_TO_POSTGRESQL.md), clinical and imaging exchange in [Clinical and Imaging Interoperability](./docs/architecture/CLINICAL_IMAGING_INTEROPERABILITY.md), learning exchange in [Learning and Credential Interoperability](./docs/architecture/LEARNING_INTEROPERABILITY.md), governed domain behavior in [Governed Product Workflows](./docs/architecture/GOVERNED_PRODUCT_WORKFLOWS.md), role authority in the [Role and Approval Matrix](./docs/architecture/ROLE_APPROVAL_MATRIX.md), disconnected acquisition in the [Edge Node Profile](./docs/architecture/EDGE_NODE_PROFILE.md), executable system evidence in the [Golden Institution Journey](./docs/architecture/GOLDEN_INSTITUTION_JOURNEY.md), and local authoring inference in [Teacher AI Stack](./docs/architecture/TEACHER_AI_STACK.md); none changes the ownership boundaries below.

## Contexts

- [Platform Governance](./docs/contexts/platform-governance/CONTEXT.md): defines product-wide freedom, deployment-profile, qualification, and claim boundaries
- [Learning Catalog](./docs/contexts/learning-catalog/CONTEXT.md): owns canonical learning structures, enrollment, immutable event snapshots, learner progress/completion evidence, and achievement definitions
- [Credential Ledger](./docs/contexts/credential-ledger/CONTEXT.md): owns Institution-issued Achievement Credential lifecycle and verification status
- [Trust and Governance](./docs/contexts/trust-governance/CONTEXT.md): owns principals, institution membership, authorization, and purpose-specific identities
- [Audit and Operations](./docs/contexts/audit-operations/CONTEXT.md): owns authoritative audit evidence, operational observations, backup generations, and restore evidence
- [Integration Gateway](./docs/contexts/integration-gateway/CONTEXT.md): owns External Registrations, Adapter Credentials, protocol exchange, and delivery evidence
- [Imaging Control](./docs/contexts/imaging-control/CONTEXT.md): owns source assets, derivative identity, privacy review, and publication authority
- [Live Learning](./docs/contexts/live-learning/CONTEXT.md): owns active teaching sessions, presenter authority, durable interactions, and attendance
- [Teacher Authoring](./docs/contexts/teacher-authoring/CONTEXT.md): owns authoring drafts, local model bundles, generation provenance, and teacher approval
- [Assessment](./docs/contexts/assessment/CONTEXT.md): owns versioned items, timed attempts, responses, submissions, and grades
- [Clinical Shadow](./docs/contexts/clinical-shadow/CONTEXT.md): owns governed read-only clinical copies and their purpose, provenance, and deidentification boundaries
- [Research](./docs/contexts/research/CONTEXT.md): owns governed projects, dataset snapshots, reproducible jobs, and resulting artifacts
- [EQA](./docs/contexts/eqa/CONTEXT.md): owns external-quality schemes, Institution participation, sealed submissions, scoring, appeals, and reports
- [Edge Federation](./docs/contexts/edge-federation/CONTEXT.md): owns enrolled edge nodes, local acquisition state, checkpointed synchronization, and conflict evidence

## Relationships

- **Platform Governance -> every product context**: deployment and qualification claims must name the profile and evidence boundary to which they apply.
- **Learning Catalog -> Live Learning, Assessment, EQA, and Integration Gateway**: consumers reference canonical versions, Learner Progress Evidence, Completion Evidence, Achievement Definition Versions, or event-start snapshots instead of owning competing course or roster truth. The legacy Study surface is a Catalog/Assessment journey, not a context.
- **Trust and Governance -> every product context**: contexts authorize an institution-scoped Principal or a purpose-specific subject instead of creating independent user accounts.
- **Trust and Governance -> every data store, processor, backup, and adapter**: governed data may exist or move only under the Institution's current Residency Policy and, where required, an explicit Transfer Grant.
- **Trust and Governance -> every record-owning context**: each context enforces the Institution's Retention Schedule beneath PathLab's ceiling, honors only valid Legal Holds, and returns deletion evidence covering its derivatives and indexes.
- **Trust and Governance -> every service and signed artifact**: services receive least-privilege Service Credentials and named Key Versions through an operator-unlocked Credential Bundle; no context owns the root recovery material.
- **Every product context -> Audit and Operations**: authoritative security and governance transitions commit through the context's outbox and are projected into append-only Audit Records without granting Audit and Operations ownership of domain state.
- **Audit and Operations -> every authoritative store**: backup policy, restore drills, and evidence freshness cover each store while excluding explicitly rebuildable data.
- **Each product context -> its PostgreSQL namespace**: the owning context alone writes its tables and outbox; other contexts consume versioned events into local projections instead of reading tables or creating cross-context foreign keys.
- **Product contexts -> Integration Gateway**: contexts request protocol exchange through owned commands or events; they never expose their databases, Service Credentials, or Adapter Credentials to external systems.
- **Imaging Control -> Delivery and product contexts**: Imaging Control authorizes immutable assets and publications; consumers reference manifests rather than owning or rewriting imaging bytes.
- **Learning Catalog -> Live Learning**: a Class Session starts from immutable course, content, and roster snapshots.
- **Trust and Governance -> Live Learning**: session participation and presenter authority are granted through institution-scoped policy.
- **Learning Catalog and Imaging Control -> Teacher Authoring**: the authoring workspace receives immutable, purpose-authorized content and asset snapshots without acquiring their ownership.
- **Teacher Authoring -> Learning Catalog and Assessment**: only an explicitly Teacher-Approved Draft may request publication as a new Lesson or Item Version; local model output never publishes or grades directly.
- **Learning Catalog -> Assessment**: an Exam Session starts from immutable content and roster snapshots.
- **Learning Catalog -> Credential Ledger**: an immutable Institution-approved Achievement Definition Version and Achievement Eligibility Proposal are required before an Achievement Credential may be issued.
- **Assessment -> Credential Ledger**: only an approved Grade and its immutable evidence may establish Assessment Achievement eligibility; Credential Ledger independently authorizes issuance.
- **Trust and Governance -> Credential Ledger**: the Ledger uses an opaque Purpose Identity, Institution roles, Step-Up Authentication, and separation-of-duty evidence without copying authentication secrets.
- **Credential Ledger -> Integration Gateway**: the Ledger decides issuer authority, proof validity, expiry, revocation, supersession, and each Local Verification Decision. Gateway validates only the External Registration, transport envelope, size and structural-schema admission, quarantine, and delivery of approved Open Badges and CLR exchanges.
- **Assessment -> Audit and Operations**: confirmed submissions and grade changes require corresponding durable audit evidence.
- **Integration Gateway -> Clinical Shadow**: FHIR and DICOM adapters deliver validated source exchanges without gaining authority over Clinical Shadow records.
- **Clinical Shadow -> Learning Catalog, Research, and Imaging Control**: data crosses the clinical boundary only as a separately authorized deidentified snapshot.
- **Research Control -> Research Compute**: Control grants immutable inputs and quotas; Compute returns artifacts and provenance without production database authority.
- **Trust and Governance -> EQA**: EQA uses purpose-specific Institution participant identities rather than learner or staff identities.
- **Learning Catalog and Imaging Control -> EQA**: an EQA Round references immutable case, content, and asset versions without transferring their ownership.
- **Trust and Governance, Learning Catalog, and Platform Governance -> Edge Federation**: the Platform issues bounded node identity, policy, and catalog snapshots; an Edge Node cannot redefine those authorities while disconnected.
- **Edge Federation -> Imaging Control and product contexts**: signed, checkpointed Sync Batches propose local acquisitions and domain events to their canonical Platform owners; only an owner-issued Acceptance Receipt makes them shared truth.
