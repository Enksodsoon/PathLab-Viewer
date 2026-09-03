# Clinical Shadow

This context owns read-only clinical copies used for authorized non-diagnostic purposes and prevents those copies or their derivatives from affecting patient care.

## Language

**Clinical Shadow Record**:
A minimized, read-only copy of clinical source information retained for an authorized non-diagnostic purpose.
_Avoid_: Patient record, EHR copy

**Purpose Grant**:
The institution-approved purpose, audience, data classes, and time boundary under which Clinical Shadow data may be used.
_Avoid_: Consent flag, access role

**Source Provenance**:
The verifiable source identity, version, retrieval facts, and integrity evidence associated with a Clinical Shadow Record.
_Avoid_: Import metadata, audit log

**Deidentified Snapshot**:
An immutable, reviewed derivative approved to cross from Clinical Shadow into Learning Catalog, Research, or Imaging Control for one named purpose. EQA may consume only a separately authorized Learning Catalog or Imaging Control version and never receives direct Clinical Shadow authority.
_Avoid_: Anonymized copy, teaching export

**Clinical Writeback**:
Any change, result, annotation, order, report, or recommendation sent toward a patient-care source system.
_Avoid_: Sync, export

**FHIR R4 Shadow Exchange**:
A strictly profiled FHIR R4 4.0.1 JSON read operation used to create or verify a local Clinical Shadow Record without writeback or version conversion.
_Avoid_: FHIR integration, clinical API

**FHIR Shadow Profile Package**:
The immutable, versioned set of profiles, bindings, search limits, examples, and rejection meanings that defines exactly which FHIR R4 content may enter Clinical Shadow.
_Avoid_: FHIR schema, validation settings

**Shadow Case Bundle**:
A FHIR R4 collection containing only a pseudonymous Patient, Specimen, ImagingStudy, DiagnosticReport, Observation, and PathLab-generated same-origin Endpoint under exact PathLab profiles and closed references.
_Avoid_: Patient bundle, FHIR document

**DICOMweb Shadow Exchange**:
A DICOM 2026c read-only QIDO-RS and WADO-RS exchange that declares Retrieve Capabilities and implements every mandatory PS3.18 read resource while admitting only Whole Slide Microscopy images and Microscopy Bulk Simple Annotations.
_Avoid_: PACS integration, DICOM gateway

**Source-Time Removal Policy**:
The rule that eliminates original clinical temporal values and relationships while using only standards-valid nonidentifying replacements where a required field cannot be absent.
_Avoid_: Date shifting, timestamp scrubbing

**Deidentification Admission Receipt**:
A human-signed, reproducible record proving that one exact case passed the frozen DICOM confidentiality policy, metadata and image inspection, UID consistency checks, and its Purpose Grant before leaving quarantine.
_Avoid_: Deidentified flag, scrubbed status

## Retention ceilings

- A Purpose Grant expires no later than one year after issuance unless explicitly reviewed and renewed.
- Rejected or quarantined inbound data is destroyed within 24 hours and is never included in a backup.
- A Clinical Shadow Record is deleted within 30 days after its Purpose Grant expires.
- A Deidentified Snapshot follows its authorized destination context and may not exceed seven years.
- Access evidence and Deletion Receipts expire no later than seven years after their recorded event.
