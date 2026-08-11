# Classroom certification hardening summary

## Scope

- Base SHA: `ec97febbb9706f4b1109ba8fa45c3f807b3ff510`
- Branch: `codex/classroom-certification-hardening`
- Feature default: disabled
- No push, pull request, merge, deployment, or activation
- The exact local one-worker candidate stack passed the 30-minute, 300-participant gate
- Production was not load tested

## Corrections completed

1. Presenter state is immediate in memory and checkpointed to SQLite at a bounded rate.
2. Reserved presenter sequence blocks prevent sequence reuse after abrupt restart.
3. SSE keeps one replaceable presenter event while critical events use a bounded reliable queue.
4. Student SSE reconnects use deterministic participant jitter and full HTTP resynchronization.
5. Join mutations queue as coroutines before the one short serialized SQLite write, preventing
   a 300-join burst from exhausting the FastAPI thread pool.
6. A successful browser join immediately hydrates student state, slide selection, and notebook.
7. Final capacity readback uses bounded retries to tolerate a transient closing connection.
8. The locked Pillow entry includes official x86-64 and ARM64 CPython 3.12 wheel hashes.

## Exact-stack capacity result

The local stack used one API worker, Caddy static DZI delivery, a generated non-PHI
7,557 x 7,360 static DZI, 300 protocol participants, 2 Hz presenter movement, question/control
activity, reconnect churn, and 61 independent resource samples.

- Harness exit: 0
- Duration: 1,805.843 seconds
- Final convergence: 300/300
- Reconnect success: 100% (30/30 deliberate reconnects)
- Participant/task/tile errors: 0
- Stale presenter incidents: 0
- Lost discrete events: 0
- Presenter p50/p95/p99: 78/875/1,078 ms
- Tile p50/p95/p99: 31/313/1,015 ms
- Question p95: 1,547 ms
- Control p95: 375 ms
- API RSS min/max: 115.6/119.3 MiB
- Caddy RSS min/max: 31.21/108.5 MiB
- API/Caddy restart count: 0/0
- API/Caddy OOM killed: false/false
- SQLite presenter checkpoint rate: 0.4889 per second
- One slow subscriber was safely disconnected after one bounded critical-queue overflow;
  final HTTP resynchronization preserved convergence and all discrete events.

Raw evidence is in `capacity-300-30m-rerun.json` and `resource-samples-rerun.csv`.

## Exact-stack restart result

The API container was restarted with 20 active SSE participants. The protected harness observed
two hub epochs, 20/20 final convergence, 100% reconnect success, zero stale presenter incidents,
zero task/tile errors, and zero lost discrete events. Reconnect spread was 4.625 seconds;
presenter p95 was 47 ms and tile p95 was 63 ms. Raw evidence is in `restart-gate.json`.

## Regression evidence

- Backend: 456 passed, 4 skipped.
- Ruff: passed.
- MyPy: passed for 38 source files.
- Frontend Vitest: 36 files, 234 tests passed.
- Frontend ESLint: passed.
- TypeScript and Vite production build: passed.
- Classroom screenshot spike: passed in Chromium, Firefox, WebKit, and mobile Chromium.
- Full Playwright matrix: 117 passed, 28 failed, 7 skipped. The failures are outside classroom
  and are recorded rather than hidden; repository-wide browser certification is not green.

`origin/main` has no classroom endpoints, so a classroom protocol capacity delta cannot be
computed. Baseline architecture, test, and bundle evidence remains available; no endpoint result
was fabricated.

## Runtime boundaries retained

- One active session, 300 recent participants, 200 pending questions, and 50 slides maximum.
- Static DZI descriptors/tiles stay Caddy-served; screenshots and notes stay in IndexedDB.
- Incremental SSE events are at most 4 KiB UTF-8.
- Each subscriber has 32 bounded critical slots plus one replaceable presenter slot.
- Presenter publication is client-throttled and server-rate-limited.
- Critical overflow closes the stream and requires full-state resynchronization.
- The in-process hub requires one declared API worker and a lifetime singleton lock.
- Generated aliases are canonical public identities; optional names never authorize anything.
- Question content deletion retains only a bounded, content-free idempotency receipt.
- Control writes validate lease ID, owner, expiry, session, rate, and immutable slide snapshot.
- Notebook images are bounded to 1,600 x 1,200 and 2 MiB with text preserved on image failure.

## Readiness boundary

The local classroom candidate capacity and classroom-specific browser gates pass. Production
remains disabled, unmerged, undeployed, and not load tested. The complete repository Playwright
matrix is not fully green, so this report does not label the whole application production-ready.

## Deployment and rollback

1. Keep `PATHLAB_CLASSROOM_ENABLED=false` while backing up SQLite and applying migration
   `20260811_0016`.
2. Verify one API service, one Uvicorn worker, local SQLite/WAL, Caddy SSE flushing, static
   tile delivery, and singleton readiness.
3. Resolve or formally baseline the unrelated full-Playwright failures before release approval.
4. Activation requires separate authorization; it is only the feature flag after all gates pass.
5. Roll back by disabling the flag first. The downgrade drops classroom tables only; export any
   required classroom rows first. Browser-owned student notes are not server rollback data.
