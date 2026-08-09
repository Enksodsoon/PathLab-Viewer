# PathLab Eraser Diagram-as-Code Architecture

## Purpose

This file is the plain-text Diagram-as-Code source for the lecture-aligned PathLab architecture. Paste the block below into **Eraser.io → Diagram as Code → Flow Chart**.

The diagram distinguishes:

- current production/repository components;
- the local PathLab Forge boundary;
- privacy and data boundaries;
- lecture architecture services already implemented functionally;
- scale-out services that are intentionally deferred until evidence and state architecture justify them.

```text
direction right
colorMode pastel
styleMode plain
typeface clean

// ============================================================
// PATHLAB HYBRID CLOUD / NETWORK ARCHITECTURE
// ============================================================

USERS [label: "Users", color: gray] {
  Admin [label: "Administrator / Instructor", color: gray]
  Learner [label: "Anonymous Learner / Viewer", color: gray]
}

LOCAL [label: "ON-PREMISE / UNIVERSITY ZONE", color: orange] {
  SourceWSI [label: "Original Vendor WSI\nVSI / SVS / NDPI / MRXS / TIFF", shape: document, color: orange]
  LocalArchive [label: "University Source Archive / NAS", shape: cylinder, color: orange]

  Forge [label: "PathLab Forge", color: orange] {
    Inspect [label: "Inspect + Series Selection", color: orange]
    QC [label: "Local Viewer + QC", color: orange]
    Prepare [label: "Crop / Downsample / RGB Standardize", color: orange]
    Package [label: "prepared-v2 Package", shape: document, color: orange]
    DirectOME [label: "ome-dynamic-v1 OME-TIFF", shape: document, color: orange]
    ResumeUpload [label: "Resumable Authenticated Upload", color: orange]
  }
}

CLOUD [label: "CLOUD / HOSTED PATHLAB VIEWER", color: blue] {

  NETWORK [label: "Network + Security Boundary", color: blue] {
    OCIFirewall [label: "Firewall\nOCI Security List", color: blue]
    InternetGateway [label: "Network Gateway\nOCI Internet Gateway", color: blue]
    Caddy [label: "API Gateway / Edge\nCaddy HTTPS Reverse Proxy", color: blue]
    Auth [label: "Authentication + Authorization\nSessions / CSRF / Forge Credential", color: blue]
  }

  APP [label: "Application / Compute", color: blue] {
    React [label: "React + TypeScript SPA", color: blue]
    API [label: "FastAPI Control Plane", color: blue]
    Tusd [label: "tusd Resumable Upload", color: blue]
    Worker [label: "Serial WSI Worker", color: blue]
    TileService [label: "Dynamic OME Tile Service", color: blue]
    OpenSeadragon [label: "OpenSeadragon Viewer", color: blue]
  }

  DATA [label: "Data Services", color: green] {
    SQLite [label: "Database\nSQLite WAL", shape: cylinder, color: green]
    PrivateFiles [label: "File/Object Storage Function\nPrivate Originals + Derivatives", shape: cylinder, color: green]
    PublicFiles [label: "Authorized Static DZI Aliases", shape: cylinder, color: green]
    TileCache [label: "Cache\nBrowser + Dynamic Tile Cache", shape: cylinder, color: green]
    Backup [label: "Backup / Restore", shape: cylinder, color: green]
  }

  LIBRARY [label: "Library + Publication", color: blue] {
    LibraryAPI [label: "Folders / Collections / Search / Trash", color: blue]
    PrivacyReview [label: "De-identification Review", shape: diamond, color: blue]
    Grant [label: "Publication / Share Grant", color: blue]
    TileAuth [label: "Per-request Tile Authorization", color: blue]
  }
}

DEFERRED [label: "EVIDENCE-GATED SCALE-OUT - NOT CURRENT RUNTIME", color: purple] {
  PrivateGateway [label: "Private University ↔ Cloud Gateway / VPN", color: purple]
  CDN [label: "CDN for Safe Static Content", color: purple]
  CloudLB [label: "Load Balancer", color: purple]
  AutoScale [label: "Auto Scaling", color: purple]
  ExternalDB [label: "External Multi-node Database\nPostgreSQL or Equivalent", shape: cylinder, color: purple]
  SharedStorage [label: "Shared / Object Storage Contract", shape: cylinder, color: purple]
  DistributedQueue [label: "Distributed Job / Lock Semantics", color: purple]
}

// ============================================================
// LOCAL PREPARATION
// ============================================================

SourceWSI > LocalArchive
SourceWSI > Inspect
Inspect > QC
QC > Prepare
Prepare > Package
Prepare > DirectOME
Package > ResumeUpload
DirectOME > ResumeUpload

// ============================================================
// ADMIN REQUEST PATH
// Firewall != authentication; API gateway != network gateway
// ============================================================

Admin > OCIFirewall: HTTPS
OCIFirewall > InternetGateway
InternetGateway > Caddy
Caddy > React
React > API
API > Auth
Auth <> SQLite

// ============================================================
// FORGE INGEST PATH
// ============================================================

ResumeUpload > OCIFirewall: HTTPS
OCIFirewall > Caddy
Caddy > API: pairing / capability negotiation
Caddy > Tusd: resumable ingest
Tusd > PrivateFiles
Tusd > Worker: finalize
Worker > PrivateFiles: validate / install / convert
Worker > SQLite: lifecycle + job state

// ============================================================
// LIBRARY AND PUBLICATION
// ============================================================

API > LibraryAPI
LibraryAPI <> SQLite
LibraryAPI > PrivacyReview
PrivacyReview > Grant: explicit approval
Grant <> SQLite
Grant > PublicFiles: static_dzi
Grant > TileAuth: ome_dynamic

// ============================================================
// PUBLIC VIEWER PATH
// ============================================================

Learner > OCIFirewall: HTTPS
OCIFirewall > Caddy
Caddy > React
React > OpenSeadragon
OpenSeadragon > API: safe metadata / authorization
API > Grant
Grant > TileAuth

TileAuth > PublicFiles: static DZI
PublicFiles > Caddy
Caddy > OpenSeadragon: JPEG tile

TileAuth > TileService: dynamic OME
TileService > PrivateFiles: canonical OME + immutable index
TileService <> TileCache
TileService > Caddy: generated JPEG tile
Caddy > OpenSeadragon

// ============================================================
// DATA / BACKUP
// ============================================================

SQLite > Backup
PrivateFiles > Backup
PublicFiles > Backup

// ============================================================
// SCALE-OUT PREREQUISITES
// Dotted links mean future/evidence-gated, not current production.
// ============================================================

LocalArchive --> PrivateGateway: only if private institutional integration needed
PrivateGateway --> CLOUD

React --> CDN: only safe/versioned assets
PublicFiles --> CDN: only after revocation/privacy design

SQLite --> ExternalDB: prerequisite for multi-node writes
PrivateFiles --> SharedStorage: prerequisite for multi-node canonical storage
Worker --> DistributedQueue: prerequisite for multiple workers

ExternalDB --> CloudLB
SharedStorage --> CloudLB
DistributedQueue --> CloudLB
CloudLB --> API: multiple stateless API nodes
CloudLB --> TileService: multiple render nodes
CloudLB --> AutoScale

// ============================================================
// CORE ARCHITECTURE RULE
// ============================================================

Rule [label: "Add cloud services only when a measured bottleneck, privacy need,\nreliability requirement, or institutional integration justifies them", shape: hexagon, color: purple]

Rule --> PrivateGateway
Rule --> CDN
Rule --> CloudLB
Rule --> AutoScale
```

## Lecture service coverage

The diagram deliberately makes the lecture's terms explicit:

- **Firewall:** OCI security-list boundary.
- **Authentication:** PathLab identity/session/capability layer.
- **API Gateway:** Caddy is the current public API routing edge.
- **Network Gateway:** OCI Internet Gateway exists; private institutional gateway remains optional.
- **Database:** SQLite WAL.
- **Object Storage:** represented functionally by persistent file storage; a managed object-store migration is not required today.
- **Cache:** browser tile cache and dynamic OME tile cache.
- **Load Balancer:** deferred until there is more than one safe backend node.
- **Auto Scaling:** deferred until the state architecture supports horizontal scaling.
- **CDN:** deferred to safe static/de-identified content only if latency/bandwidth evidence requires it.

## Maintenance rule

When runtime architecture changes, update this text diagram in the same change. The rendered diagram is a view of this source; this file is the maintainable architecture definition.