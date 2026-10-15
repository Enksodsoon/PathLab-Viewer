# P0-T06 deterministic software inventories

## Result

The implementation generates deterministic SPDX 2.3 and CycloneDX 1.6 source/build inventories,
a human-readable third-party notice bundle, and a hash-bound manifest from the existing dependency,
toolchain, and asset-rights ledgers. The current reference inventory subject is commit
`41d31505bd4e471bf43248907753de99063b47ac` with tree
`097f308e805afe715ff26cf58edf22f7cf872eb8`.

This is an inventory result, not release admission. The current reference manifest reports
`BLOCKED`: all 177 current shipped inputs are `RECORDED_UNREVIEWED`. The authoritative dependency
and rights ledgers retain their own admission states; this generator never promotes them.

The generated Offline Release Kit entry is deliberately
`CONTRACT_ONLY_NOT_ASSEMBLED`. P1-T22A owns the assembler and must consume a current, admitted
manifest. These files do not prove that a kit, mirror, image, model bundle, standards corpus, or
production release exists.

## Artifacts

The canonical manifest is
[`software-inventories/manifest.json`](./software-inventories/manifest.json). It binds every input
Git blob and byte hash, complete identifier-set digests, component counts, format versions, release
blockers, the unassembled-kit state, and these generated artifacts:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `source.spdx.json` | 634706 | `da9e0dab44018d9759d61c43430b8c7f05a8dc9979e595e1bc7729c151376d8a` |
| `source.cdx.json` | 786527 | `591653c4405f6a3bd5d80bad3c927392e1f27d27600f98147f2e5d19eff82ec7` |
| `build.spdx.json` | 601056 | `0cd2efb0ab0bd97902b8630a31cd54f928c4e736a96f3f6ab4c15b616f414ea6` |
| `build.cdx.json` | 743973 | `a4d5de81b9fef956c885d734c2dc7e101886ca5b09a55f0115192f90f7fbddc2` |
| `THIRD_PARTY_NOTICES.txt` | 1465796 | `812c3eaf0b6856f3fc0f56f9af2d8a44c180566705d00747f5b2224dc24d927e` |

The source documents cover 586 dependency records, 14 admitted verification-toolchain records,
and 24 admitted asset records: 624 components in total. The build documents cover 586 components
selected by the recorded build, test, deployment, current-development, and runtime roles. SPDX and
CycloneDX retain each record's license string, exact version, source/artifact reference, checksum
when representable, role, distribution, admission state, and blocker list. The notice bundle lists
the root notice plus every recorded upstream notice path and hash. It explicitly says that a hash
index does not replace unavailable upstream notice text.

## Determinism and fail-closed checks

`scripts/generate_software_inventories.py` requires a full immutable Git subject. Its timestamp is
the subject commit time, IDs derive from stable record identifiers, arrays are sorted, JSON uses a
canonical repository encoding, and input receipts compare Git-normalized blobs so Windows line
endings do not alter semantic output. Two generations in separate directories must be byte-for-byte
identical.

`scripts/validate_software_inventories.py` validates the manifest and both format profiles,
reconciles complete record membership and identifier-set hashes against the authoritative ledgers,
checks every input and output byte receipt, validates dependency-graph coverage, regenerates all
artifacts, and compares exact bytes. `--require-release-admission` fails while any shipped input is
not admitted. It also rejects missing artifacts, tampered bytes, stale source inputs, changed
coverage, duplicate components, incomplete dependency relationships, and any claim that the
Offline Release Kit is assembled.

The admitted hash-locked `spdx-tools==0.8.5` validates both SPDX documents. The CI step installs its
complete P0-T03A lock into an isolated directory before validation. CycloneDX 1.6 receives the same
structural, relationship, field, hash, regeneration, and repeatability checks in ordinary CI. The
admitted CycloneDX CLI is the Linux ARM64 artifact recorded by P0-T03A; its official execution waits
for that exact artifact in the Institution-owned ARM64 toolchain mirror rather than substituting an
unadmitted x86 or hosted validator.

## Reproduction

From an exact checkout containing the immutable subject:

```text
python scripts/generate_software_inventories.py \
  --subject e53108fcbba14733026194aa81abc9c7875eb666 \
  --output <temporary-output>
python scripts/validate_software_inventories.py
python -m pytest -q tests/backend/test_software_inventories.py
python -m ruff check scripts/generate_software_inventories.py \
  scripts/validate_software_inventories.py tests/backend/test_software_inventories.py
```

For the official SPDX parser/validator, install only the admitted P0-T03A lock into a disposable
environment and run:

```text
python -m pip install --target <temporary-toolchain> --require-hashes \
  -r docs/supply-chain/runtime-toolchain-requirements.txt
PYTHONPATH=<temporary-toolchain> python -m spdx_tools.spdx.clitools.pyspdxtools \
  -i docs/supply-chain/software-inventories/source.spdx.json
PYTHONPATH=<temporary-toolchain> python -m spdx_tools.spdx.clitools.pyspdxtools \
  -i docs/supply-chain/software-inventories/build.spdx.json
```

The explicit release check currently returns nonzero by design:

```text
python scripts/validate_software_inventories.py --require-release-admission
```

## Promotion and handoff boundary

P0-T06 may be reviewed as the deterministic inventory implementation, but the generated software
set is not release-admitted. P0-T08 owns release-wide freedom and rights admission, P0-T09 owns the
offline mirror/source-offer closure, and P1-T22A owns Offline Release Kit assembly. Those tasks must
resolve or exclude every current blocker under their own authority and regenerate the inventories
against their exact candidate. P0-T06 does not complete Phase 0, authorize deployment, qualify a
release, or activate production.
