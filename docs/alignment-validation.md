# Slide alignment validation

Alignment is tissue independent by design, but release claims are limited to independently annotated tissue and stain combinations that pass this protocol. Renal examples alone do not qualify a general release.

Keep patient manifests outside the repository. Each private JSON manifest contains a `landmarks` array. A landmark record uses `eligible`, `movingPoint` and `referencePoint` in original slide pixels, the saved `registration` record, `referenceMicronsPerPixel: [x, y]`, and an independently reviewed `wrongStructure` flag. Errors are computed through accepted map cells using per-axis calibration. Pre-entered `errorUm` values cannot qualify a result; unsupported cells count against coverage, and invalid inputs block qualification.

Run `python scripts/evaluate_alignment.py private-manifest.json --output private-report.json`. Qualification requires median error at most 50 µm, p95 at most 100 µm, coverage of at least 80% of eligible landmarks, and zero confident wrong-structure matches. The evaluator exits with status 2 when those gates are not met.

Both Alignment 1 and Alignment 2 have influenced development and are regression sets. Freeze settings before evaluating a fresh patient/specimen-separated cohort, then add independently annotated non-renal epithelial or glandular, lymphoid, and stromal cases covering resections, small biopsies, H&E, several IHC patterns, and special stains. Report each tissue and stain combination separately. Include absent counterparts, sparse staining, folds, repeated fragments, unrelated tissue, and frozen specimens when measuring rejection behavior.

Capacity qualification is separate from registration accuracy. Run staged 25, 100, and 300-viewer tests with two and four panes, ending with a 60-minute 300-viewer run. Record tile p95, request failures, and readiness failures; the targets are below 500 ms, below 0.1%, and zero, respectively.


The component refinement pass reads bounded regions from existing DZI levels (maximum 4096 pixels per side), keeps exact power-of-two pixel-coordinate transforms, and rejects multiple plausible component assignments. Outline-only proposals remain approximate. Component-pair counts report completed attempts; they are not anatomical landmarks or patch-validation counts. Synthetic coordinate and ambiguity tests do not establish cross-stain accuracy. The development H&E–PAS experiments remain rejected.
