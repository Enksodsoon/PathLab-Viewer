# Audit and Operations

This context owns tamper-evident governance history, bounded operational observations, backup generations, restoration evidence, and production-claim evidence without becoming the authority for product-domain state.

## Language

**Audit Record**:
An append-only projection of an authoritative domain or governance transition, linked to its source event and integrity chain.
_Avoid_: Log line, activity entry

**Audit Integrity Chain**:
A partition-scoped monotonic sequence in which each Audit Record commits its predecessor hash, source outbox identity, canonical payload hash, and current record hash.
_Avoid_: Checksum column, blockchain

**Audit Checkpoint**:
A daily or release-boundary signed statement of partition heads, sequence ranges, gaps, verification result, and Audit Key Version copied to the Backup Target.
_Avoid_: Log archive, signature file

**Operational Log**:
A bounded diagnostic observation used to operate or investigate the platform but not to prove domain truth.
_Avoid_: Audit trail, event history

**Operational Metric**:
A local OpenMetrics observation scraped every 30 seconds, retained raw for at most seven days and as five-minute aggregates for at most 13 months.
_Avoid_: Telemetry event, analytics

**Diagnostic Trace**:
A local error-triggered or no-more-than-one-percent sampled request path retained for at most 24 hours and never exported automatically.
_Avoid_: Audit span, user journey

**Operator Alert**:
A durable local notification derived from a named operational rule, acknowledged in PathLab and optionally copied through an Institution-supplied notification adapter.
_Avoid_: Email alert, log warning

**Security Incident Record**:
A governed package of detections, decisions, containment actions, and evidence for one suspected or confirmed security event.
_Avoid_: Error report, alert

**Backup Generation**:
One encrypted, integrity-checked restore point plus the WAL range required to recover authoritative stores within its declared objective.
_Avoid_: Database copy, archive folder

**Backup Target**:
An Institution-owned or donated off-host disk or NAS in an Approved Data Location, physically independent of the production host and capacity-qualified for the complete backup window.
_Avoid_: Backup folder, cloud bucket

**Backup Freshness State**:
The current HEALTHY, STALE, UNAVAILABLE, or CAPACITY_BLOCKED result derived from acknowledged WAL, base backup, object manifest, integrity, and target-capacity evidence.
_Avoid_: Last backup time, backup enabled

**Restore Drill**:
A controlled recovery of a Backup Generation whose checks, timing, omissions, and result are preserved as evidence.
_Avoid_: Backup test, dry run

**Restore Evidence Window**:
The required recency of daily acknowledgement verification, weekly random-time PITR, monthly object sampling, and release-bound plus quarterly replacement-host Restore Drills.
_Avoid_: Backup schedule, disaster-recovery policy

**Qualification Evidence**:
Immutable measurements and artifacts supporting one named Qualification Claim on one exact release and deployment profile.
_Avoid_: Benchmark result, test log

## Retention ceilings

- Operational Logs expire no later than 30 days after collection.
- Raw Operational Metrics expire no later than seven days and their five-minute aggregates no later than 13 months.
- Diagnostic Traces expire no later than 24 hours.
- Security Incident Records expire no later than two years after closure.
- Governance receipts and authoritative Audit Records expire no later than seven years after their source event.
- The continuous PostgreSQL WAL pool retains every segment needed from the oldest eligible daily anchor through every target in the latest rolling seven days: at least seven days plus the qualified daily-anchor interval of no more than 26 hours, with a hard maximum segment age of nine days. WAL sealed into an older discrete Backup Generation follows that generation's independent expiry.
- Encrypted Backup Generations expire no later than 35 days after creation.
- Restore Drill reports expire no later than two years after completion.
