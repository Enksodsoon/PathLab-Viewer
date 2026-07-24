# Security Policy

PathLab Viewer processes private pathology images and administrator credentials. Security reports should be handled privately and must not contain patient information, credentials, recovery codes, private slide links, source images, database files, or infrastructure secrets.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability or data-exposure incident.

Use GitHub's private vulnerability reporting feature when it is available for this repository. Otherwise, contact the repository owner privately through an established organizational channel and include only the minimum information required to reproduce the issue safely.

A useful report contains:

- the affected component and route or file;
- the security impact;
- reproducible steps using synthetic or non-sensitive data;
- the expected and observed behavior;
- relevant version or commit information;
- a proposed mitigation, when known.

Do not test against systems or data you are not authorized to access. Do not retain or redistribute any private data encountered during investigation.

## Automated safeguards

Pull requests run current-tree disclosure checks, Python and JavaScript dependency audits,
and CodeQL analysis. Production configuration refuses placeholder secrets or insecure cookies.
Publication requires an explicit deidentification confirmation, and public responses expose
only the technical image fields needed by the viewer.

## Security boundaries

Reports involving these boundaries are especially important:

- exposure of original OME-TIFF files, temporary uploads, private derivatives, or databases;
- authentication, session, CSRF, throttling, or password-recovery bypass;
- path traversal or publication of unexpected derivative files;
- upload validation, decompression, or resource-exhaustion weaknesses;
- disclosure of credentials, recovery codes, application secrets, or audit-sensitive values;
- unauthorized modification, publication, unpublication, or deletion of slides;
- public access to administrative routes or private preview content.

## Supported code

Security fixes target the current default branch and the actively deployed release. Historical commits, forks, and modified deployments may require separate assessment.

## Disclosure and remediation

Please allow reasonable time to investigate, reproduce, fix, and deploy the issue before public disclosure. Security changes should include regression coverage and a review of related privacy, storage, logging, and deployment boundaries.
