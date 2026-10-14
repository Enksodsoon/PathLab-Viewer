# Spec Delta

## Purpose

Defines the bounded viewer lifecycle and cache behavior that must hold while responsive interfaces change dimensions or orientation.

## ADDED Requirements

### Requirement: Responsive changes retain the Viewer image budget
The Viewer MUST retain its existing adaptive image-loader policy and 50/100-tile cache configuration; resize cycles MUST NOT multiply attached viewer instances, event handlers, timers, or pending requests.

#### Scenario: Repeated alternating resize
- **WHEN** an open viewer canvas alternates between narrow and wide sizes for 20 cycles
- **THEN** one viewer remains attached, configured caches remain within their current tier, event counts do not accumulate, and the request queue settles
