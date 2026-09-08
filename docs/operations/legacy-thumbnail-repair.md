# Repair legacy missing thumbnails

Some older static-DZI derivatives have a working pyramid but no `thumbnail.jpg`.
The current prepared-package validator rejects that condition for new uploads.
This explicit offline repair recovers an overview from one existing pyramid
tile (at most 512 pixels per dimension), strips metadata while encoding JPEG,
updates derivative accounting, and adds hardlinks to existing matching public,
individual and Assessment deliveries. It preserves their URLs and slide tiles.
Existing thumbnails are never replaced. Ordinary startup does not run repair.

Before execution, retain a verified backup, close Assessment and Classroom
sessions, drain workers, and stop all application services. PostgreSQL may remain
running. Run the pinned release's `deploy/scripts/repair-legacy-thumbnails.sh` as
the normal deployment operator. The wrapper refuses running application services;
the reconciliation transaction additionally rejects active worker, Classroom and
Assessment records. Do not bypass the wrapper to repair a live application.

The command reports `thumbnails_repaired`. Missing or mismatched overview tiles,
unsafe paths, insufficient storage, or mismatched delivery descriptors stop the
operation. Repairs are additive and retryable: if interrupted after a file was
installed, rerun offline reconciliation to finish accounting and delivery links.
Do not delete existing derivatives or rotate publication grants to retry.

Restart the original service profile. Verify readiness, the authenticated
library images, existing shared URLs and a slide-backed learner assessment.
Record the release, repaired count and browser results. Successful thumbnail
maintenance does not constitute PostgreSQL cutover or capacity qualification.
