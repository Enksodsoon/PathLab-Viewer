# Use one PostgreSQL cluster with context-owned namespaces

Zero-Cash Production will run one self-hosted PostgreSQL cluster behind PgBouncer while assigning every bounded context its own namespace, least-privilege owner/runtime/migration roles, migration history, tables, transactional outbox, and local projections. Cross-context foreign keys, table reads, shared write roles, and distributed transactions are prohibited; versioned outbox events and idempotent consumers form the integration boundary, allowing a funded profile to relocate a context without changing its domain contract.
