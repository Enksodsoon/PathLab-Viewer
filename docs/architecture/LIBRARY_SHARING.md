# Virtual Library and Folder Sharing

## Purpose and boundaries

The virtual library organizes slides without changing their ID-based private or
public storage paths. Folders, descriptions, tags, notes, and sort orders live in
SQLite. Folder operations must not scan storage, run libvips, start conversion,
copy images, or move DZI and tile trees.

Folders have at most three levels, where a root folder is level one. Names are
Unicode-normalized, whitespace-collapsed, and compared case-insensitively among
siblings. Deleting a folder moves its direct slides to Unfiled and reparents its
direct children only after collision checks succeed.

## Publication grants

Publication is represented by one or more grants:

- `individual`: created by the existing publish action and removed by unpublish;
- `folder`: created for an eligible direct child of an actively shared folder.

The first grant gives the slide a stable public ID and atomically hardlinks its
existing sanitized private derivative into the public tree. Further grants only
add SQLite rows. Removing the last grant removes the public alias; removing one
of several grants keeps the slide public. Managed storage accounting excludes
public hardlinks.

Moving a slide reconciles its old and new folder grants. The worker does the same
when a direct-folder slide finishes conversion. Publication failure keeps the
ready private derivative and records an administrator-visible failure so sharing
can be retried without reconversion.

## Shared collection contract

An active folder share has one unlisted bearer token. Creating it again is
idempotent and reconciles missing eligible grants. Revocation invalidates the
token before retry-safe grant cleanup. Rotation replaces the folder token but
does not change slide public IDs or grants.

`GET /api/v1/public/folders/{folderPublicId}` returns only active, unexpired
shares and published direct children. Revoked, inactive, expired, and unknown
tokens use the same generic 404 response. The manifest exposes the folder's
public name and description plus safe slide teaching metadata and tile source.
Administrator notes, filenames, source paths, upload data, and patient content
are not public fields.

The browser route `/f/{folderPublicId}` fetches this manifest once. It creates one
OpenSeadragon instance and calls `open()` as selection changes; it does not
preload thumbnails or tiles. `/s/{publicId}` remains compatible.

## Privacy and operations

Folder links are bearer links: anyone who receives one can view the collection.
Administrators must de-identify names and teaching metadata before sharing.
Rotation or revocation prevents future manifest access but cannot retract data
already retained by a recipient or intermediary cache.

Migration `20260723_0006` backfills an individual grant for every already
published slide while preserving public IDs and filesystem state. Upgrade and
downgrade are database-only. Back up before migration; see `deploy/README.md` for
the operational sequence.
