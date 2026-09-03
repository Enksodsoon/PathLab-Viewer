# Zero-Cash Durability and Security

This document closes the durability, recovery, and related security boundary for the Zero-Cash Production Profile. It applies to acknowledged PostgreSQL authority, authoritative immutable objects, infrastructure recovery state, release evidence, and the Institution-owned Backup Target; it does not create high availability, a fixed Recovery Time Objective, whole-site durability, or a permanent zero-cash promise.

## Accounting claim

The permanent claim is the Free Software Guarantee. The operational claim is narrower: the exact deployment incurred zero incremental PathLab-specific external cash spend during its evidenced window.

- Count cloud and hosting charges, paid licenses, APIs, support, newly purchased hardware, domains, certificates, and incremental connectivity bought specifically for PathLab.
- Record gross service charges before temporary credits or promotions; an expiring credit cannot make a paid dependency part of Zero-Cash Production.
- Disclose donated or already-owned machines and media, baseline utilities and connectivity, and Institution labor even when they create no incremental PathLab cash transaction.
- Launch requires 90 consecutive days of invoices, provider billing records, usage records, and a reconciled local cost ledger proving zero incremental spend.
- After sufficient history exists, every claim uses the immediately preceding rolling 12 months. Before then, PathLab states only the completed 90-day evidence period.
- A new PathLab-specific charge, an unverified statement, an expiring mandatory free allowance, or projected incremental spend above zero makes the Zero-Cash claim NO-GO. The deployment must remove the dependency or move to the separately qualified Funded Scalable Profile.

PathLab therefore says neither "completely free" nor "free forever." It states the permanent software-license guarantee and the dates, deployment, inclusions, exclusions, and evidence supporting the observed cash result.

## Protection boundary

### Authoritative PostgreSQL writes

The five-minute Data-Protection Objective is enforced more strictly than a periodic archive schedule:

1. Barman runs on the physically independent Backup Target and uses the matching qualified PostgreSQL 18 client tools.
2. Its dedicated `pg_receivewal --synchronous` receiver uses a physical replication slot and the exact application identity named by PostgreSQL synchronous-standby configuration, so each flush is followed by immediate status feedback.
3. PostgreSQL acknowledges an authoritative commit only after the off-host receiver reports that WAL durably flushed.
4. Loss, lag, authentication failure, capacity exhaustion, or loss of durable acknowledgement never causes an automatic asynchronous fallback. Authoritative write admission stops; bounded safe reads remain available.
5. Slot growth is bounded and monitored. Approaching the primary-volume safety limit stops writes before retained WAL can consume the Encrypted Data Volume.

Qualification freezes `synchronous_commit=on`, `fsync=on`, `full_page_writes=on`, `wal_level=replica`, the physical replication slot, and the exact `synchronous_standby_names` application identity. PostgreSQL permits ordinary sessions to change `synchronous_commit`, so role defaults or parameter ACLs are not treated as enforcement. A small PathLab Authoritative Commit Guard, loaded as a pinned `shared_preload_libraries` component from the signed release, marks transactions that mutate any authoritative relation and rejects them at the server's pre-commit callback unless the effective value is exactly `on`. Application and migration roles are non-superuser, cannot unload or bypass the guard, cannot alter system/role/database defaults, and have no unguarded authoritative writer role. Startup and continuous readiness compare the guard, complete authoritative-relation inventory, effective settings, receiver state, and configuration hashes; a mismatch closes authoritative admission before traffic is accepted. Qualification attempts `off`, `local`, `remote_write`, `SET LOCAL`, reconnect, pool reuse, function, and migration paths against every authoritative relation and requires every downgraded commit to fail.

"Durably flushed" is a qualified hardware claim, not an operating-system acknowledgement assumption. The exact primary and Backup Target drive models, firmware, controller and write-cache modes, filesystem, mount options, kernel, power-loss protection, and `pg_receivewal` synchronous behavior are frozen inputs. Unprotected volatile write-back caching is disabled, and a destructive power-cut campaign must prove that every acknowledged test commit survives loss of either host at each flush boundary. A storage, firmware, kernel, filesystem, mount, or cache change invalidates that evidence.

The receiver may normally deliver substantially better than five minutes, but the claim remains a maximum accepted loss boundary, not replication, failover, uptime, or restoration-time evidence. Idle periods use a bounded heartbeat transaction so a connected process without recent durable acknowledgement cannot appear healthy.

### Authoritative immutable objects

The production data volume is a 150-GB raw encrypted volume shared by governed database, object, manifest, index, temporary, derivative, growth, and headroom needs. Neither one object nor the live object corpus has a 150-GB allowance; the actual admitted envelope is lower and is calculated by ADR-0045 at reservation time. Because even a valid admitted object may take longer than five minutes to transfer, PathLab makes protection part of authority:

```text
QUARANTINED -> PENDING_PROTECTION -> AUTHORITATIVE
                       |                 |
                       +---- failure ----+-> remains unavailable for publication
```

After local validation, the immutable content-addressed object and canonical manifest remain `PENDING_PROTECTION`. Production creates a canonical Protection Pull Grant signed by its release-bound service identity. The grant names the deployment, nonce, hash algorithm and object digest, exact byte count, manifest root, read-only hash-addressed endpoint, intended Backup Target identity, and trusted not-before and expiry times; authorization to start expires within 15 minutes, each stream has a qualified byte/rate deadline, and every retry or resume requires a new nonce and grant. The endpoint permits only authenticated `GET` or bounded range reads for the declared immutable hash: it cannot list storage, translate an arbitrary path, mutate an object, or expose a repository credential.

A bounded worker on the Backup Target verifies the grant and initiates the pull, recomputes the declared digest and byte count, and then runs restic locally against the append-only rest-server repository. Production never executes restic and never receives the repository password, volume key, ingest credential, or administrative credential. The transition to `AUTHORITATIVE` requires the Backup Target's signed Protection Receipt to bind the pull-grant hash, trusted target receipt time, restic snapshot identity, manifest root, object count, and byte total. A pending object cannot enter a Publication, Collection Manifest, Dataset Snapshot, EQA Case Version, portable export, or other authoritative reference.

## Pinned durability stack

The production pins are Barman 3.19.1, the matching PostgreSQL 18 client tools, restic 0.19.1, and rest-server 0.14.0.

| Component | Production pin | License and boundary | Purpose |
| --- | --- | --- | --- |
| Barman | 3.19.1 source and package | GPL-3.0-or-later, architecture-independent Python source executed as a separate operational work on the qualified Linux ARM64 Python/runtime package, with source and notices | Off-host PostgreSQL base, incremental, WAL, check, and recovery control |
| PostgreSQL client tools | PostgreSQL 18 package matching the qualified server minor release | PostgreSQL License; exact package identity is recorded in the Release Bill of Materials | `pg_receivewal`, `pg_basebackup`, verification, and restore tools |
| PathLab Authoritative Commit Guard | Exact PathLab release revision and PostgreSQL 18 ABI | Apache-2.0 PathLab source, built by the Authoritative Build Runner for the qualified Linux ARM64 PostgreSQL package | Server-side pre-commit rejection of authoritative transactions with weakened synchronous durability |
| restic | 0.19.1 native Linux ARM64 artifact | BSD-2-Clause | Backup Target-side pull verification and authenticated encrypted snapshots of authoritative immutable objects |
| rest-server | 0.14.0 native Linux ARM64 artifact | BSD-2-Clause | Bounded append-only repository service accessible to the Backup Target ingest worker, never to production |

Every artifact is stored in the signed Offline Release Kit with its immutable source revision or release, upstream location, signature or SHA-256, license text, notices, provenance, and SBOM identity. Production and the Backup Target never fetch a mutable `latest` artifact or compile a release.

## Backup lifecycle

| Protection work | Cadence | Completion evidence |
| --- | --- | --- |
| PostgreSQL WAL receipt | Continuous and synchronously commit-coupled | Primary commit LSN is no greater than the off-host durable flush LSN; signed receipt and heartbeat are current |
| PostgreSQL block-incremental | Daily, no more than 26 hours apart | Barman check, backup identity, parent chain, byte totals, manifest, and WAL boundary reconcile |
| PostgreSQL full | Weekly class; scheduled at `168 hours - qualified expiry margin` or sooner, with a hard completion bound of 168 hours | Independent verified base, configuration and schema identities, and complete signed manifest |
| New immutable objects | Before the authority transition | Target-initiated pull, target-side restic snapshot, and off-host Protection Receipt cover every declared hash and byte |
| Complete object inventory | Nightly | Authoritative ledger, filesystem identities, restic snapshot, counts, bytes, and manifest root reconcile |
| WAL and manifest acknowledgements | Daily | No gap, replay, signature failure, missing object, or stale target-capacity evidence |
| Random-time PostgreSQL PITR | Weekly | Target-time recovery and context, outbox, audit-chain, and schema reconciliation |
| Authoritative object sampling | Monthly | Sampled bytes recompute their content identities and match authoritative manifests |
| Cold replacement-host Restore Drill | Every release and at least quarterly | Offline kit, quorum, database, objects, infrastructure state, keys, audit chains, and rebuilt derivatives reconcile |

Continuous point-in-time recovery covers every target in the latest rolling seven days. To make that statement true at the oldest boundary, the continuous WAL pool retains all segments from the oldest eligible daily anchor: the deletion floor is seven days plus the maximum 26-hour daily-anchor interval, with qualification margin, and the hard maximum segment age is nine days. WAL needed only to make an older discrete full or incremental anchor internally consistent is sealed into that Backup Generation and is not represented as continuous PITR. This nine-day bound explicitly supersedes ADR-0032's former seven-day WAL ceiling.

Full backups complete no more than 168 hours apart. Because an exact seven-day gap leaves no execution margin between a 28-day successor anchor and a strict pre-35-day deletion deadline, the steady-state schedule must satisfy `full completion gap + qualified expiry execution margin <= 168 hours`; reaching 168 hours is a fail-closed outer bound, not a normal target. The dependency-aware expiry planner proves that the retained full-plus-incremental chains include a discrete restore anchor at least 28 days old before deleting a chain root. Every Backup Generation still has a hard maximum age of 35 days. PathLab does not describe this as a continuous 35-day PITR window.

Logical expiry begins on day 34. The backup-side lifecycle authority, using trusted target receipt time rather than a client-supplied snapshot timestamp, removes expired backup and snapshot references, completes required prune or reclamation, expires any retaining filesystem snapshot, verifies the remaining repository, and signs a Deletion Receipt before day 35. A disconnected generation carries ciphertext only under a random, non-derivable per-rotation epoch DEK; its three independently controlled recovery shares use a two-of-three threshold and remain outside the media. At creation, each Institution-owned share store accepts the trusted expiry and a fail-closed automatic erasure instruction. Before day 35 at least two stores erase their shares and sign independent erasure attestations, every wrap or escrow copy is destroyed, and the Backup Target binds those quorum attestations plus a negative header-decrypt check with all remaining authorized secrets into the Ed25519-signed Crypto-Expiry and Deletion Receipts. A rotation cannot be created unless this independent expiry path is current and qualified.

Expiry is automatic; ordinary retention cannot wait for human approval. Missing logical-deletion or epoch-key-destruction evidence before the deadline is a durability breach: readiness fails, the retention claim is withdrawn for the affected period, and authoritative admission closes. A disconnected medium never contains a self-unlocking copy, reusable root-derived DEK, or recoverable epoch-key wrap that could outlive the lifecycle authority.

Every deletion-bound governed plaintext is envelope-encrypted before database or object persistence. Independently deletable content uses a random per-object DEK; content sharing an identical purpose and retention deadline may use a purpose-and-retention-epoch DEK. When the final authorized generation expires, the key lifecycle destroys the DEK and all wraps or shares and signs a negative recovery result. Deduplication may retain an encrypted byte chunk referenced by a newer snapshot, and flash, disk remanence, or shared ciphertext may physically persist; the enforceable claim is that no authorized restore reference or legitimate key path can recover the governed plaintext, not that every physical cell was overwritten.

## Freshness and capacity

The Zero-Cash primary has one 150-GB **raw** Encrypted Data Volume. This number is a device/partition capacity, not a corpus target. All PostgreSQL files, authoritative objects, manifests, indexes, persistent derivatives, upload reservations, measured peak temporary expansion, projected 35-day growth, and required recovery workspace share the capacity boundary. ADR-0045 is applied to every reservation:

```text
C_primary_raw = 150 GB
free_primary
  - remaining_upload_bytes
  - measured_peak_temporary_bytes
  - required_derivative_bytes
  - projected_35d_authoritative_growth
>= max(0.20 * C_primary_raw, declared_restore_workspace)
```

The maximum admitted actual governed corpus is the largest measured database-plus-object state that continues to satisfy this equation under the qualified worst case. It is necessarily lower than 150 GB and is not converted into a 150-GB per-object or live-object allowance. Unknown expansion or reserve terms reject admission.

Backup-target admission likewise uses conservative measured maxima rather than assumed WSI compression or deduplication. Define:

- `O_live`: maximum live unique authoritative object bytes;
- `O_retired35`: unique object bytes deleted from live state but still referenced by an allowed generation;
- `F`: maximum encrypted PostgreSQL full-backup bytes, including the WAL and metadata needed to make its discrete anchor consistent;
- `I`: maximum encrypted daily block-incremental bytes, including its anchor-only consistency WAL and metadata;
- `N_F`: maximum count of full backups that the 35-day lifecycle can retain simultaneously;
- `N_I`: maximum count of incremental backups that the 35-day lifecycle can retain simultaneously;
- `W`: maximum observed or contractually admitted WAL bytes in any 24 hours;
- `M`: manifests, indexes, receipts, configuration and audit overhead;
- `S`: copy-on-write divergence retained by any allowed target snapshot; and
- `P`: worst-case prune or repack scratch bytes.

The minimum raw online-target capacity is:

```text
R_online = O_live + O_retired35 + N_F*F + N_I*I + 9W + M + S + max(F, P)
C_online_raw_min = ceil(R_online / 0.80)
```

The default weekly-class/daily planning bounds are `N_F = 6` and `N_I = 36`; a schedule or emergency-backup policy capable of retaining more substitutes its larger proven bound. The `9W` term is the hard maximum continuous WAL pool and does not double-count anchor-only WAL already in `F` or `I`. The in-flight full/prune term and the `0.80` divisor preserve required work space and 20-percent hard headroom. Bounds come from a 35-day stress campaign or a stricter contractual workload cap until enough production history exists.

Each disconnected medium is budgeted independently and cannot be counted as online headroom:

```text
C_rotation_raw_min = ceil((maximum_encrypted_rotation_generation + rotation_metadata) / 0.80)
```

New authoritative admission closes when:

```text
free_offhost
  - queued_protection_bytes
  - projected_35d_growth
  - next_full_bound
  - prune_scratch
< max(20% of repository capacity, restore-workspace reserve)
```

Unknown, stale, or over-limit terms fail closed; capacity pressure never triggers deletion of live authoritative data.

Backup Freshness State is HEALTHY only while all of the following are true:

- the synchronous receiver is connected and the most recent bounded heartbeat has durable off-host acknowledgement;
- the latest daily and weekly-class PostgreSQL backups remain inside their 26-hour and 168-hour limits;
- every authoritative object has a Protection Receipt and the nightly inventory is current;
- integrity, signature, audit-chain, and repository checks have no unresolved failure;
- the complete 35-day envelope, next full backup, prune workspace, restore workspace, queued protection bytes, and required 20-percent headroom fit on the Backup Target; and
- the disconnected rotation has the freshness required by its declared host-loss or site-loss claim, its epoch-key expiry path is current, and no legitimate epoch-key material has crossed its deadline.

A freshness failure becomes STALE, UNAVAILABLE, or CAPACITY_BLOCKED according to its cause. These states preserve safe reading but reject new irreversible uploads, confirmed submissions or grades, sealed EQA work, accepted Edge work, and other authoritative admissions. Automatic deletion of live authoritative data is never a capacity response.

## Encryption, authority, and evidence

The online repository resides on LUKS2 or an equivalently reviewed Institution-controlled encrypted volume. Its volume key and restic repository secret are distinct purpose-bound Backup Key Versions reconstructed through the existing SOPS-age two-of-three Root Recovery Quorum. Those secrets exist only on the Backup Target during an authorized unlocked interval. A backup-node reboot leaves protection unavailable until the quorum unlocks the target; it never falls back to an unencrypted path or a provider-owned KMS.

Deletion-bound application payloads use the per-object or purpose-and-retention-epoch DEKs described above. A disconnected rotation uses a fresh random epoch DEK that cannot be derived from a reusable root, repository password, media contents, or later epoch; three independently controlled shares require two-of-three recovery and are held outside the ciphertext medium. Root Recovery Quorum may unlock the controlled share stores but cannot regenerate a destroyed random epoch DEK.

Authority is deliberately asymmetric:

- the Backup Target owns the PostgreSQL replication credential, and production exposes only the named replication endpoint plus the signed, read-only, hash-addressed Protection Pull endpoint;
- production holds no backup-volume, restic, rest-server, repository decryption, ingest, delete, prune, unlock, restore, or administration credential;
- the Backup Target ingest worker has a distinct bounded read-and-append repository identity, while full repository maintenance authority is delivered only under a separate bounded target-side maintenance action;
- destructive recovery requires a named recovery commander and two quorum custodians; and
- ordinary policy expiry remains automatic so a missing approver cannot extend retention.

The Backup Target emits canonical, hash-chained Protection, Crypto-Expiry, Deletion, and Restore Receipts. Each receipt records its predecessor hash, monotonic sequence, trusted receipt time, deployment and cluster identity, release and schema, PostgreSQL timeline and LSNs, pull-grant hash where applicable, backup and restic snapshot identities, manifest roots, counts, bytes, tool and configuration hashes, Key Versions or non-secret share identities, expiry, and result. A dedicated Ed25519 Backup Attestation Key Version signs the receipt; the Offline Release Kit and independently held custodian evidence retain the public verification history. The current private HMAC staging manifest is not production recovery evidence.

The signed daily chain head is copied to disconnected custodian media so deletion or rollback of the entire online ledger is detectable. Signatures prove integrity and provenance, not availability: a backup administrator can still destroy an online repository, which is why the independent rotation remains required.

## Append-only target and disconnected rotation

rest-server exposes an append-only endpoint with an explicit storage quota only to the bounded Backup Target ingest identity; it is not a production endpoint. The ingest identity can read and append but cannot overwrite or delete prior repository packs, while the separate maintenance identity is unavailable to that worker. Compromise of production can still generate malicious pull requests, replay grants, or try to induce garbage ingestion and quota exhaustion, so grant nonce consumption, signer and target binding, recomputed hashes, byte/rate limits, capacity admission, and alerts must demonstrate that a previous valid generation remains recoverable under that attack.

At least one complete, verified, encrypted recovery generation is copied to Institution-owned removable or otherwise isolated media. The medium holds only epoch-encrypted ciphertext and non-secret identifiers; epoch-key shares remain independently lifecycle-controlled. The copy is connected only during a bounded refresh or Restore Drill, is verified before disconnection, and is never writable by production. Media custody, location, generation identity, receipt-chain head, epoch expiry, share identities, and verification result are recorded without exposing recovery secrets. Rotation and share-store design must ensure that automatic two-of-three crypto-expiry still succeeds while the data medium is absent or lost.

The base Zero-Cash claim covers loss of the production host and compromise of its credentials. It does not cover fire, theft, flood, or administrative compromise affecting both machines at one site. Site-loss protection may be claimed only when the disconnected copy is held in a second Approved Data Location permitted by every applicable Residency Policy and Transfer Grant. Software append-only modes, same-pool snapshots, signatures, and encryption are not described as WORM or a physical air gap.

## Restore and operating evidence

One trained primary operator and one trained alternate operator own daily receipt review, freshness reconciliation, media rotation, scheduled maintenance, and drill execution. No 24-hour response or uptime promise follows from that staffing model. Synchronous WAL receipt remains continuously prioritized; base, incremental, object-inventory, prune, scrub, and rotation work run with bounded concurrency and yield to an active learner-facing Mode Reservation without weakening the write-stop boundary.

Initial launch requires a 90-consecutive-day operated campaign on the actual production host, Backup Target, storage layout, network boundary, key topology, and named operators. Evidence is stored as signed, individually addressable gate results. A result may remain portable across release candidates only when an impact analysis proves that its exact host, storage, network, tool, configuration, control inputs, workload bound, and expected result are unchanged; a changed input invalidates and reruns that result, not unrelated campaign days. This interval must include:

- two complete 35-day creation-to-expiry cycles with signed logical-deletion and disconnected-generation crypto-expiry evidence;
- idle, peak, target-loss, network-loss, process-restart, primary-restart, slot-pressure, capacity, corruption, replay, and clock fault campaigns;
- proof under power-cut and cache-boundary faults that every acknowledged PostgreSQL write remains inside the hard off-host boundary, no application session can downgrade the frozen durability settings, and every object stays pending until the target-initiated pull and snapshot are protected;
- restoration of latest, five-minute, one-hour, and random retained PostgreSQL targets;
- complete restoration and hash reconciliation of the maximum actual governed corpus admitted by the 150-GB raw primary volume and ADR-0045 reserve equation;
- a separate 150-GB portability and restore-throughput corpus on capacity-qualified build/restore storage, recorded only as transfer, resource, and timing evidence and never as a live-object allowance;
- an isolated replacement-host recovery using the signed Offline Release Kit, actual encrypted Backup Generation, Root Recovery Quorum, network identity, infrastructure state, context databases, outboxes, Audit Integrity Chains, and object manifests;
- production-identity ransomware, malicious and replayed pull grants, garbage-ingestion and quota pressure, receipt replay, signing-key rotation, custodian loss, and old/new-key recovery drills; and
- refresh, disconnection, reattachment, verification, recovery, lost-medium, and on-time epoch-key crypto-expiry drills for the independent rotation.

The exact final candidate -- application release, durability pins, PostgreSQL minor/client pair, operating-system packages, kernel, filesystem, firmware, storage/cache configuration, network rules, key topology, and policy configuration -- must run for at least 14 consecutive days and pass every gate invalidated by its differences. Those 14 days may be the final 14 days of the 90-day campaign when the candidate is already exact and unchanged; otherwise the soak restarts from the last candidate-changing event. A monthly patch therefore triggers a signed impact analysis, targeted reruns, and a new 14-day exact-candidate soak where the candidate changes; it does not reset unaffected 90-day or completed expiry-cycle evidence. A change to retention, crypto-expiry, storage flush, repository format, or another time-dependent invariant carries its own full affected-window rerun even if that is longer than 14 days.

The real-generation drill runs without external egress inside an Approved Data Location, uses an isolated empty restore destination, and removes the recovered workspace under the applicable deletion policy afterward. Synthetic fixtures and the separate 150-GB throughput corpus may add fault or capacity coverage but cannot substitute for recovery of the actual encrypted generation and maximum admitted actual corpus. Every drill records duration, resource peaks, omissions, and result; Zero-Cash Production publishes no fixed RTO.

## Supply chain, patching, and egress

The Authoritative Build Runner admits durability and recovery components only from pinned upstream source revisions after provenance verification and qualification of the exact Linux ARM64 artifact or interpreted runtime/package combination. Barman's Python source is architecture-independent and is qualified on the exact ARM64 Python, operating-system package, and PostgreSQL-client runtime; restic and rest-server are qualified as native ARM64 artifacts. Release evidence includes dependency and license review, secret scanning, static analysis, dependency vulnerability scanning, artifact integrity and provenance verification, CycloneDX and SPDX bills of materials, and component-appropriate dynamic, protocol-abuse, restore-path, and fault tests.

OWASP ASVS 5.0.0 Level 2 is pinned for applicable PathLab web-application controls and HTTP control surfaces, including the Protection Pull endpoint and exposed rest-server boundary. Each control has evidence or a justified non-applicable disposition. PathLab does not label Barman, PostgreSQL command-line tools, restic, rest-server, the operating system, or storage firmware as globally "ASVS Level 2"; those components remain governed by their threat model and component-appropriate qualification gates.

Barman remains an independent GPL-3.0-or-later executable and package. Its source, license, notices, and distribution obligations accompany the Offline Release Kit, but its code is not linked, copied, or adapted into Apache-2.0 PathLab binaries. The other mandatory durability components retain their own compatible OSI-approved licenses and notices.

Qualified patch candidates are reviewed monthly; nothing updates automatically. A known reachable Critical vulnerability in the application, operating system, database, backup, crypto, build, or recovery path blocks production immediately. A High vulnerability requires a documented reachability decision and mitigation whose exception expires within 30 days. Changing a tool, PostgreSQL client, repository format, kernel or filesystem, crypto component, target firmware, key topology, storage layout, or material security configuration invalidates the affected gate evidence, triggers targeted requalification, and starts the exact-candidate 14-day soak without discarding unaffected 90-day campaign evidence.

Production, Backup Target, Authoritative Build Runner, and restore environment use default-deny egress. Explicit permits are limited to the declared direction and initiator: Backup Target-initiated PostgreSQL replication sessions and hash-addressed object pulls whose payloads travel production-to-target, Backup Target-to-production signed receipt delivery, Institution-approved time and network identity services, and purpose-bound Integration Gateway exchanges. Acquisition occurs in a separately controlled supply-chain step, while authoritative build and restore remain offline. Every exception is destination-, protocol-, purpose-, and time-bounded and appears in qualification evidence. No mandatory path may call a hosted CI, registry, telemetry, KMS, backup, AI, notification, or other paid service.

## Claim limits

| Claim | Zero-Cash result |
| --- | --- |
| Free Software Guarantee | Permanent for the admitted PathLab release and mandatory compatible software path |
| Zero incremental external cash spend | Only for the stated 90-day or rolling 12-month evidenced window |
| Primary data capacity | 150-GB raw encrypted volume; the admitted actual governed corpus is lower under ADR-0045 and no object receives a 150-GB allowance |
| Acknowledged PostgreSQL loss | Hard off-host synchronous boundary; maximum accepted objective remains five minutes |
| New authoritative-object loss | Object cannot become authoritative before off-host protection acknowledgement |
| Continuous PITR | Latest seven days |
| Discrete restore history | At least 28 days, with no Backup Generation older than 35 days |
| Disconnected-generation age | Ciphertext may persist, but the non-derivable epoch DEK and sufficient recovery shares expire with signed evidence before 35 days |
| Production-host loss | Qualified through online target, disconnected rotation, and replacement-host drill |
| Production-credential ransomware | Qualified against append-only prior generations and disconnected recovery media |
| Whole-site loss | Not claimed unless the disconnected copy resides in a second Approved Data Location |
| Backup-administrator compromise | Not fully prevented by software; recovery depends on the disconnected independently held copy |
| Availability and RTO | No uptime percentage, automatic failover, or fixed restoration-time promise |
| Physical media erasure | Not claimed; expiry proves removal of reachable restore references and destruction of every legitimate DEK path required to recover deletion-bound plaintext |
