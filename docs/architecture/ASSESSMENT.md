# PathLab Assessment

PathLab Assessment is a manual-first assessment authoring and delivery product for pathology slides. The approved contract is `pathlab.assessment/1`; drafts remain editable JSON documents, while published definitions and learner manifests are immutable and separately checksummed.

The feature and its dedicated service role are disabled by default. Production activation requires PostgreSQL, identity governance, backup/restore evidence, exact-release capacity certification, staged pilots, and explicit approval. Assessment does not import Study Coach, TRACE-SIM, AI, or `onnxruntime-web` code.

Practice is browser-local and anonymous. Formative supports anonymous aggregate-only or rostered participation. Quiz/Test is roster-only. Static DZI/JPEG delivery is administration-scoped and served directly by Caddy; ordinary tiles never query FastAPI or PostgreSQL.

Capability progress is recorded independently as `NOT_IMPLEMENTED`, `BUILT`, `SYNTHETICALLY_VERIFIED`, `PILOT_VALIDATED`, and `PRODUCTION_CERTIFIED`. Local tests do not establish capacity or production certification.

Current state is `BUILT`: local implementation and regression checks are complete. Protected 500-seat execution, pilots, deployment, and activation remain unperformed, so capacity evidence remains `NOT_EVALUABLE` and the production flag remains false.
