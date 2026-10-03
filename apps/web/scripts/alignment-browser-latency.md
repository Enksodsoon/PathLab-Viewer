The browser latency harness applies generated coordinate maps to actual OpenSeadragon viewers. It does not start the API or an inference worker, and does not change production code or campaign receipts. Run it only after the engine campaign pauses or completes, on the declared campaign host.

It requires a completed campaign `report.json`, its `cache/*.json` receipts, and the same frozen input manifest. It checks the campaign row against each receipt, then rehashes the registered source files and geometry with the benchmark's input-digest convention. Missing/unaccepted maps, source mismatch, unsupported browser sources, invalid geometry, blank canvases, and failed rendering retain null latency. The command exits nonzero if any selected map cannot be measured. A campaign with no accepted maps produces all-null rows and launches no browser.

For each recipe, the sampling policy selects the smallest and largest accepted supported-cell count, breaking ties by registration digest. This selects map complexity, not anatomical quality. It samples 12 evenly spaced supported-cell centroids by default, including the first measured frame. At most 32 maps are selected; samples are bounded between 8 and 32. Browser source inputs are bounded thumbnails: at most 256 registered files / 64 MiB per source and a browser-readable original image at most 16 MiB. Streaming traversal enforces these ceilings as it walks, plus 512 visited entries, 64 directories, and depth 8; symbolic roots/entries are rejected. A larger WSI needs a separately reviewed serving fixture and receives no timing here.

Recorded clocks are `performance.now()` in one browser page. `mapLookupMs` uses the current production `mapStackPoint` implementation. `viewportSetterMs` measures actual OpenSeadragon image-coordinate pan, zoom and rotation calls matching the viewer handle. `viewportToDrawnFrameMs` ends at OpenSeadragon's `update-viewport` event after `world.draw`. `mapToDrawnFrameMs` includes lookup and target application; its observed p95 divided by 1000 is `browserLatencySeconds`. Every sample verifies center, scale, rotation and nonuniform original canvas pixels. A screenshot binds the rendered output.

This isolated scope excludes React and input dispatch, map transfer, initial source loading, API queue, preparation and engine compute. It does not establish full foreground latency, anatomical accuracy, qualification, winners, or warm-worker performance. Those values remain null when unmeasured. Source-code hashes, runtime/browser/host metadata, registration/settings/input digests, original image digests, and map complexity accompany each measurement. No campaign accuracy results are replaced.

Example PowerShell invocation after the campaign pauses, from `apps/web`:

```powershell
& 'C:\Program Files\nodejs\node.exe' scripts/measure-alignment-browser-latency.mjs `
  --manifest 'C:\private\frozen-manifest.json' `
  --campaign-dir 'C:\private\completed-campaign' `
  --expected-host $env:COMPUTERNAME `
  --browser chromium `
  --output 'C:\private\browser-evidence\chromium.json'
```

Repeat separately for `firefox`, `webkit` and `mobile-chromium` on the same host. Keep output outside the repository. Conformance tests use `node --test scripts/alignment-browser-latency-inputs.test.mjs`; their synthetic map shapes check admission and sampling only and are not measured scientific evidence.
