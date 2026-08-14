# Lightweight Classroom implementation

## Scope and release state

This implementation is deliberately limited to the active-learning loop:

- the teacher starts one session from complete published static DZI slides;
- students join under generated non-identifying aliases;
- students can follow the teacher, share one live pin, ask a bounded question, request control, and receive a short control lease;
- screenshots, private drawings, saved field coordinates, and notes remain in the student's
  IndexedDB. The responsive self-contained notebook can be shared as a file or printed/saved
  as PDF through the device's native controls.

`PATHLAB_CLASSROOM_ENABLED=false` remains the default. No classroom route is registered
and the lazy classroom page bundles are not requested during ordinary disabled-mode use.
This branch does not authorize a merge, deployment, or production activation.

## Resource boundaries

- One active session, a validated `PATHLAB_CLASSROOM_MAX_PARTICIPANTS=1..2000`
  ceiling (default 300 until capacity evidence authorizes a change), and 200 pending questions.
- At most 50 slides per session and 100 local notebook entries per browser session.
- Static DZI descriptors and tiles remain Caddy-served; the API never proxies screenshot bytes.
- Incremental SSE events are limited to 4 KiB UTF-8. Each subscriber has a bounded
  512-event discrete queue plus replaceable latest-presenter, pointer, and roster slots.
  Critical queue overflow closes the stream so the client resynchronizes instead of silently
  losing a discrete event. Each participant has one live stream; a replacement closes the stale
  stream without changing the replacement's presence.
- Presenter movement uses a bounded latest-only sender: one request may be in flight and one
  newer viewport may replace the pending value. Updates are sent on the leading edge and then
  at a maximum 20 Hz cadence; the server admits at most 25 student-controller updates per second.
  Followers project deltas directly into OpenSeadragon without a React render, and the hub
  serializes each SSE event once. This keeps movement responsive without queue growth.
- Teacher guide broadcasting is opt-in and defaults off. Ordinary teacher navigation therefore
  creates no presenter requests until the teacher explicitly enables Guide. Presenter and pointer
  SSE gaps are expected when latest-only values are coalesced and do not trigger a full-state
  viewport reapplication; critical-event gaps still fail into bounded HTTP resynchronization.
- Presenter magnification is transmitted in OpenSeadragon's normalized viewport zoom space so the
  teacher and student retain the same tissue field across different screen sizes. Older image-zoom
  snapshots are panned without replaying their container-dependent magnification; the next current
  presenter event restores the correct zoom. A remote pan at unchanged magnification never calls
  `zoomTo`, preventing repeated maximum-zoom animation.
- Presenter movement is published from memory immediately. The latest viewport is checkpointed
  to SQLite at most once per two seconds per classroom; slide changes persist immediately.
- Presenter sequences are reserved in blocks of 1,024 so an abrupt restart cannot reuse a
  sequence even when the latest viewport checkpoint has not yet run.
- Live pins and control requests are bounded to one in-memory record per participant and are
  discarded with the session; they do not create new SQLite history.
- The teacher pointer is one replaceable in-memory value. Completed teacher teaching strokes
  are bounded to 40 records with at most 64 points each and are discarded on session end or
  process restart; neither feature writes database history.
- Critical queue overflow closes the slow stream, forcing bounded HTTP resynchronization.
- Presence changes are in memory, perform no database write, and emit a teacher-only
  `roster-changed` signal at most once per second. Teacher state retains its embedded bounded
  participant list and adds `participantCount`/`rosterVersion`; the roster endpoint uses
  searchable alias-keyset pages of at most 100 rows.
- A single latest-pending off-loop worker prewarms only the current and next slide descriptor,
  poster, and mathematically derived center tiles. It reads bounded prefixes and never scans a
  DZI pyramid.

## Singleton topology

The hub is intentionally in process. Production configuration must explicitly declare
`PATHLAB_CLASSROOM_SINGLETON=true`, and Compose starts Uvicorn with one worker. A lifetime
exclusive lock at `DATA_ROOT/runtime/classroom-hub.lock` makes readiness fail closed if a
second API process starts. Classroom requests reaching a non-owning process return 503.
Sticky sessions are not used as a substitute.

## Reconnection contract

1. Open the authenticated SSE endpoint.
2. Receive `stream-ready` with `hubEpoch` and `stateVersion`.
3. Fetch the appropriate full-state HTTP endpoint.
4. Treat HTTP state as authoritative and use later SSE events as refresh triggers.

Students explicitly close a failed native `EventSource` and recreate it after deterministic,
participant-seeded jitter with bounded backoff. A stable stream resets the backoff. This avoids
a synchronized reconnect herd while retaining ordinary SSE and HTTP resynchronization.

Participant, question, control, presenter, and session-ended events are incremental. SSE
generators open short database scopes only for authentication/state and never retain a
transaction while streaming. Caddy uses `flush_interval -1`; heartbeats are SSE comments.

## Identity, questions, and control

The signed participant cookie carries a high-entropy opaque token. SQLite stores only its
SHA-256 hash. The public alias is HMAC-derived from that token with bounded indexed collision
retries; an optional normalized display name is visible only to the teacher and is never
authorization or uniqueness data.

Question content is deleted immediately when answered. A content-free receipt containing
only session, participant, hashed idempotency key, original ID, and time prevents a delayed
retry from recreating the deleted question. Receipts cascade when the session ends.

Every control grant increments `controlEpoch` and creates a random `leaseId`. Student
presenter writes atomically validate participant, lease, server-side expiry, active session,
rate limit, and snapshotted slide. Stale writes return 409. Opening a question revokes student
control in the same transaction before moving the presenter field.

## Storage and privacy

Notebook writes are transactional IndexedDB records keyed by session UUID and immutable
slide ID. Image encoding is bounded to 1600 x 1200 and 2 MiB, using WebP with JPEG fallback.
If capture fails, a non-empty text note is still saved. The browser storage estimate and
persistence request are best effort; the UI warns that data is local browser data.

Student pen, highlight, erase, undo, clear, color, size, and compact stroke history operations
run entirely in the browser. Entering drawing mode disables slide navigation and pauses remote
presenter application, freezing the field until the student finishes. The drawing canvas is
composited into the bounded tissue capture only when the student saves a note; neither drawing
vectors nor the resulting image are sent to a classroom API. The saved entry also records the
normalized slide field and zoom so the private note retains its context.

Teacher teaching marks are deliberately simpler: pen and highlight with color and size,
per-mark removal, and clear-all. A laser, green arrow, or red arrow can be shared as a transient
coalesced pointer. Only a completed bounded stroke is broadcast; raw pointer samples and
student-private drawings never leave their originating browser.

HTML export escapes all user text, embeds images as data URLs, includes a restrictive CSP,
and has no external scripts or network dependency. Devices supporting Web Share can send the
notebook to Files or AirDrop; the print path provides the native save-as-PDF workflow. Explicit
deletion is available for shared devices. Classroom APIs, pages, and SSE use
no-store/no-referrer behavior; DZI cache headers remain separate and versioned.

## API outline

Teacher endpoints live below `/api/v1/admin/classroom`; participant endpoints live below
`/api/v1/classroom`. Important operations are session create/end, bounded full state, SSE,
join/reconnect, live pin update/clear, question create/open/delete, control request/grant/revoke,
and presenter updates.
Operational metrics expose only bounded counters, not student behavior history.

## Local verification and certification

Use `tests/load/classroom_sse.py` for protocol-level clients. It refuses non-local targets and
requires an explicitly created ephemeral classroom. It continuously consumes SSE while
publishing presenter movement, requesting a real tile, exercising questions and control, and
creating bounded churn. Browser rendering and screenshot checks remain separate from protocol
scale. The 300-user protected certification is a later explicit run.

Production remains **NOT CERTIFIED** until the exact release SHA passes the protected
baseline-versus-candidate capacity, restart, churn, cold-tile, question, control, and soak
gates. Never load-test production.

## Deployment and rollback

1. Back up the SQLite database and apply Alembic revision `20260813_0019` while the feature
   remains disabled.
2. Verify one API service, one Uvicorn worker, local SQLite/WAL, Caddy SSE flushing, static
   tile delivery, and readiness.
3. Run the exact-release certification before considering activation.
4. Activation, if separately authorized, is only `PATHLAB_CLASSROOM_ENABLED=true` with the
   singleton declaration already true.
5. Roll back by disabling the flag first. The migration downgrade drops only classroom
   tables; export/backup any required classroom rows before downgrade. Local student notes
   are browser-owned and are not part of server rollback.
