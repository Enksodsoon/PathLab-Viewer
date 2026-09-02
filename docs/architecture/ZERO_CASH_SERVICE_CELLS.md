# Zero-Cash Service Cells

Logical bounded contexts keep independent databases, roles, migrations, APIs, and events. The Zero-Cash profile groups only contexts with compatible runtime lifecycles; a funded profile may split any cell without changing domain contracts.

| Service cell | Lifecycle | Logical ownership hosted | Process boundary |
| --- | --- | --- | --- |
| Resident dependencies | Continuous | Durable delivery, persistence, pooling, and event transport | Caddy, PostgreSQL, PgBouncer, and single-node JetStream remain separate upstream executables. |
| `pathlab-control` | Continuous | Platform Governance, Trust and Governance, Learning Catalog, Credential Ledger, Audit intake and projection, mode control, Imaging metadata, delivery authorization, durable notices, and minimal LTI or credential-verification ingress | One compact PathLab process; modules cannot access another context database. Protocol-heavy synchronization, import, export, and conformance work is handed to a named batch reservation. |
| `pathlab-live` | Live Learning reservation | Live Learning session ownership, durable interaction, attendance, and media authorization | One PathLab process; Galene is a separately supervised executable started only when Teacher Broadcast is reserved. |
| `pathlab-assessment` | Assessment reservation | Assessment authoring delivery, attempts, provisional reconciliation, grading, and reports | One PathLab process with its own database role and connection allotment. |
| `pathlab-batch` | One named batch reservation | Exactly one of Imaging conversion, EQA, Clinical and external integration, bulk Credential Ledger work, bulk Edge synchronization, or portability import/export | One multi-call PathLab binary launched with a single fail-closed mode; mode modules cannot run concurrently. tusd and approved format tools remain separate supervised executables when required. |
| `pathlab-research-runner` | Research reservation | One quota-bound Research Job | One sandboxed process without production database credentials; inputs and outputs cross through signed manifests. |

Inactive service cells have no running process. Every launch declares its mode, cgroup, database role, event subjects, filesystem grants, network policy, and shutdown/checkpoint contract; a missing declaration is a NO-GO.
