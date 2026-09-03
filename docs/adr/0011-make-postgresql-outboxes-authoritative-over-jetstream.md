# Make PostgreSQL outboxes authoritative over JetStream

Every authoritative domain transaction will commit its state and an outbox record atomically in PostgreSQL; JetStream delivers jobs and domain events but can be rebuilt from those outboxes after loss. Consumers use inbox deduplication, idempotency keys, and unique business constraints for exactly-once effects, while the Zero-Cash profile uses one JetStream replica and funded profiles use three without changing event contracts.
