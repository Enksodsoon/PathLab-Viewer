# Study Coach public beta operations

Study Coach is an educational, pseudonymous feature. It is not clinical software, a diagnostic tool, an assessment certification, or evidence of improved learning.

## Release boundaries

- `PATHLAB_STUDY_MODE_ENABLED` and `PATHLAB_STUDY_COACH_AI_ENABLED` default to `false`.
- Deterministic scoring, faculty hints, explanations, and sources do not depend on AI.
- The checked TRACE-SIM release manifest is deliberately not approved. No model binary is in this repository, so AI activation fails closed.
- The model may be added only after its license, provenance, exact artifact/runtime hashes, known-vector outputs, privacy review, and physical-device results are approved with status `public_beta_bounded_safe_actions`.
- Merge, deployment, Study Mode activation, AI activation, device qualification, and 500-learner capacity certification are separate decisions.

## Deployment sequence

1. Back up the database and deploy with both flags disabled.
2. Apply migrations through `20260821_0022` and check `/readyz` and `/livez`.
3. Enable Study Mode only for preparation and import an immutable faculty-previewed Study Pack from Forge.
4. Complete privacy review and owned/borrowed physical-device checks.
5. Run `tests/load/study_coach_capacity.js` against a non-production certification course with exactly 500 one-time invitations. Record API errors and p95 plus server CPU, RAM, database, connection-pool, and disk deltas.
6. Activate one deterministic beta course. Enable local AI separately only after its release and per-device preparation gates pass.

The capacity script requires `PATHLAB_BASE_URL`, `PATHLAB_STUDY_INVITATIONS_CSV`, `PATHLAB_STUDY_TASK_ID`, and `PATHLAB_STUDY_ANSWER`. Its thresholds are error rate below 0.1% and submission p95 below 500 ms. A successful script run is not sufficient without the recorded server deltas and an explicit check for database-lock, pool, and stream exhaustion.

## Rollback and privacy

Disable AI first, then Study Mode if necessary. Revoke learner sessions before any migration downgrade. Retain or purge pseudonymous progress according to the shortened course policy; dependent course data must be purged before downgrade. The hourly purge worker keeps due-data removal inside the six-hour requirement. Never add learner-level AI telemetry to operational monitoring.
