# Build signed Offline Release Kits on an owned runner

An Authoritative Build Runner will execute the full clean-checkout lint, type, unit, integration, browser, security, license, SBOM, native-ARM64, packaging, and offline-install pipeline and emit a signed Offline Release Kit plus evidence manifest. GitHub Actions may duplicate checks but cannot authorize release or be required for build, deploy, restore, or activation; production hosts never compile artifacts, and missing hosted connectivity must not change the resulting release inputs or gates.
