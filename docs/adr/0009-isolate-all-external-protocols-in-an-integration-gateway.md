# Isolate all external protocols in an Integration Gateway

PathLab will place LMS/SIS, DICOM/FHIR, EQA federation, media, notification, and webhook adapters behind one Integration Gateway ownership boundary. The Zero-Cash Production Profile runs these adapters in one scale-to-zero process with isolated credentials and data contracts, while funded deployments may split busy adapters independently; external systems never receive direct access to a product context's database or become its canonical authority.
