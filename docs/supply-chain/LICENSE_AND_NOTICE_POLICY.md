# License and notice policy

This policy implements [ADR 0046](../adr/0046-release-pathlab-under-apache-2-0.md)
for the release boundary admitted by the signed
[P0-T02 relicensing disposition](./P0_T02_RELICENSING_DISPOSITION.md). It is a
repository and packaging contract, not a claim that third-party works are
PathLab-authored or that every planned Full-Surface dependency is release-ready.

## Material classifications

- **PathLab-authored material.** Material covered by the signed disposition is
  licensed under Apache-2.0. New PathLab-authored source and documentation use
  `SPDX-License-Identifier: Apache-2.0` where the file format safely supports a
  comment. Existing files inherit the root license when they are within the
  covered boundary; bulk header-only rewrites are not required.
- **Third-party works.** Dependencies, fonts, icons, vendored or copied material,
  standards artifacts, and upstream notice text retain their recorded upstream
  licenses and attributions. Neither `LICENSE` nor package metadata relicenses
  them. Their exact admission state remains controlled by the dependency and
  asset ledgers.
- **Generated files.** Lock files, compiled requirements, build output, and
  mechanically generated inventories carry the license of their expressive
  source or generator inputs as applicable. They do not create a license grant
  for the packages or data they describe. A generated file that accepts comments
  should identify its generator and use `SPDX-License-Identifier: Apache-2.0`
  only when its expressive content is covered PathLab material.
- **Excluded or unresolved material.** Paths excluded by the signed disposition,
  unknown ownership, incompatible inbound terms, and `BLOCKED` or
  `NOT_EVALUABLE` ledger entries are outside the Apache release boundary until an
  accountable immutable receipt admits them. The retired
  `packages/viewer-ui/**` blobs remain excluded and are not relicensed.

## Contributions and provenance

Every contribution must identify its origin and be submitted by a person who has
the right to provide it under the proposed terms. A contributor must disclose
copied, adapted, generated, and tool-assisted material; name its source and
license or applicable terms; preserve required notices; and add or update the
relevant supply-chain ledger. Contributions use a `Signed-off-by:` trailer to
record the contributor's Developer Certificate of Origin attestation. Material
with unknown ownership or incompatible terms is rejected rather than inferred
from a filename, package name, repository presence, or tool output.

## Source and object distribution contract

Every source archive and repository snapshot distributed as PathLab Viewer must
place unmodified copies of root `LICENSE` and `NOTICE` at the archive root and
include this policy plus applicable third-party license and notice material.

The Python project metadata declares `Apache-2.0` and packages `LICENSE` and
`NOTICE` as license files. A wheel must therefore contain both under its
`.dist-info/licenses/` directory, and an sdist must contain both at its root.

The web build copies `LICENSE` and `NOTICE` to the root of `apps/web/dist` after
Vite succeeds. Any archive made from that directory must retain both files.

Other binary bundles, installers, container images, offline kits, and appliance
images must expose readable copies at a conventional license location documented
by their release owner and include all applicable third-party notices. Until a
bundle proves those placements and its complete dependency/asset admission, it
is not a releasable PathLab distribution. This policy does not itself implement
or approve a deployment, release, pilot, qualification, or activation.

## Fail-closed checks

`python scripts/check_public_repository.py` rejects a tree when required root
rights files, policy text, contribution provenance rules, package license
metadata, or the web legal-file copy contract are missing or inconsistent. Build
validation must additionally inspect the actual Python wheel, Python sdist, and
web `dist` output; metadata or a green unrelated test is not a substitute for
artifact inspection.
