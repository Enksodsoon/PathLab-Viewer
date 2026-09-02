# Limit each Shadow case to six profiled FHIR resource types

Each accepted Shadow Case Bundle will be a FHIR R4 collection containing only a pseudonymous Patient, Specimen, ImagingStudy, DiagnosticReport, Observation, and PathLab-generated same-origin Endpoint. Exact PathLab profiles, closed reference resolution, and equality with deidentified DICOM UIDs are mandatory; demographics, narratives, attachments, arbitrary free text or extensions, external references, source identifiers, contained resources, and provenance that expands the identity surface are rejected.
