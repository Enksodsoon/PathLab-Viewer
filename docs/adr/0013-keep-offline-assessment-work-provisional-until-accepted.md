# Keep offline Assessment work provisional until accepted

During a Zero-Cash host outage, an Attempt may continue in an encrypted bounded Provisional Journal, but PathLab will not represent that work as submitted, graded, or durable until idempotent replay commits it to PostgreSQL with corresponding audit outbox evidence. Server-authoritative deadlines, monotonic Response Revisions, and an immutable Submission Receipt distinguish accepted work from local recovery material.
