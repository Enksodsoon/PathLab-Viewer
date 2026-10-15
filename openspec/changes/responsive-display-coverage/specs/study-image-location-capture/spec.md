# Spec Delta

## Purpose

Defines ready-gated learner capture of a visible image location in source coordinates, preserving the existing submission format and study approval boundaries.

## ADDED Requirements

### Requirement: Visible-center capture waits for image readiness
The learner MUST NOT capture a visible image center until the active image item and its source dimensions are ready, and MUST discard its viewer reference when the viewer detaches.

#### Scenario: Capture before and after image readiness
- **WHEN** a learner opens a study task before its image finishes loading
- **THEN** center capture is disabled until image readiness, after which it produces the existing normalized `{x, y}` value

### Requirement: Captured location follows image geometry
The captured center MUST be transformed through the active image item and viewport so that pan, zoom, resize, and orientation changes preserve source-image location accuracy.

#### Scenario: Capture a synthetic image landmark
- **WHEN** a learner centers a recognizable landmark in a non-square synthetic image and captures its visible center after viewport transforms
- **THEN** the submitted normalized coordinate matches the source landmark within one source-image pixel

### Requirement: Study submission boundaries remain unchanged
Responsive coordinate capture MUST preserve the established request shape and MUST NOT change research consent, event-queue, or approval behavior.

#### Scenario: Submit the captured location
- **WHEN** the learner submits a task after capturing an image location
- **THEN** the request contains the same normalized `{x, y}` fields and follows the existing study-consent and submission flow
