# Library Domain and Bounded Query Contract

## Domain boundaries

Folders, collections, and saved views are separate concepts:

- A folder is one canonical Windows-like location. A slide belongs to zero or
  one folder. Folders nest to at most eight levels.
- A collection is an ordered teaching set. A slide may belong to any number of
  collections without changing its folder.
- A saved view is versioned, validated filter JSON evaluated by the same
  library-query adapter. It never stores SQL.

Names use Unicode NFKC normalization, collapsed whitespace, and case-folded
sibling uniqueness. Folder moves reject cycles and reject any move whose
complete subtree would exceed the depth limit.

## Trash

Slide Trash records its previous folder, revokes publication grants, and hides
the slide from ordinary locations. Restore returns it to that folder when the
folder still exists and is active, otherwise to Unfiled. Permanent deletion is
explicit and reuses the existing background physical-deletion worker.

Folder Trash marks its complete subtree without promoting descendants or
changing slide-folder relationships. Restore clears the subtree markers.
Permanent folder deletion requires an already-trashed, slide-free subtree and
deletes descendants before their parents.

## Bounded APIs

The authenticated `/api/v2` library surface separates:

- navigation and special-location counts;
- lazy direct children for one expanded folder;
- bounded item pages and deterministic opaque cursors;
- facets loaded only when requested;
- status for at most 100 explicit slide IDs;
- short CRUD and batch mutations of at most 50 slides.

Item pages default to 48 and cap at 100. Card/table payloads intentionally omit
original filenames and administrator notes. One-slide detail requests expose
those administrator-only fields explicitly.

SQLite FTS5 is created and synchronized when supported. The search adapter
detects it at runtime and otherwise uses bounded indexed/filterable SQLite
queries. This adapter boundary permits a later PostgreSQL search migration
without changing the HTTP contract.

Library requests use database metadata only. No navigation, search, facet, or
organization request may walk storage, open an OME-TIFF, decode pixels, or
copy/move a DZI tree.

## Thumbnails

The existing serial conversion job generates one stripped JPEG thumbnail with
a 384-pixel longest edge and quality 80 from the already-open libvips image.
Browsing never decodes a WSI. Private thumbnails require administrator
authentication and use private caching plus an ETag. A published thumbnail is
hardlinked through the existing publication boundary and removed with the
public alias after the final grant disappears.

## Publication grants and dormant sharing

An individual grant represents the existing `/s/{publicId}` publication. A
share grant will represent one active folder or collection share. The first
grant creates the hardlinked public alias; later grants add database rows.
Removing the final grant removes the alias.

Multi-slide share activation is disabled by default. The schema is forward
compatible, but creation fails with `PRIVACY_SCANNER_REQUIRED` until a later
automated privacy scanner has evidence. Routine folder and collection
organization never creates a publication grant.

## Migration and rollback

Migration `20260723_0006` upgrades from `20260723_0005`, retains every existing
slide and public identifier, and backfills one individual grant for each
published slide. Downgrading to `20260723_0005` removes only library-v2 schema
and columns. Operators must back up the SQLite database and data root before
upgrade or rollback; deployment is separate from migration verification.
