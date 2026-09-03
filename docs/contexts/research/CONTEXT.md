# Research

This context owns governed investigations, immutable inputs, reproducible execution descriptions, and the evidence produced by Research compute.

## Language

**Research Project**:
A governed investigation with named purpose, participants, data permissions, quotas, and retention.
_Avoid_: Workspace, study

**Dataset Snapshot**:
An immutable, versioned selection of authorized assets and metadata used by a Research Project.
_Avoid_: Dataset, mounted folder

**Environment Manifest**:
The signed, offline-approved software, dependency, configuration, and execution identity required to reproduce a Research Job.
_Avoid_: Container, requirements file

**Research Job**:
One quota-bound execution against a Dataset Snapshot under an Environment Manifest.
_Avoid_: Notebook session, task

**Research Quota**:
The hard grant for one Research Job: one OCPU, four GB memory, 20 GB ephemeral workspace, four wall-clock hours, and 15 idle minutes.
_Avoid_: Resource request, notebook size

**Research Artifact**:
An immutable output whose hashes, producing Research Job, inputs, and review status are recorded.
_Avoid_: Result file, model

**Artifact Admission**:
The owning context's explicit review and acceptance of a private Research Artifact for a separately governed purpose.
_Avoid_: Publish result, model activation, copy output

**Research Launch Gate**:
The exact-host four-hour, 20-GB reference campaign proving quota enforcement, checkpoint and resume, isolation, deterministic reproduction, signed artifact import, cleanup, and control-plane independence.
_Avoid_: Notebook test, research capacity

## Retention ceilings

- Research Project authorization must be reviewed and renewed no later than annually.
- Failed-job scratch data expires no later than seven days after job termination.
- Batch checkpoints and temporary workspace state expire no later than 30 days after Research Project closure.
- Workspace copies of governed datasets expire no later than 90 days after Research Project closure.
- Approved Research Artifacts, Environment Manifests, Dataset Snapshot manifests, and provenance expire no later than seven years after Research Project closure.
- Access and Research Job operational logs expire no later than one year after collection.
