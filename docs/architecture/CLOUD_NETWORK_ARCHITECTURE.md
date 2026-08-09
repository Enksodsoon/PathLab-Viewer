# PathLab Cloud and Network Architecture

## Purpose

This document applies the cloud/network architecture vocabulary used in the Architecture of Cloud / Network for AI Computing lecture to the actual PathLab Viewer and PathLab Forge system. It is an architecture decision record, not a requirement to add every named cloud service.

The governing rule is:

> Choose services from workload, data sensitivity, latency, scale, failure modes, cost, and evidence. Do not add infrastructure only to make a diagram look more sophisticated.

## Architecture classification

PathLab is a **hybrid architecture**.

### Local / institution-controlled side

- Original proprietary WSI datasets remain local by default.
- PathLab Forge performs source discovery, series selection, viewing, crop/downsample, standardization, QC, packaging, and resumable upload.
- Institutional source archives and optional backup copies remain under university control.

### Cloud / hosted Viewer side

- Caddy HTTPS edge and SPA delivery.
- FastAPI control plane.
- `tusd` resumable upload transport.
- Background validation/conversion worker.
- Dynamic OME tile service.
- SQLite WAL metadata database.
- Private originals/prepared artifacts, private derivatives, authorized public derivatives, and bounded tile cache.

### Hybrid boundary

Only an explicitly prepared or accepted ingest crosses from Forge/institutional storage into Viewer. Publication is a second, independent boundary: anonymous viewers receive only safe metadata and authorized image delivery. No endpoint exposes arbitrary raw-file ranges.

This separation gives PathLab the main benefit of hybrid architecture: sensitive source handling stays local while browser delivery and centrally managed teaching access can use hosted infrastructure.

## Lecture service mapping

| Lecture service | PathLab implementation | Status | Decision |
|---|---|---|---|
| Firewall | OCI security list + Caddy route restrictions + internal Docker network | Implemented | Keep and harden |
| Authentication | Argon2id administrator auth, signed sessions, CSRF, Forge pairing credentials | Implemented | Keep |
| API Gateway | Caddy is the external API edge/reverse proxy; FastAPI routes the application API | Implemented functionally | Do not add a separate managed gateway yet |
| Network Gateway | OCI Internet Gateway exists; no private institution-to-cloud gateway | Partial | Add private gateway/VPN only if institutional network integration requires it |
| Load Balancer | Caddy proxies to one API/tile service instance; no horizontal backend pool | Not horizontally implemented | Defer until state is externalized and multi-node load is justified |
| Auto Scaling | Single-node Docker Compose with explicit resource limits | Not implemented | Do not add yet |
| CDN | Browser/static caching only; no geographic CDN | Not implemented | Defer; use only for explicitly safe content if evidence justifies it |
| Object Storage | Persistent filesystem/block storage provides the file-storage function | Implemented as local filesystem, not managed object store | Preserve for core path; object storage is optional for backups/static public derivatives later |
| Database | SQLite WAL + SQLAlchemy/Alembic | Implemented | Keep while single-node workload is proven adequate |
| Cache | Browser immutable tile cache + bounded dynamic OME tile cache + libvips cache | Implemented | Keep; Redis is not required for the current topology |

## Why PathLab should not blindly implement every lecture component

The lecture teaches architecture reasoning, not service-count maximization. PathLab's present constraints matter:

- low-cost deployment;
- current single Linux host;
- SQLite WAL as the authoritative database;
- filesystem-backed slide lifecycle and atomic publication;
- one serial conversion worker by design;
- bounded dynamic rendering;
- de-identification/privacy boundaries;
- a target of up to 300 active viewers that must be demonstrated by measured evidence.

Adding horizontal auto scaling before shared state is redesigned would create a more complicated but less reliable system.

## Trust and network zones

### Zone A — Local source zone

Contains:

- university WSI source;
- proprietary vendor files and companions;
- PathLab Forge;
- optional local archive/NAS.

Rules:

1. Proprietary source WSI remains local by default.
2. Forge prepares or negotiates an accepted Viewer ingest format.
3. Upload credentials are revocable and scoped.
4. No public Viewer capability reaches back into local source storage.

### Zone B — Public edge

Contains Caddy and the public host interface.

Externally reachable traffic should be limited to:

- HTTPS (`443`);
- HTTP (`80`) only for redirect/ACME requirements;
- restricted administrative SSH from an approved CIDR at the infrastructure layer.

Caddy must continue to block internal hook and direct dynamic-render paths from external clients.

### Zone C — Application/control plane

Contains:

- FastAPI;
- `tusd`;
- worker;
- internal tile service.

Only Caddy should expose the ordinary browser-facing application. Internal services should communicate on private container networking wherever possible.

### Zone D — State/data plane

Contains:

- SQLite WAL database;
- private temporary uploads;
- private canonical originals/OME;
- private sanitized derivatives;
- authorized public aliases;
- dynamic OME tile index;
- bounded tile cache.

These paths are not equivalent. Publication must never turn the private storage root into a general static web root.

### Zone E — Anonymous viewer

The anonymous browser may receive only:

- unlisted/share identifiers;
- explicitly safe display/teaching metadata;
- DZI descriptors;
- authorized JPEG tiles/thumbnails;
- education capabilities when the education extension is integrated and published.

It must not receive administrator annotations, original filenames, private notes, raw OME files, database access, or arbitrary byte-range access to canonical originals.

## Request flow aligned with the lecture

The lecture's conceptual path is:

`User -> Firewall -> API Gateway -> Authentication -> Load/Compute -> Cache/Database/Object Storage -> Result`

PathLab's current concrete path is:

```text
Administrator / Viewer
        |
        v
OCI network rules
        |
        v
Caddy HTTPS edge
        |
        +------------------------------+
        |                              |
        v                              v
React SPA / static assets          /api/*
                                       |
                                       v
                                   FastAPI
                                       |
                    +------------------+------------------+
                    |                  |                  |
                    v                  v                  v
                 SQLite            filesystem        tile authorization
                                                           |
                                                           v
                                                    internal tile service
                                                           |
                                                           v
                                                   OME index + original
                                                           |
                                                           v
                                                     bounded tile cache
```

For static published DZI, Caddy can deliver the authorized derivative directly rather than passing the image body through the Python control plane.

## Upload and ingest flow

### Browser OME-TIFF path

```text
Admin Browser
   -> FastAPI upload admission
   -> short-lived tus token
   -> tusd resumable upload
   -> private temporary storage
   -> finalize length/signature/SHA-256
   -> serial worker
   -> OME/TIFF validation
   -> libvips conversion
   -> sanitized DZI + thumbnail
   -> ready_private
   -> explicit review
   -> publication grant
```

### Forge prepared-v2 path

```text
Local WSI
   -> Forge inspection/QC/crop/downsample
   -> prepared-v2 package
   -> authenticated resumable desktop ingest
   -> package/inventory validation
   -> atomic private install
   -> ready_private
```

### Forge ome-dynamic-v1 path

```text
Local WSI
   -> Forge standardized calibrated OME
   -> capability negotiation
   -> authenticated direct OME ingest
   -> geometry/profile/hash validation
   -> immutable OME tile index
   -> canonical private OME install
   -> render_mode=ome_dynamic
   -> ready_private
   -> authorized on-demand tiles
```

## Firewall decision

The firewall concept is already represented at several layers:

1. OCI security-list ingress limits.
2. Caddy public-route restrictions.
3. Docker internal network boundaries.
4. FastAPI authentication/authorization and CSRF at the application layer.

These layers have different purposes and should remain separate. Network filtering does not replace authentication, and authentication does not replace network filtering.

## API Gateway decision

A separate managed API Gateway is **not currently required**.

Caddy already provides the core gateway responsibilities needed by PathLab:

- one public origin;
- HTTPS termination;
- request routing;
- static SPA delivery;
- upload proxying;
- API proxying;
- blocking internal routes;
- controlled internal redirect to dynamic tile rendering.

A managed API gateway becomes worth reconsidering only if PathLab becomes a multi-service/multi-node platform with independently deployed APIs, external consumers, centralized quotas, or institutional API governance requirements.

## Load balancer decision

A load balancer answers "where should this request go?" PathLab currently has only one authoritative API instance and one tile-service instance, so a horizontal backend load balancer has no meaningful pool to distribute traffic across.

Caddy remains the single edge proxy.

### Conditions required before horizontal load balancing

Do not add multiple application nodes until all of these are addressed:

1. shared or external database suitable for multi-node writes;
2. shared/object storage or another canonical storage contract;
3. no node-local session dependency;
4. safe cross-node job claiming;
5. shared/reproducible publication state;
6. dynamic tile cache behavior defined across nodes;
7. multi-node backup/restore procedure;
8. load-test evidence showing the current single node is the actual bottleneck.

Only then should the target become:

```text
Cloud Load Balancer
      |
      +---- API node A
      +---- API node B
      +---- API node N
```

## Auto-scaling decision

Auto scaling answers "how many instances should exist?"

It is intentionally deferred. The current architecture uses bounded single-node resources and a serial conversion worker to prevent WSI processing from starving viewers. Auto scaling should not be used to hide an unresolved storage/database architecture.

If a future multi-node architecture is adopted, auto scaling should initially apply only to stateless/read-heavy services, with explicit floors and ceilings. Conversion workers should scale separately and only after storage and queue semantics are designed for it.

## Network Gateway decision

OCI currently has an Internet Gateway, which connects the cloud subnet to the internet. That is not the same architectural function as a private hospital/university-to-cloud gateway.

A private network gateway should be added only if PathLab needs continuous private access to institutional services such as:

- university identity provider;
- protected NAS/object store;
- institutional database;
- internal PACS/pathology systems;
- monitoring or backup infrastructure.

The future pattern would be conceptually:

```text
University private network
        |
   firewall/router
        |
 site-to-site VPN / private tunnel
        |
 cloud network gateway
        |
 PathLab private services
```

This must not create a route allowing anonymous Viewer traffic to browse university storage.

## CDN decision

A CDN is **not a current requirement**.

PathLab already reduces origin work by:

- serving static DZI directly through Caddy;
- using immutable browser caching for authorized static tiles;
- adapting browser tile concurrency;
- using a bounded dynamic OME tile cache.

A CDN should be considered only when measured evidence shows geographic latency or origin bandwidth is a real bottleneck.

If introduced, the safest first CDN scope is:

1. versioned application assets;
2. possibly explicitly public/de-identified static teaching derivatives with well-defined revocation/purge behavior.

Do not CDN-cache:

- raw OME/originals;
- private previews;
- administrator annotation responses;
- session-authenticated private metadata;
- recovery/authentication responses;
- dynamic capabilities whose revocation must take effect immediately.

## Object storage decision

The lecture's "object storage" concept maps to PathLab's need to store large image/file objects, but the implementation does not have to be a managed object-store service.

Current persistent filesystem/block storage is appropriate because:

- atomic publication is file-oriented;
- dynamic OME rendering needs efficient random access;
- the system is single-node;
- operational simplicity and cost are important.

Potential future object-storage uses:

- encrypted backups;
- immutable release artifacts;
- safe static public derivatives;
- disaster-recovery replicas.

Moving canonical dynamic OME to remote object storage must not occur until random-access performance, privacy, cost, and failure behavior are measured.

## Database decision

SQLite WAL remains appropriate for the present single-node architecture while measured concurrency, locking, backup, and restore gates remain healthy.

Move to PostgreSQL or another external database only when there is a concrete need such as:

- multiple API nodes;
- write concurrency beyond SQLite's demonstrated envelope;
- institutional HA requirements;
- replicas/failover;
- external analytics that should not run against the operational SQLite file.

Database migration is therefore a **scale-out prerequisite**, not a lecture-box requirement.

## Cache decision

PathLab already uses caching in the places that save the most work:

- browser cache for immutable static derivatives;
- persistent/memory cache for dynamically rendered OME tiles;
- libvips internal cache.

Do not add Redis merely because the lecture mentions cache. Redis becomes useful when PathLab has shared cross-node ephemeral state, rate-limit counters, distributed locks, or a real need for shared metadata caching.

## Serverless decision

Core PathLab WSI processing should remain container/host based for now.

Serverless is a poor fit for the core path because PathLab performs:

- multi-gigabyte resumable uploads;
- native libvips processing;
- long-running validation/conversion;
- persistent filesystem transactions;
- bounded dynamic tile rendering;
- local SQLite/file coordination.

Serverless can still be considered later for small, isolated tasks such as notifications or scheduled housekeeping, provided they do not become authoritative for the slide lifecycle.

## Scaling strategy

### Stage 0 — Current architecture

Keep the evidence-driven single-node deployment:

- Caddy edge;
- one API worker;
- one serial conversion worker;
- one dynamic tile service with bounded render concurrency;
- `tusd`;
- SQLite WAL;
- persistent filesystem;
- browser/tile caching;
- capacity certification against the real production-like host.

### Stage 1 — Optimize before distributing

Before adding nodes:

- verify 300-viewer capacity;
- measure network, CPU, memory, disk and cache-hit behavior;
- keep static image bodies out of FastAPI when possible;
- tune browser adaptive concurrency from evidence;
- identify whether the bottleneck is edge, network, disk, API, dynamic rendering, or conversion.

### Stage 2 — Add low-risk cloud services only when justified

Possible additions:

- CDN for versioned web assets;
- external encrypted backup/object storage;
- managed monitoring/alerts;
- private network gateway if institutional integration requires it.

### Stage 3 — Horizontal scale-out

Only after state is externalized:

- PostgreSQL or equivalent external database;
- shared/object storage contract;
- distributed job/lock semantics;
- multiple stateless API/web nodes;
- cloud load balancer;
- bounded auto scaling;
- shared or deterministic tile-cache strategy.

## Architecture acceptance questions

Every future architecture change must answer:

1. How many active users is this solving for?
2. Which measured bottleneck does it remove?
3. Does any sensitive data cross a new boundary?
4. Does it change the public/private storage boundary?
5. What happens when the new service is unavailable?
6. What is the cost floor and worst-case cost?
7. Can it be backed up and restored?
8. Can access be revoked immediately when required?
9. Does it preserve existing slide/version/attempt integrity?
10. What evidence demonstrates the change is better than the current architecture?

## Architecture decision summary

PathLab should **use the lecture to improve systematic architecture reasoning, not to force all ten named services into production**.

The current preferred architecture is:

```text
LOCAL / UNIVERSITY
  Source WSI
     |
  PathLab Forge
     |
     | prepared-v2 or ome-dynamic-v1 over HTTPS
     v
CLOUD / HOSTED VIEWER
  OCI firewall boundary
     |
  Caddy API edge
     |
  FastAPI + tusd + Worker + Tile Service
     |
  SQLite + Private Storage + Tile Cache
     |
  explicit privacy/publication grant
     v
ANONYMOUS LEARNER / VIEWER
  Safe metadata + authorized DZI/JPEG only
```

That is the PathLab interpretation of the lecture's final rule: choose where the system runs, protect and route requests, scale only where justified, store each data type appropriately, and keep the architecture documented as code.