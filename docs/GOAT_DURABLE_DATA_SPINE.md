# GOAT Durable Data Spine

GOAT domain services must not depend on process memory for authoritative
business state.

This persistence contract establishes the required durability invariants.

## Event store

Aggregate state changes are represented by ordered append-only events.

Every stream is scoped by tenant and stream identity.

Every event has:

- deterministic stream version
- globally unique event ID
- event type
- canonical JSON payload
- SHA-256 payload integrity digest
- actor
- optional originating device
- UTC timestamp

Optimistic concurrency rejects writes built from stale aggregate versions.

## Transactional outbox

Every event write creates its integration message inside the same database
transaction.

This prevents:

- state committed but message lost
- message published but state rolled back

Workers lease outbox records before delivery.

Delivery supports:

- worker ownership
- retries
- availability delay
- attempt counts
- dead-letter transition
- acknowledgement

Production PostgreSQL must use equivalent transactional semantics and row
locking.

## Idempotency

External mutation endpoints must accept an idempotency key.

The durable idempotency record stores:

- tenant
- operation scope
- key
- request digest
- completion state
- response

Reusing a key with a different request is rejected.

## Inbox deduplication

External event/message consumers maintain tenant-scoped message identity.

The same message may be safely delivered more than once.

A reused message ID with a different payload is treated as an integrity
conflict.

## Snapshots

Long event streams may use versioned snapshots.

Snapshots are:

- tenant-scoped
- stream-scoped
- versioned
- integrity hashed

An older snapshot cannot replace a newer one.

## Migration integrity

Database migrations are identified by immutable versions and content
checksums.

Changing a migration after it has been applied is considered migration
drift and fails closed.

Production schema changes must be introduced through new migrations.

## Backup contract

Backups must pass:

- cryptographic file checksum
- database integrity check
- event-count verification
- migration-manifest verification

Production systems additionally require:

- encrypted backups
- off-site copies
- retention policy
- automated restore tests
- point-in-time recovery
- recovery-time measurements
- recovery-point measurements

## Production PostgreSQL adapter

The PostgreSQL implementation must preserve all invariants in this module
while adding:

- connection pooling
- TLS
- secret-managed credentials
- row-level tenant policy where appropriate
- transaction isolation
- SELECT FOR UPDATE / SKIP LOCKED outbox leasing
- partitioning strategy
- PITR/WAL archival
- read replicas where justified
- monitoring
- slow-query telemetry
- index health
- migration automation
- backup/restore drills

SQLite is the current deterministic battle-test adapter, not the final
production database engine.
