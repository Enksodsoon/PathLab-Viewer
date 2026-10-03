# Reachable annotation commands and Inspector focus

Labels: wayfinder:decision
Status: local candidate

## Confirmed evidence

Production68e0a038 at320x568 clips Open annotation inspector entirely beyond the viewport: x345.625,width44. The command bar starts at x56,width208,scrollWidth333,overflow visible. The document itself has no horizontal scroll, so this is not a reachable overflow tray. Production screenshot and read-only DOM measurements are retained in ignored release evidence. Scoped tab emulation was cleared and desktop sizing restored; the paused synthetic upload tab was not reloaded.

The existing desktop max-content/max-width rules survive mobile layout. Reset width,max-width and margins at the mobile breakpoint; use a narrow grid for five44px buttons plus a separate full-width save-status row. Move the annotation list below that second row and keep inspector-open command positioning inside the viewport. Preserve warm identity, native controls, toolbar semantics, fonts and existing components.

A native Chromium regression reproduces clipping before repair (annotation-commandbar-red). After CSS repair it reaches844x390 and proves closing the desktop Inspector loses keyboard focus (annotation-commandbar-green-chromium). The existing focus-cleanup effect returns early for desktop. Restore trigger focus on desktop closure without adding a modal trap; retain the existing mobile trap and cleanup. The corrected Chromium check passes320/390/760/844/1584 widths (annotation-commandbar-green2-chromium).

## Verification and dependencies

The added browser regression asserts all command rectangles lie in the viewport,44px button targets receive centre hits,save status remains visible,Inspector opens and closes with focus restored,and the annotation list cannot cover commands. The full annotation-responsive matrix runs all four browser targets with two workers. The real-backend narrow case uploads disposable pixels,opens Inspector,authors a point,edits its title,requires real batch acknowledgment and Saved,and checks the title after reload. Static TypeScript/build and changed-file lint pass.

Current source is68e0a038 on codex/annotation-mobile-commandbar. This is a separate repair batch from folder PR288; preserve its source aliases and integrate current main before release. No backend API,schema,dependency,activation or source-image changes are required. Protected exact-head/main gates and authenticated released320px checks remain mandatory. Do not close campaign while external secret/OneDrive facts and cancellation authorization remain unresolved.

## Candidate results

All60 annotation-responsive cases pass across four browser projects with two workers. Real-backend320px create/select/edit/save/reload passes in Chromium,Firefox,WebKit and mobile Chromium; mobile uses a native touchscreen tap. An initial full-stack test incorrectly expected drawing to auto-open Inspector; selecting the new annotation through its actual list corrects that setup assumption. No product change was inferred from it. Build/TypeScript and changed-file ESLint pass. Security baseline,dependency582-record and software612-component validators pass; strict license admission remains BLOCKED. Source aliases/dispositions are preserved; two new evidenced campaign findings were added.

Rebased onto merged folder source c1ab7f7; the register conflict was resolved by preserving all954 report aliases and all26 campaign findings, including both independent new findings. Original source dispositions are unchanged.

## First Linux full-suite run and bounded budget

Head5d60ce1 passed eight delivery gates, but CI37100892082's launcher killed its browser command after900seconds. The scale test was inspecting a native menu when the session closed; retained error context reports Protocol error (Runtime.callFunctionOn): Internal server error,session closed. The launcher raised subprocess.TimeoutExpired; no final fullstack.json was written. Do not count this as a proved menu defect or a completed Linux annotation qualification.

The scale scenario itself allows900seconds,while the whole normal browser suite also had a900second limit. Prior qualified28-case Linux suite took865.085seconds; this batch adds a real-backend narrow journey. Allocate a bounded1200second browser-suite envelope within the unchanged25-minute CI job. Keep every assertion,the900second scale-case limit,all1000 menu checks,the stress4200second envelope,and capacity/cleanup controls. Launcher child-ownership/timeout/cleanup regressions,Ruff,changed-file ESLint and security baseline pass. Retain at most one small progress receipt per scale page,so future termination leaves checked-menu count and elapsed time even if final reporting is interrupted. The original Linux failure is retained separately.

The corrected local Chromium scale scenario passes every1000-menu assertion,pagination,offline recovery and tab-search isolation. Durable progress records all1000 menus checked in56.436seconds. This Windows scoped pass does not replace the corrected Linux full-suite gate.

## Protected delivery update - 2026-10-03

This repair is included in production `bd69848` after all nine exact-main checks passed and protected deployment 37107676115 succeeded. See [release evidence and open checks](remaining-campaign-closure.md#protected-delivery-update---2026-10-03). Relevant signed-in repair verification remains open; earlier pending statements retain historical states.
