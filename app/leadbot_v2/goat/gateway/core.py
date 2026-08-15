from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, IntEnum
from typing import Any, Callable

from .security import (
    AuthStrength,
    DeviceBlocked,
    DeviceSignals,
    DeviceTrustEngine,
    ReplayProtector,
    SessionClaims,
    SessionTokenService,
    StepUpRequired,
    TokenBucketRateLimiter,
    canonical_json,
    new_id,
    sha256_hex,
    utcnow,
)


class GatewayError(RuntimeError):
    pass


class AuthorizationDenied(GatewayError):
    pass


class TenantBoundaryViolation(GatewayError):
    pass


class IdempotencyRequired(GatewayError):
    pass


class IdempotencyConflict(GatewayError):
    pass


class EndpointNotFound(GatewayError):
    pass


class GatewayAuditIntegrityError(GatewayError):
    pass


class ApiRisk(IntEnum):
    READ = 10
    WRITE = 20
    HIGH_RISK = 30
    CATASTROPHIC = 40


class DataClass(IntEnum):
    PUBLIC = 10
    INTERNAL = 20
    CONFIDENTIAL = 30
    FINANCIAL = 40
    RESTRICTED = 50


@dataclass(frozen=True)
class EndpointSpec:
    name: str

    method: str
    path: str

    allowed_roles: frozenset[
        str
    ]

    data_class: DataClass

    risk: ApiRisk

    require_idempotency: bool = False

    minimum_auth: AuthStrength = (
        AuthStrength.MFA
    )

    rate_capacity: int = 60

    rate_refill_per_second: float = 1.0


@dataclass(frozen=True)
class GatewayRequest:
    method: str
    path: str

    tenant_id: str

    bearer_token: str

    device: DeviceSignals

    request_nonce: str

    idempotency_key: str | None = None

    body: dict[
        str,
        Any,
    ] | None = None


@dataclass(frozen=True)
class AuthorizationDecision:
    endpoint: EndpointSpec

    claims: SessionClaims

    device_score: int

    step_up_required: bool


@dataclass
class IdempotencyRecord:
    request_hash: str

    result: Any


class IdempotencyStore:
    def __init__(
        self,
    ) -> None:
        self._records = {}

    def lookup(
        self,
        *,
        tenant_id: str,
        endpoint_name: str,
        key: str,
        request_body: Any,
    ) -> tuple[
        bool,
        Any,
    ]:
        identity = (
            tenant_id,
            endpoint_name,
            key,
        )

        request_hash = (
            sha256_hex(
                request_body
            )
        )

        record = self._records.get(
            identity
        )

        if record is None:
            return (
                False,
                None,
            )

        if (
            record.request_hash
            != request_hash
        ):
            raise IdempotencyConflict(
                key
            )

        return (
            True,
            record.result,
        )

    def save(
        self,
        *,
        tenant_id: str,
        endpoint_name: str,
        key: str,
        request_body: Any,
        result: Any,
    ) -> None:
        identity = (
            tenant_id,
            endpoint_name,
            key,
        )

        self._records[
            identity
        ] = IdempotencyRecord(
            request_hash=(
                sha256_hex(
                    request_body
                )
            ),
            result=result,
        )


@dataclass(frozen=True)
class GatewayAuditEvent:
    sequence: int

    event_id: str

    event_type: str

    tenant_id: str
    user_id: str

    occurred_at: datetime

    payload: dict[
        str,
        Any,
    ]

    payload_hash: str

    previous_hash: str

    event_hash: str


class GatewayAuditChain:
    def __init__(
        self,
    ) -> None:
        self.events = []

    def append(
        self,
        *,
        event_type: str,
        tenant_id: str,
        user_id: str,
        payload: dict[str, Any],
    ) -> GatewayAuditEvent:
        sequence = (
            len(
                self.events
            )
            + 1
        )

        previous_hash = (
            self.events[
                -1
            ].event_hash
            if self.events
            else "0" * 64
        )

        occurred_at = utcnow()

        payload_hash = (
            sha256_hex(
                payload
            )
        )

        event_id = new_id(
            "gatewayevt"
        )

        event_hash = sha256_hex(
            {
                "sequence":
                    sequence,
                "event_id":
                    event_id,
                "event_type":
                    event_type,
                "tenant_id":
                    tenant_id,
                "user_id":
                    user_id,
                "occurred_at":
                    occurred_at,
                "payload_hash":
                    payload_hash,
                "previous_hash":
                    previous_hash,
            }
        )

        event = GatewayAuditEvent(
            sequence=sequence,
            event_id=event_id,
            event_type=event_type,
            tenant_id=tenant_id,
            user_id=user_id,
            occurred_at=occurred_at,
            payload=dict(
                payload
            ),
            payload_hash=(
                payload_hash
            ),
            previous_hash=(
                previous_hash
            ),
            event_hash=(
                event_hash
            ),
        )

        self.events.append(
            event
        )

        return event

    def verify(
        self,
    ) -> bool:
        previous = (
            "0" * 64
        )

        for sequence, event in enumerate(
            self.events,
            start=1,
        ):
            if event.sequence != sequence:
                raise (
                    GatewayAuditIntegrityError(
                        "sequence mismatch"
                    )
                )

            if event.previous_hash != previous:
                raise (
                    GatewayAuditIntegrityError(
                        "previous hash mismatch"
                    )
                )

            if (
                sha256_hex(
                    event.payload
                )
                != event.payload_hash
            ):
                raise (
                    GatewayAuditIntegrityError(
                        "payload hash mismatch"
                    )
                )

            calculated = sha256_hex(
                {
                    "sequence":
                        event.sequence,
                    "event_id":
                        event.event_id,
                    "event_type":
                        event.event_type,
                    "tenant_id":
                        event.tenant_id,
                    "user_id":
                        event.user_id,
                    "occurred_at":
                        event.occurred_at,
                    "payload_hash":
                        event.payload_hash,
                    "previous_hash":
                        event.previous_hash,
                }
            )

            if calculated != event.event_hash:
                raise (
                    GatewayAuditIntegrityError(
                        "event hash mismatch"
                    )
                )

            previous = (
                event.event_hash
            )

        return True


class SecureApplicationGateway:
    def __init__(
        self,
        *,
        sessions: SessionTokenService,
    ) -> None:
        self.sessions = (
            sessions
        )

        self.replay = (
            ReplayProtector()
        )

        self.idempotency = (
            IdempotencyStore()
        )

        self.audit = (
            GatewayAuditChain()
        )

        self._endpoints = {}

        self._rate_limiters = {}

    def register_endpoint(
        self,
        spec: EndpointSpec,
    ) -> None:
        identity = (
            spec.method.upper(),
            spec.path,
        )

        if identity in self._endpoints:
            raise GatewayError(
                "endpoint already registered"
            )

        self._endpoints[
            identity
        ] = spec

        self._rate_limiters[
            spec.name
        ] = TokenBucketRateLimiter(
            capacity=(
                spec.rate_capacity
            ),
            refill_per_second=(
                spec.rate_refill_per_second
            ),
        )

    def authorize(
        self,
        request: GatewayRequest,
    ) -> AuthorizationDecision:
        identity = (
            request.method.upper(),
            request.path,
        )

        try:
            endpoint = (
                self._endpoints[
                    identity
                ]
            )

        except KeyError as exc:
            raise EndpointNotFound(
                identity
            ) from exc

        claims = (
            self.sessions.verify(
                request.bearer_token
            )
        )

        if (
            claims.tenant_id
            != request.tenant_id
        ):
            raise (
                TenantBoundaryViolation(
                    "request tenant does not match session"
                )
            )

        if (
            claims.device_id
            != request.device.device_id
        ):
            raise AuthorizationDenied(
                "device does not match session"
            )

        role = (
            claims.role
            .lower()
        )

        if (
            role
            not in endpoint.allowed_roles
        ):
            raise AuthorizationDenied(
                "role not authorized"
            )

        if (
            claims.auth_strength
            < endpoint.minimum_auth
        ):
            raise StepUpRequired(
                "insufficient authentication strength"
            )

        assessment = (
            DeviceTrustEngine.assess(
                request.device
            )
        )

        if assessment.blocked:
            raise DeviceBlocked(
                ",".join(
                    assessment.reasons
                )
            )

        if (
            endpoint.risk
            >= ApiRisk.HIGH_RISK
            and assessment
            .require_step_up
        ):
            raise StepUpRequired(
                "high-risk action requires trusted device"
            )

        if (
            endpoint.risk
            >= ApiRisk.HIGH_RISK
            and claims.auth_strength
            < AuthStrength.PASSKEY
        ):
            raise StepUpRequired(
                "high-risk action requires passkey-strength session"
            )

        if (
            endpoint.require_idempotency
            and not request.idempotency_key
        ):
            raise IdempotencyRequired(
                endpoint.name
            )

        self.replay.require_fresh(
            tenant_id=(
                claims.tenant_id
            ),
            user_id=(
                claims.user_id
            ),
            nonce=(
                request.request_nonce
            ),
        )

        limiter = (
            self._rate_limiters[
                endpoint.name
            ]
        )

        limiter.require(
            (
                claims.tenant_id
                + ":"
                + claims.user_id
                + ":"
                + endpoint.name
            )
        )

        self.audit.append(
            event_type=(
                "gateway.authorized"
            ),
            tenant_id=(
                claims.tenant_id
            ),
            user_id=(
                claims.user_id
            ),
            payload={
                "endpoint":
                    endpoint.name,
                "device_score":
                    assessment.score,
                "risk":
                    int(
                        endpoint.risk
                    ),
            },
        )

        return (
            AuthorizationDecision(
                endpoint=endpoint,
                claims=claims,
                device_score=(
                    assessment.score
                ),
                step_up_required=(
                    assessment
                    .require_step_up
                ),
            )
        )

    def execute(
        self,
        request: GatewayRequest,
        *,
        handler: Callable[
            [AuthorizationDecision],
            Any,
        ],
    ) -> Any:
        decision = self.authorize(
            request
        )

        endpoint = (
            decision.endpoint
        )

        if (
            endpoint.require_idempotency
        ):
            found, result = (
                self.idempotency
                .lookup(
                    tenant_id=(
                        decision
                        .claims
                        .tenant_id
                    ),
                    endpoint_name=(
                        endpoint.name
                    ),
                    key=str(
                        request
                        .idempotency_key
                    ),
                    request_body=(
                        request.body
                        or {}
                    ),
                )
            )

            if found:
                return result

        result = handler(
            decision
        )

        if (
            endpoint.require_idempotency
        ):
            self.idempotency.save(
                tenant_id=(
                    decision
                    .claims
                    .tenant_id
                ),
                endpoint_name=(
                    endpoint.name
                ),
                key=str(
                    request
                    .idempotency_key
                ),
                request_body=(
                    request.body
                    or {}
                ),
                result=result,
            )

        self.audit.append(
            event_type=(
                "gateway.executed"
            ),
            tenant_id=(
                decision
                .claims
                .tenant_id
            ),
            user_id=(
                decision
                .claims
                .user_id
            ),
            payload={
                "endpoint":
                    endpoint.name
            },
        )

        return result
