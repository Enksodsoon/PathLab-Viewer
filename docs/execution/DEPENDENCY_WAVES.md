# Dependency Waves and Safe Parallelism

The task cards' `Depends on` fields are authoritative. These waves are a scheduling aid for separate chats. A task starts only from a current default-branch commit containing every dependency; “another chat is working on it” is not a dependency receipt.

## Critical path

```text
P0-T01 planning PR/merge
  -> P0-T01A architecture-precedence closure
  -> Phase 0 authority, rights, pins, schemas, offline inputs, zero-cash baseline
  -> P0-T12 closure
  -> Phase 1 data plane, native runtime, modes, keys, offline kit
  -> P1-T25 closure
  -> Phase 2 Trust, approvals, evidence, ledger, backup/restore
  -> P2-T27 closure
  -> Phase 3 Imaging preparation + early Phase 4 persistence/import preparation
  -> P3-T16 two identical rehearsals
  -> P3-T17 one-and-only SQLite cutover
  -> Phase 3/4 complete vertical slices
  -> Phase 5 specialist contexts and cross-context closure
  -> Phase 6 portability/recovery/cost preflight + campaign controller
  -> Phase 7 runner rehearsal, immutable candidate integration/check/merge/deploy
  -> Phase 6 90-day operation/two strict 35-day cycles
     + Phase 7 exact-candidate 14-day soak and eligible exact-release gates
  -> Phase 6 closure -> post-window backup/zero-cash gates
  -> Phase 7 no-waiver aggregation and Golden Journey
  -> Phase 8 pilot -> qualification -> separate two-person activation
```

## Suggested waves

| Wave | Tasks that may run in separate chats after prior gates merge | Required serialization/checkpoint |
| --- | --- | --- |
| W00 | `P0-T01` | Merge the ratified planning branch. Nothing else should invent a competing destination. |
| W01 | `P0-T01A`, `P0-T02A`, `P0-T03`, `P0-T05`, `P0-T11` | Precedence audit and human copyright/rights facts stay explicit; contradictory legacy plans become baseline-only or superseded before closure. |
| W02 | `P0-T02`, `P0-T03A`, `P0-T04`, `P0-T05A`, `P0-T07`, `P0-T10` | Serialize changes touching root/package licenses, `pnpm-lock.yaml`, web brand assets or the schema registry. |
| W03 | `P0-T06`, `P0-T08`, `P0-T09`, `P0-T10A` | Rebase each task after dependency/asset/schema changes; regenerate inventories on exact heads. |
| W04 | `P0-T09A`, then `P0-T12` | Phase 0 closes only after every precedence/input/right/cost/egress/schema item reconciles. |
| W10 | `P1-T01`, `P1-T02`, `P1-T03`, `P1-T08`, `P1-T10` | Merge module/contract conventions before context teams add new layouts. |
| W11 | `P1-T04`, `P1-T05`, `P1-T06`, `P1-T11` | Serialize PostgreSQL/migration changes and root-key state changes where files overlap. |
| W12 | `P1-T07`, `P1-T09`, `P1-T11A`, `P1-T12`, `P1-T13`, `P1-T14`, `P1-T15` as dependencies allow | Envelope encryption precedes protected persisted data; exact contracts/hashes must match merged inputs. |
| W13 | `P1-T16`, then `P1-T17`, then `P1-T18` | Systemd is the sole lifecycle authority; resident graph precedes mode graph/controller. |
| W14 | `P1-T19`, `P1-T20`, `P1-T21`, `P1-T22` where dependencies permit | Native SELinux/cgroup/kit work shares deploy files; use a merge train. |
| W15 | `P1-T23`, `P1-T24`, `P1-T25` | Upgrade/campaign/closure are serial exact-head evidence tasks. |
| W20 | `P2-T01`, `P2-T02`, `P2-T03`, `P2-T06`, `P2-T09`, `P2-T11`, `P2-T15`, `P2-T17`, `P2-T19` as dependencies allow | Trust schema/bootstrap must merge before dependent identity flows; target enrollment waits on residency. |
| W21 | `P2-T04`, `P2-T07`, `P2-T10`, `P2-T12`, `P2-T16`, `P2-T20`, `P2-T21` | Capability/WebAuthn/retention/protection contracts are shared foundations. |
| W22 | `P2-T05`, `P2-T08`, `P2-T13`, `P2-T14`, `P2-T16A`, `P2-T18`, `P2-T22`, `P2-T23` | Approval/deletion/evidence/backup work may split by files but must rebase against owner contracts. |
| W23 | `P2-T18A`, then `P2-T18B`, then `P2-T18C`; `P2-T24` where independent | Delivery state, drift handling and activation/suspension control must exist before candidate evidence or activation rehearsal. |
| W24 | `P2-T25`, `P2-T26`, then `P2-T27` | Evidence campaigns are read-only against an immutable phase candidate. |
| W30 | `P3-T01`–`P3-T15` by dependency; concurrently `P4-T00`, then `P4-T01 -> P4-T04 -> P4-T21 -> P4-T02 -> P4-T14` | This is the intentional migration-preparation overlap. Preserve that exact Learning scaffold order and do not cut over yet. |
| W31 | `P3-T16`, then `P3-T17`, then `P3-T18` | Two deterministic rehearsals precede one coordinated SQLite cutover. |
| W40 | Catalog `P4-T03`–`P4-T07`; Teacher implementation `P4-T08`–`P4-T12A`; TURN contract `P4-T19A` before Live/media implementation `P4-T15`–`P4-T19`; Assessment envelope/response kinds `P4-T22`–`P4-T28` | Workstreams may advance where their exact dependencies permit; shared UI/API/migration/lock files use a merge train. |
| W41 | Teacher AI `P4-T13A`, independent WebGPU `P4-T13B`–`P4-T13E` and WASM `P4-T13F`–`P4-T13I` chains, then parent `P4-T13`; Live/media `P4-T20`–`P4-T20B`; Assessment `P4-T29`–`P4-T29C`; then `P4-T06A` and `P4-T30` | Each long campaign uses separate freeze/dry-run, start, monitor and close chats with receipt-cursor handoffs; parent closure waits for every required terminal result. |
| W50 | `P5-T00`, `P5-T01`, `P5-T01A`, `P5-T02`, then corpus tasks `P5-T02A`–`P5-T02J` and independent scaffolds `P5-T10`, `P5-T16`, `P5-T21`, `P5-T27`, `P5-T31` as dependencies allow | Gateway/fixtures/routes precede protocol/UI fan-out; corpus rights are external receipts, not assumptions. |
| W51 | Standards implementation `P5-T03`–`P5-T08` including `T04A/B`, then harness `P5-T09A`, independent LTI/OneRoster/QTI/CASE/optional-Caliper chains `P5-T09B`–`P5-T09P`, cross-profile journey `P5-T09Q`–`P5-T09S`, and parent `P5-T09`; Credential implementation `P5-T11`–`P5-T14` plus `P5-T15A`, campaign `P5-T15B`–`P5-T15E`, then parent `P5-T15`; EQA `P5-T17`–`P5-T20C`; Clinical `P5-T22`–`P5-T25B`, owner lifecycle `P5-T26A`, harness/profile/journey chains `P5-T26B`–`P5-T26Q`, then parent `P5-T26`; Research `P5-T27A`–`P5-T30C`; Edge `P5-T32`–`P5-T39E` | Independent protocol and long-duration work uses separate launch/monitor/closure chats; parent gates reconcile exact current child receipts. Gateway batch/systemd/schema hot spots serialize. |
| W52 | `P5-T40` | Specialist cross-context/deletion closure is serial and exact-head. |
| W60 | `P6-T01`, then owner adapters `P6-T02`–`P6-T15` in parallel | One context per chat/PR. Do not combine owner adapters. |
| W61 | `P6-T16`, `P6-T17`, `P6-T18`, `P6-T19`, `P6-T20`, `P6-T21` | Export/import/campaign/cleanup is serial. |
| W62 | `P6-T22`–`P6-T29`, including `P6-T24A`, where dependencies permit; in parallel prepare `P7-T01`–`P7-T08` | Arrange real host/target/media/operators early. P7 tooling/rehearsal is non-qualifying and cannot emit exact-release success. |
| W63 | After `P6-T24A` is `MERGED`, coordinated stack `P7-T09 -> P7-T10 -> P7-T11`, then `P7-T12` | Integrate/check/protected-merge/freeze/build/deploy/select the exact candidate. It is `DEPLOYED`, never activated. |
| W64 | `P6-T30` start; active `P6-T31`; `P7-T13` soak; eligible `P7-G01`–`P7-G16` and `P7-G20` | All work binds one complete `P7-T12` fingerprint and current `DeploymentSelectionReceipt(SELECTED)` head. `P7-G02` additionally requires merged `P6-T24A` and proves lightweight home-cell/routing/extraction behavior; any funded scale topology remains a separate implementation/deployment/qualification. Any selection-head change invalidates admission and requires a new `P6-T30`; equivalence cannot retain it. Long G09/G12/G14/G15 children use separate start/monitor/close chats. |
| W65 | Sequential `P6-T32 -> P6-T33`; scheduled `P6-T34`–`P6-T34D`; `P7-T14` after 14 valid days; then `P7-G18` only after `P6-T34B=SUCCESS` | Both strict expiry cycles and every drill occur inside the >=90-day interval; the portability gate waits for the real separate 150-GB backup/restore-throughput leg; monitoring uses receipts, not a retained chat. |
| W66 | After >=90 valid days and every covering statement: `P6-T35`, then `P6-T36` | Day 90 alone is insufficient when billing coverage or any drill/receipt remains open. |
| W67 | `P7-G17`, `P7-G19`, then `P7-T15` | Backup and Zero-Cash gates wait for current `P6-T36=SUCCESS`; no-waiver aggregation waits for all `P7-G01`–`P7-G20` parent results. |
| W68 | `P7-T16`, `P7-T17`, then logical run `P7-T18 -> P7-T19 -> P7-T20` | Golden G00–G38 uses one immutable manifest/admission and receipt cursor; a changed/reverted deployment selection invalidates it. |
| W80 | `P8-T01`–`P8-T12`, then `P8-T12A` only after a complete eligible rolling 12-month window exists | Pilot, pilot receipt, review, qualification, rehearsal, human activation and suspension checks are strictly ordered. `P8-T12` only schedules recurring governance; it cannot emit the separately evidenced mature Zero-Cash result. The mature window starts only when one exact selection head, `ActivationReceipt(ACTIVATED)` head, active ledger projection and complete subject/account/tariff/workload tuple are current; any head/tuple change or inactive instant resets the 12-month eligibility clock. |

## Shared-file merge trains

Never let parallel chats overwrite each other in these hot areas:

| Hot area | Rule |
| --- | --- |
| `server/wsi_viewer/main.py`, `models.py`, `database.py`, auth/security entry points | Establish module seams first; rebase and rerun architecture/database tests after every merge. |
| `migrations/` and future per-context migration roots | One reviewed migration head per context; never reuse revisions or create cross-context foreign keys. |
| `apps/web/src/App.tsx`, navigation, `api.ts`, global CSS/theme | Merge the IA/route task first; use context-owned route modules and rerun full build/e2e after integration. |
| `package.json`, `pnpm-lock.yaml`, `pyproject.toml`, offline mirror/SBOM inputs | Serialize dependency changes and regenerate provenance/SBOM/offline evidence on the exact lock head. |
| `schemas/evidence/`, contract registries and compatibility tooling | Registry/types first; one schema owner/review; no task-local aliases. |
| `deploy/systemd/`, Caddy, OpenTofu, SELinux, cgroups and Offline Release Kit | Systemd topology and resource boundaries merge before feature units; native checks rerun after any relevant change. |
| Qualification/campaign manifests | Immutable once signed. A fix creates a new manifest/candidate rather than editing evidence in place. |

## External-resource reservation lane

These are dependencies, not software tasks. Arrange them while earlier implementation proceeds:

- accountable copyright/relicensing and independent brand/rights reviewers;
- eligible owned/donated Oracle Linux ARM64 production and build/restore capacity;
- physically independent capacity-qualified Backup Target and disconnected recovery media/custodians;
- Institution network identity and certificate recovery path;
- primary/alternate operators, three key custodians and all separation-of-duty actors;
- two independent qualified Teacher AI reviewers and supported physical devices;
- lawful standards/terminology/tool fixtures and two independent appropriate implementations per claim;
- at least 100 lawful synthetic or attested already-deidentified clinical cases;
- 100 admitted owned/donated physical Edge nodes and required network/recovery media; and
- supervised pilot Institution, bounded participants/data and incident team.

If an item is unavailable when its task is reached, report `NOT_EVALUABLE`; do not substitute simulation or hidden spend.
