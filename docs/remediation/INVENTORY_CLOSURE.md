<!-- SPDX-License-Identifier: Apache-2.0 -->
# Strict software inventory closure

Inspection date: 2026-09-27. Checkout base: `cf0d2d2b0b6a298185a676988ffae69a6d01dd3c`.
Final browser collection uses a stable working snapshot with root-owned product
edits, explicitly not an immutable approved release subject.
This report records evidence and proposed closure work. It does not admit licenses,
waive policy, assemble the Offline Release Kit, or certify a production distribution.

## Current result and authoritative path

The current `software-inventories/manifest.json` has **178 release blockers**:
**171 `RECORDED_UNREVIEWED`** and **7 `BLOCKED`**. These are not 178 unknown,
unsafe, or incompatible licenses. Strict validation was reproduced and rejected
release admission with the same identifiers.

`generate_software_inventories.py` selects dependency records whose distribution is
`browser-bundled`, `bundled`, `bundled-runtime`, or
`bundled-runtime-and-operator-tooling`, excluding `planned-*` roles. Any selected
record not exactly `ADMITTED` becomes a release blocker. The current 178 comprise
134 bundled npm inputs, 40 bundled-runtime Python inputs, and four Python inputs
also used by operator tooling. No selected record is admitted.

The dependency inventory remains the authority for those records. The generator
captures registry artifacts, integrity verification, and license/notice file hashes;
it intentionally labels successful capture `RECORDED_UNREVIEWED`. The 171 such
rows have empty blocker lists, verified checksums, and recorded notice hashes.
Their outstanding work is review and distribution evidence, not a diagnosed
package resolution defect. Generation currently has no separate durable reviewed
admission overlay: hand-editing generated status would be overwritten by the next
regeneration. A reviewed, artifact-bound receipt mechanism must be designed and
approved before reliable promotion is implemented.

The separately admitted runtime-toolchain and asset-rights ledgers are also read
by the software inventory generator. Their admission does not admit equivalent
rows in the dependency inventory or an entire final distribution. Root Apache-2.0
rights likewise do not relicense dependencies. See
[license and notice policy](../supply-chain/LICENSE_AND_NOTICE_POLICY.md),
[dependency inventory](../supply-chain/dependency-inventory.json), and
[runtime admission](../supply-chain/P0_T03A_RUNTIME_TOOLCHAIN_ADMISSION.md).
The historical P0-T06 prose describing 91 blockers/five failures is not the current
manifest count.

## Seven explicit evidence blockers

| Exact input | Current blocker | Verified finding and minimal next step |
| --- | --- | --- |
| `isarray@1.0.0` | No archive notice text | Exact npm integrity matches. `package/README.md` includes the complete MIT grant and Julian Gruber copyright. The scanner only recognizes license-like basenames and misses it. Fixed bounded receipt matching described below. |
| `splaytree@3.2.3` | No archive notice text | Exact npm integrity matches. `package/Readme.md` includes the complete MIT grant and Alexander Milevski copyright. Same scanner miss, fixed below. |
| `pillow==12.3.0` | Lock/artifact mismatch | Generator chose the official source archive, whose digest is not locked. The lock intentionally contains cp312 Linux ARM64 and x86_64 wheel hashes; both exact official wheels were downloaded and verified. Each has a substantive `dist-info/licenses/LICENSE`. Fixed selection below; no lock change needed. |
| `eastasianwidth@0.2.0` | No archive notice text | Exact tarball and recorded Git commit inspected. Archive only declares MIT in package metadata; no grant text found. Recorded commit tree has no license file. Current official repository exposes `MIT-LICENSE.txt`, but later repository material is not automatically attributable to the exact old artifact. Require an immutable, accountable artifact-to-license receipt or separately authorized dependency replacement. |
| `guid-typescript@1.0.9` | No archive notice text | Exact tarball only declares ISC in package metadata; no grant text found. Recorded Git commit lookup returned 422; official repository license lookup returned 404. Require recovered upstream immutable notice/provenance or separately authorized replacement/removal of the dependency path. Do not fabricate an ISC copyright holder or substitute generic license boilerplate. |
| `onnxruntime-common@1.27.0` | No archive notice text | Exact npm integrity matches. README links mutable upstream `main` rather than including text. Official release commit and same-version `js/common/package.json` establish origin/name/version/MIT alignment. Exact LICENSE plus full ThirdPartyNotices material collected in a checksum-bound supplemental candidate, pending accountable review. No extra Git-head attestation is required by repository policy. |
| `onnxruntime-web@1.27.0` | No archive notice text | Same official origin/version binding established via `js/web/package.json`. Exact full release ThirdPartyNotices collected alongside LICENSE for this candidate. Packaging all corresponding notices and reviewing applicability remain required; no reproduced WASM build is required by the cited license/notice policy. |

Primary exact artifact metadata:
[isarray](https://registry.npmjs.org/isarray/1.0.0),
[splaytree](https://registry.npmjs.org/splaytree/3.2.3),
[Pillow](https://pypi.org/pypi/pillow/12.3.0/json),
[eastasianwidth](https://registry.npmjs.org/eastasianwidth/0.2.0),
[guid-typescript](https://registry.npmjs.org/guid-typescript/1.0.9),
[ONNX common](https://registry.npmjs.org/onnxruntime-common/1.27.0), and
[ONNX web](https://registry.npmjs.org/onnxruntime-web/1.27.0).
Candidate upstream ONNX license (tag resolved during inspection to commit
`8f0278c77bf44b0cc83c098c6c722b92a36ac4b5`):
[official version tag](https://github.com/microsoft/onnxruntime/blob/v1.27.0/LICENSE),
SHA-256 `2f07c72751aed99790b8a4869cf2311df85a860b22ded05fa22803587a48922c`.
The first returned eastasianwidth license-file commit is
`1d41951a59d63fb2d77cda021050fc070cae424a`; its exact `MIT-LICENSE.txt` hashes to
`94aa6016fb9d436508366433e9caba061443ca58f4c7eb515caec7badf90ae5a`. This is an
immutable candidate notice source, still requiring an old-artifact binding.
A byte comparison of the old eastasianwidth runtime source and that license-file
commit differs; substituting the later notice is therefore not an established exact
artifact receipt. These links supply evidence, not admission decisions.

The current ONNX path is reachable through `apps/web/src/study/traceSim.worker.ts`
and explicit imports of WASM/MJS artifacts. `guid-typescript` is its locked
transitive dependency. The actual upstream Guid caller is `lib/onnxjs/tensor.ts` (`Guid.create()`), used by
the WebGL backend. The official `./wasm` export points to `ort.wasm.bundle.min.mjs`;
its source map contains no guid-typescript, onnxjs tensor, or backend-onnxjs source.
A fresh isolated Vite build with unchanged product configuration and a read-only
membership collector passed (11.77 seconds). Its 4833 main modules and all three
worker graphs contain no guid-typescript, eastasianwidth, or archiver. The trace
worker imports the exact WASM entry plus SIMD WASM/MJS assets; those installed
inputs were byte-compared with the exact official tarball. The XLSX consumer uses
write-excel-file browser index/JSZip, while eastasianwidth is only in the declared
Node archiver ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ glob ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ cliui ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ string-width closure. These establish current
physical browser membership, not an unrestricted claim about future exports or
full source-package distributions. Removing the upstream dependency can break
unsupported full/WebGL exports, and is unnecessary to retain current Study WASM
behavior. A separately authorized artifact-bound shipped-distribution classification
repair can truthfully exclude those unshipped bytes from the browser release
selection while retaining complete source/build inventory records and upstream
notice blockers there. A future imported WebGL/Node export must invalidate that
classification;
this report does not silently alter their distribution or waive source-package
notice obligations. No runtime or package change was made.

## Narrow generator repairs

Root authorized two mechanical repairs, without tracked ledger regeneration:

1. Recognize only the two exact source URL/member path/payload hash tuples whose
   complete embedded MIT notices were verified. Tampered text, changed member path,
   different source, and mere `License: MIT` mentions remain unrecognized.
2. Select an official artifact whose SHA-256 is in the current Python lock before
   choosing an unmatched source archive. Prefer a locked sdist, otherwise the first
   official locked wheel (preserving registry order within the artifact class). Continue verifying downloaded bytes. If no official
   artifact matches the lock, preserve the mismatch blocker.

Actual immutable README payload receipts:

| Package member | SHA-256 |
| --- | --- |
| isarray `package/README.md` | `ff138e683771b187f3629c383db72ee7d632009010a36d08e18e8d2a34222ec7` |
| splaytree `package/Readme.md` | `ba6a09ed78a28536852d504086e7dd0e1f9c090a27c460bc9f301ee5783927dd` |

The complete original README payloads are regression fixtures because shortening
one would no longer prove the exact recorded hash. They retain their embedded MIT
copyright and grant text: Julian Gruber (isarray) and Alexander Milevski (splaytree).
They are third-party MIT material, not relicensed under the report's Apache header.
Source is the exact official registry tarball linked above; fixtures are small text,
not product assets. A fixture-local LF rule preserves exact payload hashes across
Windows and Linux checkouts. No external artifact is installed or executed by these tests.

Both new regression cases failed before repair; all six dependency-inventory tests
pass after repair. Ruff passes. Negative checks preserve fail-closed behavior and
verify generator output remains `RECORDED_UNREVIEWED`, not `ADMITTED`.
Generator callers traced: its CLI generates records, with `archive_notices` used
only by npm/Python acquisition paths; CI lints the script and validates the existing
ledger. No runtime caller or tracked ledger was altered.

## Remaining review and packaging work

No inspected shipped row claims `UNKNOWN`, `UNLICENSED`, or a noncommercial-only
license. This is a ledger observation, not legal certification of all contents.
MIT, BSD, ISC, Apache, BlueOak, Unlicense, and other recorded permissive terms still
require actual notice preservation and applicable attribution. Three OFL font
packages require their recorded font license/attribution and any applicable
reserved-name obligations. `jszip@3.10.1` records an MIT **or** GPL option; document
which grant is used rather than declaring GPL mandatory from the string alone.

The conditional review rows include:

- `psycopg@3.3.5` and `psycopg-binary@3.3.5`: recorded LGPL-3.0-only. Review the
  actual Python/native linking and distribution boundary, corresponding source,
  notices, and replacement/relinkability obligations. LGPL is not automatically
  a prohibited license, but automatic Apache-only admission would be unsupported.
  [GNU LGPLv3 text](https://www.gnu.org/licenses/lgpl-3.0.html) sets the combined-work
  conditions; an accountable release owner must establish how this distribution
  complies.
- `certifi@2026.7.22`: recorded MPL-2.0. Include the exact covered source, license,
  and recipient source-access information applicable to distributed executable
  forms. [Mozilla's official FAQ](https://www.mozilla.org/en-US/MPL/2.0/FAQ/) and
  [license text](https://www.mozilla.org/en-US/MPL/2.0/) describe those obligations.

No newly proven prohibited-license defect was found in the 178 selected rows.
Separate planned/development rows (e.g. AGPL test tooling or separately executed GPL
Barman) are not these 178 shipped blockers. They retain their own gates and
[ADR 0122](../adr/0122-qualify-the-durability-supply-chain-and-egress-boundary.md)
boundaries; this report does not waive them.

The existing `THIRD_PARTY_NOTICES.txt` is explicitly a hash/path index, not the full
upstream text. An admitted distribution must package the actual required licenses
and notices and provide any required source. Collect verified exact notice bytes
into a content-addressed acquisition cache; bind archive integrity, member path,
notice SHA-256, chosen license, distribution scope, source/relink obligations,
reviewer authority, and immutable approval receipt. Validate those receipts against
the lock, preserve decisions across regeneration, fail closed on changed artifacts,
and inspect the actual built web/native/Python distributions. Policy requires an
accountable immutable admission receipt; CI success and package metadata alone do
not replace it. Institution-owned ARM64 mirrors and release-bound scanner databases
also remain separate runtime qualification/Offline Release Kit requirements.

## Completed technical review materials

All **174 candidate unreviewed exact artifacts** were downloaded from their
recorded primary registry URLs and verified against the recorded SHA-256/SHA-512.
All **205 recorded notice members** were extracted without execution, checked
against their exact hashes, and stored under content-addressed ignored paths.
`admission-review-materials.json` binds each component ID, declared license,
artifact/checksum, member/path/hash/size, and collected material. Every decision
remains `PENDING_ACCOUNTABLE_REVIEW`. This includes the three mechanically repaired
rows; collection does not promote them.

`review-bundle-manifest.json` hashes the candidate inventory, per-component review
materials, supplemental receipt, and full notice concatenation.
`CANDIDATE_FULL_NOTICES.txt` contains the actual readable UTF-8 text (983070 bytes),
component IDs and provenance, plus the exact supplemental ONNX release LICENSE and
full ThirdPartyNotices. The independent raw bytes remain content-addressed, so the
candidate concatenation is not the sole receipt. The official release commit's
`js/common/package.json` and `js/web/package.json` both declare the matching exact
name/version `1.27.0` and MIT grant. The supplemental receipt additionally binds
both exact npm artifact checksums and origin repositories. This is a feasible,
reviewable external notice-material supplement; absence of npm GitHead alone is
**not** an additional policy blocker. The publication/packaging and applicability
review must still happen before ledger changes.

The dependency archive notice cache does not claim an installed ARM64 native
closure or the complete release-specific OS/binary SBOM: source archives can have
different bundled-library boundaries from deployment wheels/system packages.
Final distribution review must use the actual artifact/target-specific inventory
and license/source material. That requirement follows the existing packaging and
runtime policy; it is not a newly invented attestation condition.

## Evidence and next decision

Ignored acquisition receipts live under
`var/remediation-evidence/inventory-closure/`: current-blockers, primary-artifact,
license-and-wheel, Git-tree, remaining-notice, upstream-provenance, strict-validation,
generator-red, admission-review-materials, and ONNX supplemental-notice receipts. Candidate regeneration produced 580 records. Only isarray, splaytree, and Pillow
change substantive evidence/admission fields; 19 additional rows change registry
metadata hashes only. It has 174 unreviewed plus four explicitly blocked shipped
rows, still 178 release blockers and zero admitted dependencies. Candidate
dependency validation passes against the inspection subject. Candidate output is
isolated there for root review; it is not authoritative and no existing inventory/master ledger was edited.

Next feasible step: review the mechanical repair diff and candidate three-row
closure; regenerate authoritative inventory/SBOM receipts at an approved immutable
implementation subject with existing validators. Those three rows must become
**unreviewed**, not admitted. Then review the already collected exact notice-material set and the two ONNX
supplemental candidates. Authorize a durable artifact-bound review/notice packaging
contract and resolve eastasianwidth/guid evidence or separately scoped truthful
artifact-bound physical-bundle classification (fresh browser proof is now
available). The ONNX supplemental rows still need root review and the collected
notice paths copied into the authoritative packaging/ledger contract; all remaining
license decisions must be attributable to the actual reviewer, not invented here. An
accountable license/distribution decision is still necessary before promoting the
reviewed dependency set. A generic mass replacement of 178 admission strings is
not an acceptable closure.


## Concrete distribution/supplement proposal for root review

`inventory-ledger-proposal.patch` is an isolated review diff against the existing
ledger, not an applied authoritative edit. It includes the three proven evidence
repairs, adds exact ONNX release LICENSE/ThirdPartyNotices paths and source receipts
as `RECORDED_UNREVIEWED`, and changes only the two physically omitted packages'
distribution to `not-bundled-in-current-browser-build`. Their `BLOCKED` status,
license declaration, integrity and missing-notice facts remain intact. It retains
all 580 record IDs and full source/build graph membership and contains no
`ADMITTED` promotion. With these proposed classifications, the browser strict set
would contain 176 unreviewed rows; admission remains blocked.

`browser-distribution-proposal.json` binds 243 source/build-input canonical Git
blobs and complete path membership, the immutable package lock, all freshly emitted
asset hashes, graph evidence, and the two proposed exclusions. The source input set
was equal before and after the final isolated build. The candidate is explicitly a
working snapshot because other authorized agents' product edits are present; root
must bind the approved implementation subject and reproduce the build before
making this an authoritative receipt.

The proposed ledger was cloned from the tracked ledger rather than replacing it
with the network-regenerated candidate. Top-level timestamps, source receipts and
subject fields are unchanged; the candidate's 19 metadata-only refreshes are excluded.
Exactly seven component records differ.

Minimum integration, after root review:

1. Keep `generate_software_inventories.py` source/build membership unchanged. Its
   existing shipped-distribution selection is already separate; use the two proven
   distribution classifications only for that boundary.
2. Preserve a checksum-bound supplemental-notice table in the existing manual-input
   ledger for the two exact ONNX package/version/integrity tuples. Copy the collected
   LICENSE and complete ThirdPartyNotices to their recorded local notice paths,
   verify source URLs/revisions and both file hashes, and merge those receipts with
   archive notices during npm record generation. Successful collection produces
   unreviewed evidence, never admission. Other versions, byte changes, unknown
   origin/name/version, missing or tampered material must remain blocked.
3. Make dependency validation require the exact distribution-receipt input path
   set plus current canonical Git blob matches (the same pattern as its existing
   source-receipt validation). Include membership additions/removals, not only old
   path checks. Any changed source/entry/package/Vite/public/build-helper input
   invalidates exclusion and requires fresh build graph evidence. Keep the exact
   package versions/integrities bound. The existing bundle-budget helper reads a
   Vite manifest for sizes; it does not establish package module ownership, so it
   cannot alone prove these exclusions. The read-only Vite collector in the ignored
   proof directory supplies the actual main and each worker graph; a bounded build
   check can retain that evidence without a runtime framework.
4. Package readable collected notices using the existing web legal-file copy
   stage, and inspect the generated distribution. The current copy helper only
   handles root LICENSE/NOTICE; the hash-index notice output alone is insufficient.
   Keep full source/development-kit obligations distinct from browser exclusion.

These are technical receipt and packaging proposals, not a new rights attestation.
The accountable reviewer can inspect the collected materials before making any
license/distribution decision. No hypothetical requirement to reconstruct upstream
WASM or obtain extra npm Git-head attestations is introduced.

For full-text distribution, retain the collected 162 unique content-addressed
notice texts under `docs/supply-chain/notice-material/sha256/`, indexed by existing
component/member/hash receipts. Extend the existing `notice_bundle` generation to
include hash-verified text for shipped components and its existing input receipts
to cover these materials. Missing or tampered material must fail validation. Add
the resulting `THIRD_PARTY_NOTICES.txt` to
`apps/web/scripts/copy-release-legal-files.mjs`; include the same applicable notice
artifact in backend container and Python distribution packaging through
`deploy/Dockerfile.backend` and `pyproject.toml`. These integration files have not
been edited in this scope.


Implemented durable integration (pending stable-subject regeneration):

- The existing manual input ledger now contains two exact ONNX supplemental
  receipts. Generator/validator require the exact artifact checksum, registry
  source, repository, release package identity and unchanged local notice bytes.
  Collection remains `RECORDED_UNREVIEWED`; no admission promotion was introduced.
- The archive index binds 174 exact component/artifact/checksum tuples to 205
  captured notice members and 162 deduplicated texts. The existing notice bundle
  appends captured text for shipped components. Missing or tampered claimed text
  fails closed; blocked components without captured text remain visibly blocked.
- The existing web copy stage and both Docker targets include the generated notice
  artifact. Hatch wheel/sdist force-includes preserve root `license-files` metadata
  and package the corresponding third-party notice artifact.
- Six scoped regressions pass, including native Node copy, wrong-artifact,
  missing/tampered notice and actual dependency-validator rejection. Ruff and
  repository/asset-policy checks pass. A real Hatchling 1.32.4 wheel and sdist build
  contained byte-identical currently generated notice artifacts; this proves the
  packaging paths, while final full-text release contents await regeneration.
- Direct generation from the repaired candidate produces 1,437,058 bytes with 209
  notice sections (205 archive members and four ONNX supplemental instances).
  Receipt: `var/remediation-evidence/inventory-closure/durable-full-notices.txt`.

Authoritative generated dependency/software inventories are deliberately unchanged
until root records a stable implementation subject and regenerates their existing
receipts. Their old receipt assertions cannot substitute for this next step. The
physical browser exclusions remain unapplied; no distribution enum was added.


Coordinated regeneration commands (root executes after review):

1. Record stable implementation commit A containing the approved manual table,
   notice materials/index, generators/validators, packaging changes and tests.
   Do not change any generator input between selecting A and capturing receipts.
2. From this worktree, run the existing generator into ignored output, then apply
   only the five approved evidence deltas. The bounded merge preserves all other
   record fields, including previously captured registry metadata hashes and
   admission decisions; the new raw metadata is not falsely described as unchanged.

```powershell
$inventorySubject = git rev-parse HEAD
$inventoryPython = 'python' # Use the documented project Python runtime.
& $inventoryPython scripts/generate_dependency_inventory.py --subject $inventorySubject --workers 4 --output var/remediation-evidence/inventory-closure/stable-raw-dependency-inventory.json
& $inventoryPython var/remediation-evidence/inventory-closure/merge-approved-regeneration.py var/remediation-evidence/inventory-closure/stable-raw-dependency-inventory.json docs/supply-chain/dependency-inventory.json
& $inventoryPython scripts/validate_dependency_inventory.py --subject $inventorySubject
```

The ignored bounded merge helper asserts identical locked membership and unchanged
roles/distributions/manifests before applying the five deltas. It copies only new
subject/generated/source receipts at the document level. Review the resulting diff
and update the existing test subject/tree expectations to A. Record those generated
ledger/test changes as commit B before the next stage, because the software generator
requires its dependency ledger input to belong to its immutable subject.

```powershell
$softwareSubject = git rev-parse HEAD
& $inventoryPython scripts/generate_software_inventories.py --subject $softwareSubject
& $inventoryPython scripts/validate_software_inventories.py
& $inventoryPython scripts/validate_software_inventories.py --require-release-admission
```

The final strict command must still fail closed: with browser exclusions held and
no admission decisions, all 178 current shipped inputs remain unadmitted (176
unreviewed and two missing-notice blocked rows after the five technical repairs).
The generated notice artifact now contains full corresponding captured material.
Commit C can record the regenerated software inventories. The software generator
and validator both enumerate new notice-file membership and canonical Git blobs;
adding/removing notice material invalidates old input membership, not merely hashes.
Actual packaging qualification should then inspect this regenerated full-text file
in fresh web, backend/container and Python build artifacts.
