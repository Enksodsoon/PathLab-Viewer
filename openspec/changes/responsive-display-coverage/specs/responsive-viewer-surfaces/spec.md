# Spec Delta

## Purpose

Defines how current Viewer routes reflow across display sizes while keeping route-specific workflows, dialogs, and viewer state accessible and intact.

## ADDED Requirements

### Requirement: Current routes reflow without hiding essential content
Viewer authentication, library, shared viewing, annotation, Study, Classroom, and Assessment routes MUST keep essential controls and content reachable without unintended document-level horizontal scrolling; intentional wide data regions MUST use labelled internal scrolling.

#### Scenario: Narrow and short display
- **WHEN** a current route is rendered at 320px width or 320px height
- **THEN** essential actions remain reachable by scrolling within a clear owner and no required control is clipped by the viewport

#### Scenario: Wide tables at narrow widths
- **WHEN** a library, Study, classroom, or assessment data table exceeds the viewport width
- **THEN** its labelled container scrolls horizontally without widening the document

### Requirement: Responsive overlays preserve keyboard focus and context
Drawers, inspectors, menus, and dialogs MUST have bounded visible geometry, expose only open content to assistive technology, and return focus to a visible trigger or replacement when dismissed or when viewport mode changes.

#### Scenario: Shared library drawer keyboard lifecycle
- **WHEN** a user opens shared-library navigation, resizes across its overlay breakpoint, and closes it with Escape
- **THEN** focus moves into the open drawer, the background is inert while the drawer is modal, and focus returns to a visible navigation control

#### Scenario: Focused form with a shrinking viewport
- **WHEN** the virtual keyboard or short window reduces viewport height while an authentication or dialog field is focused
- **THEN** entered text is preserved and the field, its validation message, and submit or close control can be scrolled into view

### Requirement: Layout changes preserve route and work state
Viewport changes MUST preserve the active viewer and route state without resetting work or repeating a mutation.

#### Scenario: Resize with an active viewer and pending work
- **WHEN** the user resizes while an image, unsaved annotation, or queued upload is active
- **THEN** the same viewer, slide, series, revision, pan or zoom, annotation tool and edits, upload or conversion progress, selected library filters, Study Pack fields, imported tasks, teaching-region selection, validation messages, learner answers and confidence, consent or session state, selected point, hints, elapsed task state, pending event queue, and assessment responses remain available without repeating a mutation

### Requirement: Touch and accessibility modes retain usable controls
Essential controls MUST work without hover, primary touch targets MUST be at least 44 by 44 CSS pixels, and focus, selection, reading order, and control boundaries MUST remain perceivable under enlarged text, reduced motion, and forced-colors settings.

#### Scenario: Mixed input and forced colors
- **WHEN** touch emulation or forced-colors mode is enabled at a responsive breakpoint
- **THEN** touch controls remain usable, keyboard focus is visible, and meaningful state does not rely on color alone

### Requirement: Responsive display coverage uses current route families
Rendered acceptance coverage MUST visit representative populated, empty, loading, error, and permission-dependent states for every current route family, including current Assessment, Classroom, and Study route groups.

#### Scenario: Newer routes at short landscape and tablet sizes
- **WHEN** classroom, study-authoring, assessment administration, and assessment learner routes are opened at short-landscape and tablet viewports
- **THEN** each route's essential navigation, content, and task actions remain reachable without unintended overlap

### Requirement: Responsive acceptance uses explicit display and content cases
The Chromium layout matrix MUST include 320x568, 390x844, 568x320, 667x375, 768x1024, 1024x768, 1280x720, 1440x900, 1920x1080, 2560x1440, 3440x1440, and 3840x2160, each affected breakpoint at -1, exact, and +1px, and 320px and 480px viewport heights with focused fields. Firefox and WebKit MUST cover phone, landscape, tablet, and desktop representatives. Browser zoom MUST be checked separately from device pixel ratio.

#### Scenario: Long content under responsive constraints
- **WHEN** a user views a long filename, unbroken identifier or source URL, multiline prompt or error, or the largest existing paginated result at a narrow or zoomed display
- **THEN** required controls remain reachable, long values remain available through visible or accessible detail, and the document does not gain unintended horizontal scrolling
