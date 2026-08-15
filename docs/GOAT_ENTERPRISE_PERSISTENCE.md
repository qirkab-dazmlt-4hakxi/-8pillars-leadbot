# GOAT Enterprise Persistence Control Plane

This subsystem establishes the durable data boundary for GOAT OS.

## Transaction model

Mutating operations run inside explicit transactions.

Failures roll back.

The reference backend uses SQLite BEGIN IMMEDIATE transactions with:

- WAL journaling
- FULL synchronous durability
- foreign keys
- busy timeout
- transactional schema migration

Production PostgreSQL can implement the same repository contract.

## Optimistic concurrency

Every entity has an integer version.

Creation starts at version 1.

Updates require the caller's expected version.

A stale version fails closed instead of silently overwriting newer data.

This prevents lost updates across:

- web
- iPhone
- iPad
- Android
- Windows
- background workers
- server replicas

## Tenant isolation

Entity keys include tenant ID.

Queries require tenant ID.

Identical object identifiers belonging to different tenants remain isolated.

## Tamper-evident event history

Every durable mutation produces an event.

Each tenant maintains an ordered SHA-256 hash chain containing:

- event identity
- aggregate
- aggregate version
- event type
- actor
- payload hash
- previous event hash
- timestamp

Modification of historical payloads or chain links is detectable.

## Durable outbox

The outbox provides transactional delivery state for integrations and workers.

It supports:

- pending
- claimed
- delivered
- failed
- dead-letter

Delivery includes:

- worker lease
- lease expiration
- retry attempts
- exponential delay
- deduplication keys
- content hashes

This pattern is intended for:

- notifications
- CRM events
- accounting events
- project events
- AI workflow events
- SMS/email/push requests
- integration webhooks

## Durable inbox

The inbox records already-consumed external messages.

The same message ID and same payload is safely ignored.

The same message ID with different content is rejected as a conflict.

This prevents duplicate external events from creating duplicate business actions.

## Durable idempotency

Externally retryable operations may persist:

- tenant
- scope
- idempotency key
- request hash
- response
- expiration

A retry with identical content returns the original result.

Reuse with different content fails closed.

## Distributed leases and fencing tokens

GOAT includes durable worker leases.

Each new lease owner receives an increasing fencing token.

A stale worker therefore cannot safely impersonate the newer lease holder.

This supports future distributed:

- schedulers
- notification workers
- accounting workers
- AI workers
- document processors
- plan-analysis workers

## Snapshots

Entity snapshots preserve:

- tenant
- entity
- entity version
- payload
- payload hash
- timestamp

Snapshots support recovery and event-stream compaction strategies.

## Backup verification

The reference backend performs online SQLite backup.

Every backup receives:

- SHA-256 checksum
- byte size
- timestamp

Restore verification uses SQLite integrity_check and optional checksum matching.

The test suite actually opens the backup as a new database and confirms stored
GOAT data survives.

## Production PostgreSQL evolution

The next deployment implementation should retain these semantics while using:

- PostgreSQL transactions
- SERIALIZABLE or suitable explicit transaction isolation where required
- SELECT FOR UPDATE / advisory locks as appropriate
- JSONB
- database constraints
- partitioned event/outbox tables where scale warrants
- connection pooling
- TLS
- encryption at rest
- managed backups
- point-in-time recovery
- read replicas only where consistency requirements allow them

GOAT domain code should depend on persistence contracts rather than vendor
specific APIs.

## Recovery requirements

Production release should include scheduled tests for:

- backup creation
- restore into isolated environment
- integrity verification
- event-chain verification
- RPO measurement
- RTO measurement
- object-store consistency
- secret restoration
- disaster failover
