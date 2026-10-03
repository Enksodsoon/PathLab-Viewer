# OCI dependency advisory reconciliation

Current main 0d11f2d already fixes the reported npm advisories through PR #277. This batch retains its brace-expansion 5.0.12 and undici 8.10.2 resolution and changes only the remaining deployment-tool dependencies: PyJWT 2.15.0, urllib3 2.8.0, and setuptools 83.0.0. OCI CLI stays at 3.92.0.

The complete hashed OCI lock now has its own strict security workflow audit. A fresh installed-environment audit reports no known vulnerabilities; pip check passes and OCI CLI reports 3.92.0. Synthetic PyJWT checks cover option isolation, expiry rejection, and rejecting an RSA public key as an HMAC secret.

Dependency receipts bind to implementation commit 3598ea7359bdbe57c57c9e59f945d233aa12145a. Regenerated software inventories retain unresolved license admission decisions; security audit success does not establish license admission. Fresh protected CI and production deployment remain required.
