# PathLab Viewer OME-TIFF WSI Implementation Plan

Implement the approved design in ten independently testable milestones: repository setup; persistence/authentication; storage/quota; resumable ingestion; OME validation/DZI conversion; worker/lifecycle; admin UI; public viewer; OCI deployment/recovery; acceptance evidence and pull request.

Every behavior follows red-green-refactor. `main` remains unchanged; implementation lands through `codex/ome-tiff-wsi-viewer` and a pull request.
