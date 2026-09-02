# Edge Node Profile

This is the Full-Surface v1 deployment and conformance contract for a bounded Institution-controlled Edge Node. It preserves useful offline acquisition and read-only teaching access without creating a second Platform, a second identity authority, or a permanently running microservice stack.

## Authority boundary

Edge Federation owns Node enrollment, Node and User Authorization Leases, the ordered local acquisition ledger, Sync Batches, checkpoints, Acceptance Receipts and Conflict Records. An Edge Node is temporarily authoritative only for a Local Acquisition captured there. Imaging Control becomes authoritative for an asset only after its owning command accepts the exact signed manifest and issues an Acceptance Receipt.

While disconnected, the node may:

- capture, validate, quarantine and package Local Acquisitions;
- read unexpired, purpose-authorized Catalog and asset snapshots already cached on the node;
- renew a User Authorization Lease locally up to its 24-hour limit while the Node Lease remains valid; and
- inspect its own queued work, protection state and prior receipts.

It may not administer Principals, Memberships, Role Bindings or policy; establish or change an Enrollment, Completion Evidence, Grade or credential outcome; authorize Publication; seal EQA work; admit clinical material; run Research; activate a model; or represent cached state as current Platform truth. An unavailable or expired authority fails closed rather than widening the offline surface.

## Admitted installation

The Zero-Cash Edge Node is an Institution-owned or donated 64-bit Linux ARM64 device installed from the signed Offline Release Kit. The kit contains the exact application, database library, migrations, static interface, systemd units, licenses, SBOMs, checksums, release verification keys and recovery tools. A separately qualified native x86-64 build may use the same contract, but a legacy Desktop binary or Desktop Compatibility Profile is not Edge conformance.

Installation does not require a container engine, PostgreSQL, PgBouncer, JetStream, Redis, Kubernetes, hosted identity, hosted update service, registry, telemetry endpoint, DNS purchase, cloud storage, model endpoint, or paid API. The node exposes only its Institution-approved local acquisition interface and an outbound mutually authenticated synchronization connection; it is not an Internet-facing server.

## Process topology

| Process | Lifecycle | Bound responsibility |
| --- | --- | --- |
| `pathlab-edge-control` | Resident while the node is in service | Local interface, lease validation, trusted-time anchor, read-only snapshot access, single-writer state transitions, queue admission, health and signed local receipts. |
| `pathlab-edge-acquire` | On demand, one active job | Streams bytes into quarantine, checks declared size/type, computes content identity, runs admitted bounded validators and commits a Local Acquisition manifest. It has no Platform credential. |
| `pathlab-edge-sync` | On demand when connectivity and a current Node Lease exist | Creates signed sequenced Sync Batches, resumes byte transfer by content identity and checkpoint, verifies Exchange and Acceptance Receipts, and records conflicts. |
| `pathlab-edge-update` | One-shot maintenance action | Verifies an Edge Release Bundle offline, proves disk and rollback readiness, migrates a copy, swaps atomically, and records the release transition. |
| `pathlab-edge-wipe` | One-shot retirement or emergency action | Removes local secrets, authority state, queued objects, caches and recovery-copy references and emits a Node Wipe Receipt where the device remains operable. |

Only `pathlab-edge-control` is resident. Acquisition, sync, update and wipe processes have distinct operating-system users, filesystem grants and cgroup limits and return to zero active processes after their action. No process may query or replicate a Platform database.

## Local data layout

The node uses one LUKS2-encrypted data volume or an equivalently reviewed Institution-controlled encrypted volume. Inside it:

- `state/edge-state.db` is a single-writer SQLite database in WAL mode containing enrollment identity, lease metadata, policy and snapshot versions, Local Acquisition state, outbox entries, sync checkpoints, receipt references and deletion obligations;
- `objects/quarantine/` contains untrusted bytes inaccessible to the snapshot viewer;
- `objects/pending/` contains immutable content-addressed Local Acquisition bytes awaiting a final Platform result;
- `cache/catalog/` and `cache/assets/` contain explicitly read-only, expiring Platform snapshots and no mutable Platform truth;
- `receipts/` contains signed local manifests and Platform-issued Exchange, Acceptance, conflict and revocation evidence; and
- `tmp/` is quota-bound, contains no authoritative sole copy and is removed on process exit or boot recovery.

SQLite pages, WAL, files and manifests are never synchronized as databases. `pathlab-edge-control` atomically changes local state and appends an ordered outbox entry; `pathlab-edge-sync` packages those entries and content manifests into signed Sync Batches. Hash identity, sequence, Node identity, policy version and checkpoint make replay idempotent.

The node admits at most 10,000 queued events and 2 GB of pending Local Acquisition objects. The Platform admits at most 50 GB of pending Edge bytes across enrolled nodes. At 80 percent of either local limit the node warns and throttles new acquisition; at 90 percent it stops new acquisition while preserving read, recovery-copy and sync work. Unknown size, stale capacity or an unprotected storage volume closes acquisition.

## Local acquisition and recovery-copy states

```text
QUARANTINED
  -> VALIDATED_UNPROTECTED
  -> LOCALLY_PROTECTED
  -> QUEUED_FOR_SYNC
  -> PLATFORM_ACCEPTED | PLATFORM_REJECTED | CONFLICT
```

A capture may enter `VALIDATED_UNPROTECTED` while its source remains under operator control, but it cannot be declared safe to release from the collection site until a separate Edge Recovery Copy is verified. The copy contains the encrypted state snapshot, pending objects, manifest root, Node and release identities, Key Version, byte and object counts, and creation/expiry time. Its receipt must reconcile with the local ledger before the acquisition becomes `LOCALLY_PROTECTED`.

The Edge Recovery Copy resides on Institution-owned removable media or a second physically independent Institution device in an Approved Data Location. It uses a purpose-bound encryption key distinct from the node storage key, is disconnected after verification, and is never a cloud bucket, consumer synchronization folder, email attachment, or permanent archive. At least one verified copy covers every pending Local Acquisition before the original acquisition source is released.

After Platform acceptance, the node verifies the Acceptance Receipt and authoritative content identities before deleting its pending authority. After final rejection, it preserves only the bounded retry or appeal material. Once every included acquisition is accepted or finally rejected and the applicable window closes, the Edge Recovery Copy is cryptographically expired and removed under its receipt. It cannot extend Platform retention or serve as an undeclared portable export.

## Identity, leases and keys

An Operator installs the admitted release, and an Administrator performs enrollment using a one-time, short-lived bootstrap package bound to the Institution, node hardware declaration and release. Successful enrollment creates:

- one non-exportable or operating-system-protected Ed25519 Node Identity Key Version;
- one purpose-bound mutual-TLS client credential;
- the Platform release-verification trust root and Institution policy signing key;
- a Node Lease valid for no more than seven disconnected days; and
- an encrypted Credential Bundle containing no Platform root, database, backup, adapter or user authenticator secret.

A User Authorization Lease binds a Principal, Institution, cached policy version, capability subset and node and expires no later than 24 hours. It cannot outlive the Node Lease and grants only Offline Capability Profile actions. Password caching, external LMS assertions, shared local accounts and silent conversion of a guest to a Membership are prohibited.

The node records a signed Platform time anchor on every successful connection and uses monotonic elapsed time while disconnected. Clock rollback, loss of monotonic continuity, an anchor beyond policy tolerance, expired lease, revoked key, unknown policy, signature failure or Institution mismatch rejects protected actions. Client wall-clock claims never extend a lease or deadline.

Node-key rotation is an online, Platform-authorized transition with bounded old/new overlap and a signed receipt. Revocation immediately blocks new Platform exchange and causes other nodes to reject the old identity. A lost offline node cannot be remotely erased; Platform revocation prevents acceptance of later batches, while physical-copy recovery remains an Institution incident and deletion obligation.

## Signed update and rollback

The Platform supports the current Edge protocol and its two immediately preceding versions. Updates are never fetched or applied automatically. An Operator presents an Edge Release Bundle from the Offline Release Kit; `pathlab-edge-update` verifies release signature, checksum, SBOM identity, compatibility, free space, schema path and rollback artifact before stopping control.

Pending Local Acquisitions require a current Edge Recovery Copy before update. The updater copies the state database, runs migrations against the copy, verifies outbox sequence and manifest roots, then atomically swaps release and state. Failed verification restores the prior release and unchanged authority. An update may upcast a Sync Batch while preserving original bytes, hashes and versions; it may not discard, rewrite or silently accept pending work. A node outside N-minus-two must update before sync.

## Retirement and wipe

Planned retirement first revokes the Node identity and leases on the Platform, drains or explicitly rejects pending work, verifies any required Acceptance Receipts, and expires Edge Recovery Copies. The Administrator authorizes retirement with current step-up; an Operator runs the bounded wipe.

The wipe removes the Node Identity Key, mutual-TLS credential, storage and recovery-copy keys, SQLite database and WAL, queued objects, caches, temporary files and local logs, then records a Node Wipe Receipt with remaining Platform and backup obligations. Where encryption-key destruction is the irrecoverability mechanism, PathLab claims cryptographic deletion of its copies, not physical overwrite of flash remanence. An unreachable or stolen node remains `REVOKED_UNCONFIRMED` until Institution incident handling resolves the physical obligation; PathLab never fabricates a successful wipe receipt.

## Local retention

- Quarantined bytes expire no later than 24 hours after local capture unless they enter a validated Local Acquisition; a failed validator does not restart the clock.
- Node connection diagnostics expire no later than 30 days after collection.
- Accepted pending objects are removed no later than seven days after the verified Acceptance Receipt; final rejection material is removed no later than 30 days after the final rejection or appeal closure.
- Conflict and rejection evidence retained on the Platform expires no later than two years after final resolution or rejection; the node may discard its acknowledged projection earlier.
- Expired Catalog and asset snapshots are deleted at the next control start and cannot be opened as current state.
- Node Wipe Receipts and enrollment/revocation evidence follow the Institution governance-receipt schedule; Edge Recovery Copies never extend it.

## Resource envelope and degradation

The admitted minimum node has two 64-bit CPU cores, 2 GB RAM, 16 GB free encrypted local storage plus the separately held Edge Recovery Copy, and an Institution-approved display/input path where local viewing is enabled. The release reserves 512 MB for the operating system, caps the resident control process at 256 MB and 0.25 CPU, and permits one active acquisition or sync process up to 1 GB and one CPU. At least 256 MB and 0.25 CPU remain emergency headroom.

The node does not assume continuous connectivity. When connected, its declared minimum useful path is 5 Mbit/s outbound with resumable transfer; slower service remains safe but receives no 24-hour drain claim. Resource pressure first pauses acquisition, then sync byte transfer, while preserving state commitment, receipts, read-only inspection and orderly shutdown. Swap thrashing, unlimited retry, unbounded logs and restart loops are prohibited.

## Zero-cash accounting boundary

Every node, recovery medium, charger, display, local network path, removable medium, electricity source, operator effort and any separately qualified x86-64 build appears in the deployment inventory and Zero-Cash Evidence Window. Owned or donated resources may produce zero incremental PathLab-specific cash spend but are disclosed; temporary credits, free mobile data, personal cloud storage or expiring hosted services cannot satisfy the profile.

No Edge claim is “free forever.” Edge conformance requires the Free Software Guarantee plus evidence that the named devices and connectivity incurred zero incremental PathLab-specific external cash spend during the same initial 90-day and subsequent rolling 12-month window as the deployment. If an institution must buy a node, media, connectivity or support, the software remains free but that deployment uses the Funded Scalable Profile or states the observed nonzero cost.

## Conformance gate

The exact-release campaign enrolls 100 nodes across N, N-minus-one and N-minus-two; holds a seven-day disconnected backlog totaling one million events and 50 GB; exercises 10 concurrent control syncs and two byte transfers; and drains accepted work within 24 hours on the qualified network declaration. It includes duplicate, delayed, reordered, replayed and malicious batches; lease and clock expiry; Node and policy key rotation; conflict resolution; restart at every commit boundary; disk and inode pressure; corrupt SQLite WAL and object bytes; stolen-node revocation; update rollback; recovery from an Edge Recovery Copy; and confirmed Node Retirement.

Success requires hash- and count-equal accepted assets, no forbidden offline authority, no cross-Institution disclosure, no acceptance from an expired or revoked node, no lost accepted receipt, bounded resource use, complete local cleanup and proof that each Platform owner—not Integration Gateway or the node—made the final domain decision. Desktop protocol success is recorded separately and cannot substitute for this gate.
