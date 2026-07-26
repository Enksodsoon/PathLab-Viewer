# Task 3 report: Canvas Focus admin shell

## Scope

- Rebuilt the admin library as a two-track Canvas Focus shell: a narrow persistent
  product rail plus a centered, maximum-width content canvas.
- Converted the library navigator and slide-details inspector to fixed overlays,
  integrated quick views into the navigator, and added the real theme control.
- Replaced the legacy library stylesheet with semantic light/dark styles and a
  horizontally contained mobile action dock.
- Preserved existing URL parameters, API calls, actions, dialogs, selection,
  sharing, publishing, upload, processing, failure, Trash, and pagination flows.

## RED evidence

`pnpm.cmd --dir apps/web test -- src/test/library-explorer.test.tsx -t "Canvas Focus"`

The new Canvas Focus contracts failed on the missing icon-rail region, overlay
navigator contract, and overlay inspector contract. The 82 incumbent tests
passed.

## GREEN evidence

- Focused library unit tests: 25/25 passed.
- Full unit suite, deterministic single worker: 16 files / 85 tests passed.
- Responsive Playwright matrix: 44/44 passed across Chromium, Firefox, WebKit,
  and mobile Chromium, including 320, 390, 600, 768, 901, 1251, 1440, and 1920px.
- Lint: passed.
- Production build: passed.
- `git diff --check`: passed.
- Impeccable detector: `[]`.
- Independent Impeccable finish review: clean, with no actionable visual,
  accessibility, responsive, or contract regressions.

## Validation notes

- Escape removes inert state before restoring navigator-toggle focus.
- The inspector remains nonmodal and does not change main-canvas bounds.
- Card `content-visibility` and containment were restored after the full suite
  exposed their removal; persistent toolbar blur was removed.
- No backend, viewer lifecycle, conversion, storage, deployment, or public-link
  behavior was changed.

## Fix round 1: short rail reachability and mobile touch targets

### Review findings

- At 768×600, the desktop rail had 666px of required content inside a 600px
  fixed-height container, but `overflow-y` remained `visible`; Sign out had no
  rail scrolling path.
- At ≤600px, representative filter, state/pagination, menu, and selection
  actions retained 40–42px target heights instead of the required 44px floor.

### RED evidence

- The new CSS contract ran with one incumbent pass and one expected failure
  because the mobile 44px selector group did not exist.
- The two new Chromium browser contracts both failed as expected:
  `overflow-y` was `visible` rather than `auto` at 768×600, and the mobile
  Close filters target measured 40px rather than at least 44px.

### Fix

- The persistent desktop rail now owns thin vertical scrolling while the
  ≤600px dock explicitly retains horizontal scrolling and hidden vertical
  overflow.
- At ≤600px, filter close/clear, state/pagination, menu, and selection action
  controls now have 44px minimum width and height. The existing breadcrumb
  44px contract remains intact.
- The existing semantic-control E2E assertion now distinguishes the 40px
  desktop compact control from the required 44px mobile target.

### GREEN evidence and validation

| Check | Result |
| --- | --- |
| Focused CSS contract | PASS: 2/2 |
| Focused Chromium rail/touch regressions | PASS: 2/2 |
| Full unit suite with one worker | PASS: 16 files / 86 tests |
| Full responsive Playwright matrix | PASS: 52/52 across Chromium, Firefox, WebKit, and mobile Chromium |
| `pnpm.cmd --dir apps/web lint` | PASS |
| `pnpm.cmd --dir apps/web build` | PASS |
| `git diff --check` | PASS |

Rendered Browser QA at `/admin` confirmed:

- at 768×600, the rail reports `clientHeight: 600`,
  `scrollHeight: 666`, and `overflow-y: auto`; scrolling placed Sign out fully
  inside the rail at y=538–588;
- at 390×844, Close filters measured 44×44 and Clear filters measured
  approximately 75.8×44;
- no framework overlay or application error appeared. Console output was
  limited to the repository's existing React Router v7 future-flag warnings.

No backend, query, action, viewer, storage, conversion, sharing, focus/inert,
or deployment contract changed in this fix round.

## Fix round 2: nested mobile breadcrumb target

### RED evidence

- The mobile CSS contract failed because the ≤600px block did not include
  `.library-breadcrumb-row nav button`.
- At 390×844 on `/admin?location=folder:folder-organs`, the new Chromium
  regression measured the nested All slides breadcrumb at 32px high rather
  than the required 44px.

### Fix

The ≤600px rules now give nested breadcrumb buttons a 44px minimum width and
height, matching the already-hardened Back, Forward, and Up controls without
changing desktop breadcrumb density.

### GREEN evidence and validation

| Check | Result |
| --- | --- |
| Focused CSS contract | PASS: 2/2 |
| Focused nested-breadcrumb Chromium test | PASS: 1/1 |
| Relevant library unit suite | PASS: 2 files / 27 tests |
| Full responsive Playwright matrix | PASS: 56/56 across Chromium, Firefox, WebKit, and mobile Chromium |
| `pnpm.cmd --dir apps/web lint` | PASS |
| `pnpm.cmd --dir apps/web build` | PASS |
| `git diff --check` | PASS |

Rendered Browser QA opened a real folder at 390×844, measured its All slides
ancestor breadcrumb at approximately 57.4×44, and verified that activating it
returned the route to `/admin`. No framework overlay or application error
appeared; console output remained limited to the existing React Router v7
future-flag warnings.

No API, query, action, focus/inert, navigator, inspector, sharing, viewer,
storage, conversion, or deployment behavior changed in this fix round.
