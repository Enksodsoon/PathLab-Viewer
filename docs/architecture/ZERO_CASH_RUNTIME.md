# Zero-Cash Runtime

## Authoritative pins

| Component | Production pin | Verification |
| --- | --- | --- |
| OpenTofu | 1.12.6 Linux ARM64 | SHA-256 `9bd0228a81bcd0c88f7045c74378f45a815779f19897191dff7d9efba9976b9e` plus upstream release signature/provenance |
| OCI provider | 8.29.0 Linux ARM64 | SHA-256 `9f063889b3d803ed2a2f2169f3b231aa0412603e0c6e7430a3b026fbc84dca7e`; provider 9.x requires a separate major-upgrade campaign |
| Base image | `Oracle-Linux-9.8-aarch64-2026.08.14-0` resolved to the target region's immutable image OCID | Region-specific OCID, image publication record, and clean-host inventory |
| Supervisor | Oracle Linux distribution systemd, current qualified package `252-67.0.1.el9_8.4.aarch64` | Exact RPM NEVRA and repository metadata in the Release Bill of Materials |

The OpenTofu lockfile contains both operator-platform and `linux_arm64` hashes. Production initialization uses a signed offline `filesystem_mirror` containing the pinned OpenTofu/provider archives; direct registry installation, mutable versions, and `latest` tags are prohibited.

## State custody

- OpenTofu uses an encrypted local backend under one durable single-writer operator lease; the host-local lock is never presented as multi-operator coordination.
- State and saved plans use OpenTofu's declared AES-GCM encryption with key material delivered through the PathLab credential hierarchy.
- Every successful apply increments a monotonic sequence, signs a manifest containing the release, configuration commit, prior and resulting state hashes, plan hash, operator lease, and timestamp, then writes an encrypted copy to an Approved Data Location.
- A missing off-host acknowledgement, concurrent lease, sequence gap, stale-state replay, decryption failure, or unexpected no-plan replacement is a NO-GO.
- State recovery must work from the signed offline release kit, the Root Recovery Quorum, and operator-owned backup without Terraform Cloud, OCI Resource Manager, object-storage state locking, or another hosted control plane.

## Native release layout

- systemd is the sole lifecycle, dependency, credential, cgroup, timer, socket, watchdog, mode-reservation, and restart-throttle authority.
- Signed immutable application bundles install at `/opt/pathlab/releases/<release-sha>/`; an atomic `current` link selects one release for deployment routing. It does not confer production activation.
- Every service has a dedicated Unix user, SELinux labels and enforcing policy, explicit filesystem and network grants, `LoadCredentialEncrypted=`, `MemoryHigh=`, `MemoryMax=`, `MemorySwapMax=0`, `CPUQuota=`, `TasksMax=`, and bounded `StartLimit*` behavior.
- Native ARM64 binaries and libraries are qualified on the exact image. QEMU-emulated success is non-certifying.
- Podman/Quadlet is not installed by default. A future admission must use the distribution build, offline signed OCI archives, digest pins, `Pull=never`, and systemd supervision without creating a second lifecycle authority.
- Moby, Docker Compose, Docker Hub, Terraform Cloud, OCI Resource Manager, hosted registries, and hosted CI are not production dependencies.

## Runtime qualification

The exact release must pass clean-host install, upgrade, rollback, host-loss restore, SELinux-enforcing, cgroup pressure and containment, watchdog and restart-throttle, credential unlock, mode transition, package-cache deletion, and offline reinstall campaigns. Monthly patched candidates require the same ABI and workload evidence before replacing a pin; no automatic package or provider promotion is permitted.

## Immutable release deployment switch

1. Install the signed Offline Release Kit immutably under `/opt/pathlab/releases/<release-sha>/` and verify every manifest, SBOM, notice, binary, migration, and signature.
2. Require HEALTHY Backup Freshness State plus current release-bound restore evidence.
3. Apply only expand-only, backward-compatible migrations; a destructive or contract migration belongs to a later release after every reader and rollback path has moved forward.
4. Start candidate services on isolated loopback ports under their final credentials, SELinux policy, and cgroups; run dependency checks and complete synthetic product transactions.
5. Enter a maintenance Mode Reservation, atomically switch the `current` link and Caddy upstream, and record the release transition in the Audit Integrity Chain.
6. Observe all health, error, resource, outbox, and synthetic gates for 30 minutes. A breach rolls application binaries and routing back without reversing compatible schema expansion.
7. Mark the deployment transition complete only after the observation receipt and off-host state, audit, and release acknowledgements succeed. This does not confer the Delivery State Ledger's `ACTIVATED` state; that requires the later two-person ceremony in Phase 8.
