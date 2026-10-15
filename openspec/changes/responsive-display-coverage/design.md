# Design

## Context

Current main is split across route-specific page shells and stylesheets; some responsive behavior already exists and must be preserved. Admin drawer behavior provides a local focus/inertness pattern. Study coordinates are transformed through the attached OpenSeadragon item, while the shared-viewer and annotation test fixtures currently return missing tile images.

## Goals / Non-Goals

**Goals:** Make focused repairs to current-main route families, reuse existing breakpoints and focus patterns, gate coordinate capture on ready image geometry, and extend browser evidence with synthetic rendered tiles and resize lifecycle checks.

**Non-Goals:** Replacing route layouts, changing public APIs or saved data, modifying research approval boundaries, changing the adaptive loader/cache policy, qualifying physical devices, or claiming cross-browser zoom where browser zoom is unavailable.

## Decisions

- Keep current route/component ownership and existing per-surface breakpoints. Fix route-local height conflicts and give long pages, dialogs, and tables clear scroll containers instead of replacing the layout system.
- Reuse the admin drawer's modal focus, inert background, Escape, and restoration behavior for shared navigation. On resize, close only overlays whose presentation mode changed and select a visible focus destination without remounting the route.
- Track image readiness alongside the attached viewer reference. Enable study center capture only when the current world item has valid dimensions; clear both readiness and the reference on detach. Preserve the existing normalized `{x, y}` submission.
- Replace invalid/missing tile fixture responses with deterministic synthetic, non-square image tiles containing visible landmarks. Assert source-coordinate values after pan, zoom, resize, and orientation transitions.
- Use the existing Playwright setup and current dependency version. Assert viewer identity, bounded configured cache tiers, and settled request queues across 20 narrow/wide cycles; treat memory as diagnostic only.
- Cover route families with existing spec suites and focused additions for Study, classroom, and assessment. Keep intentional assessment card reflow and labelled internal table scrolling intact.

## Risks / Trade-offs

- Route-local CSS changes can affect shared classroom overlays imported by Study → scope selectors to explicit route roots and rerun both Study and classroom checks.
- Some E2E tests currently assume page copy that differs from the rendered current-main route → fix stale selectors only when the current screen evidence proves the assumption wrong; record untouched baseline failures explicitly.
- Playwright emulation does not establish real browser zoom, screen-reader output, touch hardware, or monitor scaling → keep those as separately qualified checks.

## Migration Plan

No data migration is required. Changes are client-side and can be rolled back by reverting the frontend patch; the branch contains OpenSpec and browser-test artifacts for review.
