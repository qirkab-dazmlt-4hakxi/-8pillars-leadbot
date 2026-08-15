# GOAT Application Server and Realtime Transport

This layer converts GOAT's internal business and intelligence systems into
an actual server contract that native and web clients can use.

## ASGI

GOAT includes a dependency-free ASGI 3 application adapter.

The business runtime itself does not depend on FastAPI, Flask, Django or
another application framework.

It may be hosted by any standards-compliant ASGI server.

A development runner optionally uses Uvicorn when installed.

## HTTP security

Protected HTTP calls reuse GOAT Secure Application Gateway controls:

- signed server sessions
- tenant isolation
- device binding
- device-trust evaluation
- authentication-strength gates
- replay protection
- endpoint RBAC
- rate limiting
- idempotency controls
- tamper-evident gateway audit

## Health and readiness

The service exposes:

- GET /healthz
- GET /readyz

These are intentionally separate from authenticated business endpoints.

## Session endpoint

GET /v1/session/me returns the authenticated GOAT identity context.

It allows a native client to verify:

- user
- tenant
- role
- device binding
- authentication strength
- current device-trust score

## Cross-platform sync endpoint

GET /v1/sync exposes the existing GOAT append-only server change feed.

Supported client targets include:

- iPhone
- iPad / iPad Pro
- Android
- macOS
- Windows
- web

Clients retain a durable sequence cursor.

Project filtering occurs server-side.

## GOAT realtime voice protocol

Realtime voice uses:

- WebSocket transport
- signed GOAT session
- tenant validation
- device binding
- device-trust verification
- ordered client sequence numbers
- server sequence numbers
- explicit turn IDs
- heartbeat
- interruption
- barge-in
- text input
- binary audio input
- audio acknowledgments
- transcript events
- assistant text events
- assistant audio metadata events
- explicit turn completion
- explicit session close

## Binary audio protocol

Client audio frames use:

- first 8 bytes: unsigned big-endian sequence number
- remaining bytes: encoded audio payload

This avoids Base64 overhead for continuous audio.

The audio encoding is negotiated in the WebSocket handshake.

## Voice state machine

A session transitions through controlled states:

CONNECTING
→ READY
→ LISTENING
→ THINKING
→ SPEAKING
→ READY

Interruption may move THINKING or SPEAKING to INTERRUPTED.

Incoming user audio while GOAT is speaking triggers barge-in behavior.

## GOAT-owned intelligence boundary

The transport and session architecture belongs to GOAT.

Foundation models and speech engines remain replaceable providers behind
the GOAT Intelligence Fabric.

A future provider bridge can attach:

audio
→ transcription
→ GOAT reasoning/router
→ tools
→ organizational memory
→ response generation
→ speech synthesis

without giving the external inference provider authority over:

- tenant isolation
- permissions
- finance
- company data ownership
- tool authorization
- audit policy
- memory policy
- project state
- payment authority

## Observability

The runtime records:

- request count
- HTTP status counts
- request latency
- active voice sessions
- opened/closed voice sessions
- received audio frames
- received audio bytes
- text turns
- interruptions
- completed turns

The in-process registry is an abstraction point.

Production deployment can export these metrics to OpenTelemetry,
Prometheus or another telemetry platform.

## Secrets

The development runner requires GOAT_SESSION_SECRET from server-side
environment configuration.

No session signing secret belongs in:

- iPhone application bundle
- Android application bundle
- JavaScript
- Windows application
- macOS application
- repository source code

Production deployment should load it from a proper secret manager or
KMS-backed mechanism.

## Next architecture layer

The next major build should connect this transport to:

1. GOAT Intelligence Fabric and provider-independent streaming inference.
2. Persistent PostgreSQL repositories for newer GOAT domains.
3. Durable distributed replay/session/rate state.
4. Encrypted object storage.
5. APNs / FCM mobile push.
6. Native-client bootstrap and device registration.
7. WebAuthn/passkey registration and assertion verification.
8. production deployment and observability.
