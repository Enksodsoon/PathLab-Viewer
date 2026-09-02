# Stage learner-mode transitions over thirty minutes

A scheduled learner-facing Mode Reservation will stop admitting conflicting heavy work at T-30 minutes, checkpoint and drain it by T-20, start reserved services at T-15, run dependency and synthetic-transaction checks at T-10, and issue an auditable Mode Readiness Receipt at T-5. A NO-GO result prevents participant admission, while completion grants a 15-minute reconciliation window for outboxes, provisional journals, receipts, and worker drain before resources can be released or reassigned.
