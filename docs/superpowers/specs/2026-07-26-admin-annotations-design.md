# Admin Annotation System Design

## Goal

Give the authenticated administrator a full manual pathology annotation workspace while
keeping public and shared viewers annotation-free. Stability outranks feature throughput:
annotation failures must never break slide viewing, and the feature adds no runtime service,
conversion work, derivative files, or public data.

## Architecture

Annotations load only on `/admin/preview/:slideId` when
`PATHLAB_ANNOTATIONS_ENABLED=true`. The public `/s`, `/f`, and `/c` routes do not import the
annotation chunk, call annotation APIs, or receive annotation fields.

The existing OpenSeadragon 6 viewer remains authoritative for tiles, pan, zoom, fullscreen,
network recovery, and cleanup. An optional attachment callback mounts a native SVG overlay
whose geometry is stored in source-image pixels. An RBush index culls offscreen shapes.
At most 2,000 SVG shapes are mounted and 5,000 are cached; a density canvas and zoom prompt
replace individual SVG shapes above the display cap.

FastAPI exposes session-protected annotation reads and CSRF-protected mutations under
`/api/v2/admin/annotations`. SQLite WAL remains the only database. An additive Alembic
migration creates layer, annotation, and bounded revision tables and adds
`slides.annotation_version`. No public endpoint or serialization path is added.

## Workspace and Tools

The approved Focus workspace uses a compact left tool strip, collapsible right inspector,
overlay annotation list, and existing Canvas Focus tokens. At 760 px and below, tools move
to a bottom dock and the inspector becomes a sheet.

Tools: hand/pan, select and marquee, point/count marker, ruler, polyline, three-point angle,
rectangle, ellipse, polygon, freehand closed ROI, brush-add, brush-subtract/eraser, and
text/callout. Editing includes vertex manipulation, move/resize, duplicate, copy/paste,
union, subtraction, intersection, split, multi-select, bulk edits, delete/restore, and
session undo/redo.

Named layers support ordering, locking, opacity, visibility, search, filters, and zoom-to.
Annotations support title, classification, tags, notes, stroke/fill styling, and label
visibility. Measurements report coordinates, count, length, angle, perimeter, and area.
Recognized `nm`, `µm`, and `mm` calibration converts results to µm/mm; missing or unknown
calibration stays in px/px² with an explicit warning.

## Persistence and Failure Handling

Geometry uses a strict discriminated JSON union with denormalized bounding boxes. Each row
has an integer version and client mutation ID. Saves debounce for 750 ms, flush on Ctrl+S,
and contain at most 50 operations in one all-or-nothing transaction. A stale base version
returns `409 ANNOTATION_CONFLICT`; the UI offers server reload or save-as-duplicate.

Current state plus 25 revisions is retained. Deletes become 30-day tombstones; each later
write purges no more than 100 expired rows. Unsaved drafts use origin-scoped IndexedDB,
limited to 5 MiB total and seven days, and clear only after server acknowledgement or
explicit discard.

Errors in rendering or editing detach annotation handlers, restore OpenSeadragon navigation,
keep the local draft, and show Retry. Network errors back off without claiming a save.
Audits contain actor, action, target IDs, counts, duration, and result only—never geometry,
labels, notes, tags, or imported content.

## Interchange and Limits

Export formats are lossless `pathlab-annotations/v1` JSON, QuPath-compatible GeoJSON, and
CSV measurements. Import accepts PathLab JSON and GeoJSON after client preview and strict
server validation. The default import creates a new layer. Ellipses become polygon
approximations in GeoJSON.

Hard defaults:

- 25,000 active annotations per slide
- 100 layers per slide
- 8,192 vertices per shape
- 250,000 vertices and 8 MiB per import
- 256 KiB normal annotation request
- 2,000 mounted SVG shapes
- 5,000 cached annotation shapes

`polygon-clipping@0.15.7` handles bounded polygon booleans in a Web Worker, which is
terminated after two seconds without replacing source geometry. `rbush@4.0.1` provides
client spatial indexing. Both dependencies are pinned.

## Rollout Boundaries

`PATHLAB_ANNOTATIONS_ENABLED` defaults to false and is the kill switch. Production rollout
is separate from GitHub delivery: back up, migrate with the flag off, smoke-test auth and
all viewer routes, enable, then verify create/save/reload. Rollback disables the flag or
restores old application code while retaining additive tables and annotation data. Schema
downgrade is never automatic.

Excluded from this release: AI segmentation, collaboration, non-admin permissions, public
annotations, DICOM export, raster masks, diagnostic certification, GitHub merge, and OCI
deployment.
