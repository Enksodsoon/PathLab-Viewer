# Study Coach closed-pilot operations

Study Coach is an educational, pseudonymous feature. It is not clinical software, a diagnostic tool, an assessment certification, or evidence of improved learning.

## Ownership and release boundaries

- Viewer owns Study Pack authoring, faculty preview, publication, courses, and learner Study Mode. Forge only prepares slides and uploads accepted static DZI content.
- `PATHLAB_STUDY_MODE_ENABLED`, `PATHLAB_STUDY_COACH_AI_ENABLED`, and `PATHLAB_STUDY_COACH_AI_PILOT_ENABLED` default to `false`.
- Deterministic scoring, faculty hints, explanations, and sources do not depend on AI.
- The checked TRACE-SIM manifest remains truthfully unapproved and synthetic-only. The separate `closed_pilot_unapproved` authorization can expose it only to an acknowledged private course.
- Public AI activation remains unavailable. Merge, deployment, pilot activation, physical-device qualification, capacity certification, and public approval are separate decisions.

## Exact private artifact

The model binary is not committed to Git. Install it atomically under the configured private data root:

```text
pathlab-viewer install-study-model --artifact C:\private\trace-sim.int8.onnx
```

Installation rejects the wrong name, byte size, or SHA-256. The accepted artifact is exactly 3,257,665 bytes with SHA-256 `9ca7e812951712eb29fd24c1fbf825afdb0b8a743ed941d96e186dab4d90c8a1`; its checkpoint identity is `2d625b1fad5c97584e1f7c69c3a95a6761fd934adaf17b1cecce329247e9fa0d`.

The browser runtime is pinned to ONNX Runtime Web 1.27.0 because npm does not publish a stable 1.29.0 package. It runs single-threaded WASM in a dedicated worker with no WebGPU, CDN, cross-origin isolation, or server inference. A future runtime change requires regenerated content hashes and exact-runtime known-vector evidence.

## Deployment and private-pilot sequence

1. Back up the database and deploy with all three flags disabled.
2. Apply migrations through `20260821_0023`; verify `/readyz` and `/livez`.
3. Install the exact artifact and confirm the installation command succeeds.
4. Enable Study Mode, keeping both AI flags disabled, and author/preview an immutable pack in Viewer.
5. Complete privacy review and owned or borrowed physical-device checks.
6. Enable both AI flags only for one acknowledged `closed_pilot_trace_sim` course. Generate invitations only after acknowledgement.
7. Confirm learner preparation passes model/WASM hashes, exact-runtime known vectors, persistence/offline reload, timeout handling, and worker-memory checks before opt-in appears.
8. Monitor API health, aggregate readiness/fallback/action counts, purge jobs, and server resource deltas. Never add learner-level AI telemetry.

Capacity certification uses `tests/load/study_coach_capacity.js` against a non-production course with 500 one-time invitations. Record error rate and p95 together with server CPU, RAM, database, connection-pool, and disk deltas; a script pass alone is not certification.

## Rollback and privacy

Disable AI first; learners immediately retain deterministic Study Mode. Disable Study Mode and revoke sessions only if needed. Retain or purge pseudonymous progress according to the shortened course policy, and purge dependent course data before any migration downgrade. Never persist learner/action associations, local feature records, coordinates, answers, model outputs, or reasons.
