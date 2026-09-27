# Forge sync caller qualification

Date: 2026-09-27. Status: **actual caller compatibility verified locally on Windows**. This qualifies metadata synchronization and opaque pagination; it does not qualify a packaged desktop release or production activation.

## Source and runtime

`git ls-remote --symref https://github.com/Enksodsoon/PathLab-Forge.git HEAD` returned default branch `main` and SHA `7de0d9159ee0c999c52de51670b21c86609cf790`. Its official pinned-source ZIP has SHA-256 `bf0b67a5dbdceca6956c6846967f55b610f3331eacab1a5fe0246a11338feeba`. Every archived source file remained byte-identical after qualification builds.

The current source layout is the repository root, including [ViewerSyncService.java](https://github.com/Enksodsoon/PathLab-Forge/blob/7de0d9159ee0c999c52de51670b21c86609cf790/src/main/java/org/pathlab/forge/viewer/ViewerSyncService.java). The historical `study-coach-forge/forge` prefix is not present in this archive.

The original local Forge directory, its `.git`, and its private untracked CMD file were preserved. Source, harnesses, synthetic databases and outputs reside under ignored `var/remediation-evidence/forge-qualification/`. The final build uses its short `F/` extraction. No Forge or Viewer product/package source was changed for this task.

Existing tooling was used: Temurin JDK `17.0.19+10`, the source-pinned Gradle `9.6.1` wrapper, and pnpm `11.9.0`. Missing pinned Maven dependencies were resolved through the existing wrapper; no JDK/Gradle installation or dependency-version update occurred. Java compilation targets release 17 and includes `-Xlint:all`.

## Executed caller and HTTP contract

The harness executes the unmodified compiled **ViewerPairingService**, **ViewerSyncService**, and **SqliteViewerSyncStore**. Pairing creation and exchange travel over real loopback HTTP. Only an isolated synthetic admin approves the disposable device; credentials remain in the harness's memory store. The sync service then makes its own authorized requests, parses actual response JSON, follows opaque `nextCursor`, and persists its SQLite state.

A standard-library HTTP bridge forwards these requests to the current Viewer application's actual FastAPI routes using the existing desktop contract fixture. It does not supply handwritten library pages. The Viewer baseline is `cf0d2d2b0b6a298185a676988ffae69a6d01dd3c` plus the closure working tree; runtime source hashes are retained with the evidence. No production host, real credentials, private uploads, browser or original Forge CMD was used.

| Synthetic library | Actual page sizes `(slides, folders)` | Caller result |
| --- | --- | --- |
| 102 folders, 1 slide | `(1, 100)`, `(0, 2)` | 1 unique slide and 102 unique folders |
| 102 folders, 101 slides | `(100, 100)`, `(1, 2)` | 101 unique slides and 102 unique folders |

Both cases verified that the slide's `folder-100` parent arrives on page two and resolves in the caller's stored library. The request cursor exactly matches the preceding response's opaque cursor. Both resources stay at or below 100 entries per page, the final cursor is null, and transport receipts contain no duplicate IDs. The changefeed cursor `1` persists; a second no-change sync requests `after=1` and skips library refresh. Closing and reopening the actual SQLite store preserves slides, folders and cursor. Missing bearer authorization returns 401.

The two cases were executed initially and again against the final complete-build classes. The service's existing 100-page and 1 MiB JSON bounds were retained.

## Checks and receipts

| Check | Result |
| --- | --- |
| Existing `ViewerSyncServiceTest` | 3 passed |
| Complete Gradle `check`, including frontend build/resources | 188 Java tests: 185 passed, 3 skipped; 0 failures/errors |
| Forge frontend Vitest | 46 passed across 4 files |
| TypeScript/Vite build and existing bundle budget | Passed; entry 98,069 bytes, largest chunk 342,393 bytes |
| Existing Forge repository policy script | Passed before and after build |
| Current Viewer late-folder pagination contract | Both parameterized HTTP cases passed |
| Actual Forge HTTP/SQLite integration | Both datasets passed, including final repeat |

Commands executed from the extracted Forge root included:

```text
gradlew.bat --no-daemon --no-configuration-cache --max-workers=1 -Porg.gradle.java.installations.auto-download=false -Dorg.gradle.jvmargs=-Xmx512m test --tests org.pathlab.forge.viewer.ViewerSyncServiceTest -x frontendBuild -x frontendInstall
gradlew.bat --offline --no-daemon --no-configuration-cache --max-workers=1 -Porg.gradle.java.installations.auto-download=false -Dorg.gradle.jvmargs=-Xmx512m check
scripts/verify-repo.ps1
```

The frontend was installed with `pnpm install --frozen-lockfile`; its standalone tests used `pnpm exec vitest run --maxWorkers=1 --minWorkers=1`. The ignored harness was compiled with JDK 17 `javac --release 17 -Xlint:all`, then executed by the project's Python runtime through `run_forge_http.py` with `PYTHONPATH` pointing to this Viewer worktree. `FORGE_QUALIFICATION_RUN_ID=final` identifies the final isolated fixtures. A new run identifier gives a fresh fixture directory for reproduction.

Retained evidence under `var/remediation-evidence/forge-qualification/`:

- `remote-default.txt`, `source-manifest.json`, `runtime-manifest.json`, and the pinned ZIP.
- `forge-focused-tests.log`, `forge-complete-check.log`, `forge-java-test-summary.json`, `forge-frontend-tests.log`, `forge-policy-final.log`, and `viewer-folder-contract-tests.log`.
- `ForgeHttpQualification.java`, `run_forge_http.py`, `classpath.txt`, and `forge-http-integration-final.log`.
- `http-case-1-final/http-receipts.json` and `http-case-101-final/http-receipts.json`, plus each caller's output and synthetic persisted stores.
- `F/build/test-results/test/` contains the complete JUnit XML results.

Initial build failures were qualification setup issues and are retained: offline dependency jars were absent; omitting frontend resources produced three shell HTTP 404 tests; the SHA-named extraction made the Windows esbuild executable path 270 characters and spawning failed despite the file existing. Resolving pinned dependencies and building the same byte-identical archive at the shorter ignored path produced the successful complete check. No product repair was made from those failures.

## Remaining qualification limits

The three skipped Java cases require actual H&E/OME inputs and real-image quality probes; no such inputs were supplied. This campaign verifies actual Java HTTP callers and SQLite persistence with synthetic library metadata. It does not verify microscopy conversion, image pixels, offline image download, TLS/Caddy deployment, or a production server session.

No packaged Forge window, browser-rendered folder workflow, accessibility/touch layout, physical device, macOS credential store/signing, installer or distribution artifact was exercised. The full Java suite includes the existing Windows credential-store test with its isolated random test target; the HTTP integration deliberately uses an in-memory credential store. These caller receipts do not substitute for packaged-device/UI qualification, redistribution approvals, protected release gates or production activation.
