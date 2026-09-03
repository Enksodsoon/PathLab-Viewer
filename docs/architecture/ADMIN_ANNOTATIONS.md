# Private Administrator Annotations

> **Precedence status: `BASELINE_ONLY`.** This document describes the current
> private, default-off implementation. The [Architecture Precedence
> Register](./ARCHITECTURE_PRECEDENCE.md), [Imaging Control
> context](../contexts/imaging-control/CONTEXT.md), and accepted ADRs control
> target annotation, sharing, role, and activation semantics.

## Boundary and failure model

PathLab annotations are a private, admin-only review aid. They are not a
diagnostic device, collaborative record, or public teaching-link feature. The
workspace can load only at `/admin/preview/{slideId}` after the private slide
response reports `annotationsEnabled: true`. Public `/s`, `/f`, and `/c` routes
receive no annotation fields, issue no annotation API requests, and do not
request the lazy annotation bundle.

`PATHLAB_ANNOTATIONS_ENABLED=false` is the default and the operational kill
switch. When disabled, private annotation endpoints return
`404 ANNOTATIONS_DISABLED`; the ordinary OpenSeadragon viewer remains usable.
Rendering, editing, draft-storage, and save failures detach annotation handlers,
restore pan/zoom, and preserve recoverable local work. No annotation path starts
a service, conversion job, storage scan, derivative file, or public artifact.

`PATHLAB_ADMIN_ANNOTATION_CANARY_ENABLED=true` is a narrower, default-off
production canary. It enables the same workspace and mutation APIs only for
authenticated administrator slide previews while
`PATHLAB_ANNOTATIONS_ENABLED=false` remains unchanged. It does not add fields
or API access to public or Classroom routes. Set the canary back to `false` and
redeploy to remove the workspace without deleting saved annotation data.

## Architecture

- React loads `AnnotationWorkspace` as a private-only dynamic import.
- A native SVG overlay attaches to the existing OpenSeadragon instance and
  stores coordinates in source-image pixels.
- RBush culls the viewport. At most 2,000 individual SVG annotations mount,
  5,000 records remain cached, and a bounded density view replaces shapes above
  the display cap.
- Geometry, measurement, edit history, imports, and autosave live in the lazy
  client module. Polygon boolean work runs in a two-second-bounded Web Worker.
- FastAPI exposes session-protected reads and CSRF-protected writes only under
  `/api/v2/admin/annotations`.
- SQLite WAL remains the only database. A slide version makes every write
  transaction optimistic and atomic; stale writes fail with
  `409 ANNOTATION_CONFLICT`.

## Persistence and resource limits

Normal saves debounce for 750 ms and contain at most 50 operations and 256 KiB.
Imports are limited to 8 MiB and 250,000 vertices. Each slide supports at most
25,000 active annotations, 100 layers, and 8,192 vertices per shape.

The database retains current state plus 25 revisions. Deletes are tombstones
with a 30-day retention period; a later write purges at most 100 expired
tombstones. Browser drafts retain only recovery mutations, are limited to
5 MiB per origin, expire after seven days, and clear only after server
acknowledgement or explicit discard.

Audit events contain actor, action, target identifiers, counts, duration, and
result. They must never contain geometry, labels, notes, tags, or import
content.

## Backup and restore

Annotations, layers, revisions, tombstones, and `slides.annotation_version` live
in the same SQLite database as slide metadata. The normal online SQLite backup
therefore preserves them. File archives remain unchanged because annotations
create no files.

Before an annotation-capable release:

1. keep `PATHLAB_ANNOTATIONS_ENABLED=false`;
2. pause uploads and conversion work;
3. create the normal database/files backup and verify checksums;
4. restore that backup on a disposable host;
5. run `alembic upgrade head`;
6. verify readiness and existing private/public viewers before enabling the
   feature.

A restore drill must compare layer, annotation, revision, tombstone, and slide
version counts as well as representative private/public slide delivery. Do not
test restore over the only production data copy.

## Rollout and rollback

Enabling either flag is a separate production decision. The admin canary may be
used for one administrator session before the globally certified flag is
available. Verify create, save, reload, revision restore, and public-route
isolation. Watch API latency, SQLite lock errors, database growth, browser
memory, and unsaved-draft warnings.

For an admin-canary incident, first set
`PATHLAB_ADMIN_ANNOTATION_CANARY_ENABLED=false` and redeploy. For a global
annotation incident, set `PATHLAB_ANNOTATIONS_ENABLED=false`. Both preserve all
annotation tables and data while restoring the standard viewer path.
Application rollback should retain the additive schema. Schema downgrade is
destructive: migration `20260726_0009` drops
annotation layers, annotations, revisions, and the slide version column. Use it
only with explicit data-loss acceptance and a verified backup; never make it an
automatic rollback step.

## Verification limits

Repository tests cover authentication, CSRF, validation, migration
round-trips, backup content, SQLite/WAL concurrency, bounded rendering, browser
routes, and bundle budgets. Synthetic 25,000-record runs establish machine-local
query and rendering behavior only. They do not establish live multi-user,
physical-device, OCI, clinical, or production-load acceptance.
