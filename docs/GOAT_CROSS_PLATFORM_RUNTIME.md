# GOAT OS Universal Client Runtime

GOAT OS is designed around one authoritative server-side domain model
with multiple secure client surfaces.

Supported target platforms:

- iPhone / iOS
- iPad and iPad Pro / iPadOS
- Android phones
- Android tablets
- macOS
- Windows
- standards-compliant web browsers

The platform clients are not authoritative data stores.

The server remains authoritative for:

- finance
- security administration
- bid approvals
- procurement awards
- ledger mutations
- privileged configuration
- identity and access policy
- high-risk operational decisions

## Offline-first design

Approved low-risk operational records may be queued offline.

Each mutation carries:

- tenant identity
- user identity
- device identity
- aggregate identity
- base version
- command
- idempotency key
- immutable payload digest
- classification
- timestamp

Restricted and financial mutations are never persisted into the normal
offline mutation queue.

Conflicts are handled deterministically:

1. server authoritative
2. client authoritative only for permitted classifications
3. merge disjoint fields
4. manual review when fields overlap or data is high risk

## Device trust

Device trust considers:

- revocation
- jailbreak/root
- device attestation
- managed-device status
- emulation/virtualization
- public network signals
- anonymizer signals
- impossible-travel anomalies

No single network signal is treated as proof of malicious behavior.

High-risk operations require stronger authentication and trusted-device
posture.

## Authentication

GOAT supports policy levels:

- password
- MFA
- passkey
- step-up authentication

Financial writes, security administration, and estimate approval require
stronger policy than routine CRM and field operations.

## Data protection

Data is classified:

- public
- internal
- confidential
- restricted
- financial

Offline persistence policy becomes progressively stricter with
classification.

Financial data is not approved for normal persistent offline caching.

Restricted data is memory-only by default.

## API security

The client/server boundary includes:

- explicit API versions
- request IDs
- tenant/user/device identity
- payload digests
- short-lived replay nonces
- timestamp skew validation
- idempotency identifiers
- device revocation checks

Future production persistence must back replay state and idempotency with
durable shared infrastructure rather than process-local memory.

## Privacy-safe notifications

Lock-screen content is minimized by classification.

Financial and restricted content is not displayed directly in push
notification previews.

## Client architecture

Native/mobile/web clients should share:

- API schemas
- domain identifiers
- capability names
- data classifications
- feature flags
- sync protocol
- error codes
- telemetry schema
- authentication policy

Platform-specific implementations should be limited to device capabilities
such as camera, biometric authentication, passkeys, secure storage, push
notifications, file handling, background execution, and stylus support.

## Production work still required

This runtime is the domain/security contract.

Shipping applications still require:

- production API service
- durable persistence
- client UI applications
- encrypted platform storage
- passkey provider integration
- push provider integration
- application signing
- CI/CD
- App Store distribution
- Google Play distribution
- Windows packaging
- macOS distribution
- web deployment
- crash reporting
- observability
- remote configuration
- device-management integration where required
