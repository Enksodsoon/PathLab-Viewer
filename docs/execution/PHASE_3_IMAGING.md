# Phase 3 — Imaging Migration and Re-admission

Phase 3 preserves every current Viewer, Library, upload, DZI, sharing, annotation, private-result and Desktop behavior while moving authority into the Imaging context and protection model. Because the source SQLite database also contains Study and Classroom state, final cutover waits for the Phase 4 persistence/import prerequisites and happens exactly once. All tasks inherit [README](./README.md).

## P3-T01 — Scaffold Imaging Control authority

- **Outcome:** Imaging Control has its own logical database, roles, migration head, outbox, command/event schemas and deny-by-default capability seam.
- **Depends on:** `P1-T25`, `P2-T27`, `P1-T02`, `P1-T04`, `P1-T06`, `P2-T04` `MERGED`.
- **Read first:** Imaging context, Context Map, Final Endpoint authority table, Receipt Schema Registry Imaging section.
- **Change surface:** Phase-1 context namespace, Imaging migrations/contracts/tests; current `models.py`, `domain.py`, `main.py` only at explicit seams.
- **Implement:** identities and repositories for source/derivative assets, manifests, upload/protection/admission, publications, annotations and private result artifacts.
- **Prove:** empty migration, transaction/outbox atomicity, role/cross-database denial, version compatibility and rollback-before-data.
- **Stop/hand off:** no current source data, route or authority moves in this task.
- **Unlocks:** `P3-T02`–`P3-T14`.

## P3-T02 — Inventory all SQLite and filesystem authority

- **Outcome:** Produce one deterministic source-to-context map for every existing SQLite table/row/identifier and filesystem object, including Imaging, Trust, Study/Catalog, Classroom/Live, Desktop/Edge and private result data.
- **Depends on:** `P3-T01` `MERGED`.
- **External prerequisites:** label=EP-P3-SOURCE-01; kind=DATA_OR_CORPUS; requires=AVAILABLE; accountable=Source custodian; validity=exact SQLite bytes object roots and custody remain unchanged through P3-T02 closure; evidence=SignedSourceSnapshotReceipt.
- **Read first:** [SQLite-to-PostgreSQL](../architecture/SQLITE_TO_POSTGRESQL.md), the migration-input-only [PostgreSQL Migration](../architecture/POSTGRES_MIGRATION.md), migrations `0001` onward, and the P4 plan; SQLite to PostgreSQL and accepted ADRs control conflicts.
- **Change surface:** read-only inventory/mapping tooling, signed fixture manifests and tests.
- **Implement:** counts, null/enums/timestamps, keys/relationships, privacy/retention class, destination owner, orphan/missing/symlink/corrupt classification and stable hashes.
- **Prove:** repeated-run equality and 100% table/column/object coverage.
- **Stop/hand off:** any unmapped or ambiguous state is `NOT_EVALUABLE`; never mutate or silently repair the source.
- **Unlocks:** `P3-T03`, `P3-T15` and Phase 4 legacy importers.

## P3-T03 — Reconcile content-addressed objects and manifests

- **Outcome:** Deterministically map originals, DZI derivatives, thumbnails, public aliases, annotation exports and Private Result Artifacts to immutable manifests, hashes, provenance and authoritative/rebuildable classifications.
- **Depends on:** `P3-T01`, `P3-T02`, `P1-T08` `MERGED`.
- **Read first:** Imaging context, the migration-input-only [Rebuildable Tile Cache](../architecture/REBUILDABLE_TILE_CACHE.md), and current storage/publication/delivery code; the Imaging Control context and accepted ADRs control conflicts.
- **Change surface:** Imaging manifest/reconciler, current storage/delivery/worker/Desktop finalizer adapters and tests.
- **Implement:** alias/reference reconciliation, duplicate content identity, missing/orphan reporting and rebuild recipe identity without pixel decode during inventory.
- **Prove:** repeated identity, corruption/path/symlink/missing/orphan/duplicate fixtures and exact manifest roots.
- **Stop/hand off:** no authority transition or corruption-hiding repair.
- **Unlocks:** `P3-T06`, `P3-T08`, `P3-T09`, `P3-T15`.

## P3-T04 — Implement Upload Reservations and capacity admission

- **Outcome:** Admit uploads only under Imaging Mode Reservations using declared source/expansion/workspace/derivative/backup/restore/35-day-growth and safety-headroom terms.
- **Depends on:** `P3-T01`, `P1-T09`, `P1-T18`, `P1-T19`, `P2-T19` `MERGED`.
- **Read first:** Imaging context, ADRs 0044–0045, current storage accounting/runtime protection/upload UI.
- **Change surface:** Imaging reservation/admission schema/service/API/UI, tus grant and tests.
- **Implement:** trusted size/type, expiry/release, throttle/shed, backup freshness and dynamic capacity checks; stream direct to supervised tusd.
- **Prove:** unknown/stale/negative capacity, backup outage, concurrent reservations, overflow, 80/90% pressure, restart and abandoned cleanup.
- **Stop/hand off:** never buffer WSI bodies through `pathlab-control` or admit while protection evidence is stale.
- **Unlocks:** `P3-T05`.

## P3-T05 — Preserve resumable OME-TIFF receipt and validation

- **Outcome:** Run tus receipt plus the existing bounded TIFF/BigTIFF/OME validation contract inside the Imaging reservation with content offsets/hashes, restart and terminal rejection/expiry.
- **Depends on:** `P3-T04` `MERGED`.
- **Read first:** the migration-input-only [OME-TIFF Pipeline](../architecture/OME_TIFF_PIPELINE.md), current upload/OME/prepared-ingest code, and Upload Receipt schema; the Imaging Control context and accepted ADRs control conflicts.
- **Change surface:** upload API/tusd integration, OME validators, worker/frontend transport and focused tests.
- **Implement:** no user paths, size/expansion/dimension/compression/metadata limits, safe ICC/color handling and privacy/rejection staging.
- **Prove:** disconnect at multiple offsets, process restart, malformed offset, truncation, corrupt TIFF, bomb, traversal, disk/inode pressure and cleanup.
- **Stop/hand off:** validators and format tools do not create Imaging authority or relax the supported-input profile.
- **Unlocks:** `P3-T06`.

## P3-T06 — Enforce protection before Source Asset authority

- **Outcome:** Keep validated source and required non-rebuildable bytes `PENDING_PROTECTION` until target-side pull acknowledges their exact manifests, then atomically admit only the protected Source Asset into Imaging authority.
- **Depends on:** `P2-T21`, `P3-T03`, `P3-T05` `MERGED`.
- **Read first:** durability protection boundary, Receipt Schema Registry protection/admission rows, ADR 0117 and Golden Journey G09–G11.
- **Change surface:** Imaging source-admission transaction, target grant/receipt integration, storage state and tests.
- **Implement:** failed/retried protection, exact target/hash/size/key/config binding, duplicate idempotency and release of rejected staging; no derivative or publication prerequisite.
- **Prove:** target outage, stale/capacity-blocked/wrong/replayed receipt, five-minute fault and restart before/after protection and source-admission commit.
- **Stop/hand off:** no asynchronous or local-only fallback; Source Asset authority before protection is `NEGATIVE`.
- **Unlocks:** `P3-T07`.

## P3-T07 — Convert deterministic static DZI after source admission

- **Outcome:** Convert an authoritative protected Source Asset into private atomic static DZI derivatives with exact tool/config/source manifests and bounded workspace/resource behavior.
- **Depends on:** `P3-T06`, `P1-T17`–`P1-T19` `MERGED`.
- **Read first:** OME-TIFF Pipeline, ADR 0043, current conversion/tile code and Golden Journey G11.
- **Change surface:** Imaging batch conversion, manifests, staging cleanup, tests and resource observations.
- **Implement:** deterministic tile layout, sRGB/16-bit policy, atomic finalize, no dynamic decode fallback, rebuild contract and zero residual staging.
- **Prove:** missing/unprotected source rejection, restart at boundaries, hash repeatability, maximum source, corrupt output, resource limits and cleanup.
- **Stop/hand off:** derivative success cannot replace source admission or authorize publication.
- **Unlocks:** `P3-T08`–`P3-T14`.

## P3-T08 — Authorize and serve immutable static DZI

- **Outcome:** Every browser-visible asset has an integrity-verified DZI Browser Representation and explicit private/restricted/public audience authorization delivered through Caddy.
- **Depends on:** `P3-T07` `MERGED`.
- **Read first:** Final Endpoint data paths, current tile/Viewer/Caddy code, and [Adaptive Viewer Capacity](../architecture/ADAPTIVE_VIEWER_CAPACITY.md) as legacy measurement-baseline input only; the [Final Production Endpoint](../architecture/FINAL_PRODUCTION_ENDPOINT.md) and current accepted Imaging/capacity contracts control any conflict.
- **Change surface:** representation authorization, tile capability/delivery, Caddy, OpenSeadragon route/UI and tests.
- **Implement:** immutable descriptor/tile manifests, five-minute private capabilities, cache headers, revocation and bounded poster/loaded-canvas failure behavior.
- **Prove:** tamper, revoked/expired/replayed capability, wrong audience, restart, shaped network and supported physical client/accessibility cases.
- **Stop/hand off:** never send the source WSI or dynamically decode it in a browser fallback.
- **Unlocks:** Library, shares, annotations and Phase 4 WSI references.

## P3-T09 — Move Library queries and metadata to Imaging

- **Outcome:** Search, facets, bounded cursors, source/privacy/storage metadata and authorized Library reads use Imaging repositories without filesystem walks or cross-context queries.
- **Depends on:** `P3-T03`, `P3-T08` `MERGED`.
- **Read first:** the migration-input-only [Library Domain](../architecture/LIBRARY_DOMAIN.md) and current library backend/UI/tests; the Imaging Control context and accepted ADRs control conflicts.
- **Change surface:** Imaging Library schema/repository/API and web data adapters.
- **Implement:** deterministic stable cursors, query limits, Institution/purpose filters, exact route compatibility and no WSI decode for browsing.
- **Prove:** maximum fixture, Unicode/search/facet/cursor consistency, concurrent changes, wrong Institution and bounded query/resource behavior.
- **Stop/hand off:** cached/folder/filesystem observation never becomes metadata authority.
- **Unlocks:** `P3-T10`, `P3-T11`, `P3-T12`.

## P3-T10 — Preserve folders, collections, saved views, and Trash

- **Outcome:** Versioned Imaging aggregates preserve folder trees, collections, saved-view definitions, batch actions, Trash/restore/purge and existing identifiers under exact capabilities.
- **Depends on:** `P3-T09` `MERGED`.
- **Read first:** Library Domain, current folder/collection/Trash UI and migrations.
- **Change surface:** Imaging schemas/repositories/routes, Library components and migration mappings.
- **Implement:** depth/cycle/uniqueness rules, immutable collection publication inputs, bounded batches, retention triggers and concurrency controls.
- **Prove:** move/cycle/race, Unicode uniqueness, saved-view injection, Trash restore/purge, route/UI/accessibility and restart.
- **Stop/hand off:** saved views store bounded filter contracts, not arbitrary SQL.
- **Unlocks:** `P3-T12`, `P3-T13`, Phase 4 content selection.

## P3-T11 — Rebuild bounded thumbnails and caches

- **Outcome:** Generate and serve authorized thumbnails/rebuildable tile-cache entries from exact source/version/tool manifests with bounded eviction and zero authority.
- **Depends on:** `P3-T08`, `P3-T09` `MERGED`.
- **Read first:** Library thumbnails, Rebuildable Tile Cache, current tile cache/service.
- **Change surface:** cache indexes/workers/delivery/UI and tests.
- **Implement:** separate private/public cache keys, safe lazy rebuild, quota/pressure eviction and no retention extension.
- **Prove:** eviction/rebuild equality, wrong-audience cache, corrupt/missing cache, pressure/restart and source withdrawal.
- **Stop/hand off:** cache absence is rebuildable; cache content cannot substitute for protected source.
- **Unlocks:** imaging corpus and portability exclusions.

## P3-T12 — Implement authenticated Restricted Shares

- **Outcome:** Asset/folder/collection manifests can be shared only with authenticated, purpose/audience-bound recipients using private no-store responses and five-minute revocable capabilities.
- **Depends on:** `P2-T10`, `P3-T08`, `P3-T10` `MERGED`.
- **Read first:** Imaging context, Library publication section, ADRs 0074–0075 and 0111.
- **Change surface:** sharing/publication backend, Share UI/shared viewer and tests.
- **Implement:** exact audience/purpose/expiry/revocation/reissue, immutable manifest, private headers and audit/deletion behavior.
- **Prove:** wrong Institution/purpose/audience, expiry/replay, revoke <=5 minutes, browser cache and identifier leakage.
- **Stop/hand off:** Restricted Share is not anonymous publication.
- **Unlocks:** Learning/Research/EQA consumption after their exact owner-task dependencies merge.

## P3-T13 — Re-admit anonymous Public Releases

- **Outcome:** Keep every legacy anonymous share inactive until its exact reconciled Collection Manifest receives WSI Reviewer initiation and independent Publication Officer approval; preserve withdrawal and external-download warning.
- **Depends on:** `P2-T05`, `P3-T08`, `P3-T10` `MERGED`.
- **Read first:** Governed Product Workflows Imaging section, Role Matrix publication pair, current publication/share code.
- **Change surface:** publication aggregates/routes/UI, migration/re-admission queue, public delivery and tests.
- **Implement:** visible pixel/name/privacy review, immutable manifest, no self-approval, new approval on any change, origin withdrawal and no false recall claim.
- **Prove:** unreconciled identifier, stale step-up, same person, mixed privacy, PHI canary, changed manifest, revoke/cache and warning behavior.
- **Stop/hand off:** preserving a legacy ID is not approval; anonymous annotations remain prohibited.
- **Unlocks:** public surface and Golden Journey G13.

## P3-T14 — Version private and governed annotations

- **Outcome:** Owner-private drafts with one expiring editor lease and optimistic predecessors produce immutable audience/purpose-restricted Annotation Layer Versions.
- **Depends on:** `P2-T04`, `P3-T08` `MERGED`.
- **Read first:** Imaging context, baseline-only [Private Administrator Annotations](../architecture/ADMIN_ANNOTATIONS.md), and ADRs 0076 and 0111; the Imaging Control context and accepted ADRs control conflicts.
- **Change surface:** annotation backend/routes, `apps/web/src/annotations/`, migrations/interchange and tests.
- **Implement:** 25,000-object/50-MB/100-layer bounds, geometry/calibration/version validation, recovery drafts, retention/deletion, GeoJSON/QuPath quarantine and restricted consumption.
- **Prove:** lease conflict/expiry, restart/restore, malicious/out-of-bounds/self-intersecting geometry, uncalibrated measurement, limits, browser memory and authorization.
- **Stop/hand off:** no CRDT, multi-editor, last-write-wins, anonymous annotation, or unsupported-semantics flattening; DICOM ANN export belongs to Phase 5.
- **Unlocks:** `P3-T15`, Phase 5 clinical annotation exchange.

## P3-T15 — Preserve Desktop as a compatibility profile

- **Outcome:** Migrate current pairing, ingest, prepared finalization and synchronization through versioned Imaging/Integration seams while explicitly remaining a Desktop Compatibility Profile rather than Edge conformance.
- **Depends on:** `P3-T01`–`P3-T10`, `P3-T14`, and `P1-T02` `MERGED`.
- **Read first:** Edge context/profile, current Desktop routes/sync/finalizer/UI and fixtures.
- **Change surface:** Desktop compatibility adapters, Imaging proposals, pairing/credential migration and tests.
- **Implement:** stable IDs/hashes, resume, rotation/revocation, mutation conflict evidence, PostgreSQL state and N/N-2 contracts.
- **Prove:** existing fixtures plus duplicate/reorder/replay/revoked pairing/interrupted ingest/conflict/route compatibility and versioned annotation pull/push, lease/predecessor conflict, retry and N/N-2 round trip.
- **Stop/hand off:** no Node Lease, offline Platform authority or Edge claim.
- **Unlocks:** `P3-T16`, Phase 5 Edge adapter.

## P3-T16 — Complete two identical cross-context migration rehearsals

- **Outcome:** Import one immutable SQLite/object snapshot twice into fresh context databases and obtain identical owner mappings, rows, hashes, manifests, routes and first-write boundaries.
- **Depends on:** `P3-T02`–`P3-T15` plus `P4-T01`, `P4-T02`, `P4-T14`, and `P4-T21` persistence/import prerequisites `MERGED`.
- **Read first:** PostgreSQL migration/cutover docs, every owner mapping from P3-T02 and relevant Phase 4 cards.
- **Change surface:** migration orchestrator/importers, parity/synthetic workflow verifier and evidence.
- **Implement:** Imaging, Trust, Study/Catalog, Classroom/Live, Assessment-related legacy state, Desktop, jobs and objects; no production mutation.
- **Prove:** row/key/hash/object parity, deterministic mappings, permission/session/route checks, outbox replay and rollback-before-first-write.
- **Stop/hand off:** any unexplained difference is `NEGATIVE`; do not cut over or add a second dual-write path.
- **Unlocks:** `P3-T17`.

## P3-T17 — Execute the single SQLite-to-PostgreSQL authority cutover

- **Outcome:** In one maintenance reservation, drain writes, verify READY, preserve an immutable protected source, atomically switch all current owners, close rollback at the first PostgreSQL authoritative write and permanently prevent a second cutover.
- **Depends on:** current terminal `SUCCESS` from `P3-T16`, `P2-T24`, and `P2-T26`, with every protected check named by their manifests current on the exact cutover head.
- **Read first:** SQLite/PostgreSQL cutover docs, Delivery State Ledger, exact cutover evidence schema.
- **Change surface:** cutover command/config/readiness, immutable manifest/receipt and runbook.
- **Implement:** complete all-source scope, no-write drain, final delta/parity, routing switch, rollback-before-write, post-write no-rollback guard and legacy source archival/expiry.
- **Prove:** faults at every boundary, duplicate invocation, stale snapshot/receipt, successful pre-write rollback and prohibited post-write rollback.
- **Stop/hand off:** never perform Imaging-only and later Learning cutovers. Missing canonical cutover evidence schema blocks execution.
- **Unlocks:** `P3-T18`, dependable Phase 4 runtime data.

## P3-T18 — Run Imaging qualification and close Phase 3

- **Outcome:** On the exact phase candidate, exercise maximum admitted source/corpus, Viewer/Library routes, static DZI, uploads, Restricted/Public shares, 25,000-object/50-MB annotations, Desktop compatibility, retention/deletion/restore, supported physical clients and WCAG 2.2 AA.
- **Depends on:** `P3-T01`–`P3-T17` and `P2-T14` `MERGED`, plus current terminal `SUCCESS` from `P2-T26` on the same release-bound protection inputs.
- **Read first:** Production Qualification Imaging gate, Feature Completion Matrix, and [Adaptive Viewer Capacity](../architecture/ADAPTIVE_VIEWER_CAPACITY.md) as legacy measurement-baseline input only; the [Final Production Endpoint](../architecture/FINAL_PRODUCTION_ENDPOINT.md) and current accepted Imaging/capacity contracts control any conflict.
- **Change surface:** campaign harness/evidence only; fixes become child tasks and invalidate the candidate.
- **Implement:** none; this task executes and reconciles the frozen Imaging evidence package, while any product, harness or manifest correction requires a separate task and new candidate.
- **Prove:** hashes/privacy/authority/routes survive restart/migration/restore; corruption/bomb/storage/backup/client/accessibility cases and terminal cleanup all pass.
- **Stop/hand off:** missing physical client/corpus/restore evidence is `NOT_EVALUABLE`; historical tests are supporting only.
- **Unlocks:** full Phase 4 feature work and Phase 7 exact-release rerun.
