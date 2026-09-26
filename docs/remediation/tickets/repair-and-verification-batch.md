# Repair and verification batch

Parent: ../MAP.md
Labels: wayfinder:task
Status: in progress
Assignee: Codex

## Evidence-backed scope

Current-code reproductions cover upload commit rollback and renewal identity, folder trash/restore integrity, worker deletion and heartbeat failures, prepared-import cleanup after commit, JPEG restart tables, annotation bulk edits and desktop layer synchronization, Study admission races and expiry, spatial scoring, blocked browser storage, durable IndexedDB acknowledgment, serial notebook export, and transient Classroom pin admission.

Four journeys reuse existing components and routes: Library commands/QuickLook/client navigation, a persistent authenticated upload dock, Classroom stage/tray/anchored questions, and Study invitation/task/confidence controls. Publication and feedback policy remain authoritative.

## Validation so far

Focused backend and frontend regressions pass. Classroom/Study browser campaign passed 12 scenarios across Chromium, Firefox, WebKit and mobile Chromium; 72 synthetic screenshots retained in ignored var/remediation-evidence/classroom-study-matrix. Notebook persistence passed four engines, including 105 competing writes against the existing 100-record limit. Library/upload matrix passed twelve scenarios across the same four browser targets (eleven together, then one bounded WebKit retry), including real streamed TUS bytes and processing acknowledgment. Fresh frontend lint/build and backend mypy pass; scoped Ruff checks pass. Native loopback full-stack passed with synthetic OME/TUS/worker/tiles. These checks precede the remaining edits and require final exact-head verification.

The first broad backend and frontend runs overlapped repairs and are diagnostic receipts, not a pristine baseline. Do not label targeted checks, routed synthetic browser fixtures, or build success as production qualification.

## Remaining gates

Finish report reconciliation and independent regressions, fresh full suites, native full-stack, PostgreSQL, lint/type checks, inventories, protected required checks and review. No PR, merge, deployment or production verification is complete.

Local Docker daemon is unavailable; real PostgreSQL integration awaits required CI. Native full-stack passed using an ignored wrapper for pinned pnpm11.9.0. The broad backend diagnostic had six failures: three commit-bound inventory gates await regenerated receipts, the navigation query regression and existing-share trash regression were repaired and scoped checks pass, and the Windows capacity harness deadline still fails locally during setup. The existing resource deadline remains unchanged; required Linux CI must pass. The broad frontend run loaded older modules during edits; its four failures have passing focused regressions. Neither broad run is a final green suite.

Recent repairs also cover saved metadata/date/tag filters and manual cursor paging, post-trim identity/display-name validation, bounded legacy username streaming, deletion sync events, optional notebook failures, acknowledgment-only Student pins, drawing scope on guided slide changes, serialized invitation polling, and progress CSV download/404. Future sharing additions remain unavailable in the UI: only currently reviewed slides are published.
