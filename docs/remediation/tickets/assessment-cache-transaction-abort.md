# Assessment cache transaction abort

Labels: wayfinder:ticket

At7db6f4b, successful IndexedDB put followed by transaction.abort rolls back the write without an error event. cacheAssessmentDraft only handles completion and error, so its promise remains pending and the builder cannot display the recovery-unavailable notice. Actual Chromium, Firefox and WebKit reproduce this; the record remains absent after rollback.

Handle transaction abort for both reads and writes, close opened connections in finally, and resolve reads only after transaction completion. Request success alone does not establish a completed transaction. Keep database schema and server optimistic revision contracts unchanged.

Twelve zero-retry browser cases pass15.5seconds across four projects. They abort actual read/write transactions after successful requests, verify rejection and connection closure, retain a previously committed control, and verify the recovery-unavailable notice without interfering with server acknowledgment. The first UI test expected the notice before any edit triggered caching; this fixture ordering error is retained separately. The corrected test triggers the edit first. Build6.36seconds and changed-file lint pass. Affected checks and renewed review pending.

Ignored receipts: var/cache-abort-probe-red.log, var/cache-abort-probe-green.log, var/cache-transaction-browser.log, var/cache-transaction-browser-final.log and var/cache-transaction-build.log.

No blocked-upgrade, complete offline, cross-write ordering, production transaction-abort or clinical qualification claim. This candidate follows PR301 and requires exact-head gates, protected release and live verification.

Independent old-source Chromium read-abort red returns resolved instead of AbortError after request success; candidate restored in finally. Affected52tests6files pass40.24seconds. Read red receipt: var/cache-transaction-read-red.log. Final correction review pending.

Renewed independent review clears the corrected test and reports no remaining Critical, Important or Minor findings. Fresh hosted gates and protected delivery required.

Complete first frontend run544pass/1Classroom polling failure retained. Isolated Classroom3pass; final two-worker complete suite545tests85files282.53seconds passes. Failure cause remains unproven; no Classroom product change. Fresh hosted gates and protected delivery remain required.
