# Classroom-protected background jobs

> **Precedence status: `BASELINE_ONLY`.** This default-off runtime guard records
> current implementation behavior only. The [Architecture Precedence
> Register](./ARCHITECTURE_PRECEDENCE.md), [Live Learning
> context](../contexts/live-learning/CONTEXT.md), and [Zero-Cash
> Runtime](./ZERO_CASH_RUNTIME.md) control destination scheduling, isolation,
> capacity, and activation conflicts.

This contract is disabled by default through
`PATHLAB_CLASSROOM_PROTECTION_ENABLED=false`. It does not change the deployed
Classroom until separately activated and verified.

When enabled, the database-backed runtime guard serializes Classroom start and
worker job admission. A live or draining Classroom blocks queued background
jobs, requests cancellation of running jobs, and blocks tus upload admission.
Ending a live session starts a 120-second cooldown. The worker releases blocked
jobs only after the cooldown expires and the database remains readable.

The first implementation slice stops running conversion jobs at the validation
boundary. A conversion already inside native libvips is allowed to finish; live
session creation remains in `CLASSROOM_DRAINING` until that job reaches a
terminal state. Isolated child-process termination and resumable checkpoints
are later work and must not be claimed by this slice.

The worker performs no background maintenance while protection is active. It
uses short database transactions and never shares a database session with the
Classroom SSE generator. Upload admission is checked by Caddy before forwarding
requests to tusd and again by the tus pre-create hook.

Evidence produced by local or CI tests is synthetic engineering evidence. It is
not capacity certification, production validation, or clinical qualification.
