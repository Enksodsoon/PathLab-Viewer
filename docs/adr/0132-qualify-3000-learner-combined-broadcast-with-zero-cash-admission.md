# Qualify 3,000-learner combined broadcast with zero-cash admission

This decision supersedes the numeric Live Learning and Teacher Broadcast targets in ADRs 0002, 0006, 0022, 0027, 0066 and 0128. Their remaining authority, privacy, recovery, resource, and exact-release requirements continue to apply. Accepted ADR history and historical evidence remain unchanged. This decision establishes a target, not implemented capacity or permission to raise production admission.

## Combined workload

One Instructor and the same 3,000 learners complete a 60-minute Class Session on the existing Zero-Cash Production host. All learners receive teacher audio/video while traversing six static-DZI cases. Admission completes within five minutes. Pointer and viewport updates run at 10 Hz; all learners answer six prompts; 600 learners submit questions; 300 learners reconnect and resynchronize. The frozen manifest includes a live-service restart and media failure, separate bounded fault windows, correct Attendance Intervals, submitted workspace evidence, and final convergence.

Event fanout p95 is at most one second, durable acknowledgement p95 at most two seconds, and reconnect/resynchronization p95 at most ten seconds. No Durable Interaction may be lost and no Host Resource Partition may be breached.

The publisher encodes VP8 at 540p with a 600,000-bit/s video cap and Opus with a separate 32,000-bit/s audio cap. There is one publisher and 3,000 receive-only learners, no server transcoding, and no recording. Media startup p95 is at most five seconds and end-to-end delay p95 at most two seconds. Each learner must receive decoded audio and video throughout at least 99 percent of its non-fault observation window. The manifest freezes the content, client/network matrix, direct/TURN mix, sampling method, clock uncertainty, and fault windows before execution; missing receiver or clock evidence cannot pass. Connection counts do not prove decoded delivery. Media Fallback proves recovery only; a slides-only learner does not satisfy the combined target. Automatic media recovery after the declared fault must also be observed.

Separate non-media and media engineering campaigns precede the combined repeat. Qualification uses the same release, profile, host, configuration and evidence identities. Assessment and every other context retain their separate workload and heavy-mode reservations.

## Safe partial delivery and evidence

Independently verified repairs may ship at a measured safe operating limit while the combined 3,000 target remains unmet. The lower combined limit needs a complete 60-minute campaign proving both media and interactions at that count; a ramp stage, separate larger SSE pass, or historical result cannot establish it. Such delivery cannot claim Full-Surface qualification or activation.

Requested workload, qualified interaction capacity, qualified media capacity, qualified combined capacity, current operating admission, target result, and restoration result are separate fields in the next versioned capacity protocol. Legacy v2 evidence remains historical and cannot satisfy this target. Runtime limits, manifests, controllers, report validators and finalizers must migrate together before new limits are usable. Preserve the existing operating cap until that migration and fresh evidence are complete; capacity success never activates annotations, identity, AI or other feature flags implicitly.

After verified restoration and independent generator admission, use smoke, 100, 300, 600, 1,200, 2,000 and 3,000 reconnaissance stages. Stop escalation on safety or correctness failure. Run the full qualification hold and recovery separately at the intended limit, inside a window that reserves time for independent cleanup verification. Harness failure, workload failure, and restoration not proved are distinct outcomes.

## Zero-cash usage admission

No additional paid capacity or mandatory service is authorized. Before admission, verify the actual account allowance, reset boundary, tariff and current usage. A conservative durable ledger accounts for media, tiles, backups, test campaigns and other relevant traffic; local counters reconcile with provider observations without losing unreported usage or concurrent reservations. Stale or unavailable accounting denies new media reservations.

Reserve the maximum bounded session bytes before admitting it, with a default 60-minute reservation. Keep the greater of 20 percent of the verified monthly allowance and the essential-operations forecast reserved for operations and uncertainty. Include transport/relay/retransmission overhead using the qualified wire envelope, not only codec payload. Extensions require a new atomic reservation. Local enforcement stops excess media traffic before the free allowance can be crossed, preserves durable state, and exposes the reason and remaining admissible duration in the UI. Delayed billing alerts are observations, not the enforcement mechanism. No fixed monthly class-hour or permanent-free promise follows.

At full codec caps the 3,000-receiver payload is 1.896 Gbit/s and 853.2 GB per hour, before protocol overhead and tiles. These are planning bounds, not measured throughput. If the unchanged host or free allowance cannot support the frozen workload, report the target unmet and retain the proved safe cap. Do not lower quality thresholds after observing a failure.
