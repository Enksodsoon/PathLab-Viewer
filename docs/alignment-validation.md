# Slide alignment validation

Alignment is tissue independent by design, but release claims are limited to independently annotated tissue and stain combinations that pass this protocol. Renal examples alone do not qualify a general release.

Keep patient manifests outside the repository. Each private JSON manifest contains a `landmarks` array. A landmark record uses `eligible` to identify an anatomical point with a real counterpart, `errorUm` for the physical mapped-point error or `null` when the software rejected it, and `wrongStructure` when a confident result selected a different structure.

Run `python scripts/evaluate_alignment.py private-manifest.json --output private-report.json`. Qualification requires median error at most 50 µm, p95 at most 100 µm, coverage of at least 80% of eligible landmarks, and zero confident wrong-structure matches. The evaluator exits with status 2 when those gates are not met.

Freeze settings after the Alignment 1 development set. Evaluate Alignment 2 without tuning, then add patient-separated non-renal epithelial or glandular, lymphoid, and stromal cases covering resections, small biopsies, H&E, several IHC patterns, and special stains. Report each tissue and stain combination separately. Include absent counterparts, sparse staining, folds, repeated fragments, unrelated tissue, and frozen specimens when measuring rejection behavior.

Capacity qualification is separate from registration accuracy. Run staged 25, 100, and 300-viewer tests with two and four panes, ending with a 60-minute 300-viewer run. Record tile p95, request failures, and readiness failures; the targets are below 500 ms, below 0.1%, and zero, respectively.
