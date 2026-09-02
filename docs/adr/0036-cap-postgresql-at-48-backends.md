# Cap PostgreSQL at 48 backends

Zero-Cash PostgreSQL will set `max_connections=48` and reserve four emergency connections. PgBouncer transaction pooling imposes a global 32-server application cap with zero minimum pools, an active Exclusive Operating Mode may consume at most 12 of those slots, and the remaining non-emergency capacity is budgeted for migrations, monitoring, backups, and WAL operations; every service must apply bounded queues, deadlines, and admission backpressure instead of opening connections beyond the Connection Envelope.
