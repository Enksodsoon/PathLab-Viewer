# Limit zero-cash Clinical Shadow to deidentified data

Zero-Cash Production will implement and qualify read-only FHIR and DICOM Clinical Shadow workflows only for synthetic or institution-verified deidentified data. Identifiable patient data is rejected by this profile and requires a separately isolated funded deployment; no profile permits Clinical Writeback or allows PathLab output to influence the official diagnostic record or patient care.
