# Partition Edge and Platform authority by domain

Edge Federation will use explicit domain-partitioned authority rather than last-write-wins multi-master replication. An Edge Node owns bounded local acquisition and cache state, while the Platform remains canonical for identity, Learning Catalog, policy, publication, Assessment and grading, and shared metadata; signed, sequenced, checkpointed Sync Batches are idempotently accepted through owner-issued receipts, and irreconcilable proposals become Conflict Records instead of silent overwrites.
