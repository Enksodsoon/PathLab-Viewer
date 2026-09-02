# Edge Federation

This context owns enrolled edge nodes, bounded offline acquisition state, checkpointed synchronization, and conflict evidence without creating a second Platform authority.

## Language

**Edge Node**:
An enrolled institution-controlled installation permitted to operate a bounded local capability set under a current Node Lease.
_Avoid_: Replica, satellite server

**Offline Capability Profile**:
The bounded set of Local Acquisition and read-only Catalog or asset activity permitted while an Edge Node is disconnected.
_Avoid_: Offline mode, local platform, full replica

**Desktop Compatibility Profile**:
An admitted legacy Desktop ingest or synchronization contract that does not by itself establish Edge conformance.
_Avoid_: Edge protocol, node API, federation support

**Node Lease**:
A signed, expiring grant defining the Edge Node's identity, allowed capabilities, policy version, and maximum seven-day disconnected-operation boundary.
_Avoid_: Login token, permanent enrollment

**User Authorization Lease**:
A locally renewable grant, valid for at most 24 hours, that binds one Principal to cached institution policy while the Edge Node's Node Lease remains valid.
_Avoid_: Offline account, remembered login

**Local Acquisition**:
An imaging asset and provenance package first captured by an Edge Node, for which that node is authoritative until Platform acceptance or explicit rejection.
_Avoid_: Upload, local copy

**Edge Recovery Copy**:
A temporary Institution-encrypted recovery copy of pending Local Acquisitions and node authority state, held separately from the Edge Node until Platform acceptance or final rejection.
_Avoid_: Cloud backup, replica, permanent archive

**Edge Release Bundle**:
An offline-verifiable signed installation or update package admitted for one Edge protocol version and Compatibility Window.
_Avoid_: Auto-update, download, latest build

**Sync Batch**:
An immutable, signed, sequenced, and idempotent package of proposed domain changes and content manifests with a resumable checkpoint.
_Avoid_: Replication packet, database sync

**Acceptance Receipt**:
The immutable Platform acknowledgement identifying which Sync Batch entries were accepted, rejected, or routed to governed conflict resolution.
_Avoid_: Sync success, HTTP response

**Authority Partition**:
The explicit ownership rule assigning local acquisition and cache state to an Edge Node while retaining canonical identity, catalog, policy, publication, Assessment, and shared metadata on the Platform.
_Avoid_: Multi-master, last-write-wins

**Conflict Record**:
Durable evidence that two valid proposals cannot be applied without an owning domain's explicit resolution rule or authorized human decision.
_Avoid_: Failed sync, latest version

**Node Retirement**:
The governed revocation of an Edge Node's identity and leases followed by removal or cryptographic erasure of its local authority, cached data, and secrets.
_Avoid_: Uninstall, device deletion, offline node

**Node Wipe Receipt**:
Immutable evidence identifying the retired node, revoked key and leases, removed local records and objects, outstanding Platform obligations, and wipe result.
_Avoid_: Factory reset, deleted flag, uninstall complete

**Compatibility Window**:
The supported synchronization range consisting of the current Platform protocol version and its two immediately preceding versions.
_Avoid_: Best effort compatibility, any version

**Edge Capacity Envelope**:
The Zero-Cash limit of 100 enrolled Edge Nodes, ten concurrent control-sync sessions, two concurrent byte transfers, 10,000 queued events and two GB pending objects per node, and 50 GB total pending Edge bytes on the Platform.
_Avoid_: Federation scale, node limit

**Edge Launch Gate**:
The exact-host federation campaign across 100 N-through-N-2 nodes, a seven-day backlog, one million events, 50 GB of objects, adversarial delivery, conflicts, lease and key transitions, restart, and authority isolation.
_Avoid_: Sync test, federation capacity

## Retention ceilings

- A Conflict Record expires no later than two years after the owning context records its final resolution.
- Rejection evidence expires no later than two years after the Platform records the final rejection in an Acceptance Receipt.
- An Edge Recovery Copy expires after the Platform accepts or finally rejects every included Local Acquisition and the applicable appeal or retry window closes; it never extends a Platform retention clock.
