# Adaptive viewer and 300-user capacity contract

## Outcome

The viewer is designed to remain useful on a 2 OCPU, 12 GB OCI host while up to
300 viewers are active. This is a capacity target, not a production
certification: release evidence must come from the `capacity300` profile on the
actual host while an authorized conversion and administrator workflow run.

No viewer can fetch unseen image data during a complete network outage. PathLab
therefore optimizes the experience in this order:

1. Show the existing sanitized 384 px thumbnail immediately.
2. Keep already rendered tiles on screen during a dropout.
3. Limit outstanding requests to match the observed connection.
4. Prefer a responsive lower-resolution view over a stalled high-resolution
   view.
5. Resume ordinary OpenSeadragon loading when connectivity returns.

The DZI format, tile size, JPEG quality, publication boundary, authorization
rules, and private 24-hour immutable browser cache are unchanged.

## Browser loading policy

Every individual and shared viewer offers three modes. The choice is stored
locally in the browser and contains no slide or user information.

| Mode | Concurrent tile requests |
| --- | --- |
| Auto | 2, 4, 8, or 12 on desktop; at most 8 on a narrow screen |
| Data saver | 2 |
| Full detail | 12 on desktop; 8 on a narrow screen |

Auto starts from the browser's data-saver and effective-connection hints, when
available. It then evaluates uncached tile resource timings and tile failures
in five-second windows after at least 12 samples:

| Window | Target |
| --- | --- |
| Offline, failure rate over 5%, or p75 over 2 s | 2 |
| Failure rate over 1%, or p75 over 1 s | 4 |
| p75 over 400 ms | 8 |
| Otherwise | 12 desktop / 8 narrow |

Concurrency decreases immediately. It increases only after two consecutive
healthy windows. Cached resources are excluded from latency sampling. A
dropout does not destroy or recreate the OpenSeadragon instance, so visible
tiles remain available.

## Resource isolation

The browser performs all adaptation; it adds no server-side image processing,
cache daemon, service worker, persistent offline store, or dynamic tiler.
OpenSeadragon remains a lazy viewer chunk, and the administrator application is
a separate lazy chunk. Caddy continues to serve versioned derivatives without
using the Python API process for the response body.

Existing runtime limits protect the control plane: one API worker, one serial
libvips conversion worker with `VIPS_CONCURRENCY=1`, and explicit container CPU
and memory limits. Do not raise worker concurrency or the conversion CPU limit
to chase viewer latency. Change server limits only from a baseline/candidate
measurement that demonstrates the bottleneck and preserves the gates below.

## Release evidence

The preferred production procedure is the manually approved **Capacity
certification** GitHub Actions workflow. It is serialized with production
deployments, accepts only the exact current `main` commit after CI and security
checks succeed, and runs from a GitHub-hosted runner rather than the OCI host.
It requires the literal confirmation `CERTIFY_PRODUCTION_300` and approval of
the protected `production` environment.

The protected environment supplies:

- variable `PRODUCTION_BASE_URL`;
- secrets `LOAD_TEST_PUBLIC_ID` and `LOAD_TEST_ADMIN_SLIDE_ID`, selecting the
  explicitly approved teaching slide;
- secrets `LOAD_TEST_ADMIN_USERNAME` and `LOAD_TEST_ADMIN_PASSWORD`;
- the existing OCI Bastion variables and credentials used by deployment.

The runner fetches only the approved public metadata and DZI descriptor. It
derives a bounded deterministic manifest for the highest three levels without
reading production storage. The manifest, raw observations, k6 stream, browser
log, credentials, IDs, and synthetic source stay in a temporary directory and
are removed on exit. Artifacts contain only aggregate Markdown and JSON.

For a non-production authorized host, a manifest can still be generated
explicitly and passed to the standalone profile:

```bash
BASE_URL="https://authorized-test-host.example" \
MANIFEST_PATH=/absolute/path/to/viewer-load-manifest.json \
deploy/scripts/run-viewer-load-test.sh capacity300
```

The profile ramps to 300 viewers over two minutes, holds all 300 for ten
minutes, and ramps down for one minute. Each virtual viewer loads metadata,
poster, and DZI once, then requests a 70/30 mix of shared-cache and random tiles
in browser-like parallel batches.

During the ten-minute hold:

- start one representative authorized conversion;
- sign in as an administrator, search, edit safe metadata, and observe upload
  and conversion status;
- record host and container CPU, memory, swap, disk I/O, network, and OOM
  state;
- run one real browser on an ordinary connection and one shaped to 256 Kbit/s,
  1 s RTT, and 5% loss;
- interrupt the shaped browser's network for 30 seconds and confirm the poster
  or loaded canvas remains visible, the offline status appears, and navigation
  continues after reconnection.

The workflow creates an uncompressed synthetic, non-PHI OME-TIFF of
approximately 330 MB. It uploads the file through the real administrator UI,
waits for conversion to reach `ready_private`, never publishes it, and schedules
its deletion in cleanup. The approved teaching slide is changed only by
temporarily appending a run marker to its private administrator note; cleanup
restores the exact original value. A failed cleanup fails certification.

The host observer is a forced-command operation limited to
`observe-load <seconds>`, with a multiple-of-ten duration from 10 through 900.
It reports path-free aggregate samples every ten seconds. It cannot run
arbitrary commands or read application content.

The run aborts immediately when any of these safety boundaries is reached:

- readiness fails twice consecutively;
- request failures reach 1% after the 30-second warm-up;
- CPU is at least 90% for 30 seconds or at least 85% for 60 seconds;
- memory is at least 90% for 30 seconds;
- swap grows, an OOM kill occurs, a container restarts, or the exact four
  services are not running;
- free disk space falls below 10%.

Pass only when:

- tile, metadata, poster, and DZI failure rates are below 0.1%;
- tile p95 is below 500 ms and poster p95 below 1.5 s on the unshaped load
  generator;
- host CPU remains below 80% sustained, memory below 85%, swap does not grow,
  and no container is OOM-terminated;
- the administrator workflow remains responsive and the conversion completes;
- the shaped-browser behavior above is observed without claiming that unseen
  tiles load during the 30-second outage.

The k6 profile does not create production authorization, alter shares, upload
slides, or run automatically during deployment or CI.

The standalone k6 profile does not perform those mutations. The protected
certification workflow does perform only the reversible administrator and
temporary synthetic-upload operations described above after environment
approval.
