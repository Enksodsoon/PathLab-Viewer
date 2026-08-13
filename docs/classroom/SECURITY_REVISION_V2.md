# PathLab Classroom Security Revision V2

## Purpose

This document is a **stacked security revision** for the lightweight Classroom work in PR #93.

It does **not** replace, rewrite, close, merge, or invalidate PR #93 or the existing Classroom plan. The original plan remains the implementation baseline. This revision adds only the security, privacy, and resource-hardening changes discovered during the fresh review of the current Viewer and Forge state.

Base reviewed Classroom head: `a2bfb60464f53ba0eae7c071b99752917917a62f`

Current Viewer main reviewed: `097ca6eb2c73141dff0416f0816e8af694d498bf`

Current Forge main reviewed after merged Viewer-sync delivery.

Classroom remains disabled by default. No production activation is authorized by this document.

---

## Threat model focus

The Classroom diff introduces these new trust boundaries:

- unauthenticated join requests;
- anonymous participant cookies and participant CSRF tokens;
- student SSE connections;
- student pins, questions, and control requests;
- temporary student presenter leases;
- teacher/admin presenter, pointer, and teaching-mark operations;
- student-local screenshot and notebook storage;
- static DZI paths disclosed to joined participants;
- internal library/folder metadata crossing into the learner UI.

Assets requiring protection include:

- administrator sessions and control authority;
- private or de-identified slide metadata;
- learner-private notes and screenshots;
- learner identity separation on shared devices;
- classroom availability and low-latency tile delivery;
- integrity of presenter/control state;
- internal library organization and folder names.

The intended production invariant remains: **Classroom must add negligible server load compared with tile delivery and must fail closed without exposing private content or cross-learner state.**

---

# Validated findings

## SR2-01 — Shared-browser learner identity and notebook isolation

**Severity: Medium**  
**Status: Reportable / must fix before pilot**

### Evidence

The participant cookie is persistent and HttpOnly for the active classroom. When the same browser joins the same classroom again, the server intentionally restores the existing participant rather than creating a new one. The new display name is ignored during this rejoin path.

The student notebook is stored in IndexedDB and is keyed/listed by `sessionId` only. Notebook entries currently have no participant/owner partition.

### Attack path

1. Student A joins a classroom on a shared browser.
2. Student A creates private screenshots and notes.
3. Student A leaves the workstation without manually deleting browser data.
4. Student B opens the same classroom on that browser.
5. The existing participant cookie restores Student A's participant identity.
6. The notebook loads all entries for the session.
7. Student B can see Student A's private notes/screenshots and can act under Student A's classroom identity.

### Required revision

- Partition notebook records by a local learner owner key in addition to session ID.
- Never list notebook entries using `sessionId` alone.
- Add an explicit **Shared device / Switch learner** flow.
- The switch flow must clear/rotate the participant cookie through a server endpoint; JavaScript must not be able to read the HttpOnly participant credential.
- A new learner on the same device must receive a new participant identity and an empty private notebook view.
- Existing local notes must not be deleted automatically; they remain associated with the previous local owner and require explicit export/delete.
- Add regression tests proving Student B cannot read Student A's notes or inherit Student A's control/question identity after an explicit learner switch.

Do not add server-side notebook synchronization.

---

## SR2-02 — Internal folder-path names disclosed to classroom participants

**Severity: Medium privacy risk**  
**Status: Reportable / must fix before pilot**

### Evidence

Classroom session creation walks the administrator folder hierarchy and snapshots raw `Folder.name` values into `folder_path`. `_session_slide_json()` includes `folderPath`, and student state returns this object directly to participants.

The existing Viewer privacy boundary requires explicit de-identification review before folder/collection names and teaching metadata are exposed through public sharing. Individual slide publication does not make the slide's internal canonical folder path public.

### Attack path

1. An administrator keeps a published/de-identified slide inside an internal folder whose name contains internal course, diagnostic, research, accession, patient, or operational wording.
2. The teacher creates a Classroom session from that published slide.
3. Classroom snapshots the internal folder hierarchy without a separate disclosure review.
4. Any joined participant receives the folder-path names in student state.

### Required revision

Choose the lowest-complexity option for the first pilot:

- **Preferred:** remove `folderPath` from the student projection entirely; retain it only in teacher/admin state.

If learner grouping is later needed:

- use an explicit teacher-authored, session-scoped safe group label;
- never derive learner-visible grouping from raw canonical folder names without the same de-identification review used by public folder sharing.

Add a regression test with a deliberately sensitive synthetic folder name and prove it is absent from the student response.

---

## SR2-03 — Unbounded anonymous join waiters can exhaust the one-worker classroom API

**Severity: Medium availability**  
**Status: Reportable / must harden before production enablement**

### Evidence

`POST /api/v1/classroom/join` is unauthenticated by design. Join work is serialized through a single `asyncio.Lock`, but there is no bounded waiting-room size or request-rate admission before waiting for the lock.

The supported production topology intentionally uses one API worker. Serializing the database mutation protects SQLite, but an attacker does not need a valid join code to create many concurrent requests waiting on the application lock.

### Attack path

1. Remote client sends a large number of concurrent join POST requests.
2. Requests pass body validation and wait on the same join lock.
3. Pending request tasks and sockets accumulate even when the supplied join code is invalid.
4. Legitimate students compete with the backlog and the one API worker loses responsiveness.

### Required revision

- Add a bounded in-process join admission queue/counter before the serialized mutation.
- Reject overflow quickly with `429` or `503` plus `Retry-After`.
- Keep the bound small enough to protect memory but large enough for a normal class burst.
- Do not use strict per-IP limits as the primary control because a university classroom may share NAT/proxy egress.
- Keep join mutation serialization for SQLite safety.
- Extend the load harness with an invalid-code flood running concurrently with legitimate joins; legitimate joins must remain bounded and no API OOM/restart may occur.

No Redis or additional rate-limit service is required.

---

## SR2-04 — A participant can open unbounded SSE streams

**Severity: Medium availability**  
**Status: Reportable / must fix before pilot**

### Evidence

A valid participant can call the student SSE endpoint repeatedly. `ClassroomHub.subscribe()` adds every connection to the subscriber set and increments the live-connection count, but there is no per-participant stream cap and no hard classroom SSE ceiling.

The participant connection counter tracks multiple connections but does not reject them.

### Attack path

1. Attacker obtains a valid participant session by joining the displayed classroom code.
2. The same participant opens many SSE connections.
3. Every connection remains long-lived and receives classroom fan-out events.
4. File descriptors, API connections, Caddy upstream connections, queue references, and fan-out work grow independently of the 300-participant limit.
5. A single participant can therefore consume capacity reserved for the class.

### Required revision

- Enforce a small per-participant SSE limit (recommended: 2 concurrent streams; one is normal, one permits brief reconnect overlap).
- Enforce a bounded global classroom SSE ceiling with modest headroom above the supported class size.
- Reject additional streams before subscription rather than relying on slow-subscriber cleanup.
- Preserve deterministic reconnect jitter and HTTP full-state resynchronization.
- Add focused tests proving the third concurrent stream for one participant is rejected and a connection storm cannot exceed the global bound.

---

## SR2-05 — One learner can monopolize questions or spam teacher pin events

**Severity: Medium classroom availability/integrity**  
**Status: Reportable / must fix before pilot**

### Evidence

The question system has a session-wide pending limit of 200 and a lifetime receipt limit of 500 per participant, but no small per-participant pending limit and no time-based question throttle. A single joined participant can therefore fill the session-wide pending queue.

Pin updates replace one in-memory pin per participant, which bounds memory, but every accepted pin update emits a critical teacher event and there is no participant pin rate limit. Alternating set/clear requests can create repeated critical events and database reads.

### Attack path A — question starvation

1. One joined participant scripts question submissions with unique idempotency keys.
2. The participant creates the full 200 pending questions.
3. Every other learner receives `QUESTION_NOT_ACCEPTED` until the teacher deletes questions.

### Attack path B — pin event spam

1. One joined participant repeatedly sets and clears a pin.
2. Each accepted mutation publishes a critical teacher SSE event.
3. Teacher queue churn and API/database work increase despite the one-pin memory bound.

### Required revision

- Limit pending questions per participant to **3**.
- Add a per-participant question creation interval (recommended baseline: one new question per 10 seconds; idempotent retries do not consume the interval).
- Keep the existing 200-session pending ceiling as a secondary safety bound.
- Rate-limit pin mutation per participant (recommended 2–5 accepted updates/second; normal UI produces far less).
- Prefer coalescing non-final pin movement; the committed question pin remains a discrete critical event.
- Add abuse tests proving one participant cannot block another participant from submitting a question.

---

# Validated hardening items (not separate vulnerabilities)

## HR2-01 — Presenter frequency must match the certified load profile

The 300-participant local capacity evidence exercised presenter movement at approximately **2 Hz**. The client sender currently permits a much higher cadence (50 ms interval / up to 20 Hz), and the student controller has a 25 Hz server-side ceiling.

For the first pilot, production configuration and code should use:

- teacher viewport: 2 Hz normal, 4 Hz hard maximum;
- student presenter viewport: 2 Hz normal, 4 Hz hard maximum;
- remote teacher pointer: 5–10 Hz maximum;
- local pointer remains browser-local and may render at display refresh rate;
- always send the final settled viewport immediately.

Re-run the 300-participant gate using these exact production limits.

Do not raise frequencies until a like-for-like capacity run shows clear headroom.

---

## HR2-02 — Classroom slide tile access is intentionally not session-scoped

Current Classroom requires already-published static DZI slides and returns the direct `/tiles/{publicId}/{version}/...` path. Caddy serves these published derivatives without a per-request Classroom authorization check.

This is **not classified as a vulnerability in V2** because the source slide is already in the product's explicitly published/unlisted state before Classroom starts. However, a participant who learns the tile path may continue to request that published derivative after the Classroom ends while that publication/version remains active.

For the first low-resource pilot:

- preserve this behavior only for slides that have already passed publication/de-identification review;
- state clearly that Classroom join is not a revocable tile-access boundary;
- do not claim session-scoped confidentiality for classroom slides.

If a future requirement demands private/session-expiring slide access, design it separately using a static low-overhead capability/alias architecture. Do not route every tile through FastAPI merely to add revocation.

---

## HR2-03 — Keep dynamic OME out of the live Classroom path

The latest Forge release prefers direct OME delivery for normal Viewer storage efficiency. PR #93 deliberately accepts only published `static_dzi` slides.

Preserve the prior product plan:

- add a future **Prepare for Classroom** Forge profile that generates and validates a static DZI before class;
- do not enable first-time dynamic OME rendering during a live class;
- keep conversion and heavy image processing outside the live-session critical path.

This is a performance/integration requirement, not a new security finding.

---

# Repository and release blockers

## RB2-01 — PR #93 CI is not currently merge-green

The latest Security workflow passes, but the CI backend job stops at the public-repository history check. The current PR history contains commit author emails that violate the repository's privacy-safe history policy, and a classroom certification runtime fixture contains a non-example email address.

Required before merge:

- reconstruct/squash the eventual merge branch with privacy-safe commit metadata;
- sanitize the fixture email;
- rerun the full protected CI matrix;
- do not weaken or bypass the repository disclosure scanner to make the branch pass.

This is a release-governance blocker, not an application-runtime vulnerability.

## RB2-02 — Full repository browser evidence is not completely green

The classroom-specific browser checks passed in the retained local evidence, but the recorded full Playwright matrix includes unrelated failures. Before release, either fix those failures or document a reviewed baseline proving they are pre-existing and unrelated to the Classroom change.

---

# Preserved original Classroom plan

Everything below remains unchanged from PR #93 and the earlier Classroom design unless explicitly modified by this V2 overlay:

- feature disabled by default;
- one active Classroom session;
- anonymous generated learner aliases;
- static DZI served by Caddy;
- no Redis;
- no WebSocket service;
- no new background worker;
- no server screenshot generation;
- screenshots and private notes stored in browser IndexedDB;
- private student drawing stays local;
- teacher Guide/Follow workflow;
- exact pinpoint questions;
- temporary student presenter control;
- transient teacher pointer and teaching marks;
- sparse SQLite presenter checkpoints;
- singleton in-process hub;
- deterministic reconnect jitter and HTTP resynchronization;
- no AI, video, chat, or heavy analytics in Classroom;
- no production activation until exact-release capacity evidence passes.

The earlier product priorities also remain intact:

- build a separate local **My Notebook** study surface after Classroom Core;
- allow browse/edit/delete/reopen/export/import of local notes;
- add granular pointer/field/slide control later;
- combine pinpoint question + optional control request later;
- add temporary Focus Class later;
- add lightweight session title/objectives/reordering later;
- keep advanced LMS, formal assessment, AI tutor, video/chat, and heavy analytics deferred.

---

# Required implementation order for Security Revision V2

1. **Fix shared-browser learner isolation (SR2-01).**
2. **Remove internal folder paths from student projection (SR2-02).**
3. **Bound unauthenticated join admission (SR2-03).**
4. **Bound per-participant and global SSE connections (SR2-04).**
5. **Add per-participant question and pin abuse controls (SR2-05).**
6. Lower presenter/pointer frequency to the first-pilot certified profile (HR2-01).
7. Add focused security/abuse regression tests for every item above.
8. Re-run classroom unit/frontend/browser checks.
9. Re-run the 300-participant exact-stack capacity test with deliberate abuse traffic.
10. Repair the branch-history/public-repository CI blocker without weakening the scanner.
11. Run complete CI and Security workflows.
12. Keep Classroom disabled and retain PR #93 until the stacked security revision is reviewed.

---

# Security acceptance gates

The revision is ready for merge consideration only when all are true:

- a second learner on a shared browser cannot inherit the first learner's identity or notebook;
- student state contains no raw internal folder path;
- invalid join floods are bounded and legitimate joins remain responsive;
- one participant cannot exceed the per-participant SSE connection limit;
- total Classroom SSE connections cannot exceed the configured hard ceiling;
- one participant cannot fill all pending question capacity;
- rapid pin mutation is rate-limited/coalesced without breaking normal exact-pin questions;
- stale/revoked student presenter leases still fail closed;
- no screenshots or notebook images are uploaded;
- no new Redis/WebSocket/background service is added;
- 300-participant convergence/reconnect/tile/control/question gates pass with the exact production cadence;
- API/Caddy have no restart or OOM event;
- protected CI is green;
- Security workflow is green;
- public-repository disclosure checks are green;
- Classroom remains disabled until separate production activation approval.

---

## Forge security scope result

The latest merged Forge path remains loopback-bound for its local web UI, uses high-entropy local browser credentials, and keeps Viewer delivery outbound/private. No new Forge-side security blocker was identified that requires changing the existing Classroom plan.

The existing Forge redistribution/licensing and installer-signing decisions remain separate governance/release work and are not changed by this Classroom V2 security overlay.
