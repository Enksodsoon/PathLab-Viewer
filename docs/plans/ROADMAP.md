# PathLab Prep Delivery Roadmap

This roadmap intentionally uses six vertical milestones. Each milestone is divided into small tasks, but only one task is active at a time in `docs/plans/active/current.md`.

## Milestone 1 — Server prepared-slide vertical slice

Outcome:

```text
synthetic .plslide
→ prepared upload reservation
→ tus upload
→ checksum
→ safe asynchronous import
→ ready_private
→ private preview
```

Tasks:

1. Package schema, typed models and deterministic fixture generator.
2. Safe TAR and DZI validator.
3. Database migration, import states and asynchronous importer.
4. Prepared upload API, tus completion and synthetic end-to-end test.
5. Single-copy canonical DZI storage and publication mapping.

Do not start desktop development until this milestone works with a generated package.

## Milestone 2 — Desktop batch CLI

Outcome:

```text
OME-TIFF/SVS files or folders
→ inspection
→ sequential batch conversion
→ RGB OME-TIFF
→ DZI
→ .plslide
→ batch report
```

Tasks:

1. Create `Enksodsoon/PathLab-Prep` with shared contracts and queue model.
2. File/folder discovery, duplicates and reader abstraction.
3. Sequential RGB OME-TIFF and DZI pipeline.
4. Persistent SQLite queue, restart recovery and batch reports.
5. Package generation compatible with server v1.

No full GUI or upload in this milestone.

## Milestone 3 — Automatic resumable upload

Outcome:

```text
completed desktop package
→ capability check
→ reservation
→ tus upload/resume
→ server import
→ ready_private
```

Tasks:

1. Desktop server client and capability negotiation.
2. Scoped credential storage abstraction.
3. tus upload, interruption and resume.
4. One conversion plus one upload pipeline.
5. Status polling, safe cleanup and private-preview launch.

Automatic public publication remains disabled.

## Milestone 4 — Desktop viewer and batch GUI

Outcome:

- Add files/folders and scan subfolders
- Batch preflight table
- Pan, zoom, series selection and physical scale
- Individual rectangle crop
- Shared presets and per-slide overrides
- Queue progress, pause, retry and cancel
- Server upload status and private preview

The GUI must call the already-tested conversion and upload services; it must not contain their core logic.

## Milestone 5 — VSI and real-format validation

Outcome:

- Complete VSI plus ETS dataset discovery
- Missing companion-file detection
- Primary-series review
- Real VS200 viewing, crop, 2× conversion and upload
- Real SVS and OME-TIFF mixed batch
- Compatibility evidence without committing source slides

A file format is supported only after real evidence exists.

## Milestone 6 — Packaging, legacy compatibility and hardening

Order:

1. Windows 10/11 x64 installer and portable build.
2. Current macOS Apple Silicon build.
3. Current macOS Intel build where available.
4. Windows 8.1 x64.
5. Windows 7 SP1 x64 investigation.
6. macOS 10.15, 10.14 and 10.13 Intel investigation.
7. Device pairing and revocation.
8. Backup/restore and public-mapping reconstruction.
9. Malicious-package, low-disk, restart and load evidence.
10. License and native-dependency inventory.

Do not call an older OS supported until actual launch, viewing, batch conversion, upload and queue-recovery evidence exists.

## Task-size rule

Each Codex task should normally:

- Have one observable result.
- Touch roughly 3–8 related files.
- Include focused tests.
- End in one focused commit.
- Stop after reporting evidence.

If a task grows beyond this size, split it before implementation rather than continuing indefinitely.