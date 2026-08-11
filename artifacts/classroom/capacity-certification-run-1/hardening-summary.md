# Classroom certification hardening summary

## Scope

- Base candidate: `b1d04512ffc01a7624acdc604823cbeae8d4c7fc`
- Branch: `codex/classroom-certification-hardening`
- Feature default: disabled
- No push, pull request, merge, deployment, or activation
- The 30-minute capacity certification was not run
- All temporary containers, volumes, images, and copied DZI fixture data were removed afterward

## Corrections

1. Presenter viewport state is immediate in memory and checkpointed to SQLite no more than
   once per two seconds per classroom, with immediate persistence for slide changes.
2. Presenter sequences are reserved in 1,024-number blocks so abrupt restart cannot reuse an
   emitted sequence without coupling viewport persistence to movement frequency.
3. SSE subscribers retain one replaceable latest-presenter event while discrete control and
   question events remain in the bounded reliable queue.
4. Student SSE failures explicitly close native EventSource and reconnect using deterministic,
   participant-seeded bounded jitter.
5. The local-only protocol harness continuously consumes SSE while presenter, tile, question,
   control, convergence, and churn work execute concurrently.

## Focused evidence

- Backend classroom/load-contract tests: 24 passed before the sequence-reservation correction.
- Backend presenter, hub, classroom, and migration tests after reservation: 29 passed.
- Ruff: passed.
- MyPy: passed for 37 modules.
- Full backend and load-contract collection: 456 passed and 4 skipped.
- Frontend Vitest: 36 files and 234 tests passed.
- Frontend ESLint: passed.
- Current frontend production build: passed.

## Valid normal short smoke

This local smoke used 20 protocol participants, one real 7,557 x 7,360 PathLab static DZI,
Caddy SSE flushing/static tiles, one API worker, 2 Hz presenter movement, five questions,
control grant/revoke, and deliberate churn.

- Final convergence: 20/20
- Reconnect success: 100% for deliberate churn
- Participant/task/tile errors: 0
- Stale presenter incidents: 0
- Lost discrete control events: 0
- Presenter latency p50/p95/p99: 47/63/78 ms
- Tile latency p50/p95/p99: 15/16/32 ms
- API RSS observed mid-run: 121.22 MiB
- Caddy RSS observed mid-run: 18.1 MiB
- Presenter events: 88
- SQLite presenter checkpoints: 22
- Checkpoint rate: 0.489 per second

## Restart evidence boundary

An abrupt pre-reservation restart reproduced one presenter-sequence regression while all 10
participants eventually converged. The new reservation unit test proves that an emitted sequence
from a reserved block is not reused after an abrupt runtime replacement. Subsequent local process
replacement attempts showed zero regression and full final HTTP convergence, but did not produce
a trustworthy two-hub-epoch SSE sample because Windows process supervision/timing made the exact
stream replacement ambiguous.

Therefore the protected restart/reconnect capacity gate remains **NOT CERTIFIED** and must be
repeated through the exact container restart mechanism before the 30-minute certification.

## Independent build blocker

The exact backend Docker build stopped at hash verification because the downloaded Pillow 12.3.0
wheel SHA-256 did not match `deploy/backend-requirements.txt`. Hash checking was not weakened and
dependencies were not changed. The short smoke used the existing validated local Python runtime
with current branch source plus the freshly built current Caddy/frontend image.
