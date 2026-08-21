# PathLab Viewer Free-Tier 1,200-Seat Stability Implementation Plan

## Context

Implement the approved design in `docs/superpowers/specs/2026-08-14-pathlab-free-classroom-design.md` from exact `origin/main` SHA `16cc3b84f6a17564bf2c8c544d7ca0bb32be9e0c`. Preserve the dirty root checkout. Capacity and production claims are fail-closed.

## Global Constraints

- Permanent cost is $0: existing OCI A1 2 OCPU/12 GB and existing 200 GB storage only.
- One active static-DZI Classroom; one Classroom Uvicorn worker and singleton in-memory hub.
- Production stress only inside an explicitly entered, environment-approved three-hour ICT window (normally 02:00–05:00) after backup/restore, exact-SHA CI/security, no-real-room, rollback, egress, and cost gates.
- Configured capacity is 1..2000; final production ceiling follows strict evidence: 1500, 1200, or rollback to 300/NOT CERTIFIED.
- Never claim certification from local tests, protocol clients as browsers, historical evidence, a partial stage, or a different SHA.
- TDD for behavior changes; aggregate-only evidence; masked credentials; trap-based restoration and cleanup.

## Task 1: Design artifact and evidence-pipeline repair

- Clone the retained System Design DOCX template into `docs/architecture/PATHLAB_FREE_CLASSROOM_SYSTEM_DESIGN.docx` and fill it with the approved design, operations, security, alternatives, rollout, and evidence boundaries.
- Preserve template styles/page setup and run structural audits. Render every page with the provided document runtime; if LibreOffice remains unavailable, record the missing visual-render gate without substituting a different renderer.
- Add failing load-contract tests for the exact five-service topology and executable observer path.
- Fix observer/workflow agreement for `api`, `classroom`, `caddy`, `tile-service`, `tusd`, and `worker` as each environment requires, and eliminate direct execution dependence when file mode cannot be preserved.
- Require exact deployed SHA and current browser CI before capacity certification.
- Add evidence schema v2 and tests for all fields from the design, generator/shard validity, abort/recovery/cleanup, aggregate-only output, credential masking, egress/cost, and fail-closed cleanup.

## Task 2: Runtime role isolation and bounded SQLite access

- Add failing backend/config/Compose/Caddy tests for `PATHLAB_SERVICE_ROLE=general|classroom|all`, production rejection of `all`, and `PATHLAB_CLASSROOM_SERVICE_URL=http://classroom:8001`.
- Implement a dedicated `classroom` container from the existing image with one Uvicorn worker, 1 CPU, and 1 GiB. Keep general API at 0.5 CPU/512 MiB.
- General alone runs migrations and reconciliation and uses pool `5/0/1s`; Classroom uses pool `4/0/1s` and skips general startup jobs. Preserve combined development role.
- Route Classroom HTTP/SSE paths to Classroom before the generic API route; retain direct Caddy static DZI.
- Replace per-readiness schema introspection with startup validation plus cached lightweight readiness.
- Return `503 CLASSROOM_BUSY` and `Retry-After` for bounded Classroom saturation.

## Task 3: Classroom backend scaling

- Add failing tests for capacity bounds 1..2000, atomic admission and `409 CLASSROOM_FULL`, bounded HMAC aliases/collisions, no presence database writes, single-stream replacement, teacher-only one-second `roster-changed` coalescing, queue size 512, and event-loop responsiveness.
- Add teacher-only keyset roster pagination/search with `after`, `limit<=100`, and `q`; return `items`, `total`, `nextCursor`, `rosterVersion`.
- Add `participantCount` and `rosterVersion` to teacher state while retaining embedded participants.
- Keep presenter/pointer latest-only and critical discrete events lossless within the bounded queue.
- Add bounded current/next slide descriptor/poster/common-tile prewarm without pyramid scans.

## Task 4: Classroom frontend scaling and full-feature behavior

- Add failing frontend tests for one initial student snapshot with `hubEpoch/stateVersion`, gap resync, deterministic 0.5–10 second reconnect spread with capped exponential backoff, roster reconciliation at most once per second, pagination/search, visible-row rendering, tile concurrency 2..4, and deterministic 0–250 ms guided slide jitter.
- Implement teacher roster debounce, pagination/search, and visible-row rendering without regressing controls, accessibility, responsive layouts, invites, phases, export, or reconnect UX.
- Preserve notebooks/screenshots/drawings/pins/questions/control leases/pointer/teaching strokes and offline recovery.
- Keep conversion/dynamic rendering low priority but functional during Classroom load.

## Task 5: Component watchdog and deployment safety

- Add failing unit/contract tests for a 15-second systemd timer, three-failure component-local restart, diagnostics capture, and three-restarts-per-ten-minute anti-flap stop.
- Implement/install/rollback the watchdog through existing deploy scripts. Probe component-local live/readiness and restart only `api`, `classroom`, or `tile-service`.
- Add deployment preflight/postflight guards for exact SHA, current CI/security, backup plus restore drill, no active real Classroom, rollback release, synthetic fixtures, annotations disabled, projected egress below 9 TB, OCI cost SGD 0, all containers/endpoints, cleanup, and zero Bastion sessions.
- Temporarily set capacity 2000 only inside a trap that restores the prior configuration and applies the evidence-derived final ceiling.

## Task 6: Distributed load, browser sentinels, and certification workflow

- Add failing tests for six synchronized public Linux shards, future start epoch, per-shard achieved-user/timing/generator gates, and rejection of stalled or saturated shards.
- Expand protocol scenarios to 80% teacher-follow and 20% independent pan/zoom, all Classroom interactions, realistic descriptor/poster/common/random tiles, and reconnect/fault recovery.
- Add functional sentinels for a synthetic 330 MB upload/conversion, annotation save/reload/export, library/share, dynamic viewer, and Desktop pairing/ingest with cleanup.
- Add Playwright coverage on Chromium, Firefox, WebKit, and mobile Chromium for the specified production journeys and browser performance/error gates.
- Implement staged 2/100 smoke, 300/600/900 boundaries, 1200x60m strict certification, 1500x10m headroom, guarded 1750/2000x5m stress, and recovery to 1200 with all strict and early-stop criteria from the design.

## Task 7: Integration verification, review, and guarded release

- Run focused suites after each task, then complete backend, frontend, load-contract, Ruff, mypy, ESLint, TypeScript, production build, Compose, migration-head, security, CodeQL, and repository-safety verification.
- Run the full browser matrix and local/container smoke without upgrading their result into production capacity evidence.
- Complete task reviews and one broad whole-branch review; fix load-bearing findings.
- Push a reviewable branch and require current protected checks. Merge/deploy only when exact-SHA and rollback gates pass.
- In the approved window, run guarded production stages and publish the exact evidence outcome. Apply 1500, 1200, or 300/NOT CERTIFIED exactly as dictated by strict evidence.
