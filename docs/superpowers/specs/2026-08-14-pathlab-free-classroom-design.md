# PathLab Viewer Free-Tier 1,200-Seat Stability Design

## Status

Approved for implementation on 2026-08-14. Production capacity claims remain fail-closed until the protected live certification completes.

## Goals

- Sustain one Classroom with 1,200 students plus one teacher for 60 minutes on the existing OCI Always Free A1 2 OCPU/12 GB VM and existing 200 GB storage.
- Pass a strict 1,500-student 10-minute headroom stage and measure guarded breakpoints at 1,750 and 2,000.
- Preserve all Classroom interactions while functional sentinels exercise annotations, library/shares, upload/conversion, dynamic viewing, and Desktop pairing/ingest.
- Contain Classroom failures so the general API stays responsive and automatically recover failed API, Classroom, or tile components.
- Produce aggregate-only, reproducible evidence tied to the exact deployed SHA and current browser CI.

## Non-goals and boundaries

- No paid compute, runner, database, cache, load balancer, CDN, storage, or additional OCI instance.
- No claim of host, region, or free-instance-reclamation high availability.
- Protocol clients prove concurrency; browser canaries prove real UI behavior. The result must not be described as thousands of browser instances.
- Heavy-stress stages locate a breakpoint; only a later 60-minute strict hold can certify a capacity.

## Global constraints

- Permanent cost is $0: retain OCI A1 2 OCPU/12 GB and 200 GB total storage.
- One active Classroom uses static, published, privacy-passed DZI served directly by Caddy.
- One Classroom Uvicorn worker owns the singleton in-memory hub; no horizontal Classroom workers.
- General annotations stay disabled until migration, security, browser, and live-capacity sentinels pass.
- Production stress runs only inside an explicitly entered three-hour ICT window approved through the protected `production` environment. The recommended normal window remains 02:00–05:00 ICT, but a one-off diagnostic/certification window may use another time without a code change. Every window still requires no active real Classroom, a verified backup/restore drill, rollback release, synthetic fixtures, and fail-closed cleanup.
- The configured participant range is 1..2000. The final production limit is 1500 after strict 1200 and 1500 passes, 1200 after only the sustained gate passes, or restored to 300 with NOT CERTIFIED after a 1200 failure.
- Strict gates: failures below 0.1%; presenter SSE p95 <=250 ms; control/general API p95 <=500 ms; static tile p95 <500 ms; poster p95 <1.5 s; question p95 <=2 s; complete state/reconnect convergence; no lost critical event, queue overflow, pool timeout, SQLite lock error, readiness loss, OOM, or unexpected restart; sustained CPU <80%, memory <85%, and no swap growth.
- Stop heavy escalation when CPU is >=80% for 30 seconds, memory >=85%, queue pressure >=75%, event-loop p99 >250 ms, failures >=0.5%, any pool/SQLite error appears, or latency exceeds twice its SLO for two minutes.

## Proposed architecture

### Application roles

`PATHLAB_SERVICE_ROLE` accepts `general`, `classroom`, or development-only `all`.

- `general`: serves all non-Classroom APIs, runs migrations and storage reconciliation, and uses a SQLite pool of 5 with zero overflow and a one-second timeout.
- `classroom`: serves Classroom HTTP and SSE only, owns the singleton hub, skips migrations/reconciliation, and uses a separate SQLite pool of 4 with zero overflow and a one-second timeout.
- `all`: retains the combined development/test behavior and is rejected by production validation.

Caddy sends `/api/v1/classroom/*` and `/api/v1/admin/classroom/*` to `PATHLAB_CLASSROOM_SERVICE_URL=http://classroom:8001`, sends other API traffic to the general API, and continues to serve `/tiles/*` directly.

### Classroom data flow

- Admission is serialized and exact. The configured ceiling is checked atomically; excess participants receive `409 CLASSROOM_FULL`.
- Public aliases are derived from an HMAC of the join token with bounded unique retries, avoiding a full-room alias scan.
- Presence is in memory. Stream connect/disconnect performs no database write. Each participant has one live SSE stream; a replacement closes the stale stream.
- Presence changes emit a teacher-only `roster-changed` signal at most once per second. Presenter/pointer state remains latest-only. Questions, control, pins, and teaching marks use a bounded 512-entry discrete queue.
- Teacher roster access is keyset-paginated and searchable at no more than 100 rows per request. Teacher state adds `participantCount` and `rosterVersion`; embedded participants remain for compatibility.
- Students take one initial snapshot using `hubEpoch` and `stateVersion`, resynchronizing only on a gap or version mismatch.
- Reconnect attempts use deterministic 0.5–10 second initial spreading and capped exponential backoff.
- Classroom tile requests begin at concurrency two and never exceed four. Guided slide switches use deterministic 0–250 ms jitter. Only bounded descriptor, poster, and common-tile hotsets for current and next slides are prewarmed.

### Saturation and recovery

- Classroom mutation acquisition is bounded; transient saturation returns `503 CLASSROOM_BUSY` and `Retry-After` rather than waiting 30 seconds.
- Readiness uses startup schema validation and a cached lightweight probe rather than per-request introspection.
- A systemd timer probes API, Classroom, and tile components every 15 seconds. After three consecutive failures it captures diagnostics and restarts only that component. It stops after three restarts in ten minutes to prevent flapping.

## Interfaces

- `PATHLAB_SERVICE_ROLE=general|classroom|all`
- `PATHLAB_CLASSROOM_SERVICE_URL=http://classroom:8001`
- `PATHLAB_CLASSROOM_MAX_PARTICIPANTS=1..2000`
- `GET /api/v1/admin/classroom/sessions/{id}/participants?after=&limit=100&q=` returns `items`, `total`, `nextCursor`, and `rosterVersion`.
- Teacher state adds `participantCount` and `rosterVersion` without removing embedded participants.
- Teacher-only SSE event `roster-changed`.
- Saturation: `503 CLASSROOM_BUSY` with `Retry-After`; full room: `409 CLASSROOM_FULL`.
- No database migration is planned; existing `(session_id, public_alias)` uniqueness supports alias pagination.

## Evidence and rollout

Evidence schema v2 records per-shard achieved users, per-journey latency percentiles, generator health and timing drift, SSE convergence, queue/event-loop/pool/SQLite pressure, sockets/FDs, container CPU/memory/restarts/OOM, disk/network, abort cause, recovery, cleanup, exact SHA, and browser-CI identity. Artifacts are aggregate-only and credentials are masked.

Six synchronized public GitHub-hosted Linux shards progress through 2, 100, 300, 600, 900, 1,200, 1,500, 1,750, 2,000, recovery to 1,200. Any unhealthy shard invalidates the result. Production begins with annotations disabled and the ordinary limit; a trap restores configuration after the temporary 2,000 ceiling.

## Alternatives rejected

- Additional OCI capacity, managed databases/caches, paid runners, and load balancers violate the permanent $0 constraint.
- A third-party tile CDN changes privacy and dependency boundaries.
- Multiple Classroom workers break the singleton hub and SQLite consistency model.
- Raising limits without fixing reconnect, roster, presence, and evidence paths cannot support a defensible capacity claim.

## Open evidence gates

- The strict static-tile p95 target has not yet passed even at the historical 300-user public-tile test; it remains a hard certification gate, not an assumed outcome.
- The single free VM remains a host-level single point of failure and may be reclaimed under Oracle policy.
- The final production participant ceiling is determined only by strict live evidence.
