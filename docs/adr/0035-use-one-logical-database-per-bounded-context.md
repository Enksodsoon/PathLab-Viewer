# Use one logical database per bounded context

Each bounded context will own a separate logical database inside the single Zero-Cash PostgreSQL cluster. Every database has distinct owner, runtime, migration, and read-only diagnostic roles plus an independent migration history; PgBouncer multiplexes transaction-scoped connections across them, and cross-database access extensions, shared roles, foreign data wrappers, and application-level joins are prohibited so the boundary remains relocatable in a funded profile.
