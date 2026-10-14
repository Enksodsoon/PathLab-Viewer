# P0-T06 deterministic software inventories

## Result

The implementation generates deterministic SPDX 2.3 and CycloneDX 1.6 source/build inventories,
a human-readable third-party notice bundle, and a hash-bound manifest from the existing dependency,
toolchain, and asset-rights ledgers. The current reference inventory subject is implementation commit
`adeaf3ba033d4a99dfefcaa53a802e6fdf8fedd1` with tree
`bd9eb0d5108ac7283aa08c73a6cde5d458bcdd38`.

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
| `source.spdx.json` | 634706 | `c318cad2ae79c5b64a926642a882d2c245459b553ecd9456fc89400c4169e7ec` |
| `source.cdx.json` | 786527 | `eb3ff134018c99a824dc363de467d89d28e3e2b47c74efb36d2fafc876d43ba7` |
| `build.spdx.json` | 601056 | `ae34c8177f22a29f8a5e4a5a38028028fd03bcb867c6efd2ffffedd438965c16` |
| `build.cdx.json` | 743973 | `f210114e3eb98acbfbfee6532913588a6b9eb6a1abd23e0c24f6e8d917e6887e` |
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
  --subject adeaf3ba033d4a99dfefcaa53a802e6fdf8fedd1 \
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
