# Zero-cost Teaching Studio staging plan

Prepared 2026-09-07. **Plan only; no staging services or database cutover have
been started. Full Assessment remains NOT_EVALUABLE and disabled.**

## Recommended layout

Use an isolated staging Compose project on the existing OCI host and existing
data volume. Run the full capacity campaign during a reserved maintenance
window, with production writers and background work stopped. This preserves
the candidate's access to the same two CPUs it will have after cutover.
Concurrent production traffic would confound this qualification.

This is process, credential, network and data isolation on one trusted host,
not an independent VM or disaster-recovery site. A host failure affects both.

## Verified inventory and cost boundary

| Resource | Current observation | Staging decision |
| --- | --- | --- |
| Compute | One running A1 instance, 2 OCPUs, 12 GB RAM | Reuse; no resize or additional VM |
| Boot volume | 50 GB allocated; about 11 GB free in its filesystem | Keep staging data and backups off boot |
| Data volume | 150 GB allocated, attached and mounted at `/srv/pathlab/data`; about 125 GB free | Reuse existing free space |
| Total allocated volumes | 200 GB in inspected production compartment | No new boot/block volume or cloud snapshot |
| Production services | Six services, SQLite, no Assessment | Preserve until qualified cutover |
| Qualification environment | Reviewer protected, protected branches only, no secrets yet | Configure target and six scoped secrets |

Oracle's current [Always Free documentation](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
lists 1,500 A1 OCPU-hours and 9,000 GB-hours monthly, 200 GB combined boot/block
storage, and 10 TB outbound transfer. Use these conservative limits; do not
assume the older 4-OCPU/24-GB allowance. Account-specific billing eligibility,
home region, other compartments and month-to-date usage must be checked before
execution. The inspected inventory alone is not a tenancy-wide billing audit.

The proposed incremental infrastructure allocation is zero. A second VM needs
another boot volume and cannot be justified as zero-cost from this inventory.
No paid runner, managed database, load balancer, storage allocation or account
upgrade is part of this plan.

## Storage and isolation

Reserve a root-owned `0700` staging parent on the existing data filesystem,
outside its `originals`, `private`, `public`, `delivery`, and `database` trees.
Bind only its dedicated child directories into staging containers. Production
backend/worker UID 10001 must be unable to traverse the parent. Verify that
upload, static serving, storage accounting and backup discovery cannot include
this parent; current production file backups enumerate specific content trees.
Staging must never bind the live database, writable live assets, production
session secret or production upload directory.

Use separate Compose project/service names, PostgreSQL database and role,
network, cookies, session secret, admin identity, host observer token, and
HTTPS origin. PostgreSQL and observer internals stay off public host ports.
The staging origin must not inherit production admin cookies.

| Working storage budget | Maximum planned use |
| --- | ---: |
| Immutable source snapshot and required files | 15 GiB |
| Independent staging files and migration working set | 15 GiB |
| Backup and disposable restore files | 15 GiB |
| PostgreSQL/WAL and database restore | 8 GiB |
| Logs and evidence | 3 GiB |
| Margin | 4 GiB |
| Total | 60 GiB |

These are admission budgets, not measured future sizes. Measure source bytes
before starting; stop if they exceed the budget. Require at least 40 GiB free
on the data filesystem throughout. Copy enumerated source trees only, never
recursively copy the filesystem root into its own staging child. Never use
writable hardlinks to production assets. Keep one prior release and verified
rollback images; do not blindly prune Docker images or backups to make room.

## Execution sequence

1. Confirm zero-cost eligibility and current usage; reserve the maintenance
   window. Verify idle Classroom, no learner administration, drained jobs,
   fresh backups and the existing runtime restoration procedure.
2. Prepare the isolated target using the reviewed release, PostgreSQL and
   identity governance. Reconcile the current 20-connection Compose limit with
   the campaign's 32-connection prerequisite and bounded application pools.
   Implement host monitoring from actual process/database counters, including
   exact release SHA; missing telemetry must fail the run.
3. Rehearse migration twice from one immutable snapshot and compare manifests.
   Restore a signed PostgreSQL backup into a disposable target and validate
   object references, permissions, sessions, Classroom, annotations and
   Teaching Studio. Follow the current [cutover contract](../architecture/SQLITE_TO_POSTGRESQL.md);
   the older migration command alone is not complete cutover evidence.
4. Configure the six secrets in `assessment-capacity`. Run authenticated
   authoring, publication, learner access, save/resume, submit, grading and
   export checks with privacy-passed static-DZI material and synthetic users.
5. Reserve the full host for the 500-seat, 60-minute campaign plus recovery,
   cleanup and verification. Allow a planning window of at least two hours;
   this is an estimate, not a completion promise. Load generators run outside
   OCI on eligible standard public-repository CI runners; verify billing and
   concurrency before dispatch. Do not run a load generator on the target.
6. Complete separate 30/100/300-user pilots, recording usability and recovery
   findings. Synthetic identities do not substitute for these user pilots.
7. Add Assessment-aware guarded deployment, health, inventory, backup and
   recovery support. Activate only on passing evidence, then perform the
   authenticated OCI Studio and learner journey checks. A code change that
   affects the candidate invalidates earlier exact-release conclusions.

Restore normal production after each staging window. After PostgreSQL accepts
its first production write, recovery must follow PostgreSQL backup/forward
repair rules; reverting to the old SQLite database would lose new work.

## Traffic budget and stop conditions

The current harness requests 500 × 20 = 10,000 tiles per campaign. At an
assumed 100 KiB average tile this is about 0.95 GiB of tile traffic; at 512 KiB
it is about 4.9 GiB, before API traffic and browser canaries. Measure the actual
asset bytes, request count and response overhead. Admit at most 20 GiB for
one complete campaign and keep the repository's projected monthly egress
below 9 TB. Abort or rescope before exceeding either budget. Do not export
private source files into CI artifacts.

Stop on nonzero projected incremental charges, insufficient disk reserve,
unexpected production activity, missing host samples, resource thresholds,
failed recovery, lost confirmed responses or duplicate submissions. Retain a
NEGATIVE or NOT_EVALUABLE result; do not lower qualification gates to finish.

This route can avoid additional infrastructure charges, but requires planned
service downtime and successful measurements. It does not establish that
500 learners will fit the existing host.
