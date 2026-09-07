# Teacher Studio Assessment Contract v2 — Implementation Plan

This plan traces the approved contract to seven coherent commits. Every commit must pass
its focused tests before the next begins; final gates run against the complete branch.

## Commit 1 — Contract and persistence

- Add Python and TypeScript v1/v2 discriminated document contracts and shared fixtures.
- Add contract bounds and deterministic SHA-256 ordering helpers.
- Add Alembic `20260828_0035` plus model fields for immutable manual grading.
- Add v1 compatibility, v2 parsing/limits, rating, randomization, and migration tests.

Gate: Ruff, mypy for touched modules, contract/model tests, SQLite upgrade/downgrade,
single Alembic head, TypeScript build.

## Commit 2 — Draft migration, preflight, and import

- Add focused `assessment_v2_validation`, `assessment_v2_branching`, and migration modules.
- Add revision-checked clone migration and authoritative preflight routes.
- Make v2 publish call the same validator while preserving v1 compiler behavior.
- Extend import to mint section/item/option IDs and remap only complete section routes.

Gate: migration/ownership/conflict/preflight/import tests and public repository check.

## Commit 3 — Section authoring and question essentials

- Replace the legacy flat canvas and delete commented builder/obsolete CSS.
- Add section CRUD/undo, collapse, pointer and keyboard reorder, stable numbering,
  navigator preview/issues/readiness, and icon expand/collapse.
- Add complete stable-ID choice editing, dropdown, rating, validation, help, feedback,
  thumbnail media, education metadata, routing, blueprint, field issue focus, templates,
  paste-to-create, library import, and lazy QR.

Gate: focused authoring unit tests, accessibility checks, lint, TypeScript, production build.

## Commit 4 — Shared learner runtime

- Share one renderer across preview/practice/formative/quiz and implement device widths.
- Implement stable seed reset, contiguous-run ordering, section-exit routing, unreachable
  response/outbox cleanup, skipped-required behavior, and attempt seed persistence.
- Keep one section OpenSeadragon instance, replace sources, restore viewport, and implement
  accessible navigation lock.
- Snapshot/release sanitized annotation overlays and direct thumbnail assets.

Gate: ordering/routing fixtures in both languages, renderer/outbox/viewer tests, learner API
journeys, offline/reconnect Playwright segment, and no per-question API navigation.

## Commit 5 — Publication and collection controls

- Extend v2 publish for multi-class atomic administrations and one-time access codes.
- Add collection controls, response limits, expiry behavior, manual acceptance, and release
  downgrade when manual grading is required.
- Preserve CSRF, idempotency, throttle, session, archival, ownership, and default-off gates.

Gate: multi-class rollback, anonymous/rostered/quiz, limit/expiry/archive/idempotency,
cross-organization, and v1 compatibility API tests.

## Commit 6 — Responses, grading, review, analytics, and export

- Make Responses the canonical Summary/Questions/Individuals/Needs grading product and
  redirect the old report route.
- Add atomic grouped/individual immutable grading, partial points, feedback, save-next,
  progress, conflict reload, and local comment retention.
- Build release-policy learner review field by field.
- Add distributions, reachable denominators, section drop-off, real diagnostic labels, and
  streaming CSV/bounded XLSX fields with formula protection.
- Poll count-only monitor every 15 seconds only while visible.

Gate: grading/conflict/privacy/release/analytics/export tests plus reporting UI tests.

## Commit 7 — Demo, E2E, budgets, and documentation

- Add five versioned templates and a non-sensitive v2 local demo covering sections,
  branching, dropdown, all rating styles, validation, manual grading, release, and a
  privacy-passed slide.
- Add full teacher → learner offline/reconnect → grade/release → review Playwright journey,
  isolation suites, learner bundle budget, batching/direct-delivery/bounded-report checks,
  and v2 500-seat capacity fixture without a certification claim.
- Update public documentation and evidence report.

Final gate: frozen install; frontend lint/test/build; Ruff/mypy; relevant and full backend;
PostgreSQL migrations; capability/public-repository checks; Compose/Caddy; available ARM64;
Playwright; diff check; one Alembic head; default-off checks. Launch strict port 4175 and
verify the editable demo at desktop/tablet/mobile widths.

## Traceability matrix

| Contract area | Primary modules | Primary evidence |
|---|---|---|
| Schema and limits | `assessment_contract_v2.py`, `assessment/types.ts` | contract parity fixtures |
| Branching/order | `assessment_branching.py`, learner runtime | SHA/routing fixtures |
| Validation | `assessment_validation.py` | preflight/publish equivalence |
| Review/privacy | `assessment_review.py` | forbidden-field serialization tests |
| Persistence | migration `20260828_0035`, models | SQLite/PostgreSQL migration tests |
| Authoring | builder/canvas/editor components | authoring/accessibility tests |
| Learner | shared renderer, outbox, OSD section host | unit + Playwright reconnect |
| Grading/results | routes, Responses UI, exports | API/UI/conflict/export tests |
| Delivery boundary | capability flags, bundle script, Caddy | default-off/budget/direct asset tests |

## Stop conditions

Stop and report `PARTIAL` rather than weakening a frozen contract if v1 compatibility,
privacy stripping, atomic publication/grading, migration reversibility, default-off state,
or learner bundle isolation cannot be proven. Never merge, deploy, activate, or claim
capacity certification in this campaign.
