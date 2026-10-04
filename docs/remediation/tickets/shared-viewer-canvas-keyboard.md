# Shared viewer canvas keyboard ownership

Labels: wayfinder:ticket

## Decision

Keep horizontal arrows from the OpenSeadragon canvas within the image. Continue adjacent-slide navigation from the rest of the shared viewer, subject to existing editable-field and modifier guards.

## Evidence and callers

Additional source `docs/reports/CODEX_FULL_HANDOFF_REPORT.md:375`, BUG-05. At production source c570116, a first canvas ArrowRight starts OpenSeadragon panning and prevents default. Its next keydown while the action is held does not prevent default; the window handler in SharedViewerPage then selects the next slide. This affects public folder and collection shared viewers. The rotation dial already prevents its handled arrows; the report's claim about that control is not reproduced.

The actual browser regression fails on original source in Chromium, Firefox and WebKit after the second keydown changes the heading. Initial probe selected two canvases, including the navigator, and failed during setup; that is separate from the successful reproduction using the focusable image canvas. Red receipts: `var/handoff-keyboard-red.log` and `var/shared-canvas-keyboard-red.log`.

## Repair

For Left/Right only, return when the event target is inside `.openseadragon-canvas`. Do not rely on defaultPrevented for repeated events. Keep OpenSeadragon handling pan, existing zoom and Escape behavior, slide buttons and arrows outside the canvas. No dependencies, API, data or feature activation changes.

## Verification and delivery

Actual browser regression passes Chromium, Firefox and WebKit locally after the guard: held Right/Left keeps the slide, outside-canvas Right selects the next slide, and reload preserves that selection. Complete affected browser matrix, frontend suite, lint/build, independent review and fresh protected release checks are tracked separately. The repair is not yet deployed; production remains c570116.

Final local qualification: strengthen Left coverage at position1 to avoid the previous-slide clamp. Four-engine regression passes4/4 in16.9seconds, including mobile Chromium; complete affected matrix passes32/32 in1.5minutes. Changed-file ESLint and production build8.94seconds pass. Default frontend run570pass/1existing authentication build-test30-second timeout is retained; four-worker rerun passes all571tests across85files in189.25seconds. No timeout or authentication code changed. Independent review is clear after strengthening the test and correcting the Study asset-root wording in the source audit. Protected CI, merge and deployment remain pending.


## Current verified production c37cf81

PR307 merged c37cf81 after all nine reviewed-head gates. Fresh main CI37162376381/Security37162376369 passed all nine latest exact-SHA contexts; the unchanged Library-sort observation, focused45-case suite and20replays are retained separately from the successful same-SHA failed-job rerun. Protected deployment37164136683 succeeded with actual restore69tables/106325files/3286131731bytes/schema20260907_0037. Fresh health200/200 and anonymous drafts401 passed. Native explicit Refresh retained synthetic viewer tiles/two annotations/NO CHANGES and private assessment two questions/2.502points/All changes saved; Library return loaded authenticated content. [Release receipt](../evidence/production-c37cf81-release.json) records scope and limitations. Original findings and external closure requirements remain visible.
