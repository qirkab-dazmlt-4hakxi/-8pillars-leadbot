# GOAT Secure Application Gateway

This subsystem is the authoritative boundary between GOAT clients and
GOAT company services.

Supported client surfaces are intended to include:

- iPhone
- iPad / iPad Pro
- Android
- macOS
- Windows
- web

## Authentication boundary

GOAT server sessions are cryptographically signed.

The session envelope includes:

- session ID
- user ID
- tenant ID
- role
- device ID
- authentication strength
- issue time
- expiration
- audience
- nonce

The session envelope is not a replacement for WebAuthn/passkey
verification.

Production passkey assertions should be verified with a standards-compliant
WebAuthn implementation before GOAT issues its server session.

## Device trust

GOAT evaluates device/network signals including:

- known-device status
- device attestation
- jailbreak/root signal
- attestation anomalies
- impossible travel
- Tor
- VPN/proxy
- public network
- clock skew

The system does not use socioeconomic, neighborhood, demographic or other
discriminatory proxies.

High-risk actions require stronger authentication and stronger device trust.

## Tenant isolation

The request tenant must equal the authenticated session tenant.

Client portal access is additionally project scoped.

Cross-tenant and cross-project access fail closed.

## Replay defense

Mutating and authenticated traffic may include unique request nonces.

A nonce already observed inside its replay window is rejected.

## Idempotency

Sensitive writes can require an idempotency key.

Replaying the same key with the same request returns the original result.

Reusing the key with different content fails as a conflict.

This protects:

- payments
- financial adjustments
- purchase orders
- change orders
- timecard posting
- message sends
- other externally retryable mutations

## Rate limiting

GOAT uses endpoint-specific token buckets.

Production infrastructure should additionally enforce limits at the edge,
API gateway and provider boundaries.

## Secure object registration

GOAT object upload control provides:

- tenant
- project
- object visibility
- filename
- MIME type
- expected size
- expected SHA-256
- expiring one-time upload intent
- integrity verification
- quarantine on mismatch

Production object bytes should reside in encrypted durable object storage.
The database stores authoritative metadata and references.

## Client portal

Portal permissions are explicit.

Examples:

- view project
- view documents
- upload documents
- view photos
- view schedule
- view change orders
- approve permitted change orders
- view invoices
- project messaging

A client only sees specifically granted projects.

## Notification outbox

GOAT notification delivery is asynchronous.

Channels include:

- in-app
- push
- email
- SMS

The outbox supports:

- deduplication
- claiming
- retry
- exponential delay
- dead-letter state

SMS/email/push providers remain replaceable delivery adapters.

## Cross-platform synchronization

GOAT maintains an append-only server change feed.

Every change has:

- sequence
- tenant
- project
- entity type
- entity ID
- operation
- payload
- payload hash
- timestamp

Clients retain cursors.

Project filtering occurs server-side.

This supports reconnect and incremental synchronization without requiring
clients to redownload the entire tenant database.

## Audit integrity

Gateway authorization and execution produce chained audit records.

Audit events retain:

- sequence
- event identity
- tenant
- user
- timestamp
- payload hash
- previous hash
- event hash

Tampering is detectable.

## Production hardening still required

Before public production release, the gateway should be connected to:

- standards-compliant WebAuthn/passkey verification
- durable PostgreSQL or equivalent persistence
- Redis or durable distributed replay/rate state
- encrypted cloud/private object storage
- production TLS termination
- WAF/DDoS protections
- certificate rotation
- secret manager / HSM or KMS
- APNs
- Firebase Cloud Messaging
- email delivery provider
- lawful SMS provider
- centralized observability
- distributed tracing
- backups and restore testing

The architecture is intentionally provider-independent.
