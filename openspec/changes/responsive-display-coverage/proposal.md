# Proposal

## Why

The current Viewer has responsive behavior distributed across authentication, library, shared viewing, annotation, Study, classroom, and assessment surfaces, but its existing rendered checks do not cover cross-breakpoint state and focus behavior or the newest route families. Display changes must preserve active viewer and learner work while keeping the existing design usable at short, narrow, and enlarged viewports.

## What Changes

- Repair layout and overlay behavior across current main routes, including Study, classroom, and assessment, while preserving each route's existing visual structure.
- Make shared-library drawer focus/inertness match the admin drawer and close transient annotation overlays predictably on layout-mode changes.
- Gate Study center capture on ready image dimensions and verify coordinate transforms with deterministic synthetic rendered tiles.
- Extend rendered checks for display transitions, focused short-height forms, accessibility settings, and configured viewer resources without altering public APIs or saved data.

## Capabilities

### New Capabilities
- `responsive-viewer-surfaces`: Responsive reflow, focus, and state behavior across Viewer routes.
- `study-image-location-capture`: Ready-gated image-center capture in the existing normalized coordinate format.
- `viewer-resource-limits`: Viewer attachment lifecycle and bounded image-loading behavior through resize cycles.

### Modified Capabilities

None. This repository has no existing OpenSpec capability inventory.

## Impact

Affected code is limited to the Viewer web app, its existing Playwright and component tests, deterministic synthetic browser fixtures, and OpenSpec artifacts. Public routes, APIs, saved-data shapes, authentication boundaries, research approval boundaries, adaptive loader policy, and existing cache configuration remain unchanged.
