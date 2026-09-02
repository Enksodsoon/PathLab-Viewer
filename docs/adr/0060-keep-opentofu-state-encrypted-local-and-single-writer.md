# Keep OpenTofu state encrypted, local, and single-writer

OpenTofu will use its encrypted local backend under one durable operator lease, with AES-GCM state and plan encryption sourced from the PathLab key hierarchy. Every successful apply advances a monotonic sequence and produces a signed manifest plus encrypted off-host state copy; concurrent leases, stale replay, sequence gaps, unexpected replacement, or missing backup acknowledgement fail closed, and no hosted state, lock, registry, or infrastructure service is required for recovery.
