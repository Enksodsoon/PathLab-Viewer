# Imaging Control

This context owns the identity, integrity, derivation, privacy status, and publication authority of imaging assets while keeping byte delivery replaceable.

## Language

**Source Asset**:
An immutable original imaging object or governed companion set accepted into PathLab.
_Avoid_: Original file, upload

**Derivative Asset**:
An immutable representation produced from a Source Asset under a recorded transformation.
_Avoid_: Converted file, cache

**Asset Manifest**:
The signed identity, hashes, relationships, format facts, and provenance of one Source Asset or Derivative Asset.
_Avoid_: Metadata file, sidecar

**Publication**:
An explicit grant making a privacy-approved asset representation available to a defined audience.
_Avoid_: Public file, share link

**Restricted Share**:
An authenticated, purpose- and audience-bound Publication using private no-store responses and five-minute Tile Capabilities, with revocation effective within five minutes.
_Avoid_: Private link, expiring URL

**Public Release**:
An officer-approved anonymous Publication of individually privacy- and provenance-approved content-addressed assets, carrying an explicit warning that downloaded or externally cached copies cannot be erased.
_Avoid_: Public share, revocable link

**Publication Re-admission**:
A fresh Public Release and Collection Manifest review that an existing anonymous share must pass before it may become active under Full-Surface Launch.
_Avoid_: Grandfathered link, migrated approval, identifier preservation

**Collection Manifest**:
An immutable Publication candidate enumerating each exact asset version, Browser Representation hash, privacy and provenance decision, and intended audience for a folder or collection.
_Avoid_: Shared folder, live collection

**Tile Capability**:
A short-lived authorization to retrieve an immutable tile representation without transferring publication ownership to Delivery.
_Avoid_: Tile token, public URL

**Browser Representation**:
A derivative optimized and qualified for interactive browser viewing without claiming to preserve every source-format semantic.
_Avoid_: Canonical image, source format

**Exchange Representation**:
A standards-conformant derivative whose supported semantic subset and transformation provenance are explicit.
_Avoid_: Equivalent copy, universal format

**Private Result Artifact**:
A non-published measurement, inference, or analysis package attached to a Source Asset with producing-workflow provenance.
_Avoid_: AI result, sidecar file

**Private Annotation Draft**:
A mutable annotation workspace visible only to its owning Principal until explicit publication review.
_Avoid_: Annotation layer, autosave file

**Annotation Layer Version**:
An immutable, purpose- and audience-bound publication of at most 25,000 validated annotation objects and 50 MB of canonical geometry and measurement data.
_Avoid_: Shared annotations, GeoJSON file

**Restricted Annotation Publication**:
A reviewed Annotation Layer Version available only to an authenticated Learning, Research, or EQA purpose and audience.
_Avoid_: Public annotations, shared draft, anonymous overlay

**Annotation Editor Lease**:
An expiring grant allowing one editor to derive the next Annotation Layer Version from one exact predecessor under optimistic revision checks.
_Avoid_: Edit lock, collaboration session

**Browser Publication Gate**:
The fail-closed requirement that an authorized, integrity-verified static DZI Browser Representation exist before a Publication can become active.
_Avoid_: Conversion complete, preview ready

**Upload Reservation**:
A bounded Imaging-mode grant for one declared source object whose identity, remaining bytes, format expansion evidence, storage headroom, expiry, and resumable-upload identifier are fixed before admission.
_Avoid_: Upload session, available quota

**Storage Admission Ledger**:
The auditable calculation reserving an upload's remaining bytes, measured peak temporary space, required derivatives, projected 35-day authoritative growth, restore workspace, and hard volume headroom before an Upload Reservation is issued.
_Avoid_: Free-space check, storage quota

## Retention ceilings

- Rejected uploads expire no later than 24 hours after rejection.
- Incomplete resumable uploads expire no later than seven days after their last accepted byte.
- Assets in Trash expire no later than 30 days after deletion.
- Deterministically rebuildable Derivative Assets and tile caches are excluded from backups and may be evicted under storage pressure.
- Private Result Artifacts expire no later than two years after their producing workflow closes.
- Source Assets, non-rebuildable annotations, and their provenance require annual custody review and expire no later than seven years after the last authorized purpose closes.

## Mode availability

- Authorized static DZI delivery remains available through the Resident Control Plane in every non-maintenance operating mode.
- Direct OME dynamic decoding, conversion, and OME-Zarr or DICOM derivative generation run only in an Imaging Mode Reservation and queue otherwise.
- Original WSI objects are never sent to a browser as a substitute for an unavailable Browser Representation.
- tusd accepts bytes only during a valid Imaging Mode Reservation and Upload Reservation; interruption outside that window preserves resumable state until its seven-day inactivity ceiling.
