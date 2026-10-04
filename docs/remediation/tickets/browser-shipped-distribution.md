# Browser shipped distribution classification

Labels: wayfinder:ticket

## Decision

Qualify the two exact source dependencies absent from the compiled browser before changing their physical distribution classification. Preserve all source graph records, integrity, notice blockers and admission decisions. Browser absence is not a source license grant or a complete software admission.

## Evidence

Fresh immutable ddc74e4 observation captured the main4835-module graph and three worker graphs2/10/4, with no guid-typescript, eastasianwidth or archiver module. All125 emitted assets from the manifest-enabled read-only observer match the standard production build byte for byte. Standard packaging adds LICENSE, NOTICE and THIRD_PARTY_NOTICES.txt. Input Git blobs remain stable before/after; the package lock and artifacts are hashed. Ignored primary-worktree receipt: `var/browser-membership-ddc74e4-manifest/receipt.json`. Earlier no-manifest observation remains separate.

The two source rows remain BLOCKED for missing exact notices. Strict current release selection remains178unadmitted inputs,176unreviewed plus2blocked. Excluding the two proven unshipped components from that selection would still leave176unreviewed; no accountable admission decision is manufactured.

## Contract being implemented

The isolated helper rejects changed committed/working input bytes or membership, ignored public-file copies, mismatched package integrity, an imported excluded package in a worker graph, escaping artifact paths, replaced emitted bytes and unexpected artifact files. It requires all three legal files when inspecting standard packaged output. Application changes only the two physical distribution fields and their evidence pointers after validation; source rights fields remain intact.

Capture complete build/configuration inputs and all compiled graphs at an immutable implementation commit. Require fresh output comparison in hosted checks. Keep generic inventory membership intact and fail closed when imports or build inputs change. A compiler/validator receipt and isolated guard checks are not yet an authoritative ledger decision.

## Current scope and next evidence

Combined helper and existing dependency inventory cases:29passed,1Windows symlink permission skip. Ruff and Node syntax pass. Independent review cleared corrected patch-input coverage, canonical LF public bytes and linked-directory confinement. First positive fixture exposed Windows Path separator normalization in the new helper; POSIX artifact paths fix that setup failure. Main PR307 is separately mergedc37cf81 with allnine fresh-main checks and protected deployment37164136683successful; this work is isolated and does not delay or alter its product tree.

Compiler capture, source/asset comparison integration, generator/validator integration, immutable receipt capture, independent review, coordinated inventory regeneration and fresh protected checks remain required. Authoritative distribution/admission records are unchanged. Exact source-notice gaps and accountable reviews remain visible even if the narrower browser classification is proved.
