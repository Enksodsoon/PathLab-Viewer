# Findings register

954 report sections retain aliases and source hashes. Counts describe sections, not distinct bugs. Reviewed PRs 267–270 and 272 are deployed at `3cb26bc`; authenticated checks of the latest release and two external security facts keep the campaign open. The 29 separate security subclaims retain their individual dispositions.

[findings.json](findings.json) records evidence and canonical groups. [REPAIR_COVERAGE.md](REPAIR_COVERAGE.md) tracks repair coverage. [Remaining closure](tickets/remaining-campaign-closure.md) tracks release evidence and open qualification. The latest release passed a synthetic Classroom tile reload; signed-in Library, upload, teacher and Study checks remain open.

| Disposition | Source sections |
| --- | ---: |
| confirmed | 300 |
| duplicate | 26 |
| false positive | 111 |
| fixed upstream | 189 |
| hardening | 328 |

| Source | Line | Alias | Claim | Disposition |
| --- | ---: | --- | --- | --- |
| BUG_REPORT.md | 25 | section-25 | Key Finding Categories | duplicate |
| BUG_REPORT.md | 38 | section-38 | 2. Master Bug & Vulnerability Register | duplicate |
| BUG_REPORT.md | 434 | SEC-01 | [SEC-01] Global RBAC Capability Bypass on Administrative Subsystems | fixed upstream |
| BUG_REPORT.md | 480 | SEC-02 | [SEC-02] Privilege Escalation & Last-Owner Deletion Race in Identity Governance | fixed upstream |
| BUG_REPORT.md | 521 | SEC-03 | [SEC-03] In-Memory Rate Limiting & Unthrottled Pairing Endpoint | fixed upstream |
| BUG_REPORT.md | 547 | SEC-04 | [SEC-04] Caddy Directive Ordering Bypassing Internal Route Denials | fixed upstream |
| BUG_REPORT.md | 580 | SEC-05 | [SEC-05] Native Image Parser Execution Without Sandbox Isolation | hardening |
| BUG_REPORT.md | 598 | SEC-06 | [SEC-06] Path Boundary Validation Bypass in delivery.py When Redirects Disabled | hardening |
| BUG_REPORT.md | 634 | SEC-07 | [SEC-07] Unrestricted Proxy Header Trust in Docker Compose API Command | hardening |
| BUG_REPORT.md | 648 | CONC-01 | [CONC-01] Non-Atomic Desktop Pairing Approval & Leaked Expired Handshakes | fixed upstream |
| BUG_REPORT.md | 690 | CONC-02 | [CONC-02] Missing Transaction Lock on PostgreSQL During Password Recovery Throttle | fixed upstream |
| BUG_REPORT.md | 722 | PERF-01 | [PERF-01] $O(N^2)$ In-Memory Descendant Traversal & Unbounded Slide Loading in Classroom | fixed upstream |
| BUG_REPORT.md | 759 | PERF-02 | [PERF-02] Synchronous File Hashing Blocks Async Event Loop in Study Asset Delivery | false positive |
| BUG_REPORT.md | 786 | AUTH-01 | [AUTH-01] Missing Teacher Ownership on Classroom Sessions | fixed upstream |
| BUG_REPORT.md | 810 | BUG-06 | [BUG-06] Unhandled IndexError on OME-XML with Zero Image Elements | false positive |
| BUG_REPORT.md | 832 | BUG-07 | [BUG-07] Stale Job Recovery Skips Jobs with Null Heartbeats | hardening |
| BUG_REPORT.md | 858 | FE-01 | [FE-01] Missing Top-Level React Application Error Boundary | fixed upstream |
| BUG_REPORT.md | 883 | FE-02 | [FE-02] Session Expiration Discards Private Slide Destination (returnTo) | fixed upstream |
| BUG_REPORT.md | 907 | FE-03 | [FE-03] Indistinguishable Slide Loading Errors & Missing Retry | fixed upstream |
| BUG_REPORT.md | 928 | FE-04 | [FE-04] Direct Exposure of Internal Docker Commands in Recovery UI | hardening |
| BUG_REPORT.md | 943 | FE-05 | [FE-05] Classroom Setup Lacks Folder Search, Pagination, & State Validation | fixed upstream |
| BUG_REPORT.md | 955 | FE-06 | [FE-06] Unhandled localStorage & sessionStorage Exceptions in Private Browsing | confirmed |
| BUG_REPORT.md | 987 | FE-07 | [FE-07] Missing Login Return URL in Desktop Connect Workflow | confirmed |
| BUG_REPORT.md | 1001 | FE-08 | [FE-08] IndexedDB Connection Leak on Transaction Error in authoringStore.ts | confirmed |
| BUG_REPORT.md | 1034 | DEV-01 | [DEV-01] dev.ps1 Root-Relative Path Resolution Bug | false positive |
| BUG_REPORT.md | 1059 | ENV-01 | [ENV-01] OneDrive File Locking Interference on SQLite WAL & Derivative Tiles | hardening |
| BUG_REPORT.md | 1074 | OPS-01 | [OPS-01] Deployment Script Failures on noexec Filesystems & Unbounded Capacity Controller Recovery | fixed upstream |
| BUG_REPORT.md | 1097 | OPS-02 | [OPS-02] Missing Deterministic Software Inventories (SBOM) & Security Baseline Drift | fixed upstream |
| BUG_REPORT.md | 1121 | OPS-03 | [OPS-03] Alembic Path Separator Deprecation in alembic.ini | hardening |
| BUG_REPORT.md | 1134 | DATA-01 | [DATA-01] PostgreSQL Signed 32-bit Integer Overflow on Whole Slide Image and Ingest Byte Columns | fixed upstream |
| BUG_REPORT.md | 1166 | CONC-03 | [CONC-03] Storage Accounting Quota Bypass via Omission of PostgreSQL Advisory Locking | fixed upstream |
| BUG_REPORT.md | 1202 | REL-01 | [REL-01] Slide Deletion Worker Crash Loop & Storage Desync on Classroom Slides (RESTRICT Foreign Key) | confirmed |
| BUG_REPORT.md | 1240 | FE-09 | [FE-09] Classroom Teacher Page Unwrapped sessionStorage Failures in Safari Private Browsing | fixed upstream |
| BUG_REPORT.md | 1256 | FE-10 | [FE-10] IndexedDB Connection Leaks in Study Store | confirmed |
| BUG_REPORT.md | 1291 | BUG-08 | [BUG-08] Stale Job Recovery Query Omits Crashed checkpointing Jobs | hardening |
| BUG_REPORT.md | 1326 | TIME-01 | [TIME-01] Timestamp Offset Corruption via Unsafe replace(tzinfo=UTC) | fixed upstream |
| BUG_REPORT.md | 1346 | SEC-08 | [SEC-08] Ineffective Revocation / Information Disclosure on Public Shares | fixed upstream |
| BUG_REPORT.md | 1385 | BUG-09 | [BUG-09] Sharing Outright Crash / TypeError on Expired Shares | fixed upstream |
| BUG_REPORT.md | 1422 | CONC-04 | [CONC-04] Library Share Activation Race Condition & Duplicate Active Shares | fixed upstream |
| BUG_REPORT.md | 1468 | FE-11 | [FE-11] Boolean Polygon Clipping Crash on Degenerate Holes | hardening |
| BUG_REPORT.md | 1520 | FE-12 | [FE-12] Student Classroom Join Broken by Unhandled Notebook IndexedDB Failure | confirmed |
| BUG_REPORT.md | 1566 | FE-13 | [FE-13] Classroom Invite Page Destroys Active Review Session on Transient Poll Failure | confirmed |
| BUG_REPORT.md | 1608 | SEC-09 | [SEC-09] CSV Formula Injection in Annotation Measurement Exports | fixed upstream |
| BUG_REPORT.md | 1662 | SEC-10 | [SEC-10] Classroom SSE Teacher Event Stream Unchecked Authorization Zero-Day | fixed upstream |
| BUG_REPORT.md | 1717 | SEC-11 | [SEC-11] Unauthenticated & Unthrottled Study Invitation Code Brute-Force | hardening |
| BUG_REPORT.md | 1745 | SEC-12 | [SEC-12] Unmetered Request Body Size on Public & Student Endpoints Permitting Memory Exhaustion DoS | fixed upstream |
| BUG_REPORT.md | 1788 | SEC-13 | [SEC-13] Revoked Classroom Sessions Retain Individual Derivative Tiles on Disk & Caddy Edge | confirmed |
| BUG_REPORT.md | 1823 | SEC-14 | [SEC-14] Trashed Slide OME-TIFF File Download & Tile Viewing Authorization Leak | fixed upstream |
| BUG_REPORT.md | 1864 | SEC-15 | [SEC-15] Caddy Internal Reverse Proxy Global Root (/) Exposure Risk | hardening |
| BUG_REPORT.md | 1900 | CONC-05 | [CONC-05] Concurrent Study AI Event Reporting Triggers Unique Constraint Crashes & Lost Updates | confirmed |
| BUG_REPORT.md | 1958 | CONC-06 | [CONC-06] Study Course Learner Limit Admission Race Condition on Concurrent Redemption | confirmed |
| BUG_REPORT.md | 1999 | PERF-03 | [PERF-03] Synchronous Unbounded os.walk() in Desktop Ingest Storage Admission Freezes Event Loop | false positive |
| BUG_REPORT.md | 2036 | TIME-02 | [TIME-02] Unsafe .replace(tzinfo=UTC) in Study Pack & Desktop Serializers Corrupting Timestamp Offsets | fixed upstream |
| BUG_REPORT.md | 2063 | FE-14 | [FE-14] Unwrapped localStorage and sessionStorage in Theme, Shell Preferences, and API Client Crashes Web App in Private Browsing | confirmed |
| BUG_REPORT.md | 2114 | DATA-02 | [DATA-02] Orphaned Derivative Directories Leaking Disk Storage on Unexpected Ingest Finalizer Exceptions | confirmed |
| BUG_REPORT.md | 2166 | SEC-16 | [SEC-16] Unauthenticated Global Account Lockout Denial-of-Service via In-Memory Username Throttling | hardening |
| BUG_REPORT.md | 2200 | REL-02 | [REL-02] Classroom Teaching Annotations Exceed Hardcoded 4 KiB SSE Event Buffer Limit | false positive |
| BUG_REPORT.md | 2248 | SEC-17 | [SEC-17] Unauthenticated & Unthrottled Global Classroom Join Queue Lock Starvation Denial-of-Service | hardening |
| BUG_REPORT.md | 2296 | SEC-18 | [SEC-18] Unthrottled Student Pin & Control-Request Queue Flooding Forces Teacher SSE Disconnection (Remote DoS) | confirmed |
| BUG_REPORT.md | 2340 | SEC-19 | [SEC-19] TRACE-SIM ONNX Model Installer Missing Exception Cleanup Leaves Partial Unverified Model Files on Disk | confirmed |
| BUG_REPORT.md | 2385 | DATA-03 | [DATA-03] PostgreSQL Migration Leaves Autoincrement Sequence Unsynced (duplicate key value violates unique constraint "desktop_sync_events_pkey") | fixed upstream |
| BUG_REPORT.md | 2451 | DATA-04 | [DATA-04] Permanent Deletion of Slides and Folders Omits Desktop Sync Deletion Events & Leaves Orphaned Shares | confirmed |
| BUG_REPORT.md | 2485 | TIME-03 | [TIME-03] Inconsistent Offset-Naive utcnow() in Annotations and Worker Breaks PostgreSQL Datetime Comparisons | fixed upstream |
| BUG_REPORT.md | 2520 | PERF-04 | [PERF-04] Full Table Distinct Join Scan on PublicationGrant During Every Folder Navigation Click | hardening |
| BUG_REPORT.md | 2553 | FE-15 | [FE-15] IndexedDbDraftStorage Permanent Rejection Caching & Missing Memory Fallback Freezes Annotation Studio | hardening |
| BUG_REPORT.md | 2600 | SEC-20 | [SEC-20] Uninitialized & Deadlocked Runtime Protection Mode Bricks Background Processing and All Slide Uploads | confirmed |
| BUG_REPORT.md | 2635 | SEC-21 | [SEC-21] Unauthenticated & Unbounded Desktop Pairing Code Flooding Database Denial-of-Service | fixed upstream |
| BUG_REPORT.md | 2673 | CONC-07 | [CONC-07] Desktop Pairing Exchange Concurrency Race Issues Multiple Tokens for Single-Use Code | fixed upstream |
| BUG_REPORT.md | 2731 | CONC-08 | [CONC-08] Concurrent First AI-Event Submissions Crash with Unique Constraint Violation & Cause Lost Updates | confirmed |
| BUG_REPORT.md | 2775 | DATA-05 | [DATA-05] Slide Deletion Fails to Purge Published Derivative Directory (delivery/individual/{public_id}) Causing Permanent Storage Leak | confirmed |
| BUG_REPORT.md | 2808 | DATA-06 | [DATA-06] Desktop Library Synchronization Truncates Folders at 100 with No Pagination or Cursor | confirmed |
| BUG_REPORT.md | 2834 | DATA-07 | [DATA-07] Desktop Annotation Batch Silently Bypasses Optimistic Concurrency Control with Fake Auto-Merge | false positive |
| BUG_REPORT.md | 2855 | FE-16 | [FE-16] Stale Upload Reservation Retention Freezes Retry on Expired Upload Token | confirmed |
| BUG_REPORT.md | 2874 | FE-17 | [FE-17] Unwrapped sessionStorage in SharedViewerPage.tsx and study/api.ts Falsely Reports Valid Public Shares as Revoked / Missing in Safari Private Browsing | confirmed |
| BUG_REPORT.md | 2934 | BUG-10 | [BUG-10] Dynamic Tile Fallback Renderer Crashes on 16-bit, Alpha, and Multichannel OME-TIFF Slides with Unhandled pyvips.Error | false positive |
| BUG_REPORT.md | 2978 | PERF-05 | [PERF-05] recover_password() Executes Unindexed Full Table Scan Loading All Database Users into Python Memory | confirmed |
| BUG_REPORT.md | 3013 | SEC-22 | [SEC-22] Password Recovery Code-Validity Oracle via Differential Error Codes Bypasses Throttling | confirmed |
| BUG_REPORT.md | 3064 | SEC-23 | [SEC-23] 90-day DesktopCredential Survives Password Change / Recovery (Credential-Generation Gap) | fixed upstream |
| BUG_REPORT.md | 3082 | SEC-24 | [SEC-24] disable_membership Leaves Legacy-Admin Session Fully Valid | fixed upstream |
| BUG_REPORT.md | 3097 | SEC-25 | [SEC-25] TUS post-finish allow_expired=True Bypasses 1h Upload TTL | hardening |
| BUG_REPORT.md | 3112 | CONC-09 | [CONC-09] Conversion Staging PID-Only + Unconditional Stale-Wipe (TOCTOU / Data Loss) | hardening |
| BUG_REPORT.md | 3127 | CONC-10 | [CONC-10] Desktop Resumable Chunk Has No Lock + Trusts DB Offset + Unbounded Retry Flood | confirmed |
| BUG_REPORT.md | 3142 | CONC-11 | [CONC-11] Study Invitation Single-Use Double-Spend Race | confirmed |
| BUG_REPORT.md | 3157 | SEC-26 | [SEC-26] Public Share Manifest Leaks Trashed-Slide Metadata | fixed upstream |
| BUG_REPORT.md | 3172 | DATA-08 | [DATA-08] Share Publish / Rotate Commit-Then-Write Crash Window + Downtime | fixed upstream |
| BUG_REPORT.md | 3187 | BUG-11 | [BUG-11] Teacher Live State Silent Truncation (300 / 200, Newest Dropped) | false positive |
| BUG_REPORT.md | 3201 | SEC-27 | [SEC-27] Internal Tile-Service /_pathlab_ome/* Zero-Auth + No Trashed Check | hardening |
| BUG_REPORT.md | 3216 | SEC-28 | [SEC-28] Trashed-Slide Metadata / Annotation Read + Sync Bypass | hardening |
| BUG_REPORT.md | 3231 | SEC-29 | [SEC-29] Conversion Derivative Sanitize / Measure Symlink-Blind (Escape + TOCTOU) | fixed upstream |
| BUG_REPORT.md | 3245 | PERF-06 | [PERF-06] GET .../content Streaming FD Held Across Yield (Slow-Loris Leak) | hardening |
| BUG_REPORT.md | 3259 | SEC-30 | [SEC-30] Config Fail-Open: extra="ignore" + Placeholder Secret + Prod-Only Validation | hardening |
| BUG_REPORT.md | 3273 | OPS-04 | [OPS-04] Sticky CachedReadiness: /readyz Never Recovers Without Restart | false positive |
| BUG_REPORT.md | 3288 | BUG-12 | [BUG-12] read_protection_snapshot vs protection_snapshot Divergence (Uploads Open, Jobs Starved) | hardening |
| BUG_REPORT.md | 3304 | FE-18 | [FE-18] Unabortable TUS Upload + Unscoped resumeFromPreviousUpload | confirmed |
| BUG_REPORT.md | 3319 | FE-19 | [FE-19] Premature URL.revokeObjectURL + Detached Anchor Truncates Downloads | hardening |
| BUG_REPORT.md | 3334 | FE-20 | [FE-20] Manifest Fetch Not Abortable; Tile URL Mirrored to DOM | hardening |
| BUG_REPORT.md | 3351 | FE-21 | [FE-21] Router Catch-All Swallows 404 / Share-Invalid → Forced /admin | hardening |
| BUG_REPORT.md | 3365 | REL-03 | [REL-03] HeartbeatWriter._run Silent Death on Transient I/O Error | confirmed |
| BUG_REPORT.md | 3379 | CONC-12 | [CONC-12] TileCache.get_or_create Unbounded Event.wait() (Follower Hang) | hardening |
| BUG_REPORT.md | 3393 | OPS-05 | [OPS-05] reconcile_storage Single-Slide Raise Aborts Entire Run + Bricks Boot | hardening |
| BUG_REPORT.md | 3408 | SEC-31 | [SEC-31] delete_cookie Omits samesite/secure, Leaves Session Cookie Alive | false positive |
| BUG_REPORT.md | 3424 | CONC-13 | [CONC-13] Study pseudonym 32-bit Collision 500 (No Retry) | hardening |
| BUG_REPORT.md | 3439 | FE-22 | [FE-22] AnnotationWorkspace.triggerDownload Premature Revoke (Remaining Instance) | hardening |
| BUG_REPORT.md | 3453 | SEC-32 | [SEC-32] TileCache._reconcile Skips JPEG Validation (Persistent Poison) | hardening |
| BUG_REPORT.md | 3466 | OPS-06 | [OPS-06] Shared TileCache Root With Process-Local Accounting + Lying readyz | hardening |
| BUG_REPORT.md | 3478 | REL-04 | [REL-04] Worker delete Job Outside Try — Poison-Pill Hot Loop | confirmed |
| BUG_REPORT.md | 3488 | REL-05 | [REL-05] expire_incomplete_uploads .stat() Race Kills Worker Loop | confirmed |
| BUG_REPORT.md | 3498 | BUG-13 | [BUG-13] Classroom Auto-Expiry Skips Hub/Presenter/Prewarm Cleanup | confirmed |
| BUG_REPORT.md | 3508 | PERF-07 | [PERF-07] ClassroomHub Unbounded Per-Session Leak on Singleton | hardening |
| BUG_REPORT.md | 3518 | CONC-14 | [CONC-14] Concurrent Folder Moves Create Cycle → Infinite CTE DoS | confirmed |
| BUG_REPORT.md | 3530 | DATA-09 | [DATA-09] Unbounded sortOrder Overflows PG Integer | confirmed |
| BUG_REPORT.md | 3542 | FE-23 | [FE-23] OpenSeadragon open-failed Infinite Reconnect Storm | hardening |
| BUG_REPORT.md | 3552 | FE-24 | [FE-24] Freehand Unbounded Construction + Spread Stack Overflow | hardening |
| BUG_REPORT.md | 3564 | FE-25 | [FE-25] Upload Transport-Complete Lied as Slide-Complete + NaN Progress | confirmed |
| BUG_REPORT.md | 3576 | FE-26 | [FE-26] InviteDialog False Modal — No Trap/Inert/Restore | hardening |
| BUG_REPORT.md | 3586 | OPS-07 | [OPS-07] tusd + caddy Zero Healthcheck — Silent Upload Blackhole | hardening |
| BUG_REPORT.md | 3596 | SEC-34 | [SEC-34] Backups Plaintext — Zero Encryption (PHI Exfiltration) | hardening |
| BUG_REPORT.md | 3608 | SEC-35 | [SEC-35] Argon2 CPU-DoS on Impossible 129..1024-char Passwords | hardening |
| BUG_REPORT.md | 3618 | PERF-08 | [PERF-08] Unindexed sessions.user_id FK (Plus Siblings) | hardening |
| BUG_REPORT.md | 3628 | DATA-10 | [DATA-10] server_default vs Python default Drift + Bare-String Quoting | hardening |
| BUG_REPORT.md | 3638 | OPS-08 | [OPS-08] Migration Full-Table RAM Load + Non-Atomic Batches | hardening |
| BUG_REPORT.md | 3648 | FE-27 | [FE-27] persist() vs persisted() Confusion (Unsolicited Prompt) | hardening |
| BUG_REPORT.md | 3658 | FE-28 | [FE-28] capture() Drops Blob on Save Failure (No Feedback) | confirmed |
| BUG_REPORT.md | 3668 | FE-29 | [FE-29] Autosave Debounce Lost on Close (No Unload Flush) | hardening |
| BUG_REPORT.md | 3678 | FE-30 | [FE-30] Teacher SSE No error Handler (Stale Roster) | hardening |
| BUG_REPORT.md | 3688 | SEC-36 | [SEC-36] Caddy Security-Headers Gaps | hardening |
| BUG_REPORT.md | 3698 | OPS-09 | [OPS-09] Mutable :live Fallback Tag (No Digest Pin) | hardening |
| BUG_REPORT.md | 3708 | SEC-37 | [SEC-37] restore.sh World-Readable Staging + No Lock | hardening |
| BUG_REPORT.md | 3718 | OPS-10 | [OPS-10] Watchdog Unbounded Diagnostics (No Retention) | hardening |
| BUG_REPORT.md | 3728 | BUG-14 | [BUG-14] Uncaught SQLite FTS5 Query Syntax Errors Crash Library Search API with HTTP 500 | fixed upstream |
| BUG_REPORT.md | 3760 | CONC-15 | [CONC-15] LoginThrottle Lacks Mutex Synchronization Causing RuntimeError and Race Conditions | fixed upstream |
| BUG_REPORT.md | 3784 | REL-06 | [REL-06] FastAPI Lifespan Teardown Chain Aborts on Exception Leaking Singleton Lock | hardening |
| BUG_REPORT.md | 3820 | FE-31 | [FE-31] Unwrapped sessionStorage.setItem in ClassroomTeacherPage Locks Out Teacher with CLASSROOM_ALREADY_ACTIVE | fixed upstream |
| BUG_REPORT.md | 3848 | FE-32 | [FE-32] Asynchronous window.open + preview.document.write in Student Notebook Printing Crashes on Closed Tab | confirmed |
| BUG_REPORT.md | 3882 | SEC-38 | [SEC-38] Absence of Trusted Reverse Proxy IP Resolution in Rate Limiting Causes Global DoS | hardening |
| BUG_REPORT.md | 3908 | SEC-39 | [SEC-39] Windows Backslash & Drive-Letter Path Traversal in Prepared Ingest Unpacking Zero-Day | fixed upstream |
| BUG_REPORT.md | 3983 | SEC-40 | [SEC-40] CSV Formula Injection (CWE-1236) in Annotation Measurements Export API | fixed upstream |
| BUG_REPORT.md | 4033 | BUG-15 | [BUG-15] Missing Initial RuntimeGuard Row Causes Permanent Upload Blockade with HTTP 423 | hardening |
| BUG_REPORT.md | 4084 | BUG-16 | [BUG-16] Uncaught ValueError in Library Cursor Pagination Datetime Deserialization Returns HTTP 500 | confirmed |
| BUG_REPORT.md | 4127 | CONC-16 | [CONC-16] Concurrency Race Condition on Study Readiness and AI Event Reporting Unique Constraint | confirmed |
| BUG_REPORT.md | 4182 | FE-33 | [FE-33] Permanent SPA Robots Meta Tag Pollution in ViewerPage Blocks Search Engine Indexing | hardening |
| BUG_REPORT.md | 4224 | FE-34 | [FE-34] Uncaught DOMException in SharedViewerPage.select Crashes Shared Viewer on Safari Private Browsing | confirmed |
| BUG_REPORT.md | 4266 | REL-07 | [REL-07] Worker Missing Heartbeat During generate_dzi Causes Stale Recovery Race Condition & Dual-Worker Derivative Corruption | hardening |
| BUG_REPORT.md | 4312 | BUG-17 | [BUG-17] Unhandled Alpha and Multichannel Bands in generate_dzi Crashes Libvips with JPEG Conversion Error | false positive |
| BUG_REPORT.md | 4343 | REL-08 | [REL-08] Unhandled Windows File Locking / PermissionError in remove_slide Crashes Worker Process in Infinite Loop | confirmed |
| BUG_REPORT.md | 4397 | SEC-41 | [SEC-41] Missing Deletion Event in Desktop Sync Broadcast Leads to Zombie Local Slides & Folders | confirmed |
| BUG_REPORT.md | 4424 | DATA-11 | [DATA-11] Published Slide Trashing & Restoring Leaves State Desynchronized and Causes Public Route 404 | false positive |
| BUG_REPORT.md | 4457 | FE-35 | [FE-35] Client Autosave Acknowledgement Failure Deadlocks Mutation Queue in Perpetual Conflict | hardening |
| BUG_REPORT.md | 4494 | SEC-42 | [SEC-42] Cross-Device / Cross-Filesystem Link Failure (EXDEV) in Desktop OME Ingest Aborts Ingestion and Quarantines Files | hardening |
| BUG_REPORT.md | 4520 | FE-36 | [FE-36] Uncaught DOMException in OpenSeadragonViewer Crashes WSI Viewer in Safari Private Browsing | confirmed |
| BUG_REPORT.md | 4568 | FE-37 | [FE-37] Unwrapped sessionStorage.setItem in Study API Burns Single-Use Invitation Codes and Permanently Locks Out Learners | confirmed |
| BUG_REPORT.md | 4616 | FE-38 | [FE-38] Uncaught DOMException in StudyPage.tsx Locale Storage Crashes Study UI on Mount | confirmed |
| BUG_REPORT.md | 4657 | SEC-43 | [SEC-43] Cookie Attribute Mismatch in Study Withdrawal Leaves Persistent Session Cookie on HTTPS | false positive |
| BUG_REPORT.md | 4706 | BUG-18 | [BUG-18] Missing Parent Directory Creation in install_prepared_package Crashes on Fresh Deployments | fixed upstream |
| BUG_REPORT.md | 4746 | SEC-44 | [SEC-44] CLI Admin Creation and Password Reset Uncaught ValueError Traceback and Unvalidated Username | fixed upstream |
| BUG_REPORT.md | 4802 | DATA-12 | [DATA-12] IndexedDB Connection Leak on Transaction Error in Study Local Store | confirmed |
| BUG_REPORT.md | 4872 | DATA-13 | [DATA-13] Missing DesktopSyncEvent in Layer CRUD Operations Causes Desktop Sync Desynchronization and Conflict Lockout | confirmed |
| BUG_REPORT.md | 4922 | DATA-14 | [DATA-14] Trashing a Folder Leaves Child Slides in Invisible Orphaned State Deadlocking Permanent Deletion with HTTP 409 FOLDER_NOT_EMPTY | confirmed |
| BUG_REPORT.md | 4979 | SEC-45 | [SEC-45] Annotation Endpoints Omit Trashed Slide Check Permitting Mutation and Data Leakage on Trashed Clinical Slides | hardening |
| BUG_REPORT.md | 5015 | FE-39 | [FE-39] Premature database.close() on Request Success in Classroom Notebook Aborts Uncommitted Transactions | confirmed |
| BUG_REPORT.md | 5074 | FE-40 | [FE-40] IndexedDB Connection Leak on Transaction Error and Unhandled Storage Rejection in Study Pack Authoring | confirmed |
| BUG_REPORT.md | 5157 | BUG-19 | [BUG-19] Unescaped SQL Wildcard Characters in Library Tag Filtering Allows Wildcard Injection and Result Spoofing | confirmed |
| BUG_REPORT.md | 5199 | TIME-04 | [TIME-04] Offset-Naive Datetime Comparison in Desktop Sync Pagination Triggers TypeError / Database 500 Crash | fixed upstream |
| BUG_REPORT.md | 5246 | DATA-15 | [DATA-15] Trashed Slides Retained in Public Share Manifests Leaks Clinical Diagnoses and Breaks Shared Slides with HTTP 404 | fixed upstream |
| BUG_REPORT.md | 5339 | CONC-17 | [CONC-17] Missing Hub, Cooldown, and Presenter Cleanup on Natural Classroom Expiration and Synthetic Reset Causes SSE Connection Leaks and Sequence Desynchronization | confirmed |
| BUG_REPORT.md | 5419 | BUG-20 | [BUG-20] Shared JPEG Tables Stripping Omits DRI Marker Breaking Restart Interval Decoding in Native OME-TIFF Tiles | confirmed |
| BUG_REPORT.md | 5477 | TIME-05 | [TIME-05] Unhandled Offset-Naive Datetime Comparison in Share Delivery Manifest Route Causes TypeError Crash Resulting in 404 for All Expiring Shared Slides | fixed upstream |
| BUG_REPORT.md | 5525 | FE-41 | [FE-41] Premature Sequence Advancement on Stream Gap in Classroom Stream Sync Applies Out-of-Order Events During Background Resync | confirmed |
| BUG_REPORT.md | 5591 | CONC-18 | [CONC-18] Concurrent Task Submissions Race Past Monotonic Throttle Check Causing Unhandled Unique Constraint 500 Crash on uq_study_progress_task | confirmed |
| BUG_REPORT.md | 5659 | DATA-16 | [DATA-16] Expired Shares Remain Marked is_active=True Deadlocking Target Folder and Collection Re-Sharing with HTTP 409 SHARE_ALREADY_ACTIVE | fixed upstream |
| BUG_REPORT.md | 5705 | DATA-17 | [DATA-17] Deleted Collections and Trashed Folders Fail to Cascade Revoke Shares and Delivery Manifests Leaking Proprietary Slides | false positive |
| BUG_REPORT.md | 5742 | BUG-21 | [BUG-21] Event Sequences and Presence Expiry Handles Not Purged on Session Reset or Termination Causes Event Sequence Skew and Memory Leak | hardening |
| BUG_REPORT.md | 5774 | OPS-11 | [OPS-11] Tile Service Readiness Probe Performs Synchronous OME Index Parse and Full Directory Glob on Every Probe Inducing CPU Spikes and Service Outages | hardening |
| BUG_REPORT.md | 5803 | OPS-12 | [OPS-12] Worker Heartbeat Writer Lacks Exception Handling and Zero-Tolerance Clock Check Causes False-Positive Worker Restarts | confirmed |
| BUG_REPORT.md | 5842 | CONC-19 | [CONC-19] Absence of In-Flight Job Heartbeat During Long-Running generate_dzi Causes Stale Recovery Re-Queueing and Conversion Directory Collision | hardening |
| BUG_REPORT.md | 5885 | FE-42 | [FE-42] Tight-Loop Unbacked Retry in createClassroomSnapshotReconciler Spams API on Transient Version Lag and Aborts with Unrecoverable Rejection | hardening |
| BUG_REPORT.md | 5914 | FE-43 | [FE-43] Unhandled Promise Rejection and Lost Version on Roster Reconciliation Failure Freezes Teacher Roster Synchronization | hardening |
| BUG_REPORT.md | 5940 | PERF-09 | [PERF-09] Unbounded Recursive Directory Walk in storage.usage() Blocks ASGI Worker and Crashes with FileNotFoundError on Concurrent Ingest/Eviction | confirmed |
| BUG_REPORT.md | 5994 | CONC-20 | [CONC-20] Uncommitted Database Transaction Held During Multi-Minute Desktop Slide Archive Extraction Blocks Global Database Access and Triggers SQLite Lock Timeouts | confirmed |
| BUG_REPORT.md | 6100 | SEC-46 | [SEC-46] Missing Formula Sanitization in Annotation CSV Export Enables Client-Side CSV Injection and Remote Command Execution | fixed upstream |
| BUG_REPORT.md | 6148 | DATA-18 | [DATA-18] Study Progress CSV Export Omits Course Existence Check and Streams In-Memory Dataset Without Attachment Header | confirmed |
| BUG_REPORT.md | 6238 | BUG-22 | [BUG-22] Missing Thumbnail Requirement in Prepared Ingest Results in Orphaned Thumbnail References and Broken Gallery Images | fixed upstream |
| BUG_REPORT.md | 6269 | FE-44 | [FE-44] Classroom Event Stream Cursor Prematurely Updates Sequence on Event Gaps Permitting Out-of-Order Execution During Recovery | confirmed |
| BUG_REPORT.md | 6340 | FE-45 | [FE-45] Classroom Teaching Overlays Suppress Canvas Clear When Annotations Array Empties Leaving Ghost Annotations on Screen | confirmed |
| BUG_REPORT.md | 6391 | BUG-23 | [BUG-23] Annotation Layer Deletion Fails with 409 Conflict When Only Tombstoned Annotations Exist | hardening |
| BUG_REPORT.md | 6438 | DATA-19 | [DATA-19] Permanent Folder Deletion Omits Desktop Sync Delete Event Emitting Zombie Folders on Paired Clients | confirmed |
| BUG_REPORT.md | 6476 | CONC-21 | [CONC-21] Unsynchronized Iteration Over _subscribers in _publish() and reset_session() Triggers RuntimeError: Set changed size during iteration | false positive |
| BUG_REPORT.md | 6521 | BUG-24 | [BUG-24] Classroom Slide Readiness and Descriptor Generation Reject OME Dynamic Slides with 409 Conflict and 404 Tile Failures | hardening |
| BUG_REPORT.md | 6587 | FE-46 | [FE-46] ClassroomTeacherPage Omits EventSource Error Handler Leaving Presenters Blind to Disconnections and Dropped Streams | hardening |
| BUG_REPORT.md | 6624 | DATA-20 | [DATA-20] Unconditional Closing Vertex Append in _polygon_coordinates() Generates Duplicate Vertices Breaking RFC 7946 GeoJSON | hardening |
| BUG_REPORT.md | 6650 | DATA-21 | [DATA-21] Uncaught IntegrityError During Folder Restore Crashes with HTTP 500 on Name Collision Instead of 409 Conflict | confirmed |
| BUG_REPORT.md | 6682 | SEC-47 | [SEC-47] Unhandled Argon2 InvalidHash → 500 on Corrupt Hash | fixed upstream |
| BUG_REPORT.md | 6692 | BUG-25 | [BUG-25] KeyError on Unknown Membership Role → 500 | hardening |
| BUG_REPORT.md | 6702 | BUG-26 | [BUG-26] Org Slug/DisplayName Normalization Bypasses Validation | confirmed |
| BUG_REPORT.md | 6712 | OPS-13 | [OPS-13] Engine Cache Key Omits Password Content → Stale After Rotation | hardening |
| BUG_REPORT.md | 6722 | PERF-10 | [PERF-10] Double Full-Index Parse Per Dynamic Tile | hardening |
| BUG_REPORT.md | 6732 | SEC-48 | [SEC-48] Migration FK Check Identifier Injection via f-string | hardening |
| BUG_REPORT.md | 6742 | DATA-22 | [DATA-22] Migration Manifest Unbounded PK List → OOM | hardening |
| BUG_REPORT.md | 6752 | CONC-22 | [CONC-22] Reconcile Holds Write Lock Across FS Walks | hardening |
| BUG_REPORT.md | 6762 | SEC-49 | [SEC-49] Manual Classroom Accepts Trashed-Folder Slides | false positive |
| BUG_REPORT.md | 6772 | BUG-27 | [BUG-27] sort=manual Outside Collection → 500 | confirmed |
| BUG_REPORT.md | 6782 | BUG-28 | [BUG-28] Saved-View Tags/State/Dates Silently Dropped | confirmed |
| BUG_REPORT.md | 6792 | BUG-29 | [BUG-29] Redeem Ignores ends_at — Burns Single-Use Code | confirmed |
| BUG_REPORT.md | 6802 | FE-47 | [FE-47] DesktopConnect Stale State on ?code= Change | confirmed |
| BUG_REPORT.md | 6812 | FE-48 | [FE-48] ViewerPage Leaks noindex Meta to SPA | hardening |
| BUG_REPORT.md | 6825 | SEC-50 | [SEC-50] offline_slide Omits Checking slide.trashed_at is None Permitting Paired Desktop Clients to Exfiltrate/Download Trashed Clinical Slides | fixed upstream |
| BUG_REPORT.md | 6861 | PERF-11 | [PERF-11] Single Global Mutex Gate with 1.0s Timeout Serializes All Classroom Mutations Across Entire System Causing 503 Spikes | hardening |
| BUG_REPORT.md | 6908 | PERF-12 | [PERF-12] Unbuffered Row-by-Row database.flush() in apply_result_bundle() for Up to 2,000,000 Objects Freezes ASGI Event Loop and Triggers Process OOM | hardening |
| BUG_REPORT.md | 6965 | BUG-30 | [BUG-30] Desktop Result Delivery Admission Rejects Ingestion with 409 Conflict When Only Tombstoned Annotations Exist on Slide | hardening |
| BUG_REPORT.md | 6997 | BUG-31 | [BUG-31] Lazy Classroom Expiry in create_session() Deletes Expired Database Sessions Without Evicting In-Memory Hub State Leaking Memory | confirmed |
| BUG_REPORT.md | 7044 | DATA-23 | [DATA-23] Desktop Library Items Query Hardcodes 100-Folder Limit Without Pagination Silently Truncating Folder Trees for Paired Clients | confirmed |
| BUG_REPORT.md | 7078 | DATA-24 | [DATA-24] GeoJSON Annotation Import Unconditionally Slices [:-1] Truncating Real Vertices and Crashing on Triangles | false positive |
| BUG_REPORT.md | 7115 | PERF-13 | [PERF-13] TileRouteService._dynamic_slide() Bypasses OmeTileRenderer Index Cache Parsing Multi-Megabyte JSON on Every Single Dynamic Tile Request | hardening |
| BUG_REPORT.md | 7192 | PERF-14 | [PERF-14] build_ome_tile_index() Decodes Every Single JPEG Tile Across Entire WSI Pyramid With Pillow Freezing Ingest Worker for Minutes | hardening |
| BUG_REPORT.md | 7247 | PERF-15 | [PERF-15] ClassroomPrewarmer and restore_prewarm() Reject Dynamic OME Slides and Silently Discard Multi-Classroom Sessions | hardening |
| BUG_REPORT.md | 7312 | BUG-32 | [BUG-32] purge_due_study_data() Hard Deletes StudyLearnerSession Without Cascading StudyProgress Resulting in Orphaned Rows and Foreign Key Inconsistencies | false positive |
| BUG_REPORT.md | 7359 | BUG-33 | [BUG-33] StudyRoutes.withdraw() Hard-Deletes Learner Session Violating Schema Status Invariants and Destroying Research Participation Audits | false positive |
| BUG_REPORT.md | 7411 | FE-49 | [FE-49] AnnotationAutosave.drain() Leaves inFlight Batch Wedged on 4xx Client Errors Permanently Freezing User Workspace | hardening |
| BUG_REPORT.md | 7455 | FE-50 | [FE-50] Concurrent Base64 Data URL Conversion of 100 Offline Notebook Entries Crashes Mobile WebKit Tab With OOM | confirmed |
| BUG_REPORT.md | 7497 | BUG-34 | [BUG-34] PreparedIngest Modulo Sampling Uses Constant expected_count Instead of Loop Counter file_count Skipping Verification or Freezing Unpack | false positive |
| BUG_REPORT.md | 7534 | BUG-35 | [BUG-35] StudyPackContract.score_task() Collapses Spatial Target Rectangles to Center Points Scoring Valid Tissue Hits as False | confirmed |
| BUG_REPORT.md | 7565 | CONC-23 | [CONC-23] ClassroomHub Permanently Locks Out Reconnecting Students into _retired_participants After Transient Network Disconnections | hardening |
| BUG_REPORT.md | 7625 | FE-51 | [FE-51] OpenSeadragonViewer PerformanceObserver Hardcodes '/tiles/' Pattern Ignoring /_pathlab_ome/ Disabling Dynamic Tile Network Throttling | confirmed |
| BUG_REPORT.md | 7669 | FE-52 | [FE-52] TraceSim Web Worker Unconditionally Invokes caches.open() Crashing AI Model Preparation in Private Browsing Mode | hardening |
| BUG_REPORT.md | 7746 | SEC-51 | [SEC-51] ClassroomRoutes.expire_control() Commits Database Transaction Without Route Guard Prematurely Persisting Intermediate State | hardening |
| BUG_REPORT.md | 7796 | DATA-25 | [DATA-25] StorageAccounting.reconcile_storage() Fails Unconditionally on Trashed or Deleting Slides Missing Derivative Directories | false positive |
| BUG_REPORT.md | 7866 | BUG-36 | [BUG-36] IdentityRoutes.create_membership() Blindly Re-Inserts Violating Unique Constraint Preventing Reactivation of Disabled Memberships | hardening |
| BUG_REPORT.md | 7927 | DATA-26 | [DATA-26] apply_result_bundle() Exception Handler Wipes Out Entire Slide Results Directory Destroying Previous Successful Deliveries | false positive |
| BUG_REPORT.md | 7971 | BUG-37 | [BUG-37] upload_prepared_ingest() Exception Handler Only Catches HTTPException Leaking Partial Stream Bytes on Client Disconnect | hardening |
| BUG_REPORT.md | 8026 | FE-53 | [FE-53] stitchHoles() in booleanCore.ts Injects undefined into Coordinate Array on Degenerate Outer Ring Crashing Canvas Renderer | hardening |
| BUG_REPORT.md | 8095 | FE-54 | [FE-54] Synchronous URL.revokeObjectURL() in downloadStudyInvitations() Immediately Aborts Asynchronous File Downloads in Safari & Firefox | false positive |
| BUG_REPORT.md | 8144 | BUG-38 | [BUG-38] study_tile() Unconditionally Forbids Dynamic OME-TIFF Slides Returning 404 for All Modern Study Pack Slides | hardening |
| BUG_REPORT.md | 8209 | SEC-52 | [SEC-52] get_admin_slide() Returns Trashed Slides as Ready with Active Tile Sources Causing Immediate 404s and Metadata Leaks | hardening |
| BUG_REPORT.md | 8256 | BUG-39 | [BUG-39] folder_subtree_ids() Omission of trashed_at Filter Causes Share Generation to Crash with ShareConflict or Leak Trashed Hierarchies | fixed upstream |
| BUG_REPORT.md | 8310 | CONC-24 | [CONC-24] ClassroomHub._retire_subscriber() Mutates _subscribers and current_connections Outside _presence_lock Causing Lost Updates and Connection Count Drift | confirmed |
| BUG_REPORT.md | 8357 | FE-55 | [FE-55] ClassroomStudentPage.ask() Clears Local Pin State Without Calling Backend clearPin() Causing Ghost Pin Desynchronization | confirmed |
| BUG_REPORT.md | 8412 | FE-56 | [FE-56] Uncaught Taint SecurityError in captureVisibleTissue() Bypasses Exception Handler Crashing Student Screenshot Pipeline | false positive |
| BUG_REPORT.md | 8472 | BUG-40 | [BUG-40] Classroom Teaching Annotation Mutations Omit state_version Increments Breaking Snapshot Reconciler Recovery on Stream Reconnect | confirmed |
| BUG_REPORT.md | 8512 | CONC-25 | [CONC-25] ClassroomRoutes.publish_pin() and clear_pin() Omit MutationGuard Allowing Concurrent Pin Flooding to Race DB State | confirmed |
| BUG_REPORT.md | 8566 | FE-57 | [FE-57] ClassroomStudentPage.clicked() Commits Local Pin State Before publishPin() Network Rejection Showing Ghost Pins on Failure | confirmed |
| BUG_REPORT.md | 8621 | DATA-27 | [DATA-27] remove_slide() Fails to Remove individual_delivery_for(public_id) Directory Leaving Derivative Hardlinks Stranded Permanently | confirmed |
| BUG_REPORT.md | 8660 | BUG-41 | [BUG-41] _reconcile() Traps RuntimeGuard in Indefinite DRAINING Deadlock When Active Classroom Session Ends or Cancels Before Live Phase | confirmed |
| BUG_REPORT.md | 8733 | CONC-26 | [CONC-26] Unheartbeated Long generate_dzi() Runs Cause recover_stale_jobs() to Requeue Running Jobs Resulting in Concurrent Overwriting Workers | hardening |
| BUG_REPORT.md | 8777 | FE-58 | [FE-58] AnnotationAutosave Abandons In-Flight Queue and Freezes Version Advancement on onAcknowledged Failure Locking 409 Conflict | hardening |
| BUG_REPORT.md | 8812 | BUG-42 | [BUG-42] delete_layer Blocks Deletion of Visually Empty Layers Containing Soft-Deleted Tombstones with 409 | hardening |
| BUG_REPORT.md | 8843 | DATA-28 | [DATA-28] finalize_upload() Leaves Storage Reservation Stranded for 24 Hours on Corrupt or Invalid Uploads | hardening |
| BUG_REPORT.md | 8875 | BUG-43 | [BUG-43] validate_folder_parent() Missing Cycle Guard Causes Infinite Loop and Worker Hang on Cyclic Ancestry | confirmed |
| BUG_REPORT.md | 8894 | DATA-29 | [DATA-29] upload_result_delivery Never Unlinks Extracted .plresults Staging Archives Leaking Up to 2 GB per Delivery | confirmed |
| BUG_REPORT.md | 8921 | BUG-44 | [BUG-44] create_result_delivery Rejects Valid Analysis Result Delivery with 409 RESULT_CONFLICT Due to Unfiltered Soft-Deleted Annotations | hardening |
| BUG_REPORT.md | 8949 | PERF-16 | [PERF-16] apply_result_bundle() Per-Object database.flush() and Unbatched ORM Allocation Causes Container OOM on Result Imports | hardening |
| BUG_REPORT.md | 9002 | BUG-45 | [BUG-45] StudyRoutes.withdraw() Hard-Deletes Session Violating Clinical Audit Trail and Leaving Orphaned Records on SQLite | false positive |
| BUG_REPORT.md | 9030 | DEV-02 | [DEV-02] Standalone / Local Development Missing Fallback Route for /tiles/{public_id}/{version}/{tile_path} Returns 404 | false positive |
| BUG_REPORT.md | 9056 | FE-59 | [FE-59] SharedFolderBranch and SharedFolderNode Fail to Escape Special JSON Characters in Folder Paths Breaking Tree Construction | false positive |
| BUG_REPORT.md | 9071 | CONC-27 | [CONC-27] StudyCourse Activation Race Condition Allows Concurrent Creation of Multiple Active Courses | false positive |
| BUG_REPORT.md | 9097 | BUG-46 | [BUG-46] build_ome_tile_index() Hardcodes tif.series[0] Triggering Ingestion Failure When Slide Pyramid Is In Secondary Series | confirmed |
| BUG_REPORT.md | 9126 | CONC-28 | [CONC-28] ClassroomTeacherPage Premature suppressPublish Clearance Creates Animation Frame Feedback Loop | false positive |
| BUG_REPORT.md | 9156 | SEC-53 | [SEC-53] SQLite FTS _search_ids Unescaped Wildcard Syntax Triggers Unhandled OperationalError and 500 DoS | fixed upstream |
| BUG_REPORT.md | 9209 | BUG-47 | [BUG-47] trash_folder() Permits Trashing Folders with Active Slides Creating Invisible Ghost Slides and Unresolvable State | confirmed |
| BUG_REPORT.md | 9249 | BUG-48 | [BUG-48] delete_collection() and trash_folder() Bypass _has_active_share Check Corrupting Public Links | false positive |
| BUG_REPORT.md | 9271 | DATA-30 | [DATA-30] remove_grant() Unconditionally Purges individual_delivery_for Files Breaking Concurrent Grants | false positive |
| BUG_REPORT.md | 9309 | PERF-17 | [PERF-17] ome_tiles.py _render_fallback() Scales Entire High-Resolution Image Before Cropping Causing Massive Memory Spikes | false positive |
| BUG_REPORT.md | 9329 | SEC-54 | [SEC-54] revoke_share() Omits Deletion of Public Delivery Manifest Allowing Continued Tile Access | fixed upstream |
| BUG_REPORT.md | 9369 | BUG-49 | [BUG-49] share_delivery_public_id() Off-by-Timezone Naive vs Aware Comparison Raises TypeError and Rejects Valid Shares | fixed upstream |
| BUG_REPORT.md | 9390 | CONC-29 | [CONC-29] TileCache.get_or_create() Leader Coalescing Indefinite Hang on Worker Thread Cancellation | hardening |
| BUG_REPORT.md | 9420 | BUG-50 | [BUG-50] create_ome_ingest and create_result_delivery Commit Database Records Before File Creation Leaving Ingests in Deadlock State | confirmed |
| BUG_REPORT.md | 9463 | PERF-18 | [PERF-18] StorageLayout.usage() Unindexed Synchronous os.walk() on 500,000+ Files Freezes Worker Thread During Upload Admission | hardening |
| BUG_REPORT.md | 9489 | DATA-31 | [DATA-31] rotate_share() Fails to Migrate Staging Manifest Leaving Old Public Link Functional and New Link Broken | fixed upstream |
| BUG_REPORT.md | 9522 | PERF-19 | [PERF-19] _publish_derivative_to Redundant Per-Tile mkdir() Syscalls Severely Throttle Slide Publication | hardening |
| BUG_REPORT.md | 9548 | BUG-51 | [BUG-51] ClassroomHub Stale Participant Eviction Flaw Permanently Locks Classroom with CLASSROOM_FULL on Server Restart | hardening |
| BUG_REPORT.md | 9590 | DATA-32 | [DATA-32] desktop_finalizer.py Abandons Failed prepared_package Archives on Disk Leaking Up to 10 GB per Ingest | fixed upstream |
| BUG_REPORT.md | 9611 | CONC-30 | [CONC-30] worker.py Delete Job Strands "running" Job on SQLite for 5 Minutes Due to Disabled FK Cascades | confirmed |
| BUG_REPORT.md | 9638 | DATA-33 | [DATA-33] worker.py Conversion Failure Abandons Incomplete Pyramid Tiles on Disk Leaking Storage Indefinitely | fixed upstream |
| BUG_REPORT.md | 9665 | DATA-34 | [DATA-34] main.py TUS finalize_upload() Copy Failure Leaves Orphaned .partial Files on Cross-Device Moves | hardening |
| BUG_REPORT.md | 9698 | FE-60 | [FE-60] snapshotReconciler.ts Zero-Delay Retry Burst Causes False-Positive Reconciler Failures | hardening |
| BUG_REPORT.md | 9730 | PERF-20 | [PERF-20] notebook.ts saveEntry() Deserializes All Blobs into RAM to Check Entry Count Triggering WebKit OOM Crash | confirmed |
| BUG_REPORT.md | 9767 | FE-61 | [FE-61] ClassroomTeacherPage "Show pinned field" Omission of Local Slide Transition & Viewport Navigation Desynchronizes Presenter from Students | false positive |
| BUG_REPORT.md | 9816 | FE-62 | [FE-62] ClassroomTeacherPage Slide Navigator Selection Omits Viewport Broadcast Leaving Students Stranded on Prior Slide in Guide Mode | confirmed |
| BUG_REPORT.md | 9849 | BUG-52 | [BUG-52] teacher_state Endpoint Omits expire_control() Leaving Presenter UI Locked with Stale Expired Student Controller Lease | confirmed |
| BUG_REPORT.md | 9890 | FE-63 | [FE-63] ClassroomTeacherPage Missing session-ended SSE Event Listener Leaves Teacher in Zombie Session State on Administrative Revocation | confirmed |
| BUG_REPORT.md | 9915 | FE-64 | [FE-64] ClassroomStudentPage Missing Slide-Scoped Key / Reset on StudentDrawingOverlay Bleeds Drawings Across Guided Slide Switches | confirmed |
| BUG_REPORT.md | 9955 | SEC-55 | [SEC-55] get_slide_details() and Static thumbnail() in library_routes.py Omit Trashed Slide Checks Permitting Data Exfiltration of Soft-Deleted Pathology Slides | hardening |
| BUG_REPORT.md | 10003 | CONC-31 | [CONC-31] ClassroomRoutes.stream_response() Event Sequence Race Condition Seeds Subscriber with Stale eventSequence Desynchronizing Client Stream Recovery | false positive |
| BUG_REPORT.md | 10064 | PERF-21 | [PERF-21] apply_result_bundle Executes Per-Object database.flush() and Iterates 2,000,000 ORM Instances into Python RAM Triggering Worker OOM Crash | hardening |
| BUG_REPORT.md | 10123 | DATA-35 | [DATA-35] desktop_annotation_batch Blindly Overrides candidate.base_version to Current Slide Version Silently Destroying Concurrent Web Annotations | false positive |
| BUG_REPORT.md | 10187 | DATA-36 | [DATA-36] purge_due_study_data in study_routes.py Omits StudyProgress Deletion Permanently Stranding Orphaned Student Progress Records | false positive |
| BUG_REPORT.md | 10230 | SEC-56 | [SEC-56] export_progress in study_routes.py Omits Formula Sanitization on task_id Allowing CSV Formula Injection | fixed upstream |
| BUG_REPORT.md | 10272 | SEC-57 | [SEC-57] study_tile Endpoint in study_routes.py Omits slide.trashed_at Check Permitting Access to Soft-Deleted Pathology Slides | hardening |
| BUG_REPORT.md | 10305 | CONC-32 | [CONC-32] study_routes.py redeem Endpoint Lacks Race Condition Protection Causing Unhandled IntegrityError 500s and Course Oversubscription | confirmed |
| BUG_REPORT.md | 10342 | SEC-58 | [SEC-58] Unrestricted report_readiness Endpoint Allows Denial of Service and Data Poisoning of Faculty Study Metrics | hardening |
| BUG_REPORT.md | 10382 | BUG-53 | [BUG-53] score_task in study_pack_contract.py Evaluates Center Point Chebyshev Distance Rejecting Valid User Selections on Large Target Regions | confirmed |
| BUG_REPORT.md | 10407 | DATA-37 | [DATA-37] upload_result_delivery Deletes Entire Slide Results Directory on Single Bundle Validation Failure Wiping Previous Runs | false positive |
| BUG_REPORT.md | 10449 | CONC-33 | [CONC-33] Multi-Worker Startup Race in PreparedIngestFinalizer._recover Re-finalizes Active Ingests Causing File Extraction Collisions | hardening |
| BUG_REPORT.md | 10490 | CONC-34 | [CONC-34] Concurrent Desktop Chunk Uploads Double-Increment received_bytes Permanently Freezing Ingest in Uploading State | confirmed |
| BUG_REPORT.md | 10528 | CONC-35 | [CONC-35] Non-Atomic exchange_pairing Allows Issuance of Multiple Active Credentials from a Single Pairing Code | fixed upstream |
| BUG_REPORT.md | 10570 | FE-65 | [FE-65] StudyPage Spatial Selection Omits Canvas Visual Target Indicator Confusing Students on Click Accuracy | confirmed |
| BUG_REPORT.md | 10608 | DATA-38 | [DATA-38] localStore.ts Resolves appendLocalRecord Before IndexedDB Transaction Commits Causing Silent Data Loss on Tab Close | confirmed |
| BUG_REPORT.md | 10658 | SEC-59 | [SEC-59] withdraw Endpoint Uses Default Insecure Attributes in delete_cookie Failing to Clear Session on HTTPS | false positive |
| BUG_REPORT.md | 10691 | BUG-54 | [BUG-54] Missing Invitation Revocation Route Prevents Invalidation of Lost or Exposed Study Codes | hardening |
| BUG_REPORT.md | 10739 | FE-66 | [FE-66] Uncaught SecurityError on caches.open in Firefox/Safari Private Browsing Completely Breaks Local AI Initialization | hardening |
| BUG_REPORT.md | 10783 | PERF-22 | [PERF-22] Coarse Course-Wide Submission Throttling Blocks Answering Different Practice Tasks Forcing 30-Second Wait Per Question | hardening |
| BUG_REPORT.md | 10821 | CONC-36 | [CONC-36] Read-Route Concurrency Stampede on Course Expiration Triggers Lock Contention in learner_session | hardening |
| BUG_REPORT.md | 10856 | DATA-39 | [DATA-39] Duplicate Feature Index in StudyPage.tsx Distorts Local AI Neural Network Input Vector | hardening |
| BUG_REPORT.md | 10891 | PERF-23 | [PERF-23] get_desktop_slide_content Mandates Open-Ended Byte Ranges Disabling Chunked HTTP Download Managers | hardening |
| BUG_REPORT.md | 10930 | SEC-60 | [SEC-60] export_csv() in annotations.py Omits Formula Sanitization on metadata.title and layer Allowing CSV Formula Injection | fixed upstream |
| BUG_REPORT.md | 10976 | BUG-55 | [BUG-55] Unhandled KeyError on Missing Layer ID in export_csv Crashes Measurement Export with HTTP 500 | hardening |
| BUG_REPORT.md | 11015 | SEC-61 | [SEC-61] annotation_routes.py get_slide() Omits Soft-Delete Checks Permitting Modification and Data Exfiltration of Trashed Slide Annotations | hardening |
| BUG_REPORT.md | 11042 | DATA-40 | [DATA-40] import_annotations Assigns Duplicate sort_order = -1 on GeoJSON Imports Breaking Subsequent PathLab JSON Re-Imports | fixed upstream |
| BUG_REPORT.md | 11108 | PERF-24 | [PERF-24] list_items Redundant count(*) on Viewport Queries Causes Severe Database Load During Pan Navigation | hardening |
| BUG_REPORT.md | 11155 | BUG-56 | [BUG-56] list_items Missing Coordinate Inversion Validation Silently Returns Empty Results on Inverted Viewport Bounds | confirmed |
| BUG_REPORT.md | 11197 | DATA-41 | [DATA-41] PathLab JSON Import Does Not Re-Index Layer Sort Orders Causing Sort Collisions with Existing Slide Layers | hardening |
| BUG_REPORT.md | 11248 | DATA-42 | [DATA-42] trash_folder Fails to Mark Contained Slides as Trashed Creating Invisible Phantom Slides | confirmed |
| BUG_REPORT.md | 11294 | SEC-62 | [SEC-62] delete_collection Deletes Collection with Active Public Shares Leaving Orphaned Public Manifests | fixed upstream |
| BUG_REPORT.md | 11333 | PERF-25 | [PERF-25] TileRouteService._dynamic_slide Parses 16MB Index JSON from Disk on Every Single Tile Request | hardening |
| BUG_REPORT.md | 11375 | BUG-57 | [BUG-57] add_collection_items Omits Soft-Delete Check Allowing Trashed Slides to be Added to Collections | hardening |
| BUG_REPORT.md | 11406 | CONC-37 | [CONC-37] Time-of-Check Race Condition in activate_share Permits Duplicate Active Shares for Same Target | fixed upstream |
| BUG_REPORT.md | 11450 | PERF-26 | [PERF-26] public_manifest Fetches Entire Folder Slide Subtree into Memory Merely to Read Name and Description | fixed upstream |
| BUG_REPORT.md | 11500 | BUG-58 | [BUG-58] validate_folder_parent Lacks Loop Cycle Detection Causing Infinite While Loop on Corrupt Hierarchies | confirmed |
| BUG_REPORT.md | 11538 | SEC-63 | [SEC-63] logout() in main.py Omits secure, httponly, and samesite in delete_cookie Leaving Admin Cookie on HTTPS | false positive |
| BUG_REPORT.md | 11579 | PERF-27 | [PERF-27] recover_password() Fetches All Database Users into Memory to Normalize Username | confirmed |
| BUG_REPORT.md | 11609 | BUG-59 | [BUG-59] streamSync.ts Advances Cursor Sequence on Gap Causing Silent Desync on Subsequent Events | confirmed |
| BUG_REPORT.md | 11646 | BUG-60 | [BUG-60] autosave.ts Skips In-Flight Cleanup and Version Advancement on Acknowledgement Failure | hardening |
| BUG_REPORT.md | 11695 | PERF-28 | [PERF-28] OpenSeadragonViewer Uses buffered: true in PerformanceObserver Replaying Obsolete Resource Timings | hardening |
| BUG_REPORT.md | 11730 | DATA-43 | [DATA-43] saveEntry in notebook.ts Uses add() Instead of put() Failing on Existing Note Updates | confirmed |
| BUG_REPORT.md | 11756 | BUG-61 | [BUG-61] FolderTree.tsx flatten Lacks Visited Guard Crashing Browser Tab on Cyclic Hierarchies | hardening |
| BUG_REPORT.md | 11803 | SEC-64 | [SEC-64] ensure_grant Overwrites flagged Clinical Privacy Status to passed Bypassing PHI Gate | hardening |
| BUG_REPORT.md | 11835 | DATA-44 | [DATA-44] delete_all_slide_grants Leaves Slide in PUBLISHED State After Unpublishing Derivatives | fixed upstream |
| BUG_REPORT.md | 11869 | SEC-65 | [SEC-65] offline_slide Omits Soft-Delete Check Allowing Trashed Slide Download via Desktop Offline API | fixed upstream |
| BUG_REPORT.md | 11912 | BUG-62 | [BUG-62] deliver_file Omits URL-Encoding in X-Accel-Redirect Breaking Paths with Special Characters | false positive |
| BUG_REPORT.md | 11943 | DATA-45 | [DATA-45] storage_contribution_expression Omits Null Coalescing Causing Zero-Byte Storage Accounting | false positive |
| BUG_REPORT.md | 11972 | PERF-29 | [PERF-29] Missing Pruning on DesktopSyncEvent Causes Indefinite Database Table Bloat | hardening |
| BUG_REPORT.md | 11993 | BUG-63 | [BUG-63] upload.ts Passes NaN Progress on Zero-Byte or Indeterminate Upload Streams | confirmed |
| BUG_REPORT.md | 12014 | BUG-64 | [BUG-64] validate_ome_tiff Rejects Valid 3-Channel RGB Images Using Standard Channel Axis "C" | hardening |
| BUG_REPORT.md | 12043 | PERF-30 | [PERF-30] Synchronous Recursive Filesystem Traversal in TileCache._reconcile Blocks Server Startup | hardening |
| BUG_REPORT.md | 12072 | CONC-38 | [CONC-38] Unhandled Lock Contention on Every Tile Cache Hit via Filesystem stat Calls Under RLock | hardening |
| BUG_REPORT.md | 12114 | BUG-65 | [BUG-65] booleanCore.ts stitchHoles Inserts undefined Coordinates on Degenerate Outer Rings | hardening |
| BUG_REPORT.md | 12155 | BUG-66 | [BUG-66] roster.ts Drops Pending Version on Reconcile Failure Causing Permanent Out-of-Sync Roster | hardening |
| BUG_REPORT.md | 12188 | PERF-31 | [PERF-31] snapshotReconciler.ts Retries Without Backoff Causing Rapid False-Positive Failures on Replica Lag | hardening |
| BUG_REPORT.md | 12222 | BUG-67 | [BUG-67] validate_ome_tiff Throws Unhandled IndexError on Empty ome.images Collection | false positive |
| BUG_REPORT.md | 12249 | SEC-66 | [SEC-66] Classroom Participant Session Invalidation Omission on Session Termination | hardening |
| BUG_REPORT.md | 12279 | CONC-39 | [CONC-39] Classroom Controller Lease TOCTOU Race Condition in Control Grant | false positive |
| BUG_REPORT.md | 12313 | PERF-32 | [PERF-32] Classroom Participant Roster Sequential Full Table Scan Degradation | hardening |
| BUG_REPORT.md | 12339 | BUG-68 | [BUG-68] Classroom Event Hub Subscriber Message Buffer Leak on Session Teardown | false positive |
| BUG_REPORT.md | 12365 | DATA-46 | [DATA-46] Teaching Annotation Point Coordinate Validation & Non-Finite Number Acceptance | false positive |
| BUG_REPORT.md | 12391 | SEC-67 | [SEC-67] Classroom Question Text Unsanitized HTML Acceptance Permitting Stored XSS | false positive |
| BUG_REPORT.md | 12424 | BUG-69 | [BUG-69] Classroom Question Deletion Leaves Orphaned Receipt Records | false positive |
| BUG_REPORT.md | 12446 | SEC-68 | [SEC-68] Missing nosniff on Tile/Thumbnail Delivery (Sniff → Stored XSS) | false positive |
| BUG_REPORT.md | 12456 | REL-09 | [REL-09] Presenter Flush Loss on CancelledError + Leaked in_flight | confirmed |
| BUG_REPORT.md | 12466 | OPS-14 | [OPS-14] Capacity Monitor Non-Atomic + Advisory-Only Window | hardening |
| BUG_REPORT.md | 12476 | FE-67 | [FE-67] Study Withdraw Leaves ONNX Worker/Course State (Cross-Course Contamination) | confirmed |
| BUG_REPORT.md | 12486 | FE-68 | [FE-68] Invite Phase Poll Overlap + Post-Unmount Write | confirmed |
| BUG_REPORT.md | 12496 | FE-69 | [FE-69] OSD Rotation Persists Across Slide Change | confirmed |
| BUG_REPORT.md | 12506 | BUG-70 | [BUG-70] Prepared Ingest Rejects Valid JPEG Tile Filenames in DeepZoom Pyramids | fixed upstream |
| BUG_REPORT.md | 12536 | SEC-69 | [SEC-69] DB Pool No Pre-Ping + Inverted Classroom Timeout | hardening |
| BUG_REPORT.md | 12546 | REL-10 | [REL-10] 413 Without Drain Poisons Keep-Alive | false positive |
| BUG_REPORT.md | 12556 | CONC-40 | [CONC-40] Prewarm Shutdown Race (_loop Unsynchronized) | hardening |
| BUG_REPORT.md | 12566 | FE-70 | [FE-70] Study Invite Count Unclamped | confirmed |
| BUG_REPORT.md | 12576 | FE-71 | [FE-71] Select-Visible Ghost Count | confirmed |
| BUG_REPORT.md | 12586 | FE-72 | [FE-72] Shared Tree Keyboard Hijack + Forced Open | confirmed |
| BUG_REPORT.md | 12596 | FE-73 | [FE-73] Unhandled API 409 Derivative Error Freezes Publish Dialog | confirmed |
| BUG_REPORT.md | 12610 | FE-74 | [FE-74] Floating Annotation Workspace Occludes Micron Scale Bar & Rotation Controls | confirmed |
| BUG_REPORT.md | 12626 | FE-75 | [FE-75] OpenSeadragon Missing showErrorBox: false Injects Unstyled Raw DOM Error | hardening |
| BUG_REPORT.md | 12638 | FE-76 | [FE-76] Raw Uppercase Error Code Enums Leaked to Study Mode Learners & Authors | hardening |
| BUG_REPORT.md | 12654 | FE-77 | [FE-77] Dev Server Launcher Default Excludes Classroom API Routes (HTTP 404) | hardening |
| BUG_REPORT.md | 12675 | FE-78 | [FE-78] Password Change Form Wipes All Inputs on Confirmation Mismatch | hardening |
| BUG_REPORT.md | 12695 | FE-79 | [FE-79] Search Input Lacks Client-Side Length Limit, Crashing UI on Queries > 300 Chars | hardening |
| BUG_REPORT.md | 12710 | FE-80 | [FE-80] Edit Slide Details Accepts Empty / Whitespace Display Name, Breaking Accessible UI | confirmed |
| BUG_REPORT.md | 12729 | FE-81 | [FE-81] Private Preview Traps Admin in Dead-End View Without Exit Controls, Causing Full SPA Reloads | confirmed |
| BUG_REPORT.md | 12747 | FE-82 | [FE-82] Saved Views Route Omits Canonical Breadcrumb Handling and View State Rehydration | confirmed |
| BUG_REPORT.md | 12764 | FE-83 | [FE-83] Redundant and Duplicated Navigation Surfaces in Library Navigator and Command Toolbar | hardening |
| BUG_REPORT.md | 12781 | FE-84 | [FE-84] Single-Slide Action Context Menu Silently Destroys Multi-Slide Selection Set | confirmed |
| BUG_REPORT.md | 12799 | FE-85 | [FE-85] Folder Cards in Main Workspace Lack Management Context Actions Available in Drawer | hardening |
| BUG_REPORT.md | 12815 | FE-86 | [FE-86] Toolbar Navigation Buttons Lack Disabled States and Up-Button Root Boundaries | confirmed |
| BUG_REPORT.md | 12834 | FE-87 | [FE-87] Stale Annotation Revision History Applies Across Different Annotations, Corrupting Geometry | confirmed |
| BUG_REPORT.md | 12862 | FE-88 | [FE-88] Service Role Capability Header Mismatch Exposes Dead Classroom Route on General Workers | false positive |
| BUG_REPORT.md | 12888 | FE-89 | [FE-89] Public and Learner Error Pages Render Dead-End Screens Without Navigation Escape | confirmed |
| BUG_REPORT.md | 12909 | FE-90 | [FE-90] Study Pack Authoring Allows Blank Task Creation and Specifies Inverted Version Limits | confirmed |
| BUG_REPORT.md | 12927 | FE-91 | [FE-91] Annotation Revision History Button Misleading Scope and Missing Idle Disabled State | hardening |
| BUG_REPORT.md | 12954 | FE-92 | [FE-92] Orphaned Dead Component DeleteSlideDialog.tsx Retained in Web Source Tree | hardening |
| BUG_REPORT.md | 12969 | FE-93 | [FE-93] Multi-Selection Metadata and Style Wholesale Overwrite Destroys Individual Slide Annotation Attributes | confirmed |
| BUG_REPORT.md | 13016 | FE-94 | [FE-94] VertexEditor Hardcoded to First Point with Unhandled TypeError Crash on Empty Geometry Points | hardening |
| BUG_REPORT.md | 13040 | FE-95 | [FE-95] StorageWorkspace Discards Theme Switcher and AppRail Nests ARIA Meter Inside Interactive Button | hardening |
| BUG_REPORT.md | 13064 | FE-96 | [FE-96] Hard Browser Page Reload on "Preview" from SlideDetailsPanel and SlideViews Menu Bypasses SPA Routing | confirmed |
| BUG_REPORT.md | 13092 | FE-97 | [FE-97] Study Coach Inverted Spinbutton Limits, Raw Machine Error Codes & Destructive Window Navigation Assignment | confirmed |
| BUG_REPORT.md | 13122 | FE-98 | [FE-98] Missing Field Length Constraints (maxLength) on Slide Metadata & Upload Names Trigger 422 API Rejections | confirmed |
| CYBERSECURITY_REPORT.md | 22 | section-22 | Findings Summary | duplicate |
| CYBERSECURITY_REPORT.md | 34 | section-34 | 🔴 CRITICAL Findings | duplicate |
| CYBERSECURITY_REPORT.md | 102 | section-102 | 🟠 HIGH Findings | duplicate |
| CYBERSECURITY_REPORT.md | 212 | section-212 | 🟡 MEDIUM Findings | duplicate |
| CYBERSECURITY_REPORT.md | 367 | section-367 | 🟢 LOW Findings | duplicate |
| CYBERSECURITY_REMEDIATION.md | 9 | section-9 | P0 — Immediate (Do These First) | duplicate |
| CYBERSECURITY_REMEDIATION.md | 58 | section-58 | P1 — This Sprint | duplicate |
| CYBERSECURITY_REMEDIATION.md | 156 | section-156 | P2 — Next Sprint | duplicate |
| CYBERSECURITY_REMEDIATION.md | 269 | section-269 | P3 — Planned (Defense-in-Depth) | duplicate |
| docs/reports/BUG_REPORT_CODEX.md | 25 | section-25 | Key Finding Categories | duplicate |
| docs/reports/BUG_REPORT_CODEX.md | 38 | section-38 | 2. Master Bug & Vulnerability Register | duplicate |
| docs/reports/BUG_REPORT_CODEX.md | 400 | SEC-01 | [SEC-01] Global RBAC Capability Bypass on Administrative Subsystems | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 446 | SEC-02 | [SEC-02] Privilege Escalation & Last-Owner Deletion Race in Identity Governance | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 487 | SEC-03 | [SEC-03] In-Memory Rate Limiting & Unthrottled Pairing Endpoint | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 513 | SEC-04 | [SEC-04] Caddy Directive Ordering Bypassing Internal Route Denials | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 546 | SEC-05 | [SEC-05] Native Image Parser Execution Without Sandbox Isolation | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 564 | SEC-06 | [SEC-06] Path Boundary Validation Bypass in delivery.py When Redirects Disabled | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 600 | SEC-07 | [SEC-07] Unrestricted Proxy Header Trust in Docker Compose API Command | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 614 | CONC-01 | [CONC-01] Non-Atomic Desktop Pairing Approval & Leaked Expired Handshakes | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 656 | CONC-02 | [CONC-02] Missing Transaction Lock on PostgreSQL During Password Recovery Throttle | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 688 | PERF-01 | [PERF-01] $O(N^2)$ In-Memory Descendant Traversal & Unbounded Slide Loading in Classroom | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 725 | PERF-02 | [PERF-02] Synchronous File Hashing Blocks Async Event Loop in Study Asset Delivery | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 752 | AUTH-01 | [AUTH-01] Missing Teacher Ownership on Classroom Sessions | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 776 | BUG-06 | [BUG-06] Unhandled IndexError on OME-XML with Zero Image Elements | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 798 | BUG-07 | [BUG-07] Stale Job Recovery Skips Jobs with Null Heartbeats | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 824 | FE-01 | [FE-01] Missing Top-Level React Application Error Boundary | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 849 | FE-02 | [FE-02] Session Expiration Discards Private Slide Destination (returnTo) | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 873 | FE-03 | [FE-03] Indistinguishable Slide Loading Errors & Missing Retry | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 894 | FE-04 | [FE-04] Direct Exposure of Internal Docker Commands in Recovery UI | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 909 | FE-05 | [FE-05] Classroom Setup Lacks Folder Search, Pagination, & State Validation | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 921 | FE-06 | [FE-06] Unhandled localStorage & sessionStorage Exceptions in Private Browsing | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 953 | FE-07 | [FE-07] Missing Login Return URL in Desktop Connect Workflow | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 967 | FE-08 | [FE-08] IndexedDB Connection Leak on Transaction Error in authoringStore.ts | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 1000 | DEV-01 | [DEV-01] dev.ps1 Root-Relative Path Resolution Bug | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 1025 | ENV-01 | [ENV-01] OneDrive File Locking Interference on SQLite WAL & Derivative Tiles | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 1040 | OPS-01 | [OPS-01] Deployment Script Failures on noexec Filesystems & Unbounded Capacity Controller Recovery | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 1063 | OPS-02 | [OPS-02] Missing Deterministic Software Inventories (SBOM) & Security Baseline Drift | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 1087 | OPS-03 | [OPS-03] Alembic Path Separator Deprecation in alembic.ini | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 1100 | DATA-01 | [DATA-01] PostgreSQL Signed 32-bit Integer Overflow on Whole Slide Image and Ingest Byte Columns | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 1132 | CONC-03 | [CONC-03] Storage Accounting Quota Bypass via Omission of PostgreSQL Advisory Locking | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 1168 | REL-01 | [REL-01] Slide Deletion Worker Crash Loop & Storage Desync on Classroom Slides (RESTRICT Foreign Key) | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 1206 | FE-09 | [FE-09] Classroom Teacher Page Unwrapped sessionStorage Failures in Safari Private Browsing | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 1222 | FE-10 | [FE-10] IndexedDB Connection Leaks in Study Store | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 1257 | BUG-08 | [BUG-08] Stale Job Recovery Query Omits Crashed checkpointing Jobs | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 1292 | TIME-01 | [TIME-01] Timestamp Offset Corruption via Unsafe replace(tzinfo=UTC) | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 1312 | SEC-08 | [SEC-08] Ineffective Revocation / Information Disclosure on Public Shares | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 1351 | BUG-09 | [BUG-09] Sharing Outright Crash / TypeError on Expired Shares | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 1388 | CONC-04 | [CONC-04] Library Share Activation Race Condition & Duplicate Active Shares | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 1434 | FE-11 | [FE-11] Boolean Polygon Clipping Crash on Degenerate Holes | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 1486 | FE-12 | [FE-12] Student Classroom Join Broken by Unhandled Notebook IndexedDB Failure | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 1532 | FE-13 | [FE-13] Classroom Invite Page Destroys Active Review Session on Transient Poll Failure | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 1574 | SEC-09 | [SEC-09] CSV Formula Injection in Annotation Measurement Exports | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 1628 | SEC-10 | [SEC-10] Classroom SSE Teacher Event Stream Unchecked Authorization Zero-Day | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 1683 | SEC-11 | [SEC-11] Unauthenticated & Unthrottled Study Invitation Code Brute-Force | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 1711 | SEC-12 | [SEC-12] Unmetered Request Body Size on Public & Student Endpoints Permitting Memory Exhaustion DoS | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 1754 | SEC-13 | [SEC-13] Revoked Classroom Sessions Retain Individual Derivative Tiles on Disk & Caddy Edge | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 1789 | SEC-14 | [SEC-14] Trashed Slide OME-TIFF File Download & Tile Viewing Authorization Leak | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 1830 | SEC-15 | [SEC-15] Caddy Internal Reverse Proxy Global Root (/) Exposure Risk | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 1866 | CONC-05 | [CONC-05] Concurrent Study AI Event Reporting Triggers Unique Constraint Crashes & Lost Updates | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 1924 | CONC-06 | [CONC-06] Study Course Learner Limit Admission Race Condition on Concurrent Redemption | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 1965 | PERF-03 | [PERF-03] Synchronous Unbounded os.walk() in Desktop Ingest Storage Admission Freezes Event Loop | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 2002 | TIME-02 | [TIME-02] Unsafe .replace(tzinfo=UTC) in Study Pack & Desktop Serializers Corrupting Timestamp Offsets | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 2029 | FE-14 | [FE-14] Unwrapped localStorage and sessionStorage in Theme, Shell Preferences, and API Client Crashes Web App in Private Browsing | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 2080 | DATA-02 | [DATA-02] Orphaned Derivative Directories Leaking Disk Storage on Unexpected Ingest Finalizer Exceptions | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 2132 | SEC-16 | [SEC-16] Unauthenticated Global Account Lockout Denial-of-Service via In-Memory Username Throttling | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 2166 | REL-02 | [REL-02] Classroom Teaching Annotations Exceed Hardcoded 4 KiB SSE Event Buffer Limit | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 2214 | SEC-17 | [SEC-17] Unauthenticated & Unthrottled Global Classroom Join Queue Lock Starvation Denial-of-Service | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 2262 | SEC-18 | [SEC-18] Unthrottled Student Pin & Control-Request Queue Flooding Forces Teacher SSE Disconnection (Remote DoS) | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 2306 | SEC-19 | [SEC-19] TRACE-SIM ONNX Model Installer Missing Exception Cleanup Leaves Partial Unverified Model Files on Disk | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 2351 | DATA-03 | [DATA-03] PostgreSQL Migration Leaves Autoincrement Sequence Unsynced (duplicate key value violates unique constraint "desktop_sync_events_pkey") | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 2417 | DATA-04 | [DATA-04] Permanent Deletion of Slides and Folders Omits Desktop Sync Deletion Events & Leaves Orphaned Shares | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 2451 | TIME-03 | [TIME-03] Inconsistent Offset-Naive utcnow() in Annotations and Worker Breaks PostgreSQL Datetime Comparisons | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 2486 | PERF-04 | [PERF-04] Full Table Distinct Join Scan on PublicationGrant During Every Folder Navigation Click | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 2519 | FE-15 | [FE-15] IndexedDbDraftStorage Permanent Rejection Caching & Missing Memory Fallback Freezes Annotation Studio | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 2566 | SEC-20 | [SEC-20] Uninitialized & Deadlocked Runtime Protection Mode Bricks Background Processing and All Slide Uploads | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 2601 | SEC-21 | [SEC-21] Unauthenticated & Unbounded Desktop Pairing Code Flooding Database Denial-of-Service | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 2639 | CONC-07 | [CONC-07] Desktop Pairing Exchange Concurrency Race Issues Multiple Tokens for Single-Use Code | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 2697 | CONC-08 | [CONC-08] Concurrent First AI-Event Submissions Crash with Unique Constraint Violation & Cause Lost Updates | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 2741 | DATA-05 | [DATA-05] Slide Deletion Fails to Purge Published Derivative Directory (delivery/individual/{public_id}) Causing Permanent Storage Leak | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 2774 | DATA-06 | [DATA-06] Desktop Library Synchronization Truncates Folders at 100 with No Pagination or Cursor | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 2800 | DATA-07 | [DATA-07] Desktop Annotation Batch Silently Bypasses Optimistic Concurrency Control with Fake Auto-Merge | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 2821 | FE-16 | [FE-16] Stale Upload Reservation Retention Freezes Retry on Expired Upload Token | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 2840 | FE-17 | [FE-17] Unwrapped sessionStorage in SharedViewerPage.tsx and study/api.ts Falsely Reports Valid Public Shares as Revoked / Missing in Safari Private Browsing | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 2900 | BUG-10 | [BUG-10] Dynamic Tile Fallback Renderer Crashes on 16-bit, Alpha, and Multichannel OME-TIFF Slides with Unhandled pyvips.Error | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 2944 | PERF-05 | [PERF-05] recover_password() Executes Unindexed Full Table Scan Loading All Database Users into Python Memory | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 2979 | SEC-22 | [SEC-22] Password Recovery Code-Validity Oracle via Differential Error Codes Bypasses Throttling | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 3030 | SEC-23 | [SEC-23] 90-day DesktopCredential Survives Password Change / Recovery (Credential-Generation Gap) | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 3048 | SEC-24 | [SEC-24] disable_membership Leaves Legacy-Admin Session Fully Valid | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 3063 | SEC-25 | [SEC-25] TUS post-finish allow_expired=True Bypasses 1h Upload TTL | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3078 | CONC-09 | [CONC-09] Conversion Staging PID-Only + Unconditional Stale-Wipe (TOCTOU / Data Loss) | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3093 | CONC-10 | [CONC-10] Desktop Resumable Chunk Has No Lock + Trusts DB Offset + Unbounded Retry Flood | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 3108 | CONC-11 | [CONC-11] Study Invitation Single-Use Double-Spend Race | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 3123 | SEC-26 | [SEC-26] Public Share Manifest Leaks Trashed-Slide Metadata | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 3138 | DATA-08 | [DATA-08] Share Publish / Rotate Commit-Then-Write Crash Window + Downtime | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 3153 | BUG-11 | [BUG-11] Teacher Live State Silent Truncation (300 / 200, Newest Dropped) | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 3167 | SEC-27 | [SEC-27] Internal Tile-Service /_pathlab_ome/* Zero-Auth + No Trashed Check | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3182 | SEC-28 | [SEC-28] Trashed-Slide Metadata / Annotation Read + Sync Bypass | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3197 | SEC-29 | [SEC-29] Conversion Derivative Sanitize / Measure Symlink-Blind (Escape + TOCTOU) | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 3211 | PERF-06 | [PERF-06] GET .../content Streaming FD Held Across Yield (Slow-Loris Leak) | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3225 | SEC-30 | [SEC-30] Config Fail-Open: extra="ignore" + Placeholder Secret + Prod-Only Validation | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3239 | OPS-04 | [OPS-04] Sticky CachedReadiness: /readyz Never Recovers Without Restart | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 3254 | BUG-12 | [BUG-12] read_protection_snapshot vs protection_snapshot Divergence (Uploads Open, Jobs Starved) | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3270 | FE-18 | [FE-18] Unabortable TUS Upload + Unscoped resumeFromPreviousUpload | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 3285 | FE-19 | [FE-19] Premature URL.revokeObjectURL + Detached Anchor Truncates Downloads | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3300 | FE-20 | [FE-20] Manifest Fetch Not Abortable; Tile URL Mirrored to DOM | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3317 | FE-21 | [FE-21] Router Catch-All Swallows 404 / Share-Invalid → Forced /admin | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3331 | REL-03 | [REL-03] HeartbeatWriter._run Silent Death on Transient I/O Error | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 3345 | CONC-12 | [CONC-12] TileCache.get_or_create Unbounded Event.wait() (Follower Hang) | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3359 | OPS-05 | [OPS-05] reconcile_storage Single-Slide Raise Aborts Entire Run + Bricks Boot | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3374 | SEC-31 | [SEC-31] delete_cookie Omits samesite/secure, Leaves Session Cookie Alive | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 3390 | CONC-13 | [CONC-13] Study pseudonym 32-bit Collision 500 (No Retry) | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3405 | FE-22 | [FE-22] AnnotationWorkspace.triggerDownload Premature Revoke (Remaining Instance) | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3419 | SEC-32 | [SEC-32] TileCache._reconcile Skips JPEG Validation (Persistent Poison) | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3432 | OPS-06 | [OPS-06] Shared TileCache Root With Process-Local Accounting + Lying readyz | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3444 | REL-04 | [REL-04] Worker delete Job Outside Try — Poison-Pill Hot Loop | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 3454 | REL-05 | [REL-05] expire_incomplete_uploads .stat() Race Kills Worker Loop | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 3464 | BUG-13 | [BUG-13] Classroom Auto-Expiry Skips Hub/Presenter/Prewarm Cleanup | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 3474 | PERF-07 | [PERF-07] ClassroomHub Unbounded Per-Session Leak on Singleton | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3484 | CONC-14 | [CONC-14] Concurrent Folder Moves Create Cycle → Infinite CTE DoS | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 3496 | DATA-09 | [DATA-09] Unbounded sortOrder Overflows PG Integer | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 3508 | FE-23 | [FE-23] OpenSeadragon open-failed Infinite Reconnect Storm | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3518 | FE-24 | [FE-24] Freehand Unbounded Construction + Spread Stack Overflow | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3530 | FE-25 | [FE-25] Upload Transport-Complete Lied as Slide-Complete + NaN Progress | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 3542 | FE-26 | [FE-26] InviteDialog False Modal — No Trap/Inert/Restore | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3552 | OPS-07 | [OPS-07] tusd + caddy Zero Healthcheck — Silent Upload Blackhole | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3562 | SEC-34 | [SEC-34] Backups Plaintext — Zero Encryption (PHI Exfiltration) | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3574 | SEC-35 | [SEC-35] Argon2 CPU-DoS on Impossible 129..1024-char Passwords | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3584 | PERF-08 | [PERF-08] Unindexed sessions.user_id FK (Plus Siblings) | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3594 | DATA-10 | [DATA-10] server_default vs Python default Drift + Bare-String Quoting | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3604 | OPS-08 | [OPS-08] Migration Full-Table RAM Load + Non-Atomic Batches | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3614 | FE-27 | [FE-27] persist() vs persisted() Confusion (Unsolicited Prompt) | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3624 | FE-28 | [FE-28] capture() Drops Blob on Save Failure (No Feedback) | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 3634 | FE-29 | [FE-29] Autosave Debounce Lost on Close (No Unload Flush) | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3644 | FE-30 | [FE-30] Teacher SSE No error Handler (Stale Roster) | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3654 | SEC-36 | [SEC-36] Caddy Security-Headers Gaps | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3664 | OPS-09 | [OPS-09] Mutable :live Fallback Tag (No Digest Pin) | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3674 | SEC-37 | [SEC-37] restore.sh World-Readable Staging + No Lock | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3684 | OPS-10 | [OPS-10] Watchdog Unbounded Diagnostics (No Retention) | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3694 | BUG-14 | [BUG-14] Uncaught SQLite FTS5 Query Syntax Errors Crash Library Search API with HTTP 500 | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 3726 | CONC-15 | [CONC-15] LoginThrottle Lacks Mutex Synchronization Causing RuntimeError and Race Conditions | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 3750 | REL-06 | [REL-06] FastAPI Lifespan Teardown Chain Aborts on Exception Leaking Singleton Lock | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3786 | FE-31 | [FE-31] Unwrapped sessionStorage.setItem in ClassroomTeacherPage Locks Out Teacher with CLASSROOM_ALREADY_ACTIVE | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 3814 | FE-32 | [FE-32] Asynchronous window.open + preview.document.write in Student Notebook Printing Crashes on Closed Tab | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 3848 | SEC-38 | [SEC-38] Absence of Trusted Reverse Proxy IP Resolution in Rate Limiting Causes Global DoS | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 3874 | SEC-39 | [SEC-39] Windows Backslash & Drive-Letter Path Traversal in Prepared Ingest Unpacking Zero-Day | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 3949 | SEC-40 | [SEC-40] CSV Formula Injection (CWE-1236) in Annotation Measurements Export API | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 3999 | BUG-15 | [BUG-15] Missing Initial RuntimeGuard Row Causes Permanent Upload Blockade with HTTP 423 | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 4050 | BUG-16 | [BUG-16] Uncaught ValueError in Library Cursor Pagination Datetime Deserialization Returns HTTP 500 | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 4093 | CONC-16 | [CONC-16] Concurrency Race Condition on Study Readiness and AI Event Reporting Unique Constraint | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 4148 | FE-33 | [FE-33] Permanent SPA Robots Meta Tag Pollution in ViewerPage Blocks Search Engine Indexing | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 4190 | FE-34 | [FE-34] Uncaught DOMException in SharedViewerPage.select Crashes Shared Viewer on Safari Private Browsing | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 4232 | REL-07 | [REL-07] Worker Missing Heartbeat During generate_dzi Causes Stale Recovery Race Condition & Dual-Worker Derivative Corruption | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 4278 | BUG-17 | [BUG-17] Unhandled Alpha and Multichannel Bands in generate_dzi Crashes Libvips with JPEG Conversion Error | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 4309 | REL-08 | [REL-08] Unhandled Windows File Locking / PermissionError in remove_slide Crashes Worker Process in Infinite Loop | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 4363 | SEC-41 | [SEC-41] Missing Deletion Event in Desktop Sync Broadcast Leads to Zombie Local Slides & Folders | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 4390 | DATA-11 | [DATA-11] Published Slide Trashing & Restoring Leaves State Desynchronized and Causes Public Route 404 | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 4423 | FE-35 | [FE-35] Client Autosave Acknowledgement Failure Deadlocks Mutation Queue in Perpetual Conflict | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 4460 | SEC-42 | [SEC-42] Cross-Device / Cross-Filesystem Link Failure (EXDEV) in Desktop OME Ingest Aborts Ingestion and Quarantines Files | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 4486 | FE-36 | [FE-36] Uncaught DOMException in OpenSeadragonViewer Crashes WSI Viewer in Safari Private Browsing | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 4534 | FE-37 | [FE-37] Unwrapped sessionStorage.setItem in Study API Burns Single-Use Invitation Codes and Permanently Locks Out Learners | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 4582 | FE-38 | [FE-38] Uncaught DOMException in StudyPage.tsx Locale Storage Crashes Study UI on Mount | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 4623 | SEC-43 | [SEC-43] Cookie Attribute Mismatch in Study Withdrawal Leaves Persistent Session Cookie on HTTPS | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 4672 | BUG-18 | [BUG-18] Missing Parent Directory Creation in install_prepared_package Crashes on Fresh Deployments | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 4712 | SEC-44 | [SEC-44] CLI Admin Creation and Password Reset Uncaught ValueError Traceback and Unvalidated Username | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 4768 | DATA-12 | [DATA-12] IndexedDB Connection Leak on Transaction Error in Study Local Store | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 4838 | DATA-13 | [DATA-13] Missing DesktopSyncEvent in Layer CRUD Operations Causes Desktop Sync Desynchronization and Conflict Lockout | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 4888 | DATA-14 | [DATA-14] Trashing a Folder Leaves Child Slides in Invisible Orphaned State Deadlocking Permanent Deletion with HTTP 409 FOLDER_NOT_EMPTY | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 4945 | SEC-45 | [SEC-45] Annotation Endpoints Omit Trashed Slide Check Permitting Mutation and Data Leakage on Trashed Clinical Slides | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 4981 | FE-39 | [FE-39] Premature database.close() on Request Success in Classroom Notebook Aborts Uncommitted Transactions | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 5040 | FE-40 | [FE-40] IndexedDB Connection Leak on Transaction Error and Unhandled Storage Rejection in Study Pack Authoring | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 5123 | BUG-19 | [BUG-19] Unescaped SQL Wildcard Characters in Library Tag Filtering Allows Wildcard Injection and Result Spoofing | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 5165 | TIME-04 | [TIME-04] Offset-Naive Datetime Comparison in Desktop Sync Pagination Triggers TypeError / Database 500 Crash | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 5212 | DATA-15 | [DATA-15] Trashed Slides Retained in Public Share Manifests Leaks Clinical Diagnoses and Breaks Shared Slides with HTTP 404 | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 5305 | CONC-17 | [CONC-17] Missing Hub, Cooldown, and Presenter Cleanup on Natural Classroom Expiration and Synthetic Reset Causes SSE Connection Leaks and Sequence Desynchronization | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 5385 | BUG-20 | [BUG-20] Shared JPEG Tables Stripping Omits DRI Marker Breaking Restart Interval Decoding in Native OME-TIFF Tiles | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 5443 | TIME-05 | [TIME-05] Unhandled Offset-Naive Datetime Comparison in Share Delivery Manifest Route Causes TypeError Crash Resulting in 404 for All Expiring Shared Slides | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 5491 | FE-41 | [FE-41] Premature Sequence Advancement on Stream Gap in Classroom Stream Sync Applies Out-of-Order Events During Background Resync | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 5557 | CONC-18 | [CONC-18] Concurrent Task Submissions Race Past Monotonic Throttle Check Causing Unhandled Unique Constraint 500 Crash on uq_study_progress_task | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 5625 | DATA-16 | [DATA-16] Expired Shares Remain Marked is_active=True Deadlocking Target Folder and Collection Re-Sharing with HTTP 409 SHARE_ALREADY_ACTIVE | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 5671 | DATA-17 | [DATA-17] Deleted Collections and Trashed Folders Fail to Cascade Revoke Shares and Delivery Manifests Leaking Proprietary Slides | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 5708 | BUG-21 | [BUG-21] Event Sequences and Presence Expiry Handles Not Purged on Session Reset or Termination Causes Event Sequence Skew and Memory Leak | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 5740 | OPS-11 | [OPS-11] Tile Service Readiness Probe Performs Synchronous OME Index Parse and Full Directory Glob on Every Probe Inducing CPU Spikes and Service Outages | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 5769 | OPS-12 | [OPS-12] Worker Heartbeat Writer Lacks Exception Handling and Zero-Tolerance Clock Check Causes False-Positive Worker Restarts | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 5808 | CONC-19 | [CONC-19] Absence of In-Flight Job Heartbeat During Long-Running generate_dzi Causes Stale Recovery Re-Queueing and Conversion Directory Collision | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 5851 | FE-42 | [FE-42] Tight-Loop Unbacked Retry in createClassroomSnapshotReconciler Spams API on Transient Version Lag and Aborts with Unrecoverable Rejection | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 5880 | FE-43 | [FE-43] Unhandled Promise Rejection and Lost Version on Roster Reconciliation Failure Freezes Teacher Roster Synchronization | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 5906 | PERF-09 | [PERF-09] Unbounded Recursive Directory Walk in storage.usage() Blocks ASGI Worker and Crashes with FileNotFoundError on Concurrent Ingest/Eviction | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 5960 | CONC-20 | [CONC-20] Uncommitted Database Transaction Held During Multi-Minute Desktop Slide Archive Extraction Blocks Global Database Access and Triggers SQLite Lock Timeouts | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 6066 | SEC-46 | [SEC-46] Missing Formula Sanitization in Annotation CSV Export Enables Client-Side CSV Injection and Remote Command Execution | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 6114 | DATA-18 | [DATA-18] Study Progress CSV Export Omits Course Existence Check and Streams In-Memory Dataset Without Attachment Header | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 6204 | BUG-22 | [BUG-22] Missing Thumbnail Requirement in Prepared Ingest Results in Orphaned Thumbnail References and Broken Gallery Images | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 6235 | FE-44 | [FE-44] Classroom Event Stream Cursor Prematurely Updates Sequence on Event Gaps Permitting Out-of-Order Execution During Recovery | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 6306 | FE-45 | [FE-45] Classroom Teaching Overlays Suppress Canvas Clear When Annotations Array Empties Leaving Ghost Annotations on Screen | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 6357 | BUG-23 | [BUG-23] Annotation Layer Deletion Fails with 409 Conflict When Only Tombstoned Annotations Exist | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 6404 | DATA-19 | [DATA-19] Permanent Folder Deletion Omits Desktop Sync Delete Event Emitting Zombie Folders on Paired Clients | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 6442 | CONC-21 | [CONC-21] Unsynchronized Iteration Over _subscribers in _publish() and reset_session() Triggers RuntimeError: Set changed size during iteration | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 6487 | BUG-24 | [BUG-24] Classroom Slide Readiness and Descriptor Generation Reject OME Dynamic Slides with 409 Conflict and 404 Tile Failures | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 6553 | FE-46 | [FE-46] ClassroomTeacherPage Omits EventSource Error Handler Leaving Presenters Blind to Disconnections and Dropped Streams | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 6590 | DATA-20 | [DATA-20] Unconditional Closing Vertex Append in _polygon_coordinates() Generates Duplicate Vertices Breaking RFC 7946 GeoJSON | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 6616 | DATA-21 | [DATA-21] Uncaught IntegrityError During Folder Restore Crashes with HTTP 500 on Name Collision Instead of 409 Conflict | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 6648 | SEC-47 | [SEC-47] Unhandled Argon2 InvalidHash → 500 on Corrupt Hash | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 6658 | BUG-25 | [BUG-25] KeyError on Unknown Membership Role → 500 | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 6668 | BUG-26 | [BUG-26] Org Slug/DisplayName Normalization Bypasses Validation | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 6678 | OPS-13 | [OPS-13] Engine Cache Key Omits Password Content → Stale After Rotation | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 6688 | PERF-10 | [PERF-10] Double Full-Index Parse Per Dynamic Tile | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 6698 | SEC-48 | [SEC-48] Migration FK Check Identifier Injection via f-string | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 6708 | DATA-22 | [DATA-22] Migration Manifest Unbounded PK List → OOM | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 6718 | CONC-22 | [CONC-22] Reconcile Holds Write Lock Across FS Walks | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 6728 | SEC-49 | [SEC-49] Manual Classroom Accepts Trashed-Folder Slides | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 6738 | BUG-27 | [BUG-27] sort=manual Outside Collection → 500 | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 6748 | BUG-28 | [BUG-28] Saved-View Tags/State/Dates Silently Dropped | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 6758 | BUG-29 | [BUG-29] Redeem Ignores ends_at — Burns Single-Use Code | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 6768 | FE-47 | [FE-47] DesktopConnect Stale State on ?code= Change | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 6778 | FE-48 | [FE-48] ViewerPage Leaks noindex Meta to SPA | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 6791 | SEC-50 | [SEC-50] offline_slide Omits Checking slide.trashed_at is None Permitting Paired Desktop Clients to Exfiltrate/Download Trashed Clinical Slides | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 6827 | PERF-11 | [PERF-11] Single Global Mutex Gate with 1.0s Timeout Serializes All Classroom Mutations Across Entire System Causing 503 Spikes | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 6874 | PERF-12 | [PERF-12] Unbuffered Row-by-Row database.flush() in apply_result_bundle() for Up to 2,000,000 Objects Freezes ASGI Event Loop and Triggers Process OOM | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 6931 | BUG-30 | [BUG-30] Desktop Result Delivery Admission Rejects Ingestion with 409 Conflict When Only Tombstoned Annotations Exist on Slide | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 6963 | BUG-31 | [BUG-31] Lazy Classroom Expiry in create_session() Deletes Expired Database Sessions Without Evicting In-Memory Hub State Leaking Memory | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 7010 | DATA-23 | [DATA-23] Desktop Library Items Query Hardcodes 100-Folder Limit Without Pagination Silently Truncating Folder Trees for Paired Clients | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 7044 | DATA-24 | [DATA-24] GeoJSON Annotation Import Unconditionally Slices [:-1] Truncating Real Vertices and Crashing on Triangles | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 7081 | PERF-13 | [PERF-13] TileRouteService._dynamic_slide() Bypasses OmeTileRenderer Index Cache Parsing Multi-Megabyte JSON on Every Single Dynamic Tile Request | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 7158 | PERF-14 | [PERF-14] build_ome_tile_index() Decodes Every Single JPEG Tile Across Entire WSI Pyramid With Pillow Freezing Ingest Worker for Minutes | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 7213 | PERF-15 | [PERF-15] ClassroomPrewarmer and restore_prewarm() Reject Dynamic OME Slides and Silently Discard Multi-Classroom Sessions | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 7278 | BUG-32 | [BUG-32] purge_due_study_data() Hard Deletes StudyLearnerSession Without Cascading StudyProgress Resulting in Orphaned Rows and Foreign Key Inconsistencies | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 7325 | BUG-33 | [BUG-33] StudyRoutes.withdraw() Hard-Deletes Learner Session Violating Schema Status Invariants and Destroying Research Participation Audits | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 7377 | FE-49 | [FE-49] AnnotationAutosave.drain() Leaves inFlight Batch Wedged on 4xx Client Errors Permanently Freezing User Workspace | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 7421 | FE-50 | [FE-50] Concurrent Base64 Data URL Conversion of 100 Offline Notebook Entries Crashes Mobile WebKit Tab With OOM | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 7463 | BUG-34 | [BUG-34] PreparedIngest Modulo Sampling Uses Constant expected_count Instead of Loop Counter file_count Skipping Verification or Freezing Unpack | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 7500 | BUG-35 | [BUG-35] StudyPackContract.score_task() Collapses Spatial Target Rectangles to Center Points Scoring Valid Tissue Hits as False | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 7531 | CONC-23 | [CONC-23] ClassroomHub Permanently Locks Out Reconnecting Students into _retired_participants After Transient Network Disconnections | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 7591 | FE-51 | [FE-51] OpenSeadragonViewer PerformanceObserver Hardcodes '/tiles/' Pattern Ignoring /_pathlab_ome/ Disabling Dynamic Tile Network Throttling | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 7635 | FE-52 | [FE-52] TraceSim Web Worker Unconditionally Invokes caches.open() Crashing AI Model Preparation in Private Browsing Mode | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 7712 | SEC-51 | [SEC-51] ClassroomRoutes.expire_control() Commits Database Transaction Without Route Guard Prematurely Persisting Intermediate State | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 7762 | DATA-25 | [DATA-25] StorageAccounting.reconcile_storage() Fails Unconditionally on Trashed or Deleting Slides Missing Derivative Directories | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 7832 | BUG-36 | [BUG-36] IdentityRoutes.create_membership() Blindly Re-Inserts Violating Unique Constraint Preventing Reactivation of Disabled Memberships | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 7893 | DATA-26 | [DATA-26] apply_result_bundle() Exception Handler Wipes Out Entire Slide Results Directory Destroying Previous Successful Deliveries | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 7937 | BUG-37 | [BUG-37] upload_prepared_ingest() Exception Handler Only Catches HTTPException Leaking Partial Stream Bytes on Client Disconnect | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 7992 | FE-53 | [FE-53] stitchHoles() in booleanCore.ts Injects undefined into Coordinate Array on Degenerate Outer Ring Crashing Canvas Renderer | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 8061 | FE-54 | [FE-54] Synchronous URL.revokeObjectURL() in downloadStudyInvitations() Immediately Aborts Asynchronous File Downloads in Safari & Firefox | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 8110 | BUG-38 | [BUG-38] study_tile() Unconditionally Forbids Dynamic OME-TIFF Slides Returning 404 for All Modern Study Pack Slides | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 8175 | SEC-52 | [SEC-52] get_admin_slide() Returns Trashed Slides as Ready with Active Tile Sources Causing Immediate 404s and Metadata Leaks | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 8222 | BUG-39 | [BUG-39] folder_subtree_ids() Omission of trashed_at Filter Causes Share Generation to Crash with ShareConflict or Leak Trashed Hierarchies | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 8276 | CONC-24 | [CONC-24] ClassroomHub._retire_subscriber() Mutates _subscribers and current_connections Outside _presence_lock Causing Lost Updates and Connection Count Drift | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 8323 | FE-55 | [FE-55] ClassroomStudentPage.ask() Clears Local Pin State Without Calling Backend clearPin() Causing Ghost Pin Desynchronization | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 8378 | FE-56 | [FE-56] Uncaught Taint SecurityError in captureVisibleTissue() Bypasses Exception Handler Crashing Student Screenshot Pipeline | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 8438 | BUG-40 | [BUG-40] Classroom Teaching Annotation Mutations Omit state_version Increments Breaking Snapshot Reconciler Recovery on Stream Reconnect | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 8478 | CONC-25 | [CONC-25] ClassroomRoutes.publish_pin() and clear_pin() Omit MutationGuard Allowing Concurrent Pin Flooding to Race DB State | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 8532 | FE-57 | [FE-57] ClassroomStudentPage.clicked() Commits Local Pin State Before publishPin() Network Rejection Showing Ghost Pins on Failure | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 8587 | DATA-27 | [DATA-27] remove_slide() Fails to Remove individual_delivery_for(public_id) Directory Leaving Derivative Hardlinks Stranded Permanently | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 8626 | BUG-41 | [BUG-41] _reconcile() Traps RuntimeGuard in Indefinite DRAINING Deadlock When Active Classroom Session Ends or Cancels Before Live Phase | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 8699 | CONC-26 | [CONC-26] Unheartbeated Long generate_dzi() Runs Cause recover_stale_jobs() to Requeue Running Jobs Resulting in Concurrent Overwriting Workers | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 8743 | FE-58 | [FE-58] AnnotationAutosave Abandons In-Flight Queue and Freezes Version Advancement on onAcknowledged Failure Locking 409 Conflict | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 8778 | BUG-42 | [BUG-42] delete_layer Blocks Deletion of Visually Empty Layers Containing Soft-Deleted Tombstones with 409 | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 8809 | DATA-28 | [DATA-28] finalize_upload() Leaves Storage Reservation Stranded for 24 Hours on Corrupt or Invalid Uploads | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 8841 | BUG-43 | [BUG-43] validate_folder_parent() Missing Cycle Guard Causes Infinite Loop and Worker Hang on Cyclic Ancestry | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 8860 | DATA-29 | [DATA-29] upload_result_delivery Never Unlinks Extracted .plresults Staging Archives Leaking Up to 2 GB per Delivery | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 8887 | BUG-44 | [BUG-44] create_result_delivery Rejects Valid Analysis Result Delivery with 409 RESULT_CONFLICT Due to Unfiltered Soft-Deleted Annotations | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 8915 | PERF-16 | [PERF-16] apply_result_bundle() Per-Object database.flush() and Unbatched ORM Allocation Causes Container OOM on Result Imports | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 8968 | BUG-45 | [BUG-45] StudyRoutes.withdraw() Hard-Deletes Session Violating Clinical Audit Trail and Leaving Orphaned Records on SQLite | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 8996 | DEV-02 | [DEV-02] Standalone / Local Development Missing Fallback Route for /tiles/{public_id}/{version}/{tile_path} Returns 404 | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 9022 | FE-59 | [FE-59] SharedFolderBranch and SharedFolderNode Fail to Escape Special JSON Characters in Folder Paths Breaking Tree Construction | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 9037 | CONC-27 | [CONC-27] StudyCourse Activation Race Condition Allows Concurrent Creation of Multiple Active Courses | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 9063 | BUG-46 | [BUG-46] build_ome_tile_index() Hardcodes tif.series[0] Triggering Ingestion Failure When Slide Pyramid Is In Secondary Series | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 9092 | CONC-28 | [CONC-28] ClassroomTeacherPage Premature suppressPublish Clearance Creates Animation Frame Feedback Loop | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 9122 | SEC-53 | [SEC-53] SQLite FTS _search_ids Unescaped Wildcard Syntax Triggers Unhandled OperationalError and 500 DoS | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 9175 | BUG-47 | [BUG-47] trash_folder() Permits Trashing Folders with Active Slides Creating Invisible Ghost Slides and Unresolvable State | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 9215 | BUG-48 | [BUG-48] delete_collection() and trash_folder() Bypass _has_active_share Check Corrupting Public Links | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 9237 | DATA-30 | [DATA-30] remove_grant() Unconditionally Purges individual_delivery_for Files Breaking Concurrent Grants | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 9275 | PERF-17 | [PERF-17] ome_tiles.py _render_fallback() Scales Entire High-Resolution Image Before Cropping Causing Massive Memory Spikes | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 9295 | SEC-54 | [SEC-54] revoke_share() Omits Deletion of Public Delivery Manifest Allowing Continued Tile Access | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 9335 | BUG-49 | [BUG-49] share_delivery_public_id() Off-by-Timezone Naive vs Aware Comparison Raises TypeError and Rejects Valid Shares | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 9356 | CONC-29 | [CONC-29] TileCache.get_or_create() Leader Coalescing Indefinite Hang on Worker Thread Cancellation | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 9386 | BUG-50 | [BUG-50] create_ome_ingest and create_result_delivery Commit Database Records Before File Creation Leaving Ingests in Deadlock State | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 9429 | PERF-18 | [PERF-18] StorageLayout.usage() Unindexed Synchronous os.walk() on 500,000+ Files Freezes Worker Thread During Upload Admission | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 9455 | DATA-31 | [DATA-31] rotate_share() Fails to Migrate Staging Manifest Leaving Old Public Link Functional and New Link Broken | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 9488 | PERF-19 | [PERF-19] _publish_derivative_to Redundant Per-Tile mkdir() Syscalls Severely Throttle Slide Publication | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 9514 | BUG-51 | [BUG-51] ClassroomHub Stale Participant Eviction Flaw Permanently Locks Classroom with CLASSROOM_FULL on Server Restart | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 9556 | DATA-32 | [DATA-32] desktop_finalizer.py Abandons Failed prepared_package Archives on Disk Leaking Up to 10 GB per Ingest | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 9577 | CONC-30 | [CONC-30] worker.py Delete Job Strands "running" Job on SQLite for 5 Minutes Due to Disabled FK Cascades | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 9604 | DATA-33 | [DATA-33] worker.py Conversion Failure Abandons Incomplete Pyramid Tiles on Disk Leaking Storage Indefinitely | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 9631 | DATA-34 | [DATA-34] main.py TUS finalize_upload() Copy Failure Leaves Orphaned .partial Files on Cross-Device Moves | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 9664 | FE-60 | [FE-60] snapshotReconciler.ts Zero-Delay Retry Burst Causes False-Positive Reconciler Failures | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 9696 | PERF-20 | [PERF-20] notebook.ts saveEntry() Deserializes All Blobs into RAM to Check Entry Count Triggering WebKit OOM Crash | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 9733 | FE-61 | [FE-61] ClassroomTeacherPage "Show pinned field" Omission of Local Slide Transition & Viewport Navigation Desynchronizes Presenter from Students | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 9782 | FE-62 | [FE-62] ClassroomTeacherPage Slide Navigator Selection Omits Viewport Broadcast Leaving Students Stranded on Prior Slide in Guide Mode | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 9815 | BUG-52 | [BUG-52] teacher_state Endpoint Omits expire_control() Leaving Presenter UI Locked with Stale Expired Student Controller Lease | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 9856 | FE-63 | [FE-63] ClassroomTeacherPage Missing session-ended SSE Event Listener Leaves Teacher in Zombie Session State on Administrative Revocation | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 9881 | FE-64 | [FE-64] ClassroomStudentPage Missing Slide-Scoped Key / Reset on StudentDrawingOverlay Bleeds Drawings Across Guided Slide Switches | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 9921 | SEC-55 | [SEC-55] get_slide_details() and Static thumbnail() in library_routes.py Omit Trashed Slide Checks Permitting Data Exfiltration of Soft-Deleted Pathology Slides | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 9969 | CONC-31 | [CONC-31] ClassroomRoutes.stream_response() Event Sequence Race Condition Seeds Subscriber with Stale eventSequence Desynchronizing Client Stream Recovery | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 10030 | PERF-21 | [PERF-21] apply_result_bundle Executes Per-Object database.flush() and Iterates 2,000,000 ORM Instances into Python RAM Triggering Worker OOM Crash | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 10089 | DATA-35 | [DATA-35] desktop_annotation_batch Blindly Overrides candidate.base_version to Current Slide Version Silently Destroying Concurrent Web Annotations | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 10153 | DATA-36 | [DATA-36] purge_due_study_data in study_routes.py Omits StudyProgress Deletion Permanently Stranding Orphaned Student Progress Records | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 10196 | SEC-56 | [SEC-56] export_progress in study_routes.py Omits Formula Sanitization on task_id Allowing CSV Formula Injection | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 10238 | SEC-57 | [SEC-57] study_tile Endpoint in study_routes.py Omits slide.trashed_at Check Permitting Access to Soft-Deleted Pathology Slides | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 10271 | CONC-32 | [CONC-32] study_routes.py redeem Endpoint Lacks Race Condition Protection Causing Unhandled IntegrityError 500s and Course Oversubscription | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 10308 | SEC-58 | [SEC-58] Unrestricted report_readiness Endpoint Allows Denial of Service and Data Poisoning of Faculty Study Metrics | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 10348 | BUG-53 | [BUG-53] score_task in study_pack_contract.py Evaluates Center Point Chebyshev Distance Rejecting Valid User Selections on Large Target Regions | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 10373 | DATA-37 | [DATA-37] upload_result_delivery Deletes Entire Slide Results Directory on Single Bundle Validation Failure Wiping Previous Runs | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 10415 | CONC-33 | [CONC-33] Multi-Worker Startup Race in PreparedIngestFinalizer._recover Re-finalizes Active Ingests Causing File Extraction Collisions | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 10456 | CONC-34 | [CONC-34] Concurrent Desktop Chunk Uploads Double-Increment received_bytes Permanently Freezing Ingest in Uploading State | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 10494 | CONC-35 | [CONC-35] Non-Atomic exchange_pairing Allows Issuance of Multiple Active Credentials from a Single Pairing Code | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 10536 | FE-65 | [FE-65] StudyPage Spatial Selection Omits Canvas Visual Target Indicator Confusing Students on Click Accuracy | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 10574 | DATA-38 | [DATA-38] localStore.ts Resolves appendLocalRecord Before IndexedDB Transaction Commits Causing Silent Data Loss on Tab Close | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 10624 | SEC-59 | [SEC-59] withdraw Endpoint Uses Default Insecure Attributes in delete_cookie Failing to Clear Session on HTTPS | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 10657 | BUG-54 | [BUG-54] Missing Invitation Revocation Route Prevents Invalidation of Lost or Exposed Study Codes | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 10705 | FE-66 | [FE-66] Uncaught SecurityError on caches.open in Firefox/Safari Private Browsing Completely Breaks Local AI Initialization | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 10749 | PERF-22 | [PERF-22] Coarse Course-Wide Submission Throttling Blocks Answering Different Practice Tasks Forcing 30-Second Wait Per Question | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 10787 | CONC-36 | [CONC-36] Read-Route Concurrency Stampede on Course Expiration Triggers Lock Contention in learner_session | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 10822 | DATA-39 | [DATA-39] Duplicate Feature Index in StudyPage.tsx Distorts Local AI Neural Network Input Vector | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 10857 | PERF-23 | [PERF-23] get_desktop_slide_content Mandates Open-Ended Byte Ranges Disabling Chunked HTTP Download Managers | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 10896 | SEC-60 | [SEC-60] export_csv() in annotations.py Omits Formula Sanitization on metadata.title and layer Allowing CSV Formula Injection | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 10942 | BUG-55 | [BUG-55] Unhandled KeyError on Missing Layer ID in export_csv Crashes Measurement Export with HTTP 500 | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 10981 | SEC-61 | [SEC-61] annotation_routes.py get_slide() Omits Soft-Delete Checks Permitting Modification and Data Exfiltration of Trashed Slide Annotations | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 11008 | DATA-40 | [DATA-40] import_annotations Assigns Duplicate sort_order = -1 on GeoJSON Imports Breaking Subsequent PathLab JSON Re-Imports | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 11074 | PERF-24 | [PERF-24] list_items Redundant count(*) on Viewport Queries Causes Severe Database Load During Pan Navigation | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 11121 | BUG-56 | [BUG-56] list_items Missing Coordinate Inversion Validation Silently Returns Empty Results on Inverted Viewport Bounds | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 11163 | DATA-41 | [DATA-41] PathLab JSON Import Does Not Re-Index Layer Sort Orders Causing Sort Collisions with Existing Slide Layers | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 11214 | DATA-42 | [DATA-42] trash_folder Fails to Mark Contained Slides as Trashed Creating Invisible Phantom Slides | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 11260 | SEC-62 | [SEC-62] delete_collection Deletes Collection with Active Public Shares Leaving Orphaned Public Manifests | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 11299 | PERF-25 | [PERF-25] TileRouteService._dynamic_slide Parses 16MB Index JSON from Disk on Every Single Tile Request | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 11341 | BUG-57 | [BUG-57] add_collection_items Omits Soft-Delete Check Allowing Trashed Slides to be Added to Collections | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 11372 | CONC-37 | [CONC-37] Time-of-Check Race Condition in activate_share Permits Duplicate Active Shares for Same Target | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 11416 | PERF-26 | [PERF-26] public_manifest Fetches Entire Folder Slide Subtree into Memory Merely to Read Name and Description | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 11466 | BUG-58 | [BUG-58] validate_folder_parent Lacks Loop Cycle Detection Causing Infinite While Loop on Corrupt Hierarchies | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 11504 | SEC-63 | [SEC-63] logout() in main.py Omits secure, httponly, and samesite in delete_cookie Leaving Admin Cookie on HTTPS | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 11545 | PERF-27 | [PERF-27] recover_password() Fetches All Database Users into Memory to Normalize Username | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 11575 | BUG-59 | [BUG-59] streamSync.ts Advances Cursor Sequence on Gap Causing Silent Desync on Subsequent Events | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 11612 | BUG-60 | [BUG-60] autosave.ts Skips In-Flight Cleanup and Version Advancement on Acknowledgement Failure | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 11661 | PERF-28 | [PERF-28] OpenSeadragonViewer Uses buffered: true in PerformanceObserver Replaying Obsolete Resource Timings | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 11696 | DATA-43 | [DATA-43] saveEntry in notebook.ts Uses add() Instead of put() Failing on Existing Note Updates | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 11722 | BUG-61 | [BUG-61] FolderTree.tsx flatten Lacks Visited Guard Crashing Browser Tab on Cyclic Hierarchies | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 11769 | SEC-64 | [SEC-64] ensure_grant Overwrites flagged Clinical Privacy Status to passed Bypassing PHI Gate | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 11801 | DATA-44 | [DATA-44] delete_all_slide_grants Leaves Slide in PUBLISHED State After Unpublishing Derivatives | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 11835 | SEC-65 | [SEC-65] offline_slide Omits Soft-Delete Check Allowing Trashed Slide Download via Desktop Offline API | fixed upstream |
| docs/reports/BUG_REPORT_CODEX.md | 11878 | BUG-62 | [BUG-62] deliver_file Omits URL-Encoding in X-Accel-Redirect Breaking Paths with Special Characters | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 11909 | DATA-45 | [DATA-45] storage_contribution_expression Omits Null Coalescing Causing Zero-Byte Storage Accounting | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 11938 | PERF-29 | [PERF-29] Missing Pruning on DesktopSyncEvent Causes Indefinite Database Table Bloat | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 11959 | BUG-63 | [BUG-63] upload.ts Passes NaN Progress on Zero-Byte or Indeterminate Upload Streams | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 11980 | BUG-64 | [BUG-64] validate_ome_tiff Rejects Valid 3-Channel RGB Images Using Standard Channel Axis "C" | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 12009 | PERF-30 | [PERF-30] Synchronous Recursive Filesystem Traversal in TileCache._reconcile Blocks Server Startup | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 12038 | CONC-38 | [CONC-38] Unhandled Lock Contention on Every Tile Cache Hit via Filesystem stat Calls Under RLock | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 12080 | BUG-65 | [BUG-65] booleanCore.ts stitchHoles Inserts undefined Coordinates on Degenerate Outer Rings | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 12121 | BUG-66 | [BUG-66] roster.ts Drops Pending Version on Reconcile Failure Causing Permanent Out-of-Sync Roster | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 12154 | PERF-31 | [PERF-31] snapshotReconciler.ts Retries Without Backoff Causing Rapid False-Positive Failures on Replica Lag | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 12188 | BUG-67 | [BUG-67] validate_ome_tiff Throws Unhandled IndexError on Empty ome.images Collection | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 12215 | SEC-66 | [SEC-66] Classroom Participant Session Invalidation Omission on Session Termination | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 12245 | CONC-39 | [CONC-39] Classroom Controller Lease TOCTOU Race Condition in Control Grant | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 12279 | PERF-32 | [PERF-32] Classroom Participant Roster Sequential Full Table Scan Degradation | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 12305 | BUG-68 | [BUG-68] Classroom Event Hub Subscriber Message Buffer Leak on Session Teardown | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 12331 | DATA-46 | [DATA-46] Teaching Annotation Point Coordinate Validation & Non-Finite Number Acceptance | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 12357 | SEC-67 | [SEC-67] Classroom Question Text Unsanitized HTML Acceptance Permitting Stored XSS | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 12390 | BUG-69 | [BUG-69] Classroom Question Deletion Leaves Orphaned Receipt Records | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 12412 | SEC-68 | [SEC-68] Missing nosniff on Tile/Thumbnail Delivery (Sniff → Stored XSS) | false positive |
| docs/reports/BUG_REPORT_CODEX.md | 12422 | REL-09 | [REL-09] Presenter Flush Loss on CancelledError + Leaked in_flight | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 12432 | OPS-14 | [OPS-14] Capacity Monitor Non-Atomic + Advisory-Only Window | hardening |
| docs/reports/BUG_REPORT_CODEX.md | 12442 | FE-67 | [FE-67] Study Withdraw Leaves ONNX Worker/Course State (Cross-Course Contamination) | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 12452 | FE-68 | [FE-68] Invite Phase Poll Overlap + Post-Unmount Write | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 12462 | FE-69 | [FE-69] OSD Rotation Persists Across Slide Change | confirmed |
| docs/reports/BUG_REPORT_CODEX.md | 12472 | BUG-70 | [BUG-70] Prepared Ingest Rejects Valid JPEG Tile Filenames in DeepZoom Pyramids | fixed upstream |
| docs/reports/DEEP_SYSTEM_BUG_AUDIT.md | 45 | BUG-NEW-01 | BUG-NEW-01: Slide Deletion Worker Infinite Crash Loop on Classroom References | confirmed |
| docs/reports/DEEP_SYSTEM_BUG_AUDIT.md | 107 | BUG-NEW-02 | BUG-NEW-02: Sibling Conversion Workspace Deletion Race Condition in generate_dzi | hardening |
| docs/reports/DEEP_SYSTEM_BUG_AUDIT.md | 158 | BUG-NEW-03 | BUG-NEW-03: Password Recovery Verification Oracle & Throttle Bypass | confirmed |
| docs/reports/DEEP_SYSTEM_BUG_AUDIT.md | 221 | BUG-NEW-04 | BUG-NEW-04: Unindexed Full Table Scan in recover_password() | confirmed |
| docs/reports/DEEP_SYSTEM_BUG_AUDIT.md | 254 | BUG-NEW-05 | BUG-NEW-05: Global Unauthenticated Account Lockout & Thread-Unsafe Iteration in LoginThrottle | hardening |
| docs/reports/DEEP_SYSTEM_BUG_AUDIT.md | 308 | BUG-NEW-06 | BUG-NEW-06: Global Single-Mutex Starvation in ClassroomMutationGate | hardening |
| docs/reports/DEEP_SYSTEM_BUG_AUDIT.md | 351 | BUG-NEW-07 | BUG-NEW-07: Unthrottled Student Actions Forcibly Disconnect Presenter SSE | confirmed |
| docs/reports/DEEP_SYSTEM_BUG_AUDIT.md | 386 | BUG-NEW-08 | BUG-NEW-08: ClassroomHub._retire_subscriber Mutates Presence State Outside Lock | confirmed |
| docs/reports/DEEP_SYSTEM_BUG_AUDIT.md | 428 | BUG-NEW-09 | BUG-NEW-09: Uncaught IndexError in Subscriber.next_event | false positive |
| docs/reports/DEEP_SYSTEM_BUG_AUDIT.md | 459 | BUG-NEW-10 | BUG-NEW-10: score_task() Collapses Spatial Bounding Box to Center Point | confirmed |
| docs/reports/DEEP_SYSTEM_BUG_AUDIT.md | 488 | BUG-NEW-11 | BUG-NEW-11: Silent Overwrite of Web Annotations in Desktop Batch Sync | false positive |
| docs/reports/DEEP_SYSTEM_BUG_AUDIT.md | 524 | BUG-NEW-12 | BUG-NEW-12: Desktop Library Folder Sync Hardcoded 100-Folder Limit | confirmed |
| docs/reports/DEEP_SYSTEM_BUG_AUDIT.md | 548 | BUG-NEW-13 | BUG-NEW-13: Trashed Folders Cannot Be Permanently Deleted Due to Trashed Slides | confirmed |
| docs/reports/DEEP_SYSTEM_BUG_AUDIT.md | 580 | BUG-NEW-14 | BUG-NEW-14: Unwrapped localStorage Calls in OpenSeadragonViewer White-Screen Safari Private Browsing | confirmed |
| docs/reports/DEEP_SYSTEM_BUG_AUDIT.md | 618 | BUG-NEW-15 | BUG-NEW-15: IndexedDB Transaction Prematurely Aborted on database.close() in Classroom Notebook | confirmed |
| docs/reports/DEEP_SYSTEM_BUG_AUDIT.md | 663 | BUG-NEW-16 | BUG-NEW-16: Unbounded Base64 Conversion of 100 Notebook Entries Freezes Mobile Tab | confirmed |
| docs/reports/DEEP_SYSTEM_BUG_AUDIT.md | 688 | BUG-NEW-17 | BUG-NEW-17: Micro-Queue Connection Starvation on PostgreSQL | hardening |
| docs/reports/DEEP_SYSTEM_BUG_AUDIT.md | 718 | BUG-NEW-18 | BUG-NEW-18: Tus Upload Finalization Moves File Before Database Commit | confirmed |
| docs/reports/DEEP_SYSTEM_BUG_AUDIT.md | 747 | BUG-NEW-19 | BUG-NEW-19: autoIncludeNew Library Share Configuration Silently Ignored | confirmed |
| docs/reports/DEEP_SYSTEM_BUG_AUDIT.md | 764 | BUG-NEW-20 | BUG-NEW-20: Thundering Herd of State Resyncs on control SSE Event | hardening |
| docs/reports/DEEP_SYSTEM_BUG_AUDIT.md | 784 | BUG-NEW-21 | BUG-NEW-21: Teacher Viewer Attachment Churn and Dual-Render Cycle | hardening |
| docs/reports/DEEP_SYSTEM_BUG_AUDIT.md | 813 | BUG-NEW-22 | BUG-NEW-22: Tus Resumption Fingerprint Collision Across Re-Uploads | confirmed |
| docs/reports/FULL_SYSTEM_QA_REPORT.md | 149 | section-149 | P1 — High Severity | duplicate |
| docs/reports/FULL_SYSTEM_QA_REPORT.md | 151 | BUG-01 | BUG-01: Tus Upload Finalization Lacks Idempotency; Duplicate Invocation Triggers Uncaught HTTP 500 (TUS_FINALIZE_FAILED) | confirmed |
| docs/reports/FULL_SYSTEM_QA_REPORT.md | 172 | BUG-02 | BUG-02: Multi-Worker Job Pickup Race Condition on SQLite; No Concurrency Protection | hardening |
| docs/reports/FULL_SYSTEM_QA_REPORT.md | 193 | section-193 | P2 — Medium Severity | duplicate |
| docs/reports/FULL_SYSTEM_QA_REPORT.md | 195 | BUG-03 | BUG-03: Synchronous 2,048-Element Sorting on Every Classroom HTTP Request Path | hardening |
| docs/reports/FULL_SYSTEM_QA_REPORT.md | 217 | BUG-04 | BUG-04: Process-Wide ClassroomMutationGate Couples Independent Classroom Sessions | hardening |
| docs/reports/FULL_SYSTEM_QA_REPORT.md | 234 | BUG-05 | BUG-05: pathlab-api Entrypoint Ignores All CLI Arguments and Flags | confirmed |
| docs/reports/FULL_SYSTEM_QA_REPORT.md | 255 | section-255 | P3 — Low Severity | duplicate |
| docs/reports/FULL_SYSTEM_QA_REPORT.md | 257 | BUG-06 | BUG-06: Tile Cache Error Handler Unconditionally Unlinks Target File on Replace Exception | hardening |
| docs/reports/FULL_SYSTEM_QA_REPORT.md | 276 | BUG-07 | BUG-07: Playwright Suite Cold-Start Timing Flakes Under Parallel Execution | hardening |
| docs/reports/FULL_SYSTEM_QA_REPORT.md | 304 | section-304 | 7. Security Findings | duplicate |
| docs/reports/FULL_SYSTEM_QA_REPORT.md | 306 | section-306 | Confirmed Vulnerabilities | duplicate |
| docs/reports/FULL_SYSTEM_QA_REPORT.md | 321 | section-321 | 8. Reliability / Recovery Findings | duplicate |
| docs/reports/FULL_SYSTEM_QA_REPORT.md | 332 | section-332 | 9. Performance Findings | duplicate |
| docs/reports/FULL_SYSTEM_QA_REPORT.md | 381 | section-381 | 12. Test Gaps | duplicate |
| docs/reports/FULL_SYSTEM_QA_REPORT.md | 394 | section-394 | 13. Optimization Opportunities | duplicate |
| docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md | 42 | section-42 | 2. In-Depth Architectural Findings | duplicate |
| docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md | 44 | FE-81 | Finding 1: Private Slide Preview Dead End & Full Page Reload (FE-81) | confirmed |
| docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md | 61 | FE-82 | Finding 2: Saved Views Missing Canonical Breadcrumb & View State Rehydration (FE-82) | confirmed |
| docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md | 90 | FE-83 | Finding 3: Redundant & Duplicated Menus in Library Navigator and Toolbar (FE-83) | hardening |
| docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md | 113 | FE-84 | Finding 4: Single-Slide Action Context Menu Silently Wipes Multi-Slide Selection (FE-84) | confirmed |
| docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md | 132 | FE-85 | Finding 5: Folder Cards in Main Workspace Lack Management Context Actions (FE-85) | hardening |
| docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md | 146 | FE-86 | Finding 6: Toolbar Navigation Buttons Lack Disabled States and Up-Button Root Boundaries (FE-86) | confirmed |
| docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md | 161 | FE-87 | Finding 7: Stale Annotation Revision History Swaps Revisions Across Distinct Annotations (FE-87) | confirmed |
| docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md | 187 | FE-88 | Finding 8: Service Role Capability Header Mismatch Exposes Dead Classroom Route on General Workers (FE-88) | false positive |
| docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md | 211 | FE-89 | Finding 9: Public and Learner Error Pages Render Dead-End Screens Without Navigation Escape (FE-89) | confirmed |
| docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md | 230 | FE-90 | Finding 10: Study Pack Authoring Allows Blank Task Creation and Specifies Inverted Version Limits (FE-90) | confirmed |
| docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md | 246 | FE-91 | Finding 11: Annotation Revision History Button Misleading Scope and Missing Idle Disabled State (FE-91) | hardening |
| docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md | 271 | FE-92 | Finding 12: Orphaned Dead Component DeleteSlideDialog.tsx Retained in Web Source Tree (FE-92) | hardening |
| docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md | 284 | FE-93 | Finding 13: Multi-Selection Metadata & Style Overwrite Destroys Individual Slide Annotation Attributes (FE-93) | confirmed |
| docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md | 299 | FE-94 | Finding 14: VertexEditor Hardcoded to First Point with Unhandled TypeError Crash on Empty Geometry Points (FE-94) | hardening |
| docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md | 316 | FE-95 | Finding 15: StorageWorkspace Discards Theme Switcher and AppRail Nests ARIA Meter Inside Interactive Button (FE-95) | hardening |
| docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md | 331 | FE-96 | Finding 16: Hard Browser Page Reload on "Preview" from SlideDetailsPanel and SlideViews Menu Bypasses SPA Routing (FE-96) | confirmed |
| docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md | 344 | FE-97 | Finding 17: Study Coach Inverted Spinbutton Limits, Raw Machine Error Codes & Destructive Window Navigation Assignment (FE-97) | confirmed |
| docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md | 361 | FE-98 | Finding 18: Missing Field Length Constraints (maxLength) on Slide Metadata & Upload Names Trigger 422 API Rejections (FE-98) | confirmed |
| docs/reports/SYSTEM_VULNERABILITY_AND_BUG_AUDIT.md | 22 | section-22 | Vulnerability & Bug Register | duplicate |
| docs/reports/SYSTEM_VULNERABILITY_AND_BUG_AUDIT.md | 37 | section-37 | Detailed Findings | duplicate |
| docs/reports/SYSTEM_VULNERABILITY_AND_BUG_AUDIT.md | 41 | SEC-01 | [SEC-01] Global RBAC Capability Bypass on Administrative Subsystems | fixed upstream |
| docs/reports/SYSTEM_VULNERABILITY_AND_BUG_AUDIT.md | 98 | SEC-02 | [SEC-02] Unbounded In-Memory Key Accumulation in Rate Limiters | confirmed |
| docs/reports/SYSTEM_VULNERABILITY_AND_BUG_AUDIT.md | 154 | SEC-03 | [SEC-03] Distributed Credential Stuffing Vector on Admin Login | fixed upstream |
| docs/reports/SYSTEM_VULNERABILITY_AND_BUG_AUDIT.md | 178 | BUG-01 | [BUG-01] Incompatible SQLite BEGIN IMMEDIATE Syntax on PostgreSQL | false positive |
| docs/reports/SYSTEM_VULNERABILITY_AND_BUG_AUDIT.md | 218 | BUG-02 | [BUG-02] In-Memory SQLite (sqlite:///:memory:) Creation Crash | fixed upstream |
| docs/reports/SYSTEM_VULNERABILITY_AND_BUG_AUDIT.md | 248 | BUG-03 | [BUG-03] Timezone Skew Between Naive & Aware UTC Datetimes | fixed upstream |
| docs/reports/SYSTEM_VULNERABILITY_AND_BUG_AUDIT.md | 267 | BUG-04 | [BUG-04] Redundant Synchronous File Hashing in HTTP Thread | hardening |
| docs/reports/SYSTEM_VULNERABILITY_AND_BUG_AUDIT.md | 290 | BUG-05 | [BUG-05] Unescaped SQL LIKE Wildcards in Library Search Fallback | fixed upstream |
| docs/reports/CODEX_IMPLEMENTATION_PLAYBOOK.md | 28 | section-28 | 2. Additional Forensic Findings & Hidden Traps | duplicate |
| docs/reports/CODEX_IMPLEMENTATION_PLAYBOOK.md | 32 | section-32 | 2.1 Trap A: Double Sequential Read on Multi-Gigabyte WSIs in conversion.py | hardening |
| docs/reports/CODEX_IMPLEMENTATION_PLAYBOOK.md | 48 | section-48 | 2.2 Trap B: SQLite QueuePool Connection Starvation | hardening |
| docs/reports/CODEX_IMPLEMENTATION_PLAYBOOK.md | 57 | section-57 | 2.3 Trap C: PostgreSQL max_connections=20 Bottleneck | hardening |
| docs/reports/CODEX_IMPLEMENTATION_PLAYBOOK.md | 70 | section-70 | 2.4 Trap D: Pathology Staining Color Fidelity (Missing ICC Fallback) | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 59 | SEC-01 | [SEC-01] Global RBAC Capability Bypass on Administrative Subsystems | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 66 | SEC-02 | [SEC-02] Privilege Escalation & Last-Owner Deletion Race in Identity Governance | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 73 | SEC-03 | [SEC-03] In-Memory Rate Limiting & Unthrottled Pairing Endpoint | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 80 | SEC-06 | [SEC-06] Path Boundary Validation Bypass in delivery.py When Redirects Disabled | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 87 | CONC-01 | [CONC-01] Non-Atomic Desktop Pairing Approval & Leaked Expired Handshakes | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 94 | CONC-02 | [CONC-02] Missing Transaction Lock on PostgreSQL During Password Recovery Throttle | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 101 | PERF-01 | [PERF-01] $O(N^2)$ In-Memory Descendant Traversal & Unbounded Slide Loading in Classroom | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 108 | BUG-07 | [BUG-07] Stale Job Recovery Skips Jobs with Null Heartbeats | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 115 | FE-01 | [FE-01] Missing Top-Level React Application Error Boundary | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 122 | FE-02 | [FE-02] Session Expiration Discards Private Slide Destination (returnTo) | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 129 | FE-03 | [FE-03] Indistinguishable Slide Loading Errors & Missing Retry | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 136 | FE-04 | [FE-04] Direct Exposure of Internal Docker Commands in Recovery UI | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 143 | FE-05 | [FE-05] Classroom Setup Lacks Folder Search, Pagination, & State Validation | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 150 | FE-08 | [FE-08] IndexedDB Connection Leak on Transaction Error in authoringStore.ts | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 157 | OPS-01 | [OPS-01] Deployment Script Failures on noexec Filesystems & Unbounded Capacity Controller Recovery | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 164 | OPS-02 | [OPS-02] Missing Deterministic Software Inventories (SBOM) & Security Baseline Drift | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 171 | CONC-03 | [CONC-03] Storage Accounting Quota Bypass via Omission of PostgreSQL Advisory Locking | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 178 | REL-01 | [REL-01] Slide Deletion Worker Crash Loop & Storage Desync on Classroom Slides (RESTRICT Foreign Key) | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 185 | FE-10 | [FE-10] IndexedDB Connection Leaks in Study Store | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 192 | BUG-08 | [BUG-08] Stale Job Recovery Query Omits Crashed checkpointing Jobs | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 199 | TIME-01 | [TIME-01] Timestamp Offset Corruption via Unsafe replace(tzinfo=UTC) | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 206 | SEC-08 | [SEC-08] Ineffective Revocation / Information Disclosure on Public Shares | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 213 | BUG-09 | [BUG-09] Sharing Outright Crash / TypeError on Expired Shares | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 220 | CONC-04 | [CONC-04] Library Share Activation Race Condition & Duplicate Active Shares | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 227 | FE-12 | [FE-12] Student Classroom Join Broken by Unhandled Notebook IndexedDB Failure | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 234 | FE-13 | [FE-13] Classroom Invite Page Destroys Active Review Session on Transient Poll Failure | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 241 | SEC-10 | [SEC-10] Classroom SSE Teacher Event Stream Unchecked Authorization Zero-Day | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 248 | SEC-11 | [SEC-11] Unauthenticated & Unthrottled Study Invitation Code Brute-Force | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 255 | SEC-13 | [SEC-13] Revoked Classroom Sessions Retain Individual Derivative Tiles on Disk & Caddy Edge | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 262 | SEC-14 | [SEC-14] Trashed Slide OME-TIFF File Download & Tile Viewing Authorization Leak | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 269 | CONC-05 | [CONC-05] Concurrent Study AI Event Reporting Triggers Unique Constraint Crashes & Lost Updates | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 276 | CONC-06 | [CONC-06] Study Course Learner Limit Admission Race Condition on Concurrent Redemption | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 283 | PERF-03 | [PERF-03] Synchronous Unbounded os.walk() in Desktop Ingest Storage Admission Freezes Event Loop | false positive |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 290 | TIME-02 | [TIME-02] Unsafe .replace(tzinfo=UTC) in Study Pack & Desktop Serializers Corrupting Timestamp Offsets | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 297 | DATA-02 | [DATA-02] Orphaned Derivative Directories Leaking Disk Storage on Unexpected Ingest Finalizer Exceptions | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 304 | SEC-16 | [SEC-16] Unauthenticated Global Account Lockout Denial-of-Service via In-Memory Username Throttling | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 311 | REL-02 | [REL-02] Classroom Teaching Annotations Exceed Hardcoded 4 KiB SSE Event Buffer Limit | false positive |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 318 | SEC-18 | [SEC-18] Unthrottled Student Pin & Control-Request Queue Flooding Forces Teacher SSE Disconnection (Remote DoS) | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 325 | DATA-04 | [DATA-04] Permanent Deletion of Slides and Folders Omits Desktop Sync Deletion Events & Leaves Orphaned Shares | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 332 | TIME-03 | [TIME-03] Inconsistent Offset-Naive utcnow() in Annotations and Worker Breaks PostgreSQL Datetime Comparisons | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 339 | FE-15 | [FE-15] IndexedDbDraftStorage Permanent Rejection Caching & Missing Memory Fallback Freezes Annotation Studio | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 346 | SEC-20 | [SEC-20] Uninitialized & Deadlocked Runtime Protection Mode Bricks Background Processing and All Slide Uploads | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 353 | SEC-21 | [SEC-21] Unauthenticated & Unbounded Desktop Pairing Code Flooding Database Denial-of-Service | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 360 | CONC-07 | [CONC-07] Desktop Pairing Exchange Concurrency Race Issues Multiple Tokens for Single-Use Code | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 367 | CONC-08 | [CONC-08] Concurrent First AI-Event Submissions Crash with Unique Constraint Violation & Cause Lost Updates | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 374 | DATA-05 | [DATA-05] Slide Deletion Fails to Purge Published Derivative Directory (delivery/individual/{public_id}) Causing Permanent Storage Leak | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 381 | DATA-06 | [DATA-06] Desktop Library Synchronization Truncates Folders at 100 with No Pagination or Cursor | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 388 | DATA-07 | [DATA-07] Desktop Annotation Batch Silently Bypasses Optimistic Concurrency Control with Fake Auto-Merge | false positive |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 395 | PERF-05 | [PERF-05] recover_password() Executes Unindexed Full Table Scan Loading All Database Users into Python Memory | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 402 | SEC-22 | [SEC-22] Password Recovery Code-Validity Oracle via Differential Error Codes Bypasses Throttling | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 409 | SEC-23 | [SEC-23] 90-day DesktopCredential Survives Password Change / Recovery (Credential-Generation Gap) | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 416 | SEC-24 | [SEC-24] disable_membership Leaves Legacy-Admin Session Fully Valid | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 423 | SEC-26 | [SEC-26] Public Share Manifest Leaks Trashed-Slide Metadata | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 430 | DATA-08 | [DATA-08] Share Publish / Rotate Commit-Then-Write Crash Window + Downtime | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 437 | SEC-28 | [SEC-28] Trashed-Slide Metadata / Annotation Read + Sync Bypass | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 444 | SEC-30 | [SEC-30] Config Fail-Open: extra="ignore" + Placeholder Secret + Prod-Only Validation | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 451 | OPS-05 | [OPS-05] reconcile_storage Single-Slide Raise Aborts Entire Run + Bricks Boot | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 458 | CONC-15 | [CONC-15] LoginThrottle Lacks Mutex Synchronization Causing RuntimeError and Race Conditions | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 465 | SEC-39 | [SEC-39] Windows Backslash & Drive-Letter Path Traversal in Prepared Ingest Unpacking Zero-Day | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 472 | CONC-16 | [CONC-16] Concurrency Race Condition on Study Readiness and AI Event Reporting Unique Constraint | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 479 | DATA-11 | [DATA-11] Published Slide Trashing & Restoring Leaves State Desynchronized and Causes Public Route 404 | false positive |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 486 | SEC-44 | [SEC-44] CLI Admin Creation and Password Reset Uncaught ValueError Traceback and Unvalidated Username | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 493 | SEC-45 | [SEC-45] Annotation Endpoints Omit Trashed Slide Check Permitting Mutation and Data Leakage on Trashed Clinical Slides | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 500 | FE-40 | [FE-40] IndexedDB Connection Leak on Transaction Error and Unhandled Storage Rejection in Study Pack Authoring | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 507 | TIME-04 | [TIME-04] Offset-Naive Datetime Comparison in Desktop Sync Pagination Triggers TypeError / Database 500 Crash | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 514 | DATA-15 | [DATA-15] Trashed Slides Retained in Public Share Manifests Leaks Clinical Diagnoses and Breaks Shared Slides with HTTP 404 | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 521 | CONC-17 | [CONC-17] Missing Hub, Cooldown, and Presenter Cleanup on Natural Classroom Expiration and Synthetic Reset Causes SSE Connection Leaks and Sequence Desynchronization | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 528 | TIME-05 | [TIME-05] Unhandled Offset-Naive Datetime Comparison in Share Delivery Manifest Route Causes TypeError Crash Resulting in 404 for All Expiring Shared Slides | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 535 | DATA-16 | [DATA-16] Expired Shares Remain Marked is_active=True Deadlocking Target Folder and Collection Re-Sharing with HTTP 409 SHARE_ALREADY_ACTIVE | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 542 | DATA-17 | [DATA-17] Deleted Collections and Trashed Folders Fail to Cascade Revoke Shares and Delivery Manifests Leaking Proprietary Slides | false positive |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 549 | FE-43 | [FE-43] Unhandled Promise Rejection and Lost Version on Roster Reconciliation Failure Freezes Teacher Roster Synchronization | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 556 | PERF-09 | [PERF-09] Unbounded Recursive Directory Walk in storage.usage() Blocks ASGI Worker and Crashes with FileNotFoundError on Concurrent Ingest/Eviction | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 563 | BUG-22 | [BUG-22] Missing Thumbnail Requirement in Prepared Ingest Results in Orphaned Thumbnail References and Broken Gallery Images | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 570 | FE-44 | [FE-44] Classroom Event Stream Cursor Prematurely Updates Sequence on Event Gaps Permitting Out-of-Order Execution During Recovery | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 577 | DATA-19 | [DATA-19] Permanent Folder Deletion Omits Desktop Sync Delete Event Emitting Zombie Folders on Paired Clients | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 584 | CONC-21 | [CONC-21] Unsynchronized Iteration Over _subscribers in _publish() and reset_session() Triggers RuntimeError: Set changed size during iteration | false positive |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 591 | SEC-50 | [SEC-50] offline_slide Omits Checking slide.trashed_at is None Permitting Paired Desktop Clients to Exfiltrate/Download Trashed Clinical Slides | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 598 | DATA-23 | [DATA-23] Desktop Library Items Query Hardcodes 100-Folder Limit Without Pagination Silently Truncating Folder Trees for Paired Clients | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 605 | BUG-34 | [BUG-34] PreparedIngest Modulo Sampling Uses Constant expected_count Instead of Loop Counter file_count Skipping Verification or Freezing Unpack | false positive |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 612 | BUG-37 | [BUG-37] upload_prepared_ingest() Exception Handler Only Catches HTTPException Leaking Partial Stream Bytes on Client Disconnect | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 619 | CONC-24 | [CONC-24] ClassroomHub._retire_subscriber() Mutates _subscribers and current_connections Outside _presence_lock Causing Lost Updates and Connection Count Drift | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 631 | SEC-04 | [SEC-04] Caddy Directive Ordering Bypassing Internal Route Denials | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 637 | AUTH-01 | [AUTH-01] Missing Teacher Ownership on Classroom Sessions | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 643 | FE-06 | [FE-06] Unhandled localStorage & sessionStorage Exceptions in Private Browsing | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 649 | DEV-01 | [DEV-01] dev.ps1 Root-Relative Path Resolution Bug | false positive |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 655 | OPS-03 | [OPS-03] Alembic Path Separator Deprecation in alembic.ini | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 661 | DATA-01 | [DATA-01] PostgreSQL Signed 32-bit Integer Overflow on Whole Slide Image and Ingest Byte Columns | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 667 | FE-09 | [FE-09] Classroom Teacher Page Unwrapped sessionStorage Failures in Safari Private Browsing | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 673 | FE-11 | [FE-11] Boolean Polygon Clipping Crash on Degenerate Holes | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 679 | SEC-09 | [SEC-09] CSV Formula Injection in Annotation Measurement Exports | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 685 | SEC-12 | [SEC-12] Unmetered Request Body Size on Public & Student Endpoints Permitting Memory Exhaustion DoS | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 691 | FE-14 | [FE-14] Unwrapped localStorage and sessionStorage in Theme, Shell Preferences, and API Client Crashes Web App in Private Browsing | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 697 | SEC-17 | [SEC-17] Unauthenticated & Unthrottled Global Classroom Join Queue Lock Starvation Denial-of-Service | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 703 | DATA-03 | [DATA-03] PostgreSQL Migration Leaves Autoincrement Sequence Unsynced (duplicate key value violates unique constraint "desktop_sync_events_pkey") | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 709 | FE-17 | [FE-17] Unwrapped sessionStorage in SharedViewerPage.tsx and study/api.ts Falsely Reports Valid Public Shares as Revoked / Missing in Safari Private Browsing | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 715 | FE-31 | [FE-31] Unwrapped sessionStorage.setItem in ClassroomTeacherPage Locks Out Teacher with CLASSROOM_ALREADY_ACTIVE | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 721 | SEC-40 | [SEC-40] CSV Formula Injection (CWE-1236) in Annotation Measurements Export API | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 727 | FE-34 | [FE-34] Uncaught DOMException in SharedViewerPage.select Crashes Shared Viewer on Safari Private Browsing | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 733 | FE-36 | [FE-36] Uncaught DOMException in OpenSeadragonViewer Crashes WSI Viewer in Safari Private Browsing | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 739 | FE-37 | [FE-37] Unwrapped sessionStorage.setItem in Study API Burns Single-Use Invitation Codes and Permanently Locks Out Learners | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 745 | FE-38 | [FE-38] Uncaught DOMException in StudyPage.tsx Locale Storage Crashes Study UI on Mount | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 751 | SEC-46 | [SEC-46] Missing Formula Sanitization in Annotation CSV Export Enables Client-Side CSV Injection and Remote Command Execution | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 757 | FE-53 | [FE-53] stitchHoles() in booleanCore.ts Injects undefined into Coordinate Array on Degenerate Outer Ring Crashing Canvas Renderer | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 768 | FE-06 | [FE-06] Unhandled localStorage & sessionStorage Exceptions in Private Browsing | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 774 | FE-09 | [FE-09] Classroom Teacher Page Unwrapped sessionStorage Failures in Safari Private Browsing | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 780 | SEC-12 | [SEC-12] Unmetered Request Body Size on Public & Student Endpoints Permitting Memory Exhaustion DoS | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 786 | SEC-15 | [SEC-15] Caddy Internal Reverse Proxy Global Root (/) Exposure Risk | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 792 | FE-14 | [FE-14] Unwrapped localStorage and sessionStorage in Theme, Shell Preferences, and API Client Crashes Web App in Private Browsing | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 798 | FE-17 | [FE-17] Unwrapped sessionStorage in SharedViewerPage.tsx and study/api.ts Falsely Reports Valid Public Shares as Revoked / Missing in Safari Private Browsing | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 804 | SEC-27 | [SEC-27] Internal Tile-Service /_pathlab_ome/* Zero-Auth + No Trashed Check | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 810 | SEC-29 | [SEC-29] Conversion Derivative Sanitize / Measure Symlink-Blind (Escape + TOCTOU) | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 816 | FE-31 | [FE-31] Unwrapped sessionStorage.setItem in ClassroomTeacherPage Locks Out Teacher with CLASSROOM_ALREADY_ACTIVE | fixed upstream |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 822 | FE-34 | [FE-34] Uncaught DOMException in SharedViewerPage.select Crashes Shared Viewer on Safari Private Browsing | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 828 | FE-36 | [FE-36] Uncaught DOMException in OpenSeadragonViewer Crashes WSI Viewer in Safari Private Browsing | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 834 | FE-37 | [FE-37] Unwrapped sessionStorage.setItem in Study API Burns Single-Use Invitation Codes and Permanently Locks Out Learners | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 840 | FE-38 | [FE-38] Uncaught DOMException in StudyPage.tsx Locale Storage Crashes Study UI on Mount | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 854 | SEC-05 | [SEC-05] Native Image Parser Execution Without Sandbox Isolation | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 860 | BUG-10 | [BUG-10] Dynamic Tile Fallback Renderer Crashes on 16-bit, Alpha, and Multichannel OME-TIFF Slides with Unhandled pyvips.Error | false positive |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 866 | SEC-25 | [SEC-25] TUS post-finish allow_expired=True Bypasses 1h Upload TTL | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 872 | CONC-09 | [CONC-09] Conversion Staging PID-Only + Unconditional Stale-Wipe (TOCTOU / Data Loss) | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 878 | CONC-12 | [CONC-12] TileCache.get_or_create Unbounded Event.wait() (Follower Hang) | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 884 | REL-04 | [REL-04] Worker delete Job Outside Try — Poison-Pill Hot Loop | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 890 | REL-05 | [REL-05] expire_incomplete_uploads .stat() Race Kills Worker Loop | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 896 | FE-23 | [FE-23] OpenSeadragon open-failed Infinite Reconnect Storm | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 902 | OPS-07 | [OPS-07] tusd + caddy Zero Healthcheck — Silent Upload Blackhole | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 908 | PERF-08 | [PERF-08] Unindexed sessions.user_id FK (Plus Siblings) | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 914 | DATA-10 | [DATA-10] server_default vs Python default Drift + Bare-String Quoting | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 920 | OPS-08 | [OPS-08] Migration Full-Table RAM Load + Non-Atomic Batches | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 926 | OPS-09 | [OPS-09] Mutable :live Fallback Tag (No Digest Pin) | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 932 | OPS-10 | [OPS-10] Watchdog Unbounded Diagnostics (No Retention) | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 938 | REL-08 | [REL-08] Unhandled Windows File Locking / PermissionError in remove_slide Crashes Worker Process in Infinite Loop | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 944 | FE-35 | [FE-35] Client Autosave Acknowledgement Failure Deadlocks Mutation Queue in Perpetual Conflict | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 950 | DATA-12 | [DATA-12] IndexedDB Connection Leak on Transaction Error in Study Local Store | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 956 | DATA-14 | [DATA-14] Trashing a Folder Leaves Child Slides in Invisible Orphaned State Deadlocking Permanent Deletion with HTTP 409 FOLDER_NOT_EMPTY | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 962 | DATA-21 | [DATA-21] Uncaught IntegrityError During Folder Restore Crashes with HTTP 500 on Name Collision Instead of 409 Conflict | confirmed |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 968 | PERF-11 | [PERF-11] Single Global Mutex Gate with 1.0s Timeout Serializes All Classroom Mutations Across Entire System Causing 503 Spikes | hardening |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | 974 | PERF-12 | [PERF-12] Unbuffered Row-by-Row database.flush() in apply_result_bundle() for Up to 2,000,000 Objects Freezes ASGI Event Loop and Triggers Process OOM | hardening |
