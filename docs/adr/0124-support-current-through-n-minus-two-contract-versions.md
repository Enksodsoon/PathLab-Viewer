# Support current through N-minus-two contract versions

Every bounded context will publish versioned HTTP and event schemas, write authoritative changes through its own outbox, and consume other contexts through local projections rather than shared tables or cross-context foreign keys. The current and two preceding event and Portable Institution Package versions remain readable through explicit upcasters; schema changes are additive inside that window and never introduce dual-write authority.
