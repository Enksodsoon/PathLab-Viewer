# Phase 1 — Resident Runtime and Context Data Plane

Phase 1 builds the lightweight, offline-verifiable resident foundation. Its host-loss proof covers empty/synthetic reinstall, encrypted OpenTofu-state recovery, and quorum credential rewrap. Authoritative production-data recovery belongs to Phase 2 and complete long-duration recovery evidence to Phases 6–7. All tasks inherit [README](./README.md).

## P1-T01 — Create bounded-context module and service-cell skeletons

- **Outcome:** Establish repository-owned module boundaries for all fourteen contexts and explicit entry points for `pathlab-control`, `pathlab-live`, `pathlab-assessment`, `pathlab-batch`, and `pathlab-research-runner` without moving domain authority prematurely.
- **Depends on:** `P0-T12` `MERGED` with `SUCCESS`.
- **Read first:** [Context Map](../../CONTEXT-MAP.md), [Zero-Cash Service Cells](../architecture/ZERO_CASH_SERVICE_CELLS.md), all `docs/contexts/*/CONTEXT.md` files.
- **Change surface:** server package layout, entry-point metadata, architecture/import-boundary tests.
- **Implement:** one context package/API/event namespace each; explicit allowed dependency direction; no cross-context ORM model imports or shared write repository.
- **Prove:** architecture tests fail on cross-context table/repository access and every configured process imports only its declared contexts.
- **Stop/hand off:** this task creates scaffolding, not new product behavior or authority migration.
- **Unlocks:** `P1-T02`, `P1-T03`, `P1-T06`, `P1-T10`, and context implementation tasks.

## P1-T02 — Version repository-owned HTTP, event, and package contracts

- **Outcome:** Define OpenAPI/JSON Schema/event/package versioning, compatibility metadata, original-payload preservation, additive-change rules, and current-through-N-minus-two reader/upcaster contracts.
- **Depends on:** `P1-T01` and `P0-T10` `MERGED`.
- **Read first:** [Final Production Endpoint](../architecture/FINAL_PRODUCTION_ENDPOINT.md) compatibility section, ADR 0124, [Receipt Schema Registry](../architecture/RECEIPT_SCHEMA_REGISTRY.md).
- **Change surface:** `schemas/`, API/event libraries, contract tests and contributor guidance.
- **Implement:** schema identity and registry, producer/consumer compatibility checks, deterministic upcasters, unsupported-version quarantine and original hash retention.
- **Prove:** N, N-1 and N-2 fixtures plus duplicate/reordered/unknown/future versions; schema breaking-change gate.
- **Stop/hand off:** no upcaster may invent domain facts or overwrite the preserved original.
- **Unlocks:** `P1-T06`, `P1-T07`, `P3-T02`, `P4-T01`, and specialist protocol tasks.

## P1-T03 — Bootstrap PostgreSQL 18 context databases and roles

- **Outcome:** Provision one pinned PostgreSQL 18 cluster with one logical database, owner/migrator/runtime/read-only role set, connection allocation, tablespace/data-location declaration, and revocation test per context.
- **Depends on:** `P1-T01` `MERGED`.
- **Read first:** ADRs 0034–0036, [Zero-Cash Runtime](../architecture/ZERO_CASH_RUNTIME.md), [SQLite to PostgreSQL](../architecture/SQLITE_TO_POSTGRESQL.md), and [PostgreSQL runtime cutover](../architecture/POSTGRES_RUNTIME_CUTOVER.md) as legacy Compose-era baseline and migration input only; the Final Production Endpoint, accepted ADRs, Zero-Cash Runtime, and SQLite-to-PostgreSQL contract control every conflict.
- **Change surface:** deployment database bootstrap, configuration, tests and operator runbook; no SQLite cutover.
- **Implement:** least-privilege grants, database isolation, safe credential injection and reserved operational/emergency connections inside the 48-backend envelope.
- **Prove:** every service role can access only its database; cross-database and schema escalation attacks fail; `fsync`, `full_page_writes`, and `synchronous_commit` cannot be downgraded by application roles.
- **Stop/hand off:** shared runtime roles or cross-context grants are `NEGATIVE`.
- **Unlocks:** `P1-T04`, `P1-T05`, `P1-T06`, `P1-T10`.

## P1-T04 — Establish per-context migration ownership

- **Outcome:** Give each context its own migration head, lock/ordering rules, expand-only release policy, bootstrap fixtures, downgrade/rollback declaration, and drift detector.
- **Depends on:** `P1-T02` and `P1-T03` `MERGED`.
- **Read first:** ADRs 0035, 0081, 0082; [SQLite to PostgreSQL](../architecture/SQLITE_TO_POSTGRESQL.md); and the [PostgreSQL migration contract](../architecture/POSTGRES_MIGRATION.md) as legacy single-database migration input only. The Final Production Endpoint, accepted ADRs, and current per-context SQLite-to-PostgreSQL contract control every conflict.
- **Change surface:** `migrations/` or context migration directories, migration CLI, schema-state tests and runbooks.
- **Implement:** prevent one context migration from reading/writing another database; record exact heads in release/evidence manifests; distinguish backward-compatible binary rollback from schema reversal.
- **Prove:** empty bootstrap, N/N-1 upgrade, interrupted migration, drift and wrong-order cases across every context skeleton.
- **Stop/hand off:** destructive or contract migrations require a separately sequenced release; do not add dual writes.
- **Unlocks:** all context schema tasks, `P1-T23`.

## P1-T05 — Enforce the PgBouncer connection envelope

- **Outcome:** Deploy PgBouncer with the 32-application-connection allocation inside the 48-backend cap, per-service pools, transaction/session compatibility decisions, emergency reserve, metrics and fail-closed exhaustion behavior.
- **Depends on:** `P1-T03` `MERGED`.
- **Read first:** ADR 0036, [Final Production Endpoint](../architecture/FINAL_PRODUCTION_ENDPOINT.md), current database/session consumers.
- **Change surface:** PgBouncer configuration, service database clients, deployment units, load/failure tests.
- **Implement:** audit every synchronous, asynchronous, streaming and long-lived consumer; prevent SSE/media paths from holding database connections.
- **Prove:** pool saturation sheds bounded work without exceeding 48 backends, starving operations, leaking sessions, or wedging health endpoints.
- **Stop/hand off:** an unbounded pool or long-lived stream retaining a connection is `NEGATIVE`.
- **Unlocks:** `P1-T16`, `P1-T19`, context load tasks.

## P1-T06 — Implement atomic context outboxes

- **Outcome:** Add a reusable owning-context transaction/outbox library and per-context outbox tables/events that atomically bind aggregate version, event ID, schema version, Institution, policy/key/retention/audit metadata, payload hash and delivery state.
- **Depends on:** `P1-T02`, `P1-T03`, and `P1-T04` `MERGED`.
- **Read first:** ADR 0011, [Final Production Endpoint](../architecture/FINAL_PRODUCTION_ENDPOINT.md), [Delivery State Ledger](../architecture/DELIVERY_STATE_LEDGER.md).
- **Change surface:** context persistence/event libraries, migrations and transaction/idempotency tests.
- **Implement:** atomic commit, monotonic aggregate versions, retry leases, acknowledged-delivery marker and retention safe for reconstruction.
- **Prove:** failures pre-commit, post-commit/pre-publish and post-publish/pre-ack; no missing or duplicate semantic transition.
- **Stop/hand off:** logs, JetStream messages, or audit projections cannot replace the owner outbox.
- **Unlocks:** `P1-T07`, `P2-T15`, and all authoritative context mutations.

## P1-T07 — Add JetStream delivery and idempotent projections

- **Outcome:** Deploy single-node JetStream as reconstructable durable transport with subject ACLs, bounded storage, publisher acknowledgements, idempotent consumers, dead-letter/quarantine handling and replay from context outboxes.
- **Depends on:** `P1-T02` and `P1-T06` `MERGED`.
- **Read first:** ADR 0011, service-cell topology, event compatibility contract.
- **Change surface:** JetStream configuration/systemd unit, delivery worker, consumer library, migrations/tests/runbook.
- **Implement:** retain original event/version/hash, enforce Institution/context subjects, cap queues, reconstruct streams without changing owner truth.
- **Prove:** loss/recreate, duplicate/delay/reorder/missing/malicious message, N/N-2 upcast, consumer restart and queue pressure.
- **Stop/hand off:** a consumer writing another context's authority or treating stream state as source truth is `NEGATIVE`.
- **Unlocks:** audit projections and every cross-context workflow.

## P1-T08 — Implement the filesystem object and manifest adapter

- **Outcome:** Add content-addressed immutable object storage on the encrypted data volume with atomic writes, signed/versioned manifests, reference accounting, filesystem grants, integrity verification and rebuildable/authoritative classification.
- **Depends on:** `P1-T01`, `P1-T02`, and `P0-T10` `MERGED`.
- **Read first:** ADR 0010, [Final Production Endpoint](../architecture/FINAL_PRODUCTION_ENDPOINT.md), and the migration-input-only [Rebuildable Tile Cache](../architecture/REBUILDABLE_TILE_CACHE.md); the Final Production Endpoint, Imaging Control context, and accepted ADRs control conflicts.
- **Change surface:** object storage library, manifest schemas, filesystem layout, integrity and traversal tests.
- **Implement:** hash-addressed paths, safe staging/rename, size/count limits, ownership metadata, no user-derived paths and deterministic inventory.
- **Prove:** partial writes, hash collision simulation, traversal/symlink, corruption, concurrent admit/delete and restart cases.
- **Stop/hand off:** object bytes do not become domain authority merely because they exist.
- **Unlocks:** `P1-T09`, `P3-T04`, portability and backup object tasks.

## P1-T09 — Implement storage admission and protection states

- **Outcome:** Implement the Storage Admission Ledger and `STAGED -> PENDING_PROTECTION -> AUTHORITATIVE` eligibility contract with dynamic headroom, immutable-object inventory and registered protection evidence hooks.
- **Depends on:** `P1-T06` and `P1-T08` `MERGED`.
- **Read first:** ADRs 0044–0045, 0117; [Zero-Cash Durability and Security](../architecture/ZERO_CASH_DURABILITY_SECURITY.md), [Receipt Schema Registry](../architecture/RECEIPT_SCHEMA_REGISTRY.md).
- **Change surface:** storage accounting/admission service, schemas/migrations, APIs, metrics and tests.
- **Implement:** reserve source, derivative, WAL, database, staging, deletion and safety headroom; fail closed on stale/absent protection or capacity evidence.
- **Prove:** concurrent reservations, stale metrics, disk/inode pressure, failed protection, restart and release of abandoned reservations.
- **Stop/hand off:** this task consumes synthetic protection receipts; independent target-side protection is `P2-T21`.
- **Unlocks:** authoritative imaging/object admission and backup protection.

## P1-T10 — Define service principals and credential bundles

- **Outcome:** Create one non-human Principal, database role, Service Credential, filesystem/network grant, outbox identity and rotation declaration per owning context/service process.
- **Depends on:** `P1-T01` and `P1-T03` `MERGED`.
- **Read first:** [Role and Approval Matrix](../architecture/ROLE_APPROVAL_MATRIX.md), [Zero-Cash Key Management](../architecture/ZERO_CASH_KEY_MANAGEMENT.md), service cells.
- **Change surface:** trust bootstrap fixtures, credential manifest schemas, service configuration and privilege tests.
- **Implement:** least privilege from the exact registry-generated owner-handler capabilities and operation enums in the Role and Approval Matrix, including Deployment Selection, Credential Custody Transfer and Clinical Snapshot handlers; no namespace wildcard, shared superuser, cross-context secret, unmapped mutation, unknown operation, or human approval ability.
- **Prove:** generated-registry-to-service/handler/operation reconciliation plus credential swap, wrong service/database/filesystem/subject/capability, wildcard, unknown enum, revocation, and rotation fixtures.
- **Stop/hand off:** never commit credentials, keys or private infrastructure identifiers to source/evidence.
- **Unlocks:** `P1-T11`, `P1-T12`, `P1-T16`, `P1-T17`.

## P1-T11 — Build two-of-three SOPS/age recovery bundles

- **Outcome:** Implement offline creation, update and verification of three independent SOPS key groups with threshold two, one age identity per custodian, purpose-bound Key Versions and encrypted credential documents.
- **Depends on:** `P1-T10` and `P0-T09` `MERGED`.
- **Read first:** [Zero-Cash Key Management](../architecture/ZERO_CASH_KEY_MANAGEMENT.md), ADRs 0033, 0047, 0073.
- **Change surface:** offline key tooling, schemas/test vectors, operator runbook and security tests.
- **Implement:** AB/AC/BC recovery, custodian replacement, data-key update, public verification material and safe failure cleanup.
- **Prove:** all pairs succeed; one share fails; retired/duplicate/wrong identities fail; no plaintext in args, environment, trace, journal, repo or evidence.
- **Stop/hand off:** raw multi-recipient age is prohibited because it is not threshold recovery.
- **Unlocks:** `P1-T11A`, `P1-T12`, `P1-T13`, `P2-T24`.

## P1-T11A — Implement application-level envelope encryption and Key Versions

- **Outcome:** Provide one audited owner-context library and persistence contract that envelope-encrypts every deletion-bound governed plaintext before database or object persistence using random per-object or purpose-and-identical-retention-epoch DEKs.
- **Depends on:** `P0-T03A`, `P0-T10A`, `P1-T03`, `P1-T08`, `P1-T10`, and `P1-T11` `MERGED`.
- **Read first:** Zero-Cash Key Management primary-data encryption, Zero-Cash Durability encryption/deletion boundary and all classified field inventories.
- **Change surface:** cryptography/key-version library, wrapped-DEK metadata schemas, database/object adapters, test vectors, owner integration contract and security runbook.
- **Implement:** admitted AEAD and randomness; Institution/context/purpose/schema/retention-bound associated data; distinct Key Versions and owning-context decrypt capability; old-key decrypt-only periods; rotation/rewrap/crypto-erasure/negative recovery; ciphertext-only backup/portability behavior; and explicit coverage for Clinical identifiers, recovery material, Adapter Credentials and Assessment Provisional Journals.
- **Prove:** cross-Institution/context/purpose/key substitution, nonce misuse, tamper/truncation, wrong retention epoch, rotation/restart, expired-key negative decrypt, plaintext scans of database/object/backup/export/log/evidence paths and deterministic owner coverage checks.
- **Stop/hand off:** no home-grown cipher, provider KMS/online service, LUKS-only substitution, shared cross-context decrypt key or physical-overwrite claim.
- **Unlocks:** primary-volume integration, every governed owner schema and deletion/crypto-erasure evidence.

## P1-T12 — Implement volatile systemd credential unlock

- **Outcome:** Build `pathlab-credentials.target` and the console/root unlock flow that rewraps only authorized SOPS documents into named host-bound `LoadCredentialEncrypted=` blobs under tmpfs.
- **Depends on:** `P1-T10` and `P1-T11` `MERGED`.
- **Read first:** key-management boot/restart flow and [Zero-Cash Runtime](../architecture/ZERO_CASH_RUNTIME.md).
- **Change surface:** systemd targets/units, unlock scripts, credential manifests, runbook and leak tests.
- **Implement:** protected services remain stopped until complete unlock; atomic version selection; temporary identity destruction; same-boot restart and replacement-host rewrap paths.
- **Prove:** missing/wrong/expired share, incomplete bundle, reboot, service restart, journald/process-list/environment inspection and host-key replacement.
- **Stop/hand off:** systemd host key is wrapping convenience, never recovery authority.
- **Unlocks:** `P1-T16`, `P1-T17`, `P1-T24`.

## P1-T13 — Provision the LUKS2 primary data volume

- **Outcome:** Implement operator-unlocked LUKS2 layout for PostgreSQL, private objects, WAL staging and authoritative audit data with purpose-key hooks, mount ordering and fail-closed service dependencies.
- **Depends on:** `P1-T11`, `P1-T11A`, and `P1-T12` `MERGED`.
- **Read first:** key-management primary-data section, ADR 0073, durability protection boundary.
- **Change surface:** OpenTofu/systemd/storage scripts, mount units, SELinux labels and recovery runbook.
- **Implement:** root-recovery-derived volume key custody, stable device identity, safe formatting guard, integrity/free-space observations and no service start on wrong/unmounted paths.
- **Prove:** reboot/unlock, missing/wrong device, read-only/corrupt mount, host replacement fixture and explicit provider-encryption defense-in-depth status.
- **Stop/hand off:** never format a non-empty or ambiguously identified volume; exact-device uncertainty requires operator intervention.
- **Unlocks:** `P1-T14`, `P1-T16`, `P1-T24`.

## P1-T14 — Build OpenTofu OL9 ARM64 infrastructure and state custody

- **Outcome:** Replace production dependence on mutable Compose/Terraform workflows with pinned OpenTofu modules for the selected Oracle Linux 9 ARM64 host, storage/network identity and separately governed targets, using encrypted local single-writer state.
- **Depends on:** `P0-T09`, `P1-T11`, and `P1-T13` `MERGED`.
- **Read first:** [Zero-Cash Runtime](../architecture/ZERO_CASH_RUNTIME.md), current `deploy/terraform`, ADRs 0059–0060.
- **Change surface:** `deploy/opentofu/` or deliberate migration of `deploy/terraform/`, provider mirror/lock, state/apply scripts and runbooks.
- **Implement:** exact pins/checksums/region image OCID resolution, encrypted state/plan, monotonic signed apply manifest, lease, off-host acknowledgement and recovery.
- **Prove:** validate/plan/apply fixture, concurrent/stale/tampered state, no-network init, recovery from signed kit/state/quorum, and no hosted state/control-plane dependency.
- **Stop/hand off:** never apply to live OCI merely to prove local implementation; live mutation needs its own deployment task and operator boundary.
- **Unlocks:** `P1-T15`, `P1-T16`, `P1-T22`, `P1-T24`.

## P1-T15 — Implement immutable native release layout

- **Outcome:** Install verified bundles under `/opt/pathlab/releases/<release-sha>/`, manage an atomic `current` link, immutable configuration identity, Caddy upstream selection and bounded previous-release retention.
- **Depends on:** `P1-T14` `MERGED`.
- **Read first:** Zero-Cash Runtime native layout/deployment switch, ADR 0081.
- **Change surface:** release installer/verifier, filesystem/systemd/Caddy integration and rollback tests.
- **Implement:** reject mutable tags, wrong digests, unknown files, in-place edits and incompatible migration heads; separate installation, deployment selection and later governed activation.
- **Prove:** parallel install, atomic switch, crash at each boundary, disk pressure, previous-release rollback and artifact/config hash reporting.
- **Stop/hand off:** a successful install is evidence-only and not a Delivery State deployment or activation.
- **Unlocks:** `P1-T16`, `P1-T22`, `P1-T23`.

## P1-T16 — Supervise the resident control plane with systemd

- **Outcome:** Add hardened native units and dependencies for Caddy, PostgreSQL, PgBouncer, JetStream and `pathlab-control`, each with dedicated user, credential, filesystem/network, restart and health contracts.
- **Depends on:** `P1-T05`, `P1-T07`, `P1-T10`, `P1-T12`, `P1-T13`, and `P1-T15` `MERGED`.
- **Read first:** runtime/service-cell docs and current deploy/systemd assets.
- **Change surface:** `deploy/systemd/`, service configuration, health/readiness endpoints and integration tests.
- **Implement:** exact boot ordering, watchdogs, bounded `StartLimit*`, graceful drain, no Compose/Moby production authority.
- **Prove:** cold boot, dependency delay/failure, crash loops, credential lock, restart order and resident idle resource envelope.
- **Stop/hand off:** Docker/Compose may remain a development tool but cannot be an undocumented production dependency.
- **Unlocks:** `P1-T17`, `P1-T19`, `P1-T21`.

## P1-T17 — Supervise heavy service cells and fail-closed modes

- **Outcome:** Add inactive-by-default hardened units/targets for `pathlab-live`, Galene, `pathlab-assessment`, `pathlab-batch`, tusd/format tools and `pathlab-research-runner`, each accepting one declared mode and returning to zero processes after drain.
- **Depends on:** `P1-T10`, `P1-T12`, `P1-T15`, and `P1-T16` `MERGED`.
- **Read first:** [Zero-Cash Service Cells](../architecture/ZERO_CASH_SERVICE_CELLS.md), Final Endpoint topology, ADRs 0037–0042.
- **Change surface:** service entry points, systemd targets/templates, mode manifests, process-count tests.
- **Implement:** explicit database role, event subjects, filesystem/network grant, cgroup and shutdown/checkpoint contract per invocation.
- **Prove:** wrong/missing/multiple mode, concurrent launch, crash/drain/restart and zero-inactive-process assertions.
- **Stop/hand off:** task provides lifecycle skeletons, not specialist feature implementations.
- **Unlocks:** `P1-T18`, context mode integrations.

## P1-T18 — Implement Mode Reservations and transitions

- **Outcome:** Build the durable reservation aggregate, readiness evaluation, priority/queue policy, signed READY/NO-GO and drained receipts, transition controller and maintenance/recovery modes.
- **Depends on:** `P0-T10`, `P1-T06`, and `P1-T17` `MERGED`.
- **Read first:** ADRs 0005, 0038–0041; [Golden Journey reservation sequence](../architecture/GOLDEN_INSTITUTION_JOURNEY.md); receipt registry.
- **Change surface:** Platform Governance schema/service/API/operator UI, systemd controller, tests and runbook.
- **Implement:** exactly one heavy reservation; staged learner transition; no ordinary preemption of active learner work; Safety Shutdown only for integrity/confidentiality/stability threat.
- **Prove:** conflicting requests, stale readiness, process-count mismatch, drain timeout, control restart, pressure transition and `F-MODE-01`.
- **Stop/hand off:** a feature flag or systemd start alone cannot represent a reservation.
- **Unlocks:** `P1-T19`, all heavy-context implementation and campaigns.

## P1-T19 — Enforce cgroup resource partitions and pressure states

- **Outcome:** Implement host partitions reserving 2 GB OS/page cache, 3 GB/0.75 OCPU resident control, 6 GB/1 OCPU active mode, and >=1 GB/0.25 OCPU emergency headroom with 80% throttle, 90% shed and hard Safety Shutdown behavior.
- **Depends on:** `P1-T05`, `P1-T16`, `P1-T17`, and `P1-T18` `MERGED`.
- **Read first:** Final Endpoint topology, ADRs 0040–0041, and [Adaptive Viewer Capacity](../architecture/ADAPTIVE_VIEWER_CAPACITY.md) as legacy measurement-baseline input only; the [Final Production Endpoint](../architecture/FINAL_PRODUCTION_ENDPOINT.md) and current accepted resource/capacity contracts control any conflict.
- **Change surface:** systemd slices/unit limits, pressure monitor/controller, metrics, load/fault tests and runbook.
- **Implement:** `MemoryHigh`, `MemoryMax`, `MemorySwapMax=0`, CPU/Tasks limits, deterministic admission/degradation and protected health/operator access.
- **Prove:** memory/CPU/pool/disk/inode pressure, restart loops and recovery; no swap-based survival or limit expansion.
- **Stop/hand off:** exceeding a hard envelope is `NEGATIVE`, not an invitation to tune the gate after observation.
- **Unlocks:** `P1-T24` and every capacity campaign.

## P1-T20 — Enforce SELinux, firewall, and default-deny egress

- **Outcome:** Add enforcing SELinux policy, Unix/filesystem labels, inbound firewall contracts and production/build/backup/restore egress controls for every resident and mode process.
- **Depends on:** `P0-T11`, `P1-T16`, and `P1-T17` `MERGED`.
- **Read first:** Zero-Cash Runtime, security/egress baseline and service credential manifests.
- **Change surface:** SELinux policy, systemd sandboxing, firewall/network scripts, tests and incident/runbook docs.
- **Implement:** allow only declared same-host, Institution-supplied network identity, backup-target, or approved protocol endpoints by mode; log bounded denials without secrets.
- **Prove:** permissive mode is rejected; undeclared DNS/HTTP/socket/filesystem/exec access and cross-service impersonation fail.
- **Stop/hand off:** an online dependency needed only because it was not mirrored is a supply-chain failure, not an egress exception.
- **Unlocks:** `P1-T22`, `P1-T24`, Research/Clinical/Edge isolation.

## P1-T21 — Provide compact health and local observability foundations

- **Outcome:** Standardize `/livez`, `/readyz`, dependency/migration/outbox/backup/mode/resource states, bounded OpenMetrics/log/trace interfaces and operator-visible readiness without treating health as qualification.
- **Depends on:** `P1-T16`, `P1-T18`, and `P1-T19` `MERGED`.
- **Read first:** Audit and Operations context, ADR 0078, existing readiness/runtime protection code.
- **Change surface:** service health APIs, metrics/logging foundations, local dashboards/tests.
- **Implement:** low-cardinality metrics, privacy filters, 30-second scrape support, reason-coded fail-closed readiness and separate liveness.
- **Prove:** healthy, locked, stale migration, lost pool/stream/volume, pressure and mode mismatch fixtures; health remains responsive during shed state.
- **Stop/hand off:** HTTP 200 is not evidence of a usable API, data path, backup or qualification gate.
- **Unlocks:** `P1-T24`, Phase 2 audit/operations tasks.

## P1-T22 — Assemble and close the final exact-candidate Offline Release Kit

- **Outcome:** After every Phase 1 mutation is merged, assemble one final signed ARM64 Offline Release Kit whose immutable artifact root contains the exact applications, native dependencies, provider mirror, database migrations, systemd/SELinux assets, recovery tools, manifests, SBOMs, notices, source/attribution, checksums, tests and install/restore runbooks used by the clean-host campaign.
- **Depends on:** `P1-T01`–`P1-T21`, `P1-T22A`, and `P1-T23` `MERGED`.
- **External prerequisites:** label=P1-T22-FINAL-ARM64-RUNNER; kind=HARDWARE; requires=OWNED_NATIVE_ARM64_SELINUX_OFFLINE_BUILD_RUNNER_RESERVED; accountable=Release-Infrastructure-Owner; validity=exact-Phase-1-candidate-toolchain-and-final-assembly-window; evidence=immutable-signed-Final-ARM64-Build-Runner-Reservation-Receipt
- **Read first:** Platform Governance context definition, ADR 0080, supply-chain/offline input contract and the `P1-T22A` assembler/verifier contract.
- **Change surface:** final immutable kit/artifact root, build/evidence manifests, verification outputs and signed final-kit result only.
- **Implement:** none; run the merged `P1-T22A` assembler on the exact post-`P1-T23` source/configuration/migration/runtime heads, sign and independently verify the result, and make no source, schema, configuration or runtime correction during assembly.
- **Prove:** the final kit receipt binds every Phase 1 implementation head, exact runner/tool/input identities and one artifact root; no-network verify/install, tamper, missing artifact, wrong architecture/version and package-cache-deletion cases all close terminally.
- **Stop/hand off:** any source/configuration/migration/runtime change after assembly invalidates the kit and requires a new P1-T22 run; hosted CI is supporting evidence only, and absent native ARM64/SELinux runner evidence is `NOT_EVALUABLE`.
- **Unlocks:** `P1-T24` and later deployment/campaign tasks only on current `P1-T22=SUCCESS` for the identical phase candidate.

## P1-T22A — Implement and dry-run the Offline Release Kit assembler

- **Outcome:** Implement the deterministic assembler, signer, offline verifier and a preliminary non-final ARM64 kit fixture that P1-T23 can use to exercise upgrade and rollback mechanics before final candidate assembly.
- **Depends on:** `P0-T06`, `P0-T09`, `P1-T14`, `P1-T15`, and `P1-T20` `MERGED`.
- **External prerequisites:** label=P1-T22A-ARM64-RUNNER; kind=HARDWARE; requires=OWNED_ARM64_OFFLINE_BUILD_RUNNER_RESERVED; accountable=Release-Infrastructure-Owner; validity=exact-assembler-toolchain-and-preliminary-verification-window; evidence=immutable-signed-ARM64-Build-Runner-Reservation-Receipt
- **Read first:** Platform Governance context definition, ADR 0080 and the supply-chain/offline input contract.
- **Change surface:** owned-runner build pipeline, release schemas/scripts, signing/offline-verification tooling, preliminary fixtures, tests and documentation.
- **Implement:** deterministic artifact graph and signatures, exact input/tool provenance, offline verifier and explicit `PRELIMINARY_NON_FINAL` labeling; no hosted registry, CI, model hub or API becomes mandatory.
- **Prove:** clean owned ARM64 runner dry-run, no-network verify/install fixture, deterministic rebuild, tamper, missing artifact, wrong architecture/version and package-cache-deletion cases; the fixture refuses use as final campaign evidence.
- **Stop/hand off:** this child implements tooling and a disposable preliminary fixture only; it cannot emit the final P1-T22 kit result or qualify a release.
- **Unlocks:** `P1-T23` and final `P1-T22` assembly.

## P1-T23 — Implement expand-only upgrade and binary rollback

- **Outcome:** Implement preflight, isolated-loopback candidate start, synthetic transactions, maintenance reservation, atomic routing switch, 30-minute observation and binary/config rollback while preserving compatible schema expansion.
- **Depends on:** `P1-T04`, `P1-T15`, `P1-T18`, `P1-T21`, and `P1-T22A` `MERGED`.
- **Read first:** Zero-Cash Runtime immutable deployment-switch sequence, Delivery State Ledger, ADR 0081.
- **Change surface:** deployment controller/scripts, migration/health gates, Caddy routing, receipts and fault tests.
- **Implement:** exact artifact/config/migration/host identity, healthy backup prerequisite hook, previous target, `DeploymentSelectionReceipt(SELECTED|REVERTED|FAILED)`, atomic current-selection projection, adjacent lifecycle `DEPLOYED` only after successful observation, suspension-before-reversion hook for active releases, and no silent schema downgrade or state collapse.
- **Prove:** crash/failure between every route/link/selection/receipt boundary, stale backup/migration, candidate health breach, selection-head/route equality, rollback and post-rollback first-write compatibility.
- **Stop/hand off:** task implements mechanics only; no production deployment or activation claim follows.
- **Unlocks:** final `P1-T22` assembly and, only through that current final kit, `P1-T24` and release tasks in Phases 7–8.

## P1-T24 — Run the resident-foundation clean-host campaign

- **Outcome:** On the declared native ARM64/SELinux clean host, consume the current final P1-T22 kit and execute no-network clean install, boot/unlock, containment, dependency failure, mode transition, upgrade, rollback, package-cache deletion, offline reinstall and empty/synthetic host-loss state/credential recovery.
- **Depends on:** `P1-T12`, `P1-T14`, `P1-T19`, `P1-T20`, `P1-T21`, `P1-T22`, and `P1-T23` `MERGED`, plus current `P1-T22=SUCCESS` for the identical phase candidate.
- **External prerequisites:** label=P1-T24-CLEAN-HOST; kind=HARDWARE; requires=NATIVE_ARM64_SELINUX_EMPTY_CAMPAIGN_HOST_RESERVED; accountable=Resident-Foundation-Campaign-Owner; validity=exact-final-P1-T22-kit-host-fingerprint-and-campaign-window; evidence=immutable-signed-Clean-Host-Reservation-Receipt
- **Read first:** this phase, [Production Qualification](../architecture/PRODUCTION_QUALIFICATION.md), relevant evidence schemas.
- **Change surface:** campaign manifests/harness/evidence only; discovered fixes become child tasks and invalidate the run.
- **Implement:** none; execute the frozen clean-host campaign against an immutable candidate, capture terminal evidence and cleanup, and make no product, schema, configuration, or runtime correction during the run.
- **Prove:** signed manifest, exact final-kit artifact root, release/configuration/migration/host/tool identities, resource series, fault schedule, terminal receipts and cleanup; the consumed kit receipt remains current through closure.
- **Stop/hand off:** production-data restore is excluded; missing native ARM64/SELinux clean-host or current final-kit evidence is `NOT_EVALUABLE`; any candidate drift invalidates the run and any invariant failure is `NEGATIVE`.
- **Unlocks:** `P1-T25`.

## P1-T25 — Close the Phase 1 resident-foundation gate

- **Outcome:** Independently reconcile every Phase 1 task, protected check, merge commit, schema/migration head, clean-host campaign artifact and unresolved finding into a signed phase result.
- **Depends on:** `P1-T01`–`P1-T23` `MERGED` and current terminal `SUCCESS` from `P1-T24` on the same phase candidate.
- **Read first:** this phase, Delivery State Ledger, Production Qualification runtime/modes/keys gate.
- **Change surface:** phase evidence package/result only.
- **Implement:** none; independently aggregate current Phase 1 receipts into the signed phase result without changing the candidate or repairing evidence in place.
- **Prove:** exact-head completeness, no stale/mixed-host evidence, no unresolved rights/security/resource/authority finding and clean inactive-mode process state.
- **Stop/hand off:** Phase 1 cannot claim authoritative data recovery, production deployment, qualification or activation.
- **Unlocks:** Phase 2 and domain feature foundations.
