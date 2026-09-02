# Preserve Imaging authority and evict rebuildable bytes

Imaging Control will expire rejected uploads within 24 hours, incomplete resumable uploads within seven days, and Trash within 30 days. Deterministically rebuildable DZI, OME-Zarr, DICOM, and tile representations remain outside backups and are pressure-evictable; Private Result Artifacts have a two-year ceiling after workflow closure, while Source Assets, non-rebuildable annotations, and provenance require annual custody review and have a seven-year ceiling after their last authorized purpose closes.
