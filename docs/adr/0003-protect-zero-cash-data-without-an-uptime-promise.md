# Protect zero-cash data without an uptime promise

Zero-Cash Production will continuously archive PostgreSQL WAL and authoritative outbox state to encrypted operator-owned off-host storage for an RPO of at most five minutes, but it will publish no uptime percentage or fixed RTO because replacement compute is not guaranteed. Restore remains best effort and must be proven by drills; replication is not accepted as backup, and the later Funded Scalable Profile owns high-availability and automatic-failover claims.
