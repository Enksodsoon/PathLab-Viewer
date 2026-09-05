# Platform Governance

This context defines PathLab-wide product claims and the boundaries between freely licensed software, zero-cash operation, and funded scalability.

## Language

**Free Software Guarantee**:
The permanent guarantee that PathLab-authored production code and documentation are released under Apache-2.0 and that every mandatory software path has a compatible OSI-approved license with no license or seat fee.
_Avoid_: Completely free, free forever

**Dependency Admission**:
The fail-closed review proving a component's exact source, version, license text, obligations, maintenance status, provenance, and compatibility with the Apache-2.0 PathLab release.
_Avoid_: Package install, open-source dependency

**Release Bill of Materials**:
The versioned CycloneDX and SPDX inventories, notices, source offers, asset rights, and build provenance tied to one release artifact.
_Avoid_: Dependency list, lockfile

**Offline Release Kit**:
A signed, immutable, clean-runner output containing native ARM64 application bundles, pinned infrastructure and recovery tools, provider mirror, database migrations, manifests, SBOMs, notices, checksums, tests, and install/restore runbooks.
_Avoid_: Build artifact, release archive

**Portable Institution Package**:
A versioned, signed, Institution-encrypted, context-neutral export of governed records and authoritative objects designed for validated import across supported PathLab releases.
_Avoid_: Tenant backup, database export

**Authoritative Build Runner**:
An Institution-owned or donated non-production machine that can execute the complete release pipeline without a hosted CI, registry, package mirror, model hub, or network service.
_Avoid_: Self-hosted runner, developer laptop

**Asset Rights Ledger**:
The release-blocking inventory recording each shipped image, icon, font, audio/video object, design source, creator, provenance, license, attribution, content hash, and permitted uses.
_Avoid_: Asset folder, credits page

**Independent PathLab Identity**:
A visual and verbal design system created for PathLab without copying or implying affiliation with an unrelated organization's protected marks or trade dress.
_Avoid_: Brand inspiration, familiar style

**Zero-Cash Production Profile**:
A bounded production deployment whose incremental external cash spend is verified as zero for a stated evidence period. It does not promise high availability, unlimited scale, or permanent third-party free eligibility.
_Avoid_: Free-tier production, cost-free production

**Funded Scalable Profile**:
A production deployment that preserves the Free Software Guarantee while the operator supplies the infrastructure required for higher capacity, availability, or durability.
_Avoid_: Paid edition, enterprise-only edition

**Qualification Claim**:
A capability statement tied to one release, deployment profile, workload, environment, and completed evidence set.
_Avoid_: Supported, production-ready

**Zero-Cash Launch Gate**:
The complete evidence boundary that the Zero-Cash Production Profile must pass before activation, including the full 3,000-participant combined Live Learning and Teacher Broadcast Class Session campaign and the separate 300-learner, 100-item, 120-minute Assessment campaign.
_Avoid_: Capacity target, headroom test

**Breakpoint Stage**:
A deliberately non-certifying overload experiment used to locate a system limit above the Zero-Cash Launch Gate.
_Avoid_: Capacity certification, supported capacity

**Data-Protection Objective**:
The maximum accepted loss of acknowledged authoritative data for a deployment profile. For Zero-Cash Production it is five minutes; it is not an availability or restoration-time promise.
_Avoid_: Uptime guarantee, recovery guarantee

**Best-Effort Restoration**:
Recovery whose completion time depends on suitable replacement compute becoming available. It carries no fixed RTO or availability percentage.
_Avoid_: Automatic failover, high availability

**Full-Surface Launch**:
A launch boundary in which every planned PathLab context is production-qualified and deployable within the Zero-Cash Production Profile. Whether contexts may execute concurrently is a separate operating-mode decision.
_Avoid_: Core launch, extension roadmap

**Exclusive Operating Mode**:
A production state that reserves the bounded host for one heavy workload while other heavy workloads stop admitting work, checkpoint or queue safely, and consume no active worker resources.
_Avoid_: Disabled feature, separate edition

**Media Capacity Claim**:
A production qualification for one Teacher Broadcast to 3,000 simultaneous receive-only viewers for 60 minutes, measured separately and then together with the same 3,000-learner synchronized Class Session under ADR 0132. Slides/text fallback proves recovery only, not successful combined media qualification. Exhaustion degrades additional or affected participants to slides and text without invalidating durable Live Learning state.
_Avoid_: Classroom capacity, participant capacity

**Connection Envelope**:
The hard PostgreSQL backend allocation that bounds application, mode-specific, operational, and emergency access on a named deployment profile.
_Avoid_: Pool size, maximum clients

**Resident Control Plane**:
The continuously running Zero-Cash processes limited to delivery, authoritative persistence and pooling, durable event transport, and compact control APIs.
_Avoid_: Core edition, always-on services

**Mode Process**:
An installed and production-qualified service that starts only within its granted Exclusive Operating Mode and returns to zero active processes after draining.
_Avoid_: Optional feature, disabled service

**Mode Reservation**:
A durable, institution-authorized time window granting one heavy workload the host's protected resource envelope and recording its priority, lifecycle, and outcome.
_Avoid_: Schedule entry, feature flag

**Safety Shutdown**:
The only automatic interruption permitted for an active learner-facing Mode Reservation, triggered by a condition where continuing risks data integrity, confidentiality, or host stability.
_Avoid_: Preemption, restart

**Mode Readiness Receipt**:
An immutable READY or NO-GO decision produced before a Mode Reservation begins, identifying the exact release, dependencies, resource state, synthetic checks, and unresolved failures.
_Avoid_: Healthy status, green dashboard

**Host Resource Partition**:
The cgroup-enforced division of a declared host among the operating system and page cache, Resident Control Plane, active Mode Processes, and untouchable emergency headroom.
_Avoid_: Container limits, expected usage

**Supported Client Matrix**:
The release-specific set of browser families, major-version window, operating systems, physical device classes, input methods, and assistive technologies that must pass end-to-end qualification.
_Avoid_: Modern browser, responsive support

**Accessibility Gate**:
The manual and automated WCAG 2.2 AA evidence required for every production workflow, including keyboard, screen-reader, reflow, contrast, focus, and reduced-motion behavior.
_Avoid_: Accessibility scan, a11y-friendly

**Deployment Network Identity**:
The Institution-supplied stable public or internal DNS name, certificate authority path, renewal contract, and recovery state for one deployment.
_Avoid_: Domain, public URL

**Resource Pressure State**:
The measured NORMAL, THROTTLED, SHEDDING, or SAFETY_STOP state of one Host Resource Partition, with deterministic admission and degradation behavior.
_Avoid_: High load, overloaded

**Zero-Cash Evidence Window**:
The initial 90-day and subsequent rolling 12-month accounting period proving that a named deployment incurred no PathLab-specific incremental cash charge while disclosing contributed resources and labor.
_Avoid_: Free forever, no-cost claim

**Institution Home Cell**:
The single deployment cell that owns authoritative writes for one Institution within a deployment profile.
_Avoid_: Primary region, tenant shard

**Feature Completion Contract**:
The product-wide rule requiring a capability's complete authority, user, governance, operations, recovery, and qualification paths before it may be called complete.
_Avoid_: Done, feature implemented

**Golden Institution Journey**:
The exact-release end-to-end campaign that crosses every ratified context in authority order while injecting representative faults and finishing with deletion and cold recovery.
_Avoid_: End-to-end test, happy path

**Activation Receipt**:
The separately authorized record naming the exact qualified release, deployment profile, host, evidence heads, approved claims, review date, and rollback target activated for production.
_Avoid_: Deployment success, release complete
