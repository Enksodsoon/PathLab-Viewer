# P0-T03 dependency license and provenance inventory

## Result

`P0-T03` completed its inventory audit against commit
`79800a5d7f6ffaf0ef1280d4ef8a599a65fcbe1f` and tree
`4a8610edf7c05e064e2eb0b02671b4fc27c1e00f`. The gate result is `NEGATIVE`:
the audit ran to completion and found unresolved mandatory inputs. This result blocks Phase 0
admission for those inputs; it does not change any ratified architecture or authorize product,
deployment, qualification, or activation work.

The authoritative machine-readable record is
[`dependency-inventory.json`](dependency-inventory.json). It contains 507 unique records:

- 375 exact npm resolutions from `pnpm-lock.yaml`, including transitive and platform-optional
  packages;
- 74 unique exact PyPI resolutions from the two hash-locked deployment requirement files;
- 58 explicit non-lockfile records for GitHub Actions, pinned container images, native and hosted
  tools, planned production inputs, models and model runtimes, and standards artifacts. The exact
  bundled font, icon, and WASM runtime packages are among the npm records and are required by the
  offline validator.

Every record states its role, optionality, source, artifact, checksum status, license, archived
notice hashes, purpose, distribution status, manifest references, admission state, and blockers.
The generator retrieved exact registry artifacts, verified npm integrity and selected PyPI
artifacts against checked-in hashes, and hashed license/notice files contained in those archives.
The checked-in inventory does not treat registry metadata alone as final legal approval:
`RECORDED_UNREVIEWED` means mechanically captured and still subject to P0-T05A/P0-T06 review.

## Fail-closed findings

124 records are `BLOCKED`. The material blockers are:

- `combine-errors@3.0.3` is a mandatory bundled npm dependency with no declared license or
  archived notice text. P0-T04 owns removal of that dependency path; it is not admitted here.
- `pyproject.toml` supplies ranged, unhashed Python build/test inputs. P0-T03A must establish the
  exact offline build and verification toolchain rather than treating a developer environment as
  authoritative.
- the current Terraform lock selects OCI provider 7.32.0, while the ratified production input is
  8.29.0 Linux ARM64. Neither the current lock nor the canonical OpenTofu/provider pair has the
  required signed offline mirror and notice set yet.
- current development containers are digest-pinned, but their complete image SBOM/license/notice
  sets have not been captured. Debian packages installed inside the backend image are mutable and
  unpinned. Docker/Compose remain development-only under ADR 0059.
- the canonical native production OS, service, durability, and key-management inputs lack one or
  more exact artifact, checksum, signature, SBOM, license, or notice receipts. Exact known pins are
  preserved; missing values remain explicit rather than inferred.
- the two Teacher AI model conversions and browser runtimes are planned but not mirrored with
  signed shard, rights, license, and notice receipts. TRACE-SIM remains explicitly excluded and
  blocked from production; this audit neither activates nor removes it.
- standards, schemas, contexts, fonts, and icons require dedicated offline artifact and rights
  reconciliation. An online document or hosted service is not classified as free software or as a
  zero-cash production dependency.

These findings are handoffs, not permission to weaken the frozen authority, privacy, clinical,
capacity, recovery, rights, or zero-cash decisions.

## Reconciliation and reproduction

`scripts/validate_dependency_inventory.py` fails closed unless the inventory contains exactly all
pnpm lock resolutions, both Python hash-lock closures, every immutable external GitHub Action,
every digest-pinned external container, and the required native/model/standard records. It also
requires unresolved license, checksum, or notice evidence to be blocked; freezes the
`combine-errors` and TRACE-SIM dispositions; rejects mutable hosted CI as production authority;
and verifies source-manifest SHA-256 and Git-blob receipts.

Regenerate only when network retrieval is intentionally allowed:

```text
python scripts/generate_dependency_inventory.py --subject 79800a5d7f6ffaf0ef1280d4ef8a599a65fcbe1f
```

Validate offline on every candidate head:

```text
python scripts/validate_dependency_inventory.py --subject 79800a5d7f6ffaf0ef1280d4ef8a599a65fcbe1f
python -m pytest -q tests/backend/test_dependency_inventory.py
```

The inventory subject intentionally remains the pre-change repository tree audited by P0-T03.
Later tasks must create new evidence rather than silently rebinding this receipt.
