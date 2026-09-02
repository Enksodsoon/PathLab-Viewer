# Use a filesystem object adapter in zero-cash production

Zero-Cash Production will store content-addressed immutable assets and signed manifests on its reviewed data volume through a portable object-store interface, allowing Caddy to serve authorized bytes directly. Funded profiles may replace the filesystem adapter with S3-compatible storage without changing domain contracts; a resident single-node object-storage cluster adds overhead without removing the host failure boundary and is therefore not required.
