# Combined capacity evidence protocol v3

Precedence status: `SUPPORTING_CONTRACT`. See the [architecture precedence register](ARCHITECTURE_PRECEDENCE.md).

Status: protocol foundation, 2026-09-05. This implements a standalone, fail-closed evidence contract under [ADR 0132](../adr/0132-qualify-3000-learner-combined-broadcast-with-zero-cash-admission.md). It does not implement a 3,000-learner runtime, generate measured receipts, execute load, grant admission, or qualify production. Existing v2 readers and historical results remain separate. A v2 document cannot satisfy any v3 manifest, receipt, prerequisite or final result.

The implementation and executable field contracts are in [capacity_evidence_v3.py](../../tests/load/capacity_evidence_v3.py), next to the existing capacity evidence scripts. [test_capacity_evidence_v3.py](../../tests/load/test_capacity_evidence_v3.py) contains **synthetic protocol conformance fixtures only**. Its passing examples are not observations of a server, receiver, account or campaign.

## Authority and identity

Every envelope has exactly `schemaVersion: 3`, `protocol: "pathlab.combined-capacity/3"`, `kind`, `issuer`, `manifestDigest`, `subject`, `payload`, and `signature`. SHA-256 digests use canonical UTF-8 JSON with sorted keys and compact separators. Non-finite numbers are rejected. Integer fields reject booleans. Unknown envelope and payload fields are rejected.

The subject contains `releaseSha`, `artifactDigest`, `hostDigest`, `configurationDigest`, `clientProfileDigest`, `resourcePartitionDigest`, `installationDigest`, and `deploymentSelectionDigest`. All are lowercase SHA-256 hex strings except the 40-character release SHA. The manifest and every receipt must bind to the exact subject and manifest digest. Profile and partition digests are recomputed. A fresh, signed `current-context` must match the subject, manifest and account policy, and its operating admission must equal the frozen baseline. A different current deployment selection cannot reuse the result.

This foundation uses HMAC-SHA256 with an **externally pinned local trust configuration**: a JSON mapping of issuer names to exactly `keyHex` and `roles`. Each key must contain at least 32 bytes. Valid roles are `manifest`, `current-context`, `generator`, `clocks`, `interactions`, `media`, `resources`, `accounting`, `restoration`, `prerequisites`, and `capacity-result`. The verifier takes this configuration separately; an evidence bundle cannot supply its own authority. A source may sign only its assigned receipt role. Generator admission and restoration must use different issuer identities **and different keys** from interaction/media observers.

HMAC authenticates data from trusted adapters; it does not establish that an adapter actually made the claimed observation. A verifier possessing a shared secret can also sign. This is a local protocol boundary, not an institution signature, an independently audited attestation, an implemented evidence registry, or a substitute for protected key custody. Production trust-root distribution, signer separation and raw evidence retention/retrieval remain required integration work. Hash-shaped source references alone do not prove availability or provenance.

## Frozen manifest

The exact manifest fields are `campaignId`, `subject`, `requestedTarget`, `campaignKind`, `learners`, `frozenAtEpochMs`, `admissionStartEpochMs`, `holdStartEpochMs`, `holdEndEpochMs`, `cleanupDeadlineEpochMs`, `expiresAtEpochMs`, `baselineAdmission`, `workload`, `mediaProfile`, `clientProfile`, `faultWindows`, `resourcePartition`, `accountPolicyDigest`, `sessionNonMediaBoundBytes`, `nonMediaBoundEvidenceDigest`, and `prerequisiteEvidenceDigests`.

`requestedTarget` is always `{ "learners": 3000, "holdSeconds": 3600 }`. Campaign kinds are `interaction-engineering`, `media-engineering`, `combined`, and `reconnaissance`. A full campaign has exactly a 60-minute hold at its declared learner count. A shorter reconnaissance campaign cannot earn a qualified capacity. Admission finishes within five minutes before the hold; independent cleanup verification has a separately reserved window.

The workload freezes one Instructor, six static-DZI cases, 10 Hz pointer and viewport updates, six prompts per learner, questions from `ceil(learners / 5)` learners, and reconnects from `ceil(learners / 10)`. The media profile freezes one VP8 540p publisher with separate 600,000-bit/s video and 32,000-bit/s Opus audio caps, receive-only learners, no recording and no transcoding. It also freezes a qualified wire envelope greater than the codec payload sum, plus its evidence digest.

The client profile freezes content, network matrix, physical generator fleet, receiver cohort/roster, sampling method and clock method digests, sampling interval, maximum clock uncertainty, and exact direct/TURN receiver counts. `cohortDigest` must match in generator admission, clock evidence, interactions and media; matching counts or matching interaction/media aggregates from a different roster cannot qualify. Both routes must be represented for a full campaign; they sum to the declared count. Resource partition values bind to ADR 0040: the existing 2-OCPU/12-GiB host, 2 GiB OS, resident services 0.75 OCPU/3 GiB, active mode 1 OCPU/6 GiB, and emergency 0.25 OCPU/1 GiB.

Two non-overlapping fault windows, `live-restart` and `media-failure`, are frozen inside the hold. Observation receipts cannot redefine their timing. Separate engineering campaigns precede the combined freeze. Their full signed v3 manifest/receipts/current-context/result packages are supplied in `prerequisites`; their result digests must match the frozen manifest. The validator recursively recomputes each engineering result, verifies the appropriate individual capacity at least equals the combined count, checks restoration, exact subject, distinct campaign identities, and completion before the combined manifest was frozen. Summary success flags and historical v2 results are insufficient.

### Provisional conservative policy bounds

ADR 0132 requires bounded windows and current observations but does not specify all numeric bounds. This implementation deliberately restricts each fault window to at most 90 seconds, cleanup reserve to at least five minutes, current-context and provider/accounting freshness to five minutes, clock uncertainty to at most 100 ms, sampling intervals to at most one second, and manifest validity after cleanup to at most 24 hours. It requires at least one fanout sample per learner per second, acknowledgement evidence for the expected durable workload, and evidence for every declared reconnect. The CLI permits a manifest freeze timestamp only within the preceding five seconds.

These are conservative **protocol implementation policies**, not additional numeric claims attributed to ADR 0132 or deployed admission settings. Runtime/controller/measurement policy migration must reconcile and freeze them before a real campaign. The API accepts an explicit evaluation time for deterministic tests; the CLI uses wall-clock time and exposes no backdating option.

## Observation receipts and gates

Each campaign requires `generator`, `clocks`, `resources`, `accounting`, and `restoration`. Interaction engineering additionally requires `interactions`; media engineering requires `media`; combined requires both and `prerequisites`; reconnaissance requires both but earns no capacity. Missing, duplicate, unexpected or unused receipt kinds deny finalization. The named functions in the implementation define every required payload key and type.

| Receipt | Required proof |
| --- | --- |
| `generator` | Independent admission before execution; matching fleet and physical-client evidence; exact learner count; no saturation or dropped iterations. |
| `clocks` | Entire hold, matching frozen method, every receiver covered, before/after probes, and observed uncertainty within the frozen limit. |
| `interactions` | Entire hold and exact cohort; admission, six traversed cases and six answered prompts per learner, declared questions/reconnects and 10 Hz events; sufficient sampling; fanout p95 at most 1 s, durable ack p95 at most 2 s, resync p95 at most 10 s; zero lost durable interactions; correct attendance, submitted workspaces and final convergence for all; no retained ephemeral data or guest durable writes; exact observed fault windows. |
| `media` | Same full hold and combined cohort, every direct/TURN receiver observed and decoded, frozen codecs/profile/method, actual 540p delivery and separate publisher bitrate caps, sufficient samples without excess gaps, and exact observed faults. Startup p95 at most 5 s and end-to-end p95 at most 2 s; every receiver automatically recovers inside the frozen media fault; no slides-only receivers, recording or transcoding. Actual wire peak and bytes are measured. |
| `resources` | Exact partition and full hold, enforced cgroups, resident/mode CPU and memory within partition, emergency headroom preserved, inactive modes zero, no breaches, swap growth, unexpected restart or OOM. |
| `accounting` | Current authoritative allowance/tariff/reset observations, durable reconciled usage and reservations, bounded admission and local enforcement as described below. |
| `restoration` | Independent observation after hold and before cleanup deadline, successful command exit, exact release/configuration, baseline admission, readiness/watchdog/controller restored, annotations disabled, zero campaign fixtures and own Bastion sessions, and zero mutations of other campaigns. Runtime health alone is insufficient. |

Latency bounds include twice the measured clock uncertainty. The media denominator is the complete hold minus only the two frozen fault windows. Missing observation time cannot shrink it. `jointDecodedMsMinimum` is the minimum joint audio-and-video decoded time over **every** receiver. The validator subtracts `2 * (samplingIntervalMs + observedClockUncertaintyMs) * decodeIntervalsMaximum` before comparing to 99 percent of the non-fault window. `decodeIntervalsMaximum` must conservatively cover each receiver's disjoint decoded intervals. Aggregate connection counts, average coverage, sampled subsets and separate audio/video percentages cannot substitute for these per-receiver extrema. Real adapters must derive the extrema and interval bound from retained individual receiver evidence.

## Zero-cash admission evidence

Account identity, currency, tariff digest and expiry, actual allowance, and reset start/end are hashed into the account policy shared by manifest, current context and accounting receipt. Tariff and reset must cover the hold, cleanup and current evaluation. No hardcoded OCI allowance is treated as observed. Gross incremental charge, payment and projected incremental charge must each be zero; mandatory paid dependencies deny qualification.

Both pre-admission and final snapshots include local/provider observation times, provider usage, durable local usage, unreported usage, concurrent reservations, ledger sequence and reconciliation status. Provider age is checked directly against admission or current evaluation time, respectively; chaining two individually fresh observations cannot extend the five-minute limit. Exact ledger categories are `media`, `tiles`, `backups`, `campaigns`, and `other`; their total equals local usage. Counters cannot regress within the frozen reset period. Unreported usage must preserve at least the difference between local and delayed provider usage. Final usage reconciles the campaign's actual bytes and measured media bytes.

The campaign's reservation must be atomic, durable, acquired before admission, exclusive for the heavy mode, and last at least the default 60 minutes. Its explicit `reservedAtEpochMs + durationSeconds * 1000` must cover the entire hold through its end without crossing the frozen reset or tariff expiry. Therefore a full campaign reserved before its five-minute admission phase needs additional reserved time and bytes for admission. The byte bound is at least `ceil(learners * qualifiedWireEnvelopeBpsPerReceiver * durationSeconds / 8) + sessionNonMediaBoundBytes`. The non-media bound has a separately frozen evidence digest. Codec payload alone does not cover relay, retransmission, protocol overhead or tiles. Extension receipts are intentionally unsupported in this foundation: a nonempty extension list is `NOT_EVALUABLE`; an extension adapter must implement a new atomic reservation before it can be accepted.

Reserved operating headroom is `max(20% * verifiedAllowanceBytes, essentialForecastBytes)`. Conservative pre-admission commitment is `max(providerUsage, localUsage) + unreportedBytes + concurrentReservationsBytes + thisReservationBytes`. Final commitment uses the same formula without the consumed own reservation. Both must leave the operating reserve intact. Actual session bytes must not exceed its reservation. The enforced local ceiling must cover committed usage and remain below allowance minus the reserve. Accounting staleness, missing categories or lost reservation/reconciliation evidence deny qualification; measured overspend or enforcement failure is a negative result. This conservative calculation can overcount uncertain usage rather than silently discard it.

Reservations must be acquired within the same verified reset period used for admission; this foundation does not carry a prior-period reservation across a reset. These checks validate supplied receipts. They do not implement an atomic ledger, provider adapter, traffic limiter, reservation extension, or UI showing remaining admissible duration. No paid resource is provisioned, and no monthly class-hour or permanent-free promise follows.

## Results, producer and validator

Results separate `requestedTarget`, `qualifiedInteractionCapacity`, `qualifiedMediaCapacity`, `qualifiedCombinedCapacity`, `currentOperatingAdmission`, `combinedTargetResult`, `failureCategory`, `missingEvidence`, `workloadFailures`, and `restorationResult`. They retain exact subject, manifest digest, campaign kind and evaluation time. `activationAllowed` and `admissionChangeAuthorized` are always false.

| Evidence | Target result | Capacity meaning |
| --- | --- | --- |
| Complete current combined 3,000/60-minute proof, prerequisites and restoration | `SUCCESS` | Qualified combined capacity 3,000; operating admission remains separately reported. |
| Complete lower-count combined 60-minute proof | `PARTIAL` | That lower combined count is qualified; requested 3,000 remains unmet. |
| Standalone full engineering campaign | `PARTIAL` | Only its individual interaction or media capacity can qualify. |
| Short reconnaissance campaign | `PARTIAL` | No qualified capacity, even if its observations pass. |
| Authentic measured workload/resource/cost violation | `NEGATIVE` / `WORKLOAD_FAILURE` | Failed measurements cannot earn the corresponding capacity. |
| Missing, malformed, untrusted, stale, conflicting or restoration-unproved evidence | `NOT_EVALUABLE` / `HARNESS_FAILURE` | Combined capacity is null; missing evidence and any independently observed workload failures remain separate. |

An independently qualified interaction or media measurement may remain visible when the other measurement or combined prerequisite is missing. This is not a combined qualification. Restoration is separately `PROVED` or `UNPROVED`; missing restoration blocks all earned capacities.

The standalone producer accepts supplied source observations; it never manufactures them. It freezes a declarative manifest, or finalizes an assessment with digests of the source manifest, receipts and current context. It retains neither source payloads nor private extra fields in the final result. A signed final success is insufficient by itself: validation requires all original inputs and the external trust configuration and recomputes the assessment, including freshness. Source modification, changed current selection or altered signed claims are rejected.

```text
python tests/load/capacity_evidence_v3.py freeze --spec manifest-spec.json --issuer GOVERNANCE --key-file PRIVATE_KEY --output manifest-v3.json
python tests/load/capacity_evidence_v3.py finalize --manifest manifest-v3.json --receipts receipts-v3.json --current-context current-v3.json --trusted-keys PRIVATE_TRUST_CONFIG --issuer FINALIZER --key-file PRIVATE_KEY --output result-v3.json
python tests/load/capacity_evidence_v3.py validate --input result-v3.json --manifest manifest-v3.json --receipts receipts-v3.json --current-context current-v3.json --trusted-keys PRIVATE_TRUST_CONFIG
```

Signing key files contain raw bytes; trust configuration contains the matching hex bytes and assigned roles. Keep both outside the repository and artifacts. No keys are supplied in this documentation. A successful freeze exits zero. Finalize/validate exit zero only for target `SUCCESS`; `PARTIAL`, `NEGATIVE`, and `NOT_EVALUABLE` exit two. Finalize writes a signed `NOT_EVALUABLE` assessment for evaluable missing-evidence inputs; unreadable/malformed authority or non-JSON input exits two with a generic error instead of inventing a receipt.

## Remaining integration and verification

This package adds only the standalone v3 script, its tests and this document. It does not alter the v2 parser, v2 evidence, existing controllers, runtime cap, workflow or admission path. Before usable higher limits, migrate runtime limits, campaign/shard manifests, controller windows, source adapters, report validators and finalizers together; collect separate engineering campaigns followed by a fresh combined full hold at the same identities.

Required runtime work includes the real media publisher/fanout/receiver path, physical client/network matrix, individual decode and clock probes, sampling/fault evidence, independent generator admission, resource observations, and independently owned restoration/fixture verification. Required accounting work includes live provider allowance/tariff/reset adapters, durable transactional category ledger, concurrent reservation reconciliation, qualified wire/non-media bounds, local enforcement, extension policy and admission UI. Required governance work includes production signer custody, externally pinned trust/registry integration and raw-evidence verification. The CLI must not be wired to an admission increase until those gaps are closed with fresh evidence. Unknown measurements remain `NOT_EVALUABLE`.

Local verification on 2026-09-05: **305 tests passed in 9.38 seconds**, comprising 132 v3 synthetic conformance tests and 173 existing recovery/v2 compatibility tests. Ruff check and format passed for both new Python files. Independent review reproductions added coverage for reservation time/byte coverage across admission, prior-reset reservations, provider freshness measured directly at admission/evaluation, frozen roster binding across generator/clocks/interactions/media, and impossible unique-learner counts. Reserve/headroom byte arithmetic uses integer ceiling operations to avoid rounding below the conservative bound. The exact suite was:

```text
python -m pytest tests/load/test_capacity_evidence_v3.py tests/load/test_capacity_terminal_status.py tests/load/test_capacity_safe_verification.py tests/load/test_capacity_workflow_v2.py tests/load/test_distributed_certification.py tests/load/test_capacity_window.py
ruff check tests/load/capacity_evidence_v3.py tests/load/test_capacity_evidence_v3.py
ruff format tests/load/capacity_evidence_v3.py tests/load/test_capacity_evidence_v3.py
```

No real measurement receipt, 3,000-user run, media qualification, account allowance proof or production activation was produced by this package.
