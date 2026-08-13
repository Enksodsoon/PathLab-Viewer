# PathLab Classroom Security Revision V2

## Purpose

This is an **additive security revision** for the merged lightweight Classroom implementation.

It does **not** replace, rewrite, or invalidate the original Classroom plan from PR #93. The merged Classroom remains the implementation baseline. This revision adds only the security, privacy, and low-resource hardening requirements found by the fresh Codex Security review.

Reviewed Viewer main: `8db91e8c0d49c17f2da42f747bf4604ccc6652e1`

Reviewed merged Classroom change: PR #93

Reviewed current open Classroom follow-up: PR #95 (`codex/classroom-folder-navigation`)

Reviewed current Forge main after merged Viewer-sync delivery.

At review time:

- Viewer PR #93 is merged;
- main CI is green;
- main Security workflow is green;
- production deployment of `8db91e8c0d49c17f2da42f747bf4604ccc6652e1` completed successfully;
- Classroom remains feature-gated and should remain disabled until this V2 hardening is reviewed and the exact enabled release passes its capacity gate.

---

## Threat-model focus

The merged Classroom adds these new trust boundaries:

- unauthenticated join requests;
- anonymous participant cookies and participant CSRF tokens;
- long-lived participant SSE connections;
- learner pins, questions, and control requests;
- temporary learner presenter leases;
- teacher/admin presenter, pointer, and teaching-mark mutations;
- browser-local learner screenshots and notes;
- direct static DZI paths disclosed to joined learners;
- internal library/folder metadata crossing into learner projections.

Assets requiring protection include:

- administrator sessions and teacher control authority;
- de-identified slide metadata and internal library organization;
- learner-private notes and screenshots;
- learner identity separation on shared devices;
- classroom availability and low-latency tile delivery;
- integrity of presenter/control state;
- bounded SQLite and SSE resource use.

Primary invariant:

> Classroom must add negligible server load compared with static tile delivery and must fail closed without exposing private content or cross-learner state.

---

# Validated findings

## SR2-01 — Shared-browser learner identity and notebook isolation

**Severity: Medium**  
**Disposition: reportable; fix before pilot**

### Evidence

When the same browser joins the same active classroom again, the signed HttpOnly participant cookie restores the existing participant identity. A newly supplied display name does not create a new learner identity.

The local notebook is IndexedDB-based, but entries are keyed and listed by `sessionId` only. There is no participant/local-owner partition in the notebook record.

### Attack path

1. Learner A joins on a shared browser.
2. Learner A saves private screenshots and notes.
3. Learner A leaves the workstation without manually deleting browser state.
4. Learner B opens the same classroom on that browser.
5. The existing participant cookie restores Learner A.
6. The notebook loads entries for the same session.
7. Learner B can see Learner A's private notes/screenshots and can act under Learner A's classroom identity.

### Required revision

- Partition local notebook data by a learner-local owner key as well as session ID.
- Never list notebook entries using `sessionId` alone.
- Add an explicit **Shared device / Switch learner** action.
- Rotate/clear the HttpOnly participant cookie through a server endpoint; do not make the credential readable by JavaScript.
- A new learner on the same browser must receive a new participant identity and an empty notebook view.
- Preserve previous local notes for their original owner unless explicitly deleted/exported.
- Add tests proving learner B cannot read learner A's notes or inherit learner A's question/control identity after an explicit switch.

Do not add server-side notebook synchronization.

---

## SR2-02 — Internal canonical folder names are exposed to classroom learners

**Severity: Medium privacy**  
**Disposition: reportable; fix before pilot**

### Evidence

Classroom session creation walks the administrator folder hierarchy and stores raw `Folder.name` values in the session slide snapshot. The shared classroom slide serializer includes `folderPath`, and the learner state uses that serializer.

The existing Viewer privacy contract requires explicit de-identification review before folder/collection names and teaching metadata are exposed through public sharing. Individual slide publication does not normally expose the canonical internal folder hierarchy.

PR #95 adds private admin `folderId` to improve teacher folder selection. That admin-only addition does not create a new learner leak, but it also does not remove the already merged learner `folderPath` projection.

### Attack path

1. A de-identified published slide is kept inside an internal folder whose name contains internal course, research, diagnostic, accession, patient, or operational wording.
2. The teacher starts Classroom with that slide.
3. Classroom snapshots the raw internal folder hierarchy without a learner-facing disclosure review.
4. Joined learners receive the folder-path names.

### Required revision

For the first pilot:

- remove `folderPath` from the learner projection;
- keep canonical folder IDs/paths private to admin/teacher surfaces only.

If learner grouping is later needed, use an explicit teacher-authored session-safe label rather than raw canonical folder names.

Add a regression test containing a deliberately sensitive synthetic folder name and prove it is absent from learner state.

---

## SR2-03 — Unbounded anonymous join waiters can exhaust the single-worker API

**Severity: Medium availability**  
**Disposition: reportable; harden before Classroom enablement**

### Evidence

`POST /api/v1/classroom/join` is intentionally unauthenticated. Join work is serialized with an `asyncio.Lock`, but request admission before that lock is not bounded.

The production topology intentionally uses one API worker. The serialization protects SQLite, but an attacker does not need a valid classroom code to create large numbers of pending join requests.

### Attack path

1. Remote client floods the join endpoint with concurrent requests.
2. Requests pass request-body validation and wait on the same join lock.
3. Pending request tasks and sockets accumulate even for invalid codes.
4. Legitimate learners compete with the backlog and classroom/API responsiveness degrades.

### Required revision

- Add a small bounded in-process join waiting room/counter before the serialized database mutation.
- Reject overflow promptly with `429` or `503` and `Retry-After`.
- Keep the normal serialized SQLite join mutation.
- Do not use strict per-IP limiting as the primary defense because many legitimate learners may share NAT/proxy egress.
- Extend the load harness with invalid-code flood traffic concurrent with legitimate joins.

No Redis or external rate-limit service is required.

---

## SR2-04 — One participant can open unbounded SSE streams

**Severity: Medium availability**  
**Disposition: reportable; fix before pilot**

### Evidence

A valid participant can repeatedly open the student SSE endpoint. Every subscription is added to the in-process subscriber set and receives classroom fan-out. Participant connection counts are tracked, but they are not used as an admission limit. There is also no explicit hard classroom SSE ceiling.

### Attack path

1. Attacker legitimately joins the displayed Classroom code.
2. The same participant opens many long-lived SSE streams.
3. Every stream consumes an upstream connection and receives fan-out events.
4. Connection/file-descriptor/fan-out work grows independently of the 300-participant seat limit.
5. One participant can consume capacity intended for the whole class.

### Required revision

- Enforce a per-participant SSE ceiling (recommended: 2, allowing one normal stream plus brief reconnect overlap).
- Enforce a hard global Classroom SSE ceiling with modest headroom above supported class size.
- Reject excess connections before adding the subscriber.
- Preserve reconnect jitter and HTTP full-state resynchronization.
- Add tests proving a third stream for one participant is rejected and the global ceiling cannot be exceeded.

---

## SR2-05 — One learner can starve the question queue or spam critical pin events

**Severity: Medium classroom availability/integrity**  
**Disposition: reportable; fix before pilot**

### Evidence

Questions have a session-wide pending cap of 200 and a participant receipt cap of 500, but no small per-participant pending cap and no time-based creation throttle. One participant can therefore occupy the entire pending-question capacity.

Pin memory is bounded to one pin per participant, but every accepted pin set emits a critical teacher event. Alternating set/clear requests can create repeated critical SSE traffic without a participant pin rate limit.

### Attack path A — question starvation

1. One joined learner scripts question submissions with unique idempotency keys.
2. That learner creates all 200 pending questions.
3. Other learners cannot submit questions until the teacher removes items.

### Attack path B — pin-event spam

1. One joined learner repeatedly sets and clears a pin.
2. Every accepted mutation produces teacher-side critical event work and API/database activity.
3. Classroom responsiveness is degraded by one participant even though pin memory itself stays bounded.

### Required revision

- Limit pending questions to **3 per participant**.
- Add a per-participant new-question interval (recommended baseline: one new question per 10 seconds; idempotent retries do not consume the interval).
- Keep the existing 200-session cap as a secondary safety bound.
- Rate-limit accepted pin mutation per participant (recommended 2–5 updates/second; the normal UI produces far less).
- Keep the committed question pin discrete; coalesce only transient movement if movement is introduced later.
- Add abuse tests proving one learner cannot prevent another learner from submitting a question.

---

# Hardening requirements retained from the earlier plan

## HR2-01 — Match production presenter frequency to the tested profile

The retained 300-participant local evidence used presenter movement around **2 Hz**. The client latest-sender implementation can emit much more frequently and the student presenter server limit is substantially higher than the tested profile.

For the first pilot use:

- teacher viewport: 2 Hz normal, 4 Hz hard maximum;
- learner presenter viewport: 2 Hz normal, 4 Hz hard maximum;
- remote teacher pointer: 5–10 Hz maximum;
- local pointer remains local-rendered at device refresh rate;
- final settled viewport is sent immediately.

Re-run the exact enabled-release capacity gate using the actual configured production cadence.

Do not increase cadence until like-for-like evidence demonstrates spare headroom.

---

## HR2-02 — Published Classroom tiles are intentionally not session-revocable

Merged Classroom uses already-published `static_dzi` slides and returns direct versioned `/tiles/...` paths. Caddy serves published derivatives without a Classroom authorization check on every tile.

This is **not classified as a vulnerability in this revision** because Classroom currently requires an explicitly published/de-identified slide before session creation. A learner who receives the direct tile URL may continue requesting that published version after the Classroom ends while the publication remains active.

For the low-resource first pilot:

- preserve this behavior only for slides that already passed publication/de-identification review;
- document that Classroom join is not a revocable tile-access boundary;
- do not claim session-scoped confidentiality for these published slide derivatives.

If private/session-expiring tile access becomes a requirement, design a static capability/alias architecture separately. Do not route every tile through FastAPI merely for revocation.

---

## HR2-03 — Keep dynamic OME outside the live Classroom path

The latest Forge release prefers direct OME delivery for normal Viewer storage efficiency. Classroom intentionally requires `static_dzi` for live sessions.

Preserve the existing product plan:

- add a later Forge **Prepare for Classroom** profile that generates and validates static DZI before class;
- do not first-render dynamic OME during a live session;
- keep conversion and heavy image processing out of the classroom critical path.

---

# Current repository state and release notes

The original PR #93 merge blocker has been resolved:

- PR #93 merged on 2026-08-13;
- CI run for merged main completed successfully;
- Security run for merged main completed successfully;
- production deployment for the merged commit completed successfully.

Therefore this V2 revision must **not** rewrite PR #93 history or reopen its old CI work. It should be implemented as a normal additive hardening change from current `main`.

Open PR #95 is compatible with this revision as long as its new `folderId` remains admin-only and the learner-facing raw `folderPath` is removed by SR2-02.

---

# Preserved original Classroom plan

Unless explicitly modified above, keep the merged design unchanged:

- Classroom feature-gated;
- one active session;
- anonymous generated learner aliases;
- static DZI served by Caddy;
- no Redis;
- no WebSocket service;
- no additional background worker;
- no server screenshot generation;
- screenshots and private notes in IndexedDB;
- learner private drawing local-only;
- teacher Guide/Follow;
- exact pinpoint questions;
- temporary learner presenter control;
- transient teacher pointer and teaching marks;
- sparse SQLite presenter checkpoints;
- singleton in-process hub;
- deterministic reconnect jitter and HTTP resynchronization;
- no AI, video, chat, or heavy analytics in Classroom;
- no heavy live image processing.

Also preserve the previously agreed future priorities:

- separate local **My Notebook** study screen;
- browse/edit/delete/reopen/export/import local notes;
- granular pointer/field/slide control later;
- combine pinpoint question + optional control request later;
- temporary Focus Class later;
- lightweight session title/objectives/reordering later;
- full LMS, high-stakes assessment, AI tutor, video/chat, and heavy analytics remain deferred.

---

# Security Revision V2 implementation order

1. Fix shared-browser learner/notebook isolation (SR2-01).
2. Remove raw folder paths from learner state (SR2-02).
3. Bound anonymous join admission (SR2-03).
4. Bound participant/global SSE connections (SR2-04).
5. Add per-participant question and pin abuse controls (SR2-05).
6. Lower presenter/pointer cadence to the first-pilot certified profile (HR2-01).
7. Add focused abuse/privacy regression tests.
8. Re-run classroom frontend/backend/browser tests.
9. Re-run 300-participant exact-stack capacity with deliberate abuse traffic.
10. Run complete Viewer CI and Security workflows.
11. Keep the Classroom feature flag disabled until this hardening and the exact enabled-release capacity gate are reviewed.

---

# Security acceptance gates

All must pass before first real Classroom pilot:

- a second learner on a shared browser cannot inherit the first learner's identity or notebook;
- learner state contains no raw internal canonical folder path;
- invalid join floods are bounded and legitimate joins remain responsive;
- one participant cannot exceed the per-participant SSE ceiling;
- total Classroom SSE connections cannot exceed the configured hard ceiling;
- one participant cannot consume all pending question capacity;
- rapid pin mutation is bounded without breaking normal exact-pin questions;
- stale/revoked presenter leases still fail closed;
- screenshots and notebook images remain local-only;
- no Redis/WebSocket/background service is added;
- the exact production presenter cadence is the cadence used by the load test;
- 300-participant convergence/reconnect/tile/control/question gates pass with abuse traffic;
- API and Caddy have no OOM or restart event;
- complete CI is green;
- Security workflow is green;
- Classroom enablement remains a separate explicit production decision.

---

## Forge security scope result

The current merged Forge local web UI remains loopback-bound, uses high-entropy local browser credentials, and keeps Viewer delivery outbound/private. No new Forge-side security blocker was identified that requires changing the Classroom security plan.

Existing Forge redistribution/licensing, signing, and installer-release decisions remain separate governance work and are unchanged by this V2 security revision.
