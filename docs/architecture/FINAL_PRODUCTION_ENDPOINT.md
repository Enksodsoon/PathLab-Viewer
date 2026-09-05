# Final Production Endpoint

Capacity authority: [ADR 0132](../adr/0132-qualify-3000-learner-combined-broadcast-with-zero-cash-admission.md) controls the 3,000-learner combined target, media quality, zero-cash admission and safe partial-delivery rules. Existing operating limits remain unchanged until implementation and fresh qualification.

This is the ratified destination for PathLab Full-Surface Launch. It is a plan and acceptance contract, not evidence that the current source, deployment, or OCI host has reached the destination. Planning, implementation, local checks, protected checks, merge, deployment, pilot, qualification, and activation remain separate states under the [Delivery State Ledger](./DELIVERY_STATE_LEDGER.md). The dependency-ordered, one-chat work packages are maintained in the [Full-Surface Execution Playbook](../execution/README.md).

The complete accepted decision history is indexed in the [Production Endpoint Decision Register](../adr/README.md). The [Architecture Precedence Register](./ARCHITECTURE_PRECEDENCE.md) classifies current and historical planning documents and routes every conflict back to its controller. The navigable closure is [Wayfinder: Ratify the zero-cash Full-Surface production endpoint](https://github.com/Enksodsoon/PathLab-Viewer/issues/187).

## Destination

One Institution can install an offline-verifiable PathLab release on an eligible owned or donated Linux ARM64 host and operate every ratified capability without mandatory SaaS, paid API, hosted identity provider, model endpoint, registry, KMS, observability service, standards certification, or recurring software fee. The Zero-Cash Production Profile remains a bounded, non-HA single-host system whose heavy capabilities run in mutually exclusive modes. The same domain contracts support a later Funded Scalable Profile without creating a paid software edition or rewriting authority boundaries.

Full-Surface Launch is reached only when:

1. every context and capability in the [Feature Completion Matrix](./FEATURE_COMPLETION_MATRIX.md) satisfies the complete vertical-slice rule;
2. every exact-release gate in [Production Qualification](./PRODUCTION_QUALIFICATION.md) has current `SUCCESS` evidence on the intended host and backup target;
3. zero-cash, licensing, asset-rights, privacy, clinical-boundary, backup, restore, and key-recovery gates are all clean;
4. the golden Institution journey and supervised limited pilot complete without an unresolved critical failure; and
5. separately authorized operators activate the exact qualified release.

## Deployment profiles

| Profile | Authority and capacity | Availability and cost claim |
| --- | --- | --- |
| Zero-Cash Production | One authoritative home cell; 2 OCPU, 12 GB host RAM, a 150 GB raw encrypted primary data volume, and one separately capacity-qualified independent backup target; mutually exclusive heavy modes | No SLA, no fixed RTO, and no whole-site-loss promise. The admissible live governed corpus is dynamically lower than 150 GB because databases, WAL, indexes, staging, rebuild work, deletion, and safety headroom also consume the volume. The initial zero-cash claim covers a completed 90-day window; once 12 months exist, the mature claim covers the immediately preceding rolling 12 months. Neither is a permanent infrastructure promise. |
| Funded Scalable | The same contexts may split into dedicated processes, hosts, PostgreSQL authorities, object-delivery nodes, workers, and media forwarders | Infrastructure, connectivity, operations, redundancy, and certification may cost money. PathLab-authored software and every mandatory software path retain the Free Software Guarantee. |

## Logical authority

| Context | Sole authority | Never owns |
| --- | --- | --- |
| Platform Governance | deployment profiles, release and qualification claims, mode policy, software-freedom evidence | product-domain records |
| Trust and Governance | Principals, Institutions, Memberships, roles, Purpose Identities, Authentication Credentials, processing/residency/retention policy, deletion coordination | courses, grades, assets, Adapter Credentials, Achievement Credentials |
| Learning Catalog | Courses and immutable versions, modules, lessons, cohorts, enrollments, roster/event snapshots, Learner Progress Evidence, Completion Evidence, Achievement Definitions and immutable versions | authentication, attempts, grades, issued Achievement Credentials |
| Credential Ledger | Achievement Credential issuance, supersession, expiry, revocation, status, and verification evidence | grades, course definitions, Adapter Credentials |
| Audit and Operations | audit projections and integrity, operational observations, backup/restore and qualification evidence | source domain truth |
| Integration Gateway | External Registrations, Adapter Credentials, exact exchange profiles, delivery and quarantine evidence | external-system or PathLab domain authority |
| Imaging Control | source and derivative assets, manifests, privacy state, annotations, publication authority | teaching, assessment, clinical purpose |
| Live Learning | Class Sessions, presenter authority, durable interactions, attendance | canonical roster, asset or course state |
| Teacher Authoring | drafts, admitted local model bundles, generation provenance, teacher approval | publication, grading, diagnosis |
| Assessment | item versions, exam sessions, attempts, revisions, submissions, grading and appeals | roster, identity, Achievement Credential issuance |
| Clinical Shadow | governed read-only clinical copies, Purpose Grants, source provenance, deidentification admission | patient-care truth or writeback |
| Research | projects, dataset snapshots, environment manifests, jobs and reviewed artifacts | production model activation or clinical claims |
| EQA | schemes, rounds, Institution participants, sealed submissions, scoring, adjudication, reports and appeals | learner assessment or Achievement Credentials |
| Edge Federation | node enrollment, leases, local acquisition authority, sync batches, acceptance/conflict evidence | Platform identity, policy, grade, publication or shared truth |

## Zero-Cash process topology

Logical boundaries survive co-deployment: every context keeps its own logical database, database role, migrations, outbox, API/event schemas, filesystem grants, and retention/deletion worker.

| Runtime | Lifecycle | Responsibility and failure boundary |
| --- | --- | --- |
| Caddy | resident | HTTPS, same-origin static web/DZI delivery, bounded reverse proxy, public-path isolation. It never authenticates by inventing application authority. |
| PostgreSQL 18 | resident | One cluster containing one logical database per context. It is authoritative only through owning context transactions and outboxes. |
| PgBouncer | resident | Enforces the 32-application-connection allocation inside the 48-backend Connection Envelope. Pool exhaustion sheds work instead of expanding the cap. |
| JetStream | resident | Durable delivery only. PostgreSQL outboxes remain authoritative; stream loss is reconstructed from acknowledged outbox state. |
| `pathlab-control` | resident | Platform, Trust, Catalog, Credential Ledger, Audit intake/projection, mode control, Imaging metadata/delivery authorization, notices, and minimal LTI/verification ingress. Modules cannot query another context database. |
| `pathlab-live` | Live reservation | One leased owner per Class Session, synchronized state, durable interactions, attendance, and media authorization. A crash recovers from committed state and epoch leases. |
| Galene | Teacher Broadcast sub-reservation | One client-encoded teacher stream to receive-only learners, no recording or transcoding. Failure invokes slides/text Media Fallback. |
| `pathlab-assessment` | Assessment reservation | Timed delivery, Attempt Leases, provisional-journal reconciliation, submissions, deterministic/manual scoring, moderation, grade and appeal workflow. |
| `pathlab-batch` | one named batch reservation | Exactly one of Imaging conversion/upload finalization, Clinical/external exchange, EQA, bulk Edge sync, credential/export batch, backup-supporting inventory, or portability import/export. Each invocation declares one fail-closed mode. |
| tusd and admitted format tools | Imaging sub-reservation | Resumable byte receipt and bounded format validation/conversion under an Upload Reservation. They do not create asset authority. |
| `pathlab-research-runner` | Research reservation | One signed, noninteractive, quota-bound job with no production database credential and no default egress. Signed manifests are the only boundary crossing. |

The host reserves 2 GB for the OS/page cache, 3 GB and 0.75 OCPU for resident services, 6 GB and 1 OCPU for the active mode, and at least 1 GB plus 0.25 OCPU for emergencies. Pressure at 80 percent throttles, 90 percent sheds, and a hard integrity/confidentiality/stability threat invokes Safety Shutdown. Disk swap and restart loops are prohibited recovery strategies. Exact role, approval, and self-approval boundaries are frozen in the [Role and Approval Matrix](./ROLE_APPROVAL_MATRIX.md).

## Edge node topology

An Edge Node is an enrolled, physically separate acquisition appliance, not a second Platform authority and not an assumption about the existing Desktop client. It runs only the bounded acquisition, approved snapshot reading, local encryption, signed batch, resumable transfer, recovery-copy, update, and remote-revocation paths defined by the [Edge Node Profile](./EDGE_NODE_PROFILE.md). Offline operation cannot administer identity, issue or change grades or Achievement Credentials, publish material, operate EQA or Clinical Shadow, or run Research. Platform owner contexts make every shared-truth decision and return signed acceptance, rejection, or conflict evidence.

## Authoritative data paths

1. A context transaction changes its own PostgreSQL state and appends its event atomically.
2. Delivery workers publish the outbox event to JetStream and record its acknowledgement; event delivery never makes JetStream the source of truth.
3. Consumers update their own projections idempotently from versioned events and never read another context's tables.
4. Large bytes become immutable content-addressed objects with signed manifests. New bytes stay `PENDING_PROTECTION` until the off-host target acknowledges them.
5. Browser publication requires a static DZI Browser Representation. OME-Zarr, DICOM, FHIR, and annotation formats are bounded exchange representations, never alternate authority paths.
6. Every governed mutation carries Institution, Principal or Purpose Identity, policy version, Key Version, audit linkage, retention trigger, and deletion classification.
7. Every delivery transition emits the subject-bound receipt required by the [Delivery State Ledger](./DELIVERY_STATE_LEDGER.md); no deployment, check, or historical campaign is silently promoted into qualification or activation.

## Compatibility and portability

- HTTP, event, and package contracts are versioned in repository-owned OpenAPI, JSON Schema, and event schemas.
- Producers make additive changes within a current-through-N-minus-two window; readers use explicit upcasters and preserve original hashes and versions.
- There are no cross-context foreign keys, shared write tables, database replication as domain integration, or dual-write cutovers.
- A Portable Institution Package imports only into a new or empty Institution in v1. Authentication Credentials, Adapter Credentials, Service Credentials, sessions, private keys, recovery material, caches, and rebuildable derivatives never travel. A governed Achievement Credential travels only as its Credential Document, Verification Snapshot, current Credential Status and history, and Custody Transfer Receipt; no issuer private key or status-service secret accompanies that artifact set.
- External mappings arrive disabled, integrations are re-registered, authenticators re-enrolled, expired data omitted, and retention resolves to the stricter authorized schedule.

## Funded scalability ladder

Scaling is evidence-driven, not a different product:

1. **Vertical and lifecycle tuning:** retain one home cell, improve queries/caches, and preserve exclusive modes while measured peaks remain within the qualified envelope.
2. **Delivery and worker split:** move static object delivery, media forwarding, conversion, standards exchange, and Research runners to dedicated owned capacity using the same manifests and commands.
3. **Context process split:** extract `pathlab-live`, Assessment, Integration, Credential Ledger, EQA, Clinical, and other contexts behind their existing contracts; move each logical database to a dedicated PostgreSQL authority when its pool, storage, or maintenance boundary requires it.
4. **Institution home cells:** assign Institutions to independent cells and route by stable Institution identity. Class Sessions retain single-owner sharding; no active-active shared writes are introduced.
5. **Funded resilience:** add PostgreSQL standby/failover, clustered delivery, replicated object storage, multiple SFUs and regional cells only with separately qualified consistency, residency, recovery, and operating-cost evidence.

A sustained approach to 70 percent of a qualified CPU, memory, database, queue, storage, bandwidth, or latency envelope, or a requirement the current failure domain cannot meet, opens a scale decision before capacity is exhausted.

## Delivery roadmap

| Phase | Required result | Exit gate |
| --- | --- | --- |
| 0. Canonical plan and legal cleanup | Versioned context map, ADRs, feature matrix, licenses/notices/SBOM policy, independent brand and Asset Rights Ledger; remove or replace every unresolved mandatory dependency or asset | No unresolved authority, license, rights, zero-cash, or destination decision |
| 1. Resident foundation | Native OpenTofu/systemd install, encrypted PostgreSQL-per-context databases, PgBouncer, outboxes/JetStream, key unlock, mode controller, local observability, signed offline kit | Clean-host install/upgrade/rollback/host-loss and resource-containment evidence |
| 2. Trust and operations | Complete roles, WebAuthn, learner lifecycle, Processing Grants, residency/retention, deletion saga, audit chain, notices, backup target and restore control | Cross-Institution, privilege, deletion, key, backup and restore adversarial gates |
| 3. Imaging foundation migration | Preserve and re-admit Viewer/Library/uploads/DZI/shares/annotations/Desktop data under Imaging authority; cut SQLite to PostgreSQL once; protect objects before authority | Static DZI, maximum-source, privacy, annotation, storage, migration and rollback gates |
| 4. Learning foundation | Catalog, deterministic learning journey, Teacher Authoring/SmolLM2, Live Learning/Galene, Assessment, learner identities and complete authoring/grading workflows | Catalog, AI, 3,000-participant combined Live Learning and Teacher Broadcast and 300-learner Assessment campaigns |
| 5. Standards and specialist contexts | Integration profiles, Credential Ledger, EQA, Clinical Shadow, Research and Edge federation | Per-context conformance, isolation, workload and authority gates |
| 6. Portability and complete operations | Portable Institution Package, 35-day lifecycle, disconnected recovery rotation, release kits, upgrade and migration support | Full restore of the actual maximum-admitted live corpus, a separate 150-GB portability/restore-throughput corpus on capacity-qualified build or restore storage, two expiry cycles, key loss, ransomware and cold recovery |
| 7. Prequalification closure | Every prerequisite exact-release technical/context campaign followed by the executable [Golden Institution Journey](./GOLDEN_INSTITUTION_JOURNEY.md) on the target host and backup target | Current `SUCCESS` evidence for every non-pilot gate, with no stale or waived mandatory result |
| 8. Pilot, qualification and activation | Supervised bounded Institution pilot, incident closure, final zero-cash/capacity recheck, aggregate Qualification Claim, then separately authorized release activation | `PILOT_VALIDATED`, then `PRODUCTION_QUALIFIED`, then an Activation Receipt naming the exact deployed release, profile, host, evidence and approved claims |

Phases may overlap only where authority and evidence dependencies permit. A later phase cannot convert an earlier `NO-GO` into assumed success.

## Terminal outcomes

- `SUCCESS`: every mandatory gate passed on the exact candidate and activation may be separately considered.
- `PARTIAL`: useful work exists but at least one mandatory gate is incomplete or stale; no Full-Surface claim.
- `NEGATIVE`: a frozen gate failed; fix, redesign, or explicitly redraw the destination before retrying.
- `NOT_EVALUABLE`: required data, hardware, endpoint, rights, or evidence was unavailable; absence of evidence is not success.

The plan is complete when the decision frontier is empty and implementation work can be derived without inventing product authority. Production is complete only after the implementation, evidence, pilot, and activation conditions above are independently satisfied.
