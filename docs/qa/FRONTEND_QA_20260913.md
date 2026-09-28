# Frontend QA and repairs — September 2026

Status: sixteen reproduced repairs implemented. The 13 September campaigns,
26 September sort/keyboard checks, and 27 September follow-up passed their stated
assertions. This is not a certification of every control/state combination.
The ledger distinguishes backend journeys, mocked UI scenarios, skips, and
unmapped source candidates.

## Provenance and isolation

- The initial campaign used main `0e4ca78c971a2d64029864535b995c84462b350c`;
  the 27 September follow-up fetched and merged `272b28992d01fdbc64e33071c3e4412f3b309927`.
- Branch: `codex/frontend-qa-20260913`; original checkout and user files preserved.
- The 27 September browser and stress campaign ran from tested HEAD
  `f686bf43c1055911095f958f9e4eefca4830c86e` after the mobile menu fix
  `fa0d3283cf04f3396ac2a8146b683ac5232761e3`; run environment and bundle hashes
  are in `final-merged-stress/run-environment.json`. The later commits refresh
  generated supply-chain inventories and do not change application code.
- UI baseline: `apps/web/DESIGN.md` is `BASELINE_ONLY`; the [Architecture
  Precedence Register](../architecture/ARCHITECTURE_PRECEDENCE.md) and accepted
  ADRs control conflicts. Existing semantic tokens, typography, radii, and
  pathology-image treatment were retained.
- Local evidence: `CODEX_HOME/qa/frontend-20260913`.
- Native Windows isolated stack: generated loopback ports, SQLite, FastAPI,
  worker, tusd, Caddy, tile service, production frontend build, temporary data,
  generated synthetic administrator and synthetic OME-TIFF. Classroom,
  assessments, and annotation canary enabled locally. No real learners.
- A separate validation checkout prevented rebuilds from replacing the bundle
  being served to the ongoing load campaign.
- Live smoke used the already authenticated production tab. Observed bundle:
  `assets/index-CgLpWk-1.js`; deployed commit was not independently established.
  Production received no load campaign or record/credential changes.
- Playwright Chromium, Firefox, WebKit, and Pixel 5 Chromium emulation were used.
  Recorded engine versions: Chromium 151.0.7922.34, Firefox 153.0, WebKit 26.5.
  These are engine/emulation results, not physical iPhone/Android certification.
- Headroom was not available in the checked runtime paths; proxy routing was
  not established or changed.

## Confirmed defects and repairs

| ID | Severity | Reproduction and result | Repair and regression |
|---|---|---|---|
| FQA-1 | P2 | Open New folder, delay its POST, submit again with Enter: two POSTs were issued. | Synchronous in-flight guard and disabled dialog submits; real-backend delayed-response test verifies one durable folder. A separate injected 503 test verifies retry re-enables the form. |
| FQA-2 | P2 | Start an anonymous formative assessment backed by SQLite in an Asia/Bangkok browser: a new one-hour attempt displayed 0:00. SQLite restored a naive timestamp. | Normalize start and restored-session timestamps with `as_utc`; backend timezone assertions and Bangkok learner save/reload/submit journey. Production PostgreSQL impact was not reproduced. |
| FQA-3 | P2 | At 390px the mobile layout selector displayed “Gri”. Existing overflow checks passed despite clipped text. | Increase selector to 84px and remove the unused grid track for the hidden upload action. Test longest label fit and non-overlap across browser engines; before/after screenshots retained. |
| FQA-4 | P2 | Add a slide to a collection, reload All slides, open details: Collections displayed “—”. | Add membership ID/name data to the authenticated details endpoint and consume it in the panel. Backward-compatible optional frontend field; backend add/remove regression and real UI reload verification. |
| FQA-5 | P2 | Upload a file named OME-TIFF with an invalid signature: transfer finished but the library stayed uploading. | Persist FAILED/INVALID_TIFF_SIGNATURE, acknowledge duplicate tus notifications, retain the private source for managed cleanup, and show corrective guidance. Backend and real quota/corrupt-file/retry tests. |
| FQA-6 | P2 | Firefox's first Next-page click could be lost when deferred card layout moved the control. | Remove card content-visibility estimates; retain layout/paint containment. The 1,000-record real-backend journey verifies a single click changes the cursor/page. |
| FQA-7 | P2 | Axe found an aria-label on a generic brand div without a permitted role. | Expose the brand as a named image; both-theme WCAG A/AA audits pass on library, folder dialog, upload, and Teaching Studio. |
| FQA-8 | P1 | New assessments used the legacy schema while offering question types unsupported by that schema. | Create section-based v2 documents from both entry points; preserve legacy documents and direct rating authors to the existing upgrade action. All six types publish, save learner answers, submit, and reopen; manual grading/release/export/archive journey retained. |
| FQA-9 | P1 | WebKit viewer initialization raised a ReferenceError when OpenSeadragon checked an absent OffscreenCanvasRenderingContext2D constructor. | Small pnpm patch guards both optional constructor checks. The complete WebKit real-backend journey runs with an unexpected-page-exception assertion. |
| FQA-10 | P2 | Mobile assessment authoring hid the save indicator. | Wrap authoring metadata and retain readable save state; real checks cover all twelve requested widths and a short landscape screen. |
| FQA-11 | P2 | On short mobile screens the Classroom invitation Close action could be below an unscrollable dialog. | Bound the dialog to the viewport and allow vertical scrolling; preserve unrestricted print layout. Real mobile classroom journey reaches Close. |
| FQA-12 | P2 | A pending search URL update could overwrite a navigation transition, observed opening Storage in Firefox. | Compose URL updates from the latest parameters and avoid unnecessary debounce writes. Unit search/navigation regression and full Firefox storage journey pass. |
| FQA-13 | P2 | Small annotation viewports hid saved/unsaved status entirely. | Retain a readable status; compact Undo/Redo into accessible labeled icon controls. Real mobile geometry persistence and responsive browser regressions cover the repair. |
| FQA-14 | P2 | After Teaching Studio finishes loading, its active navigation link had 3.11:1 contrast against the light canvas at 13px. | Use the existing ink token for text while retaining the coral active underline. The audit now waits for the ready screen before testing both themes. |
| FQA-15 | P2 | On mobile, opening a library action menu and scrolling to an off-screen item closed the portal before the action could be reached. | Reposition the menu on scroll, constrain it to the viewport with its own scrolling, and prevent initial focus from scrolling the document. Mobile Chromium now opens, reaches, and activates the menu item. |

Infrastructure corrections: default browser discovery excludes the separately
configured fixture-dependent live canary; isolated Caddy now maps the assessment
service and assessment delivery directory; negative login-admission tests run
after authenticated workflows; responsive mocks explicitly answer facets/shares.
These are test-harness corrections, not claims of production outages.

## Evidence and scope

[Control/state ledger](FRONTEND_QA_20260913_COVERAGE.csv): 145 rows — 136 PASS,
6 PASS_MOCKED, 1 NOT_RUN, and 2 BLOCKED. A pass applies only to the row's stated action and
assertions. It does not extend to other states of that control. Separate generated
scenario and runtime-control ledgers retain engine results and controls actually
encountered or exercised. Static control candidates require reachability/state
mapping; an encountered control or a click alone is never counted as passed.

Final backend regressions: 116 passed, 1 platform skip (`final-backend.log`).
The complete frontend unit suite passed 374 tests in 65 files (`final-vitest.log`);
the later one-line active-link color correction was verified by four-engine Axe
checks and production builds. Full real-backend journeys: 72 passed across four
engine/device configurations, each with one opt-in stress skip:

| Engine/device | Full journey receipt | Passed / skipped |
|---|---|---|
| Chromium | `final-chromium/fullstack.json` | 18 / 1 |
| Firefox | `final-firefox/fullstack.json` | 18 / 1 |
| WebKit | `final-webkit-4/fullstack.json` | 18 / 1 |
| Pixel 5 Chromium emulation | `final-mobile-2/fullstack.json` | 18 / 1 |

The final ready-screen contrast correction also passed focused Chromium,
Firefox, and mobile Chromium reruns (`final-a11y-*/fullstack.json`); WebKit's
full receipt already includes that correction. These three repeat passes are
not three new unique workflows. All final receipts have zero retries and zero
unexpected failures. Earlier failed receipts remain local for reproduction.

The generated ledger contains 240 scenario rows: 228 passed and 12 skipped,
including focused repeat checks and the stress scenario. Runtime observations and
736 static source candidates are kept separate from scenario pass counts.
ESLint, Ruff on changed Python sources, TypeScript/Vite build, and whitespace
checks passed. No protected CI or deployment was run.

Focused follow-up on 26 September compared all six library sort orders against
the 1,000-record synthetic backend ordering and rendered card order, and swept
visible enabled Tab stops on Library and Teaching Studio. These checks passed
in Chromium, Firefox, and WebKit; mobile Chromium passed the sort journey and
skipped the hardware-keyboard traversal. Receipts are in
`final-sort-keyboard-v2-*/fullstack.json`.

The mocked matrix passed 145 scenarios with 7 intentional skips (152 total;
`final-mocked.json`, zero retries and zero unexpected failures).
After the mobile CSS correction, all 56 library browser scenarios passed again.
The four-engine text-fit check also passed. Responsive coverage includes 320,
360, 390, 600, 601, 768, 900, 901, 1250, 1251, 1440, and 1920px, plus existing
suite boundaries, short-screen cases, touch targets, focus restoration, long
names, themes, reduced motion, and theme-invariant viewer imagery.

Real isolated journeys cover creation and persistence of folders/collections/
saved views; duplicate submit and failed-create retry; search/layout/theme
persistence; all six library sorts; metadata and combined filters; move/share
rotation/revocation/trash/restore; bulk tags and collection membership; storage
actions; upload interruption/resume and real conversion; private preview,
annotation save/reload, publication and tile revocation; synthetic Classroom
teacher/student join/reload/end; Teaching Studio course/roster/class persistence;
assessment author/publish/answer/reload/submit/report; account validation and
password-change/sign-out/sign-in; large-library pagination, offline recovery,
and independent tab searches. See final receipt for actual pass/fail status.

Safe live checks included all 12 library widths, Teaching Studio layout at seven
widths, search/empty/clear, grid/list/table, filter/create/account/upload dialogs,
selection/clear, storage display, details/private preview, zoom/home, all three
loading modes, and four rotation presets. Restored `/admin`, Light, Grid,
expanded rail, empty search, no selection, default 1065×912 viewport. Final
captured warning/error console list was empty. No production mutation tests.
The open production tab was signed out during the 26 September follow-up; no
login or credential entry was attempted, so no further live checks were run.

## Earlier load campaign (before the 27 September follow-up)

Real isolated backend, metadata-only libraries of 0/1/100/1,000 records; the
records intentionally have no imaging content. Browser sessions perform paced
search/render/filter actions. Four five-minute tiers (1/5/10/20 sessions), then
a 30-minute 20-session soak. This is frontend/library responsiveness evidence,
not tile throughput, conversion capacity, or production OCI/PostgreSQL capacity.

`final-campaign/stress.jsonl` holds timestamps, action counts, error details,
final latency p50/p95/p99, system CPU, free memory, and health. CPU/memory are
host-wide. No other QA build or suite runs concurrently with this final replay.
Latency includes debounce, request, render assertion, and some filter interaction,
not server latency alone. Tier timing starts after browser-context setup.
Safety gates stop on health failure, less than 1 GiB free memory, page errors,
or two consecutive 30-second windows above 1% unexpected action errors.

The final replay completed all tiers with no errors or safety stops. It recorded
16,824 actions total, healthy recovery, all 1,000 records intact, and 20 sessions
as the highest stable tier. Minimum sampled free RAM was 6.15 GiB; maximum host
CPU was 14.0%.

| Sessions | Duration | Actions | Errors | p50 / p95 / p99 (ms) |
|---|---|---:|---:|---|
| 1 | 5 minutes | 129 | 0 | 317 / 333 / 340 |
| 5 | 5 minutes | 635 | 0 | 346 / 368 / 397 |
| 10 | 5 minutes | 1,240 | 0 | 381 / 431 / 479 |
| 20 | 5 minutes | 2,320 | 0 | 519 / 621 / 670 |
| 20 | 30-minute soak | 12,500 | 0 | 737 / 1,003 / 1,094 |

These latency samples include browser interaction and rendering with the API
request, rather than measuring API latency alone. `final-campaign/stress.jsonl`
and its Playwright receipt retain the per-window diagnostics. The disposable
stack exited and removed its temporary data after the final health and fixture
count checks.

Historical baseline evidence remains in `campaign/stress.jsonl` and
`stress-summary.json`: 15,719 actions, 2 unclassified failures (0.0127%), healthy
recovery, 1,000 records intact, highest stable tier 20. Its five-minute tiers
and 30-minute soak ran on the baseline build while separate validation builds
affected host resources (minimum free RAM 1.65 GiB, maximum host CPU 75.4%).
That older runner included setup in tier timing and only retained last-sample
percentiles. It is not substituted for the final repaired-build replay.

Screenshot evidence: `workflows-v5/browser-artifacts/library-lifecycle-metadata-86eab-n-trash-and-restore-persist-fullstack-chromium/library-390-Light.png`
shows the clipped selector; the corresponding `workflows-v9` screenshot shows
the corrected selector. Desktop and dark-mode screenshots are alongside them.

## Explicit remaining gaps

- `control-candidates.csv` remains a static source inventory. The 27 September
  continuation dynamically visited every declared route and the Storage/Trash
  substates, activated the visible route buttons and menu items, and opened every
  synthetic per-slide menu across 1,000 records. Supported workflows have
  separately bounded state coverage; unobserved input permutations are not claimed.
- Nine drawing tools now persist through the real backend. Advanced geometric
  Boolean operations, every annotation revision/conflict permutation, every
  upload cancellation timing, and all combinations of assessment identities,
  grading rules, and question settings are not exhaustive real E2E evidence.
- Quota rejection/retry, corrupt signature/retry, duplicate queue handling,
  interrupted upload resume, expired shares/sessions, recovery-code reset, six
  question types, rostered manual grading, release/export/archive/restore now
  have real-backend journeys. Their specific assertions are in the test source.
- Physical iOS/Android devices were unavailable. Native browser-chrome 200% zoom
  was not checked on the authenticated workspace after the production tab was
  signed out during follow-up. CSS zoom 2 and device emulation are separate evidence.
- Tab traversal swept visible enabled controls on Library and Teaching Studio,
  and each declared route's default ready screen, in Chromium, Firefox, and
  WebKit. It does not cover every dialog or alternate interaction state. Focus
  restoration and other focused keyboard controls also ran. Axe incomplete and
  manual-review findings are retained, not silently passed.
- Live upload exposed OME-TIFF only. Hidden/disabled alternative formats and
  feature-gated surfaces were not activated in production for testing.
- Docker daemon unavailable; native isolated stack was used. No production-scale
  database/storage qualification, merge, deployment, or protected CI qualification.

## Follow-up — 27 September 2026

The follow-up merged current `origin/main` at `272b289` and tested application
code through `fa0d328` at HEAD `f686bf4`. The latest full Chromium run passed 21
tests, skipped one opt-in stress test in the normal fullstack phase, and had zero
unexpected failures or flaky retries. The separate stress phase then ran that
test. Latest Chromium, Firefox, and WebKit route suites exercised 27 route
patterns, including unavailable routes and redirects, with no unexpected page
exceptions. Each suite also tab-traversed each route's default ready screen,
recording reachable stop counts and checking reached stops were visible and
enabled. The course/class edit-reload persistence journey passed in those
three engines. Study Pack upload/conversion/publish, authoring/import/export,
validation/delete, responsive preview, and downstream reload passed in
Chromium, Firefox, WebKit, and Pixel 5 Chromium emulation. Receipts are in
`final-merged-stress/fullstack.json`, `final-route-keyboard-*/fullstack.json`,
and `final-study-*/fullstack.json` under
`CODEX_HOME/qa/frontend-20260913`. Earlier route-only receipts are
in `final-routes-*-v2/fullstack.json`.

The FQA-15 mobile menu fix was verified in mobile Chromium. The shared portal
used to close on any captured document scroll, including the scroll needed to
reach a menu item. It now repositions during scrolling, stays within the
viewport, and focuses without moving the document. ESLint and the production
Vite build passed; Vitest passed 484 tests in 81 files; the full backend pytest
suite passed. Security baseline, architecture precedence, asset-rights, and
dependency-inventory validators passed. The isolated full-stack run reports
`productionTouched:false`; the live production tab received no mutation or
load test. No merge or deployment was performed.

The refreshed ledger has 151 rows: 143 PASS, 6 PASS_MOCKED, and 2 BLOCKED.
Every PASS is bounded by that row's action and assertions. The blocked rows are
not counted as passed: native browser-chrome zoom and physical iOS/Android
devices remain unavailable. Rare state permutations and keyboard traversal
through every dialog remain outside the recorded coverage.

The latest isolated stress campaign used metadata-only synthetic libraries
with 0, 1, 100, and 1,000 records. It completed all four five-minute tiers and
the 30-minute soak, with healthy recovery, 1,000 records intact, and no errors
or safety stops. Twenty sessions were the highest stable tier.

| Sessions | Duration | Actions | Errors | p50 / p95 / p99 (ms) |
|---|---|---:|---:|---|
| 1 | 5 minutes | 129 | 0 | 320 / 337 / 442 |
| 5 | 5 minutes | 635 | 0 | 346 / 374 / 399 |
| 10 | 5 minutes | 1,240 | 0 | 383 / 435 / 502 |
| 20 | 5 minutes | 2,300 | 0 | 531 / 682 / 783 |
| 20 | 30-minute soak | 11,840 | 0 | 760 / 1,614 / 1,966 |

That is 16,144 actions total. The host-wide CPU peak was 78.7% and minimum
free memory was 3.55 GiB; the final soak p95 rose to 1.614 seconds during this
host-load period. The app remained healthy and the stop thresholds were not
reached. Detailed windows and recovery state are in
`CODEX_HOME/qa/frontend-20260913/final-merged-stress/stress.jsonl`.
The checkout was isolated from production; fixtures and temporary stack data
were removed after recovery checks. Generated dependency and software
inventories were refreshed; software release admission remains blocked by its
separate qualification gate.

## Follow-up continuation — route and menu inventory

The continuation started from branch head
`e18dd801e28c4a2a444008ae8a71542ae3005926`. No application source changed since
the previously stress-tested app build; the diff adds E2E inventory and
regression coverage. The disposable Chromium stack rebuilt the frontend and
used SQLite, a generated administrator, and synthetic slides. Each run reports
`productionTouched:false`.

`route-coverage.spec.ts` visited the 27 declared route patterns plus
`/admin?location=storage` and `/admin?location=trash`. It recorded 277 visible
route buttons. The activation receipt records 241 successful clicks (including
reachable menu items), 26 initially disabled controls, four controls disabled
after an earlier synthetic state change, and 15 sign-out controls covered by
the account workflow. It records no missing targets, changed labels, or click
errors. Receipt: `route-control-exploration-chromium-v4/fullstack.json`.

The real-backend journeys assert complete action-menu definitions for
private-ready, published, failed, and trashed slides (7, 9, 6, and 3 items).
They exercise public-slide opening, clipboard copy, publication revocation,
retry, restore, and both library and Storage permanent-deletion confirmations.
The 1,000-record metadata-only test opens and Escape-closes every per-slide
menu across all pages, checking the same six failed-slide actions each time.
Its receipt has 1,000 rows and one unique menu definition:
`large-menu-inventory-chromium-v4/fullstack.json`. The final lifecycle receipt
is `library-delete-flows-chromium-v5/fullstack.json`; the clean three-workflow
Chromium receipt is `menu-state-e2e-chromium-v6/fullstack.json`.

The 1440px light and 390px dark screenshots are retained under
`library-delete-flows-chromium-v5/browser-artifacts/`. Typography, warm light
canvas, semantic dark surfaces, coral actions, card geometry, and the mobile
bottom dock match `apps/web/DESIGN.md`; no visual defect reproduced. Existing
responsive checks cover widths 320–1920, CSS zoom 200%, reduced motion, keyboard
use, Chromium/Firefox/WebKit, and mobile Chromium emulation.

The opened production tab currently shows Administrator sign-in. I inspected
its read-only accessibility tree and did not enter credentials or change
browser state. Authenticated production verification remains blocked; isolated
backend workflows supply the mutation evidence. The existing 50-minute load
campaign remains applicable because application source is unchanged: 1/5/10/20
session tiers and the 30-minute 20-session soak passed on the same app code at
that stage. The continuation below changes shared-viewer source; no sustained
load campaign was rerun against that final UI patch.
Physical-device testing and native browser-chrome zoom remain the two blocked
ledger rows.

## Reuse

Run `python scripts/run_fullstack_tests.py --report-dir <local-evidence-dir>`
from an environment with the documented Python/native dependencies and pnpm,
tusd, and Caddy. Add `--stress` for the bounded 50-minute campaign. It rejects
non-loopback browser targets and the seeder rejects non-disposable databases.
The launcher owns and cleans its generated processes and temporary data.

Use `scripts/frontend_qa_evidence.py --output <dir> --mocked <report.json>
--fullstack <fullstack.json>` to retain scenario rows, receipt hashes, and source
candidates. Repeated receipts are separate runs, not additive unique coverage.

## Follow-up continuation — shared viewer and class folder assignment

The checked-out branch starts at `f2331203cff3e3486f286ba23ad66789e3bbc01d`;
`origin/main` was fetched to `272b28992d01fdbc64e33071c3e4412f3b309927`, which
is in the branch ancestry. The final Chromium isolated run recorded source
diff SHA-256 `0441f15545f5f1f8aaa6f03e7d57e997fc9fd1401d058ecdde32b4392fca9b69`.
The environment was Windows, Playwright 1.62.1, disposable SQLite, a generated
administrator, and synthetic OME slides. Classroom, Assessment, and admin
annotation-canary flags were enabled. The launcher reported
`productionTouched:false`; generated test credentials were used only in the
isolated environment, with no production credentials or data.

The mobile shared-viewer drawer had two confirmed accessibility defects: its
off-screen contents remained exposed to accessibility and keyboard navigation,
and closing it did not return focus to the opener. The fix hides the closed
drawer from accessibility after its transition, exposes `aria-controls` and
`aria-expanded`, restores opener focus after every mobile close path, and lets
Escape leave fullscreen. Regression coverage now exercises the anonymous
two-slide collection route, empty and matching searches, all theme/loading
options and reload persistence, slide navigation boundaries and session
position, drawer close button/backdrop/Escape and focus, zoom and home canvas
changes, rotation by buttons/keyboard/pointer and all dismissal paths,
fullscreen, share revocation, and retry of revoked links. The synthetic class
folder picker also selects and persists its assignment after reload.

The shared-viewer UI patch passed isolated runs in Chromium, Firefox, WebKit,
and Pixel 5 mobile Chromium emulation with zero skips or flakes. Receipts:
`shared-viewer-chromium-v3/fullstack.json`,
`shared-viewer-expanded-firefox/fullstack.json`,
`shared-viewer-final-webkit/fullstack.json`, and
`shared-viewer-final-mobile-chromium/fullstack.json`. The expanded final
Chromium interaction assertions passed in 44.2 seconds at
`shared-viewer-final-chromium-current-v4/fullstack.json`; class folder
assignment passed in 17.6 seconds at
`class-folder-picker-current/fullstack.json`. The route/menu traversal remains
29 route patterns, 282 visible route controls, and 55 dialogs with 141 dialog
actions; its final receipt is
`route-dialog-recursion-v4/fullstack.json`.

The ledger now has 180 rows: 172 PASS, 6 PASS_MOCKED, and 2 BLOCKED. Newly
recorded rows cover every tested collection-viewer and class-folder control.
These results establish the listed states and actions; they do not exhaust all
possible combinations. Physical iOS/Android devices, native browser-chrome
200% zoom, authenticated production verification, and a fresh 50-minute stress
campaign against this UI patch remain unverified. The earlier synthetic stress
campaign remains a baseline for the backend/service revision only. Latest
screenshots and detailed traces are retained outside the repository under
`CODEX_HOME/qa/frontend-20260913/shared-viewer-final-chromium-current-v4/`.

## Follow-up continuation — route inventory and nested viewer Escape

The tested source tree started at `a8f80fb88500ede235ceb9cfec76c0289adb0080`
and was built in isolated full-stack runs on Windows with Playwright 1.62.1,
disposable SQLite, a generated administrator, and synthetic OME-TIFF fixtures.
Classroom, Assessment, Study Coach, and the annotation canary were enabled
locally. The full-stack receipt reports `productionTouched:false`.

Quick Look had a reproduced Escape-key defect: closing its nested rotation
popover also canceled the enclosing native dialog. The shared viewer's Escape
handler now prevents the browser's default dialog cancel and stops propagation
while it closes the popover. The E2E verifies rotation controls, Escape,
continued Quick Look visibility, and opening the same slide in the full viewer.
The extended library journey also covers the command palette's empty result,
upload and folder actions, saved folder after reload, Classroom and Study Coach
destinations, slide deep link, and exclusion of trashed slides. Assessment
coverage now archives/restores a published synthetic assessment and opens,
resets, and closes its learner preview.

`route-coverage.spec.ts` visited 29 declared route patterns, recorded 313
visible route buttons, and inventoried 44 dialogs containing 126 actions.
Route/menu activation evidence has 310 clicks, 27 disabled controls, and 27
actions mapped to dedicated lifecycle/account/assessment tests. Dialog evidence
has 76 clicks, 3 disabled actions, 3 file chooser openings covered by upload
journeys, and 44 actions mapped to dedicated library, class-folder, and
assessment tests. There are no missing-target, label-change, click-error, or
unmapped-action rows. The coverage ledger has 188 rows: 178 PASS,
6 PASS_MOCKED, and 4 BLOCKED. Blocked rows are native browser-chrome 200% zoom,
physical iOS/Android devices, authenticated production workflows, and pathology
pixel-color preservation.

The complete isolated Chromium suite passed 22 tests with one opt-in stress
test skipped, zero unexpected failures, zero retries, and zero observed page
exceptions. Receipts are in
`CODEX_HOME/qa/frontend-20260913/final-complete-chromium-20260928/`.
The latest expanded library lifecycle journey passed in Chromium, Firefox,
WebKit, and Pixel 5 Chromium emulation; each checks the second collection slide's
descriptor and a real JPEG tile response before reload. Production Vite builds
completed in the full-stack runs. `pnpm lint` and Vitest passed; Vitest reported
81 files and 484 tests. Physical devices were not available, so mobile results
are emulation evidence.

The synthetic OME-TIFF fixture is zero-filled. The retained black viewer
screenshots and successful DZI/JPEG responses validate layout and tile delivery,
not pathology color preservation. Pixel-color comparison remains blocked until
a non-PHI nonzero H&E/IHC reference fixture is available.

The latest 50-minute synthetic load campaign ran at app commit
`a8f80fb88500ede235ceb9cfec76c0289adb0080`, before the Escape-only UI patch.
Metadata-only libraries of 0, 1, 100, and 1,000 records passed. Sessions 1, 5,
10, and 20 each ran for five minutes, followed by a 30-minute soak at 20
sessions. The campaign recorded 13,974 actions and zero errors; 20 sessions
were the highest stable tier. Session count and p50/p95/p99 latency in ms:

| Sessions | Duration | Actions | p50 / p95 / p99 |
|---|---|---:|---|
| 1 | 5 minutes | 129 | 316 / 332 / 346 |
| 5 | 5 minutes | 635 | 348 / 378 / 405 |
| 10 | 5 minutes | 1,230 | 391 / 462 / 538 |
| 20 | 5 minutes | 2,260 | 571 / 729 / 798 |
| 20 | 30-minute soak | 11,980 | 822 / 1,141 / 1,274 |

Peak host CPU was about 35.55%; minimum free memory was about 6.52 GiB. No
load campaign was run against production. The stress receipt is
`CODEX_HOME/qa/frontend-20260913/final-ui-patch-stress-20260928/stress.jsonl`.
It remains service/backend baseline evidence; no fresh soak was run after the
later Quick Look and library-menu Escape propagation fixes.

The opened production page showed Administrator sign-in. No production
credentials were entered, so authenticated production verification remains
blocked. No merge or deployment was performed.

## Follow-up continuation — route, button, and menu exploration

This pass used the `feaff540291f05e5a82041953ac11f12384a84aa` source commit with
working-tree source diff SHA-256
`cf9222175bd82005e3fe2eee8a64ac52d2c95f78e5aa9ce8b1df77065031a680`. The
environment was Windows, Chromium 151.0.7922.34, Playwright 1.62.1, disposable
SQLite, a generated administrator, and one converted synthetic slide. Classroom,
Assessment, Study Coach, and the annotation canary were enabled locally.
Every full-stack receipt reports `productionTouched:false`.

The route explorer checked all declared route patterns against `App.tsx`, then
visited 29 route cases including library query states and the unmatched-route
fallback. With a real synthetic slide card present, it inventoried 289 visible
buttons. The route and menu replay produced 312 outcomes: 265 clicked, 27
disabled, and 20 linked to dedicated account, assessment, or lifecycle journeys.
It discovered 35 dialog states with 99 action outcomes: 71 clicked, 3 disabled,
3 file chooser openings, and 22 linked to dedicated journeys. The stricter
assertions found zero unexplored route buttons, menu items, or dialog actions.
Evidence is in
`CODEX_HOME/qa/frontend-20260928/route-exploration-v5/fullstack.json`.

The route pass also explored the folder picker’s close, root, and cancel actions.
Its empty-folder option and “Use this folder” control were correctly disabled;
the separate populated-folder journey selected a ready synthetic folder, saved
it, and verified the assignment after reload at
`CODEX_HOME/qa/frontend-20260928/class-folder-positive-v2/fullstack.json`.

Exploring navigator menus reproduced another Escape defect. Escape closed a
folder menu and bubbled to the page-level handler, closing the entire library
navigator and removing the menu trigger from the accessible view. The shared
`ContextMenu` now stops propagation when it handles Escape. The regression test
confirms the menu closes, the navigator stays open, and focus returns to its
trigger. The same journey opened and exercised all seven actions across folder
(rename, move, trash), collection (rename, delete), and saved-view (rename,
delete) menus, with the final state verified after reload. Receipt:
`CODEX_HOME/qa/frontend-20260928/navigator-menu-v3/fullstack.json`.

The slide-menu state journeys passed for ready/private, published/public,
failed-conversion, and trashed slides. They checked the 7-, 9-, 6-, and 3-item
menu definitions and exercised the state-specific actions. The 1,000-record
metadata fixture opened every slide menu across pagination: all 1,000 menus had
the same six failed-slide actions. Four tests passed with no skips or retries;
receipt:
`CODEX_HOME/qa/frontend-20260928/menu-state-journeys-v1/fullstack.json`.

The refreshed folder and menu journeys passed, `pnpm lint` passed, and Vitest
reported 81 files and 484 tests passed. Physical-device checks, browser-chrome
zoom, authenticated production workflows, and pathology pixel-color comparison
remain blocked for the reasons recorded above. The QA branch is pushed; no merge
or deployment was performed.


### Final mapped-workflow rerun

The synthetic account workflow passed again on the updated source: invalid-input validation, password change, sign-out, and fresh sign-in with the changed password. The six-question-type assessment workflow also passed through authoring, publication, learner save, and submission. Both ran in Chromium 151.0.7922.34 against the disposable SQLite backend with zero retries and zero errors. Receipt: `CODEX_HOME/qa/frontend-20260928/mapped-workflows-v1/fullstack.json`; environment and source-diff hash: `CODEX_HOME/qa/frontend-20260928/mapped-workflows-v1/run-environment.json`.

The refreshed ledger contains 193 rows: 183 PASS, 6 PASS_MOCKED, and 4 BLOCKED. The later release evidence below supersedes this paragraph's earlier statement that production authentication was wholly blocked.

## Final continuation — reload race, current release evidence, and stress (2026-09-28)

The production app remains deployed at `3cb26bc14ec64bc3dad85a29a6da823082615d6c` from protected run [36381707062](https://github.com/Enksodsoon/PathLab-Viewer/actions/runs/36381707062). `/livez` and `/readyz` returned HTTP 200. PRs [#274](https://github.com/Enksodsoon/PathLab-Viewer/pull/274) and [#275](https://github.com/Enksodsoon/PathLab-Viewer/pull/275) advanced `main` to `004fc7923f6887ef894055a7c318e3248e2397ad`; they changed QA tests and release records, not the deployed application source. The deployment kept Classroom enabled, general annotation writes disabled, and the authenticated admin annotation canary enabled. The current in-app browser remains signed out; no credentials were entered during this follow-up.

The authenticated production sample was later recorded in `docs/remediation/PRODUCTION_CLOSURE_QA.md`. It covers synthetic Library/search/folder persistence, upload completion and pause/resume, viewer tiles, annotation save/reload, Classroom teacher actions, one synthetic learner question, and learner reconnect. No real learners or production load were used. Production paths still unverified are separate identities joining concurrently, a specifically selected invite expiry, and automatic stale-release-chunk recovery.

A controlled annotation test reproduced a race between manual reload and an unfinished layer mutation. User-triggered reload now waits in the same serialized layer pipeline; error recovery inside that pipeline can reload inline without waiting on itself. The regression holds a synthetic reorder response, queues another reorder and an opacity change, then requests reload. It confirms no manifest request starts while the write is pending and checks the final layer state after reload. This passed in Chromium, Firefox, WebKit, and Pixel 5 Chromium emulation with zero skips or flakes. The mobile lifecycle test also closes the annotation inspector before activating the global Retry control it covers.

The updated route explorer passed on `004fc79`: 29 declared route patterns, 312 route/menu outcomes, and 35 dialog states with 99 action outcomes; no unexplored controls or unexpected application errors were recorded. Chromium was 151.0.7922.34 with Playwright 1.62.1. The latest standalone route receipt is `CODEX_HOME/qa/frontend-20260928/route-explorer-current-main/fullstack.json`; the four annotation receipts are under `CODEX_HOME/qa/frontend-20260928/annotation-reload-queue-*`. The CPU saturation stop-gate regression added on `main` passed separately.

A fresh 50-minute synthetic library campaign ran on commit `4341b4406ad4d1add17004e27c4ebb51155675b7` against disposable SQLite. Metadata library sizes 0, 1, 100, and 1,000 passed; tiers were five minutes each, followed by a 30-minute soak at 20 sessions. It completed 15,699 actions with zero errors, reached the planned 20-session tier, retained all 1,000 fixture records, and recovered healthy. No production request was generated. Results:

| Sessions | Duration | Actions | Errors | p50 / p95 / p99 |
|---|---:|---:|---:|---|
| 1 | 5 minutes | 129 | 0 | 317 / 338 / 379 ms |
| 5 | 5 minutes | 630 | 0 | 351 / 390 / 451 ms |
| 10 | 5 minutes | 1,220 | 0 | 419 / 497 / 604 ms |
| 20 | 5 minutes | 2,220 | 0 | 619 / 777 / 876 ms |
| 20 | 30-minute soak | 11,500 | 0 | 920 / 1,356 / 1,704 ms |

Peak host CPU was 55.2%; minimum free memory was 5.38 GiB. The run predates the CPU gate added in PR #275, but the observed CPU stayed below its 85% stop threshold; that gate's dedicated regression passes. Full receipts are in `CODEX_HOME/qa/frontend-20260928/final-followup-stress-4341b44/`.

`pnpm lint`, the production web build, and Vitest passed; Vitest reported 81 files and 484 tests. A combined run that included the 50-minute campaign hit the runner's 70-minute outer limit at 18 of 24 browser tests, so that combined run is not counted as a suite pass. The stress campaign, route explorer, and changed annotation workflow were rerun separately and passed. The current-main follow-up branch still needs protected CI.

The final ledger has 197 rows: 187 PASS, 6 PASS_MOCKED, and 4 BLOCKED. Remaining blocks are native browser-chrome 200% zoom, physical iOS/Android devices, the production edge paths named above, and a numeric H&E/IHC color comparison against a non-PHI source fixture. The available OME test fixture is zero-filled; production's patterned synthetic slide was visually rendered but has no source-to-screen RGB receipt. Responsive emulation, CSS zoom, and successful synthetic tile delivery remain separate evidence and do not close those blocks.
