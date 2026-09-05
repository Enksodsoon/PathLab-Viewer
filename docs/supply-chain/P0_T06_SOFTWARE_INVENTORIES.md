# P0-T06 deterministic software inventories

## Result

The implementation generates deterministic SPDX 2.3 and CycloneDX 1.6 source/build inventories,
a human-readable third-party notice bundle, and a hash-bound manifest from the existing dependency,
toolchain, and asset-rights ledgers. The reference inventory subject is implementation commit
`9d567726f0c7206fe67e7e1273072eda423dc99a` with tree
`6e2d0a450563fd20faa6568a30f51c4ed23fd4d7`.

This is an inventory result, not release admission. The reference manifest reports `BLOCKED`:
all 91 current shipped inputs are either `RECORDED_UNREVIEWED` or explicitly `BLOCKED`. The five
explicit evidence failures are `guid-typescript@1.0.9`, `onnxruntime-common@1.27.0`,
`onnxruntime-web@1.27.0`, `splaytree@3.2.3`, and `pillow@12.3.0`. The generator preserves their
upstream blocker codes. It never promotes them from their authoritative P0-T03 state.

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
| `source.spdx.json` | 532890 | `64a447f783c5c1cad38d6175c6466d9572881f71da075c122170d73708391738` |
| `source.cdx.json` | 660700 | `e815995f8f09fc52ef74345213bd69ef79f53417cfc7c7c0938c1c379a0c581c` |
| `build.spdx.json` | 506121 | `2b51a2eedad3f9dde0eaf57c6093d0f31f777657089aa6c4f60df1dd89a048fe` |
| `build.cdx.json` | 626640 | `78a3b63d51c50c87db33796e766920ae0b3fb1b66668d1bd4502617f1c7a5015` |
| `THIRD_PARTY_NOTICES.txt` | 157432 | `4ca7ec50663e379406cfd7c3845e180dc6b926e0c8342134e70cd68dcd3ef1c5` |

The source documents cover 498 dependency records, 14 admitted verification-toolchain records,
and 8 admitted asset records: 520 components in total. The build documents cover 489 components
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
  --subject 9d567726f0c7206fe67e7e1273072eda423dc99a \
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
