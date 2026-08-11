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

- One active session, at most 300 recent participants and 200 pending questions.
- At most 50 slides per session and 100 local notebook entries per browser session.
- Static DZI descriptors and tiles remain Caddy-served; the API never proxies screenshot bytes.
- Incremental SSE events are limited to 4 KiB UTF-8. Each subscriber has a bounded
  32-event discrete queue plus one replaceable latest-presenter slot.
- Presenter movement is client-throttled to four updates per second and server-limited to five.
- Presenter movement is published from memory immediately. The latest viewport is checkpointed
  to SQLite at most once per two seconds per classroom; slide changes persist immediately.
- Presenter sequences are reserved in blocks of 1,024 so an abrupt restart cannot reuse a
  sequence even when the latest viewport checkpoint has not yet run.
- Live pins and control requests are bounded to one in-memory record per participant and are
  discarded with the session; they do not create new SQLite history.
- Critical queue overflow closes the slow stream, forcing bounded HTTP resynchronization.
- The teacher state endpoint is naturally bounded by the participant and question limits.

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
SHA-256 hash. The generated alias is public; an optional normalized display name is visible
only to the teacher and is never authorization or uniqueness data.

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

Student pen, highlight, erase, undo, and clear operations run entirely in the browser. The
drawing canvas is composited into the bounded tissue capture only when the student saves a
note; neither drawing vectors nor the resulting image are sent to a classroom API. The saved
entry also records the normalized slide field and zoom so the private note retains its context.

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

1. Back up the SQLite database and apply Alembic revision `20260811_0017` while the feature
   remains disabled.
2. Verify one API service, one Uvicorn worker, local SQLite/WAL, Caddy SSE flushing, static
   tile delivery, and readiness.
3. Run the exact-release certification before considering activation.
4. Activation, if separately authorized, is only `PATHLAB_CLASSROOM_ENABLED=true` with the
   singleton declaration already true.
5. Roll back by disabling the flag first. The migration downgrade drops only classroom
   tables; export/backup any required classroom rows before downgrade. Local student notes
   are browser-owned and are not part of server rollback.
