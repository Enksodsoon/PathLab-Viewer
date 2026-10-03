# Annotation Inspector dismissal during save

Labels: wayfinder:decision
Status: candidate; protected delivery and released verification pending
Owner: root

## Evidence and callers

On signed-in production bd69848 at 320x568, the Inspector reopened after Undo, Redo and manual save recovery despite having been closed. Save and reload persistence passed separately; no data loss was observed.

At current main ae9b1ac, AnnotationStore.makeSnapshot clones the selection Set on every emit, including setAutosaveStatus and acknowledgement. AnnotationWorkspace opens the Inspector whenever that Set reference changes and is nonempty. This overrides explicit dismissal even when the selected IDs are unchanged. Two regressions reach the actual selected-annotation Save action and fail at the unexpected reopen, at widths320 and1200. Earlier fixture attempts failed before that assertion and are retained separately.

## Repair

Key the automatic opening effect by the ordered selected IDs. Preserve ordering because the first selected ID is primary. Save status, geometry and history changes with the same selection leave the panel dismissed; selecting a different annotation still opens it. Store snapshots remain immutable. Permissions, autosave acknowledgement, modal focus handling and desktop nonmodal behavior remain unchanged.

## Verification

Annotation workspace, stability, store and autosave:69passed; complete frontend494passed in81files. Four browser targets pass the controlled pending-request and acknowledgement regression at320x568. Positive controls verify different selections open the Inspector at desktop and mobile widths. Frontend lint/build and repository/security/software inventory validation pass. Strict software releaseAdmission remainsBLOCKED. Complete annotation responsive matrix:64passed across Chromium,Firefox,WebKit and mobile Chromium, zero retries. Protected CI and production verification remain pending. Existing mocked tile proxy ECONNREFUSED diagnostics and JSDOM navigation warning are retained separately from assertions.

Ignored receipts: var/remediation-evidence/annotation-inspector-red-path.log, annotation-inspector-green.log, annotation-inspector-native.log. Live bd mobile receipt is production-bd69848-mobile-annotation.json; it proves save/recovery/reload, not deployment of this candidate.
