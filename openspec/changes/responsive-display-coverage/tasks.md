# Tasks

## 1. Route layouts and responsive focus

- [ ] 1.1 Repair current-main auth, library, shared-viewer, annotation, Study, Classroom, and Assessment short/narrow layouts; verify required actions, internal scroll owners, and no unintended document overflow in rendered tests.
- [ ] 1.2 Reuse admin drawer focus/inertness for shared-library navigation and close transient annotation overlays predictably through breakpoint transitions; verify Escape and focus restoration in browser tests.
- [ ] 1.3 Verify focused short-height forms, dialog scrolling, touch targets, reduced motion, enlarged text, and forced-colors behavior with route-specific browser checks.

## 2. Study image-location capture

- [x] 2.1 Gate learner center capture on ready image dimensions and clear viewer readiness on detach; verify the button state, preserved task fields, and existing `{x, y}` payload in component tests.
- [x] 2.2 Use deterministic non-square synthetic tiles with recognizable landmarks; verify normalized source coordinates after pan, zoom, resize, and orientation changes within one image pixel.

## 3. Current-route and viewer lifecycle coverage

- [ ] 3.1 Cover populated, empty, loading, error, and permission-dependent states across current route families, including Assessment, Classroom, and Study admin and learner routes; include long filenames, unbroken identifiers and source URLs, multiline prompts and errors, and the largest existing paginated result; verify essential controls at phone, short-landscape, tablet, and desktop sizes.
- [ ] 3.2 Verify viewer identity, non-accumulating handlers/timers, adaptive loader configuration, cache tiers, and settled request queues after 20 alternating narrow/wide cycles.
- [ ] 3.3 Run Firefox and WebKit phone, landscape, tablet, and desktop representatives; in Chromium test 320x568, 390x844, 568x320, 667x375, 768x1024, 1024x768, 1280x720, 1440x900, 1920x1080, 2560x1440, 3440x1440, and 3840x2160, each affected breakpoint at -1, exact, and +1px, and focused forms at 320px and 480px heights.
- [ ] 3.4 Verify keyboard, mouse, touch emulation, and mixed pointer-capability changes; light and dark themes, reduced motion, enlarged text, and forced colors; 44x44px primary targets, textarea focus visibility, screen-reader reading order, and visible non-color state.
- [ ] 3.5 Check actual 200% and 400% browser zoom in Edge separately from DPR 1, 2, and 3; record screen-reader checks where available and identify unavailable checks without treating emulation as hardware validation.

## 4. Integration and evidence

- [ ] 4.1 Run Viewer component tests, lint, production build, responsive Playwright suites, and focused Study/Classroom/Assessment regression suites; distinguish pre-existing failures from regressions.
- [ ] 4.2 Review rendered screenshots, console output, and route coverage; resolve material mismatches and run strict OpenSpec validation before marking acceptance tasks complete.

## Workflow follow-up

- Archive the fully implemented change after acceptance evidence is complete; validate the archived spec before opening the final PR.
