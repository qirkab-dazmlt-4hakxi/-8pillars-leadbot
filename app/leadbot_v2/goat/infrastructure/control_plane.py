from __future__ import annotations

import hashlib
import math
import threading
import time
import uuid

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable

from leadbot_v2.goat.persistence.durable import (
    DurableStore,
    PendingEvent,
)

from leadbot_v2.goat.platform.runtime import (
    DataClassification,
    DevicePlatform,
    RuntimeCapabilityGate,
    SessionPrincipal,
)


# ============================================================
# ERRORS
# ============================================================


class ControlPlaneError(RuntimeError):
    pass


class HandlerNotFound(ControlPlaneError):
    pass


class GatewayRequestError(ControlPlaneError):
    pass


class RateLimitExceeded(ControlPlaneError):
    pass


class CircuitOpen(ControlPlaneError):
    pass


class FeatureDisabled(ControlPlaneError):
    pass


# ============================================================
# UTIL
# ============================================================


def _now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def _id(
    prefix: str,
) -> str:
    return (
        prefix
        + "_"
        + uuid.uuid4().hex
    )


def _required(
    value: Any,
    field: str,
) -> str:
    result = str(
        value
        or ""
    ).strip()

    if not result:
        raise ValueError(
            f"{field} is required"
        )

    return result


# ============================================================
# CIRCUIT BREAKER
# ============================================================


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class CircuitSnapshot:
    name: str
    state: CircuitState
    consecutive_failures: int
    opened_at: datetime | None


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        recovery_seconds: int = 30,
    ) -> None:
        if failure_threshold <= 0:
            raise ValueError(
                "failure_threshold must be positive"
            )

        if recovery_seconds <= 0:
            raise ValueError(
                "recovery_seconds must be positive"
            )

        self.name = _required(
            name,
            "name",
        )

        self.failure_threshold = (
            failure_threshold
        )

        self.recovery_seconds = (
            recovery_seconds
        )

        self._state = (
            CircuitState.CLOSED
        )

        self._failures = 0

        self._opened_at = None

        self._lock = (
            threading.Lock()
        )

    def before_call(
        self,
        *,
        as_of: datetime | None = None,
    ) -> None:
        now = (
            as_of
            or _now()
        )

        with self._lock:
            if (
                self._state
                == CircuitState.OPEN
            ):
                if (
                    self._opened_at
                    is not None
                    and (
                        now
                        - self._opened_at
                    )
                    >= timedelta(
                        seconds=(
                            self
                            .recovery_seconds
                        )
                    )
                ):
                    self._state = (
                        CircuitState
                        .HALF_OPEN
                    )

                else:
                    raise CircuitOpen(
                        self.name
                    )

    def success(
        self,
    ) -> None:
        with self._lock:
            self._state = (
                CircuitState.CLOSED
            )

            self._failures = 0
            self._opened_at = None

    def failure(
        self,
        *,
        as_of: datetime | None = None,
    ) -> None:
        now = (
            as_of
            or _now()
        )

        with self._lock:
            self._failures += 1

            if (
                self._state
                == CircuitState.HALF_OPEN
                or self._failures
                >= self.failure_threshold
            ):
                self._state = (
                    CircuitState.OPEN
                )

                self._opened_at = (
                    now
                )

    def snapshot(
        self,
    ) -> CircuitSnapshot:
        with self._lock:
            return CircuitSnapshot(
                name=self.name,
                state=self._state,
                consecutive_failures=(
                    self._failures
                ),
                opened_at=(
                    self._opened_at
                ),
            )


# ============================================================
# RATE LIMIT
# ============================================================


class FixedWindowRateLimiter:
    """
    Process-local deterministic limiter.

    Production multi-node deployment must move counters to shared durable
    infrastructure such as Redis or an API gateway.
    """

    def __init__(
        self,
    ) -> None:
        self._windows = {}

        self._lock = (
            threading.Lock()
        )

    def require(
        self,
        *,
        key: str,
        limit: int,
        window_seconds: int,
        as_of: datetime | None = None,
    ) -> None:
        if limit <= 0:
            raise ValueError(
                "limit must be positive"
            )

        if window_seconds <= 0:
            raise ValueError(
                "window_seconds must be positive"
            )

        now = (
            as_of
            or _now()
        )

        epoch = int(
            now.timestamp()
        )

        window = (
            epoch
            // window_seconds
        )

        identity = (
            key,
            window,
        )

        with self._lock:
            count = (
                self._windows.get(
                    identity,
                    0,
                )
            )

            if count >= limit:
                raise RateLimitExceeded(
                    key
                )

            self._windows[
                identity
            ] = (
                count
                + 1
            )


# ============================================================
# FEATURE FLAGS
# ============================================================


@dataclass(frozen=True)
class FeatureContext:
    tenant_id: str
    user_id: str
    role: str
    device_id: str
    platform: DevicePlatform


@dataclass(frozen=True)
class FeatureFlag:
    name: str

    enabled: bool = True

    kill_switch: bool = False

    rollout_percent: float = 100.0

    allowed_tenants: frozenset[
        str
    ] = frozenset()

    allowed_roles: frozenset[
        str
    ] = frozenset()

    allowed_platforms: frozenset[
        DevicePlatform
    ] = frozenset()


@dataclass(frozen=True)
class FeatureDecision:
    enabled: bool
    reason: str
    bucket: float


class FeatureFlagEngine:
    def __init__(
        self,
    ) -> None:
        self._flags = {}

    def set_flag(
        self,
        flag: FeatureFlag,
    ) -> None:
        if not (
            0.0
            <= flag.rollout_percent
            <= 100.0
        ):
            raise ValueError(
                "rollout_percent must be 0..100"
            )

        self._flags[
            flag.name
        ] = flag

    def flag(
        self,
        name: str,
    ) -> FeatureFlag:
        try:
            return self._flags[
                name
            ]

        except KeyError as exc:
            raise FeatureDisabled(
                (
                    "unknown feature: "
                    + name
                )
            ) from exc

    @staticmethod
    def _bucket(
        *,
        name: str,
        context: FeatureContext,
    ) -> float:
        material = (
            name
            + "|"
            + context.tenant_id
            + "|"
            + context.user_id
            + "|"
            + context.device_id
        )

        digest = hashlib.sha256(
            material.encode(
                "utf-8"
            )
        ).digest()

        integer = int.from_bytes(
            digest[:8],
            "big",
        )

        return (
            integer
            / (
                (1 << 64)
                - 1
            )
            * 100.0
        )

    def evaluate(
        self,
        *,
        name: str,
        context: FeatureContext,
    ) -> FeatureDecision:
        flag = self.flag(
            name
        )

        bucket = self._bucket(
            name=name,
            context=context,
        )

        if flag.kill_switch:
            return FeatureDecision(
                enabled=False,
                reason="kill_switch",
                bucket=bucket,
            )

        if not flag.enabled:
            return FeatureDecision(
                enabled=False,
                reason="disabled",
                bucket=bucket,
            )

        if (
            flag.allowed_tenants
            and context.tenant_id
            not in flag.allowed_tenants
        ):
            return FeatureDecision(
                enabled=False,
                reason="tenant_not_allowed",
                bucket=bucket,
            )

        if (
            flag.allowed_roles
            and context.role
            not in flag.allowed_roles
        ):
            return FeatureDecision(
                enabled=False,
                reason="role_not_allowed",
                bucket=bucket,
            )

        if (
            flag.allowed_platforms
            and context.platform
            not in flag.allowed_platforms
        ):
            return FeatureDecision(
                enabled=False,
                reason="platform_not_allowed",
                bucket=bucket,
            )

        if (
            bucket
            >= flag.rollout_percent
        ):
            return FeatureDecision(
                enabled=False,
                reason="outside_rollout",
                bucket=bucket,
            )

        return FeatureDecision(
            enabled=True,
            reason="enabled",
            bucket=bucket,
        )


# ============================================================
# TELEMETRY
# ============================================================


@dataclass(frozen=True)
class RequestMetric:
    operation: str
    success: bool
    latency_ms: float


@dataclass(frozen=True)
class OperationTelemetry:
    operation: str
    request_count: int
    success_count: int
    error_count: int
    success_rate: float
    p50_ms: float
    p95_ms: float
    p99_ms: float


@dataclass(frozen=True)
class SLOAssessment:
    operation: str
    success_target: float
    latency_target_p95_ms: float
    observed_success_rate: float
    observed_p95_ms: float
    success_target_met: bool
    latency_target_met: bool
    healthy: bool


class TelemetryRegistry:
    def __init__(
        self,
        *,
        max_samples_per_operation: int = 10000,
    ) -> None:
        if max_samples_per_operation <= 0:
            raise ValueError(
                "max_samples_per_operation must be positive"
            )

        self.max_samples = (
            max_samples_per_operation
        )

        self._samples = defaultdict(
            lambda: deque(
                maxlen=(
                    self.max_samples
                )
            )
        )

        self._lock = (
            threading.Lock()
        )

    def record(
        self,
        *,
        operation: str,
        success: bool,
        latency_ms: float,
    ) -> None:
        if (
            not math.isfinite(
                latency_ms
            )
            or latency_ms < 0
        ):
            raise ValueError(
                "latency must be finite and nonnegative"
            )

        metric = RequestMetric(
            operation=operation,
            success=success,
            latency_ms=latency_ms,
        )

        with self._lock:
            self._samples[
                operation
            ].append(
                metric
            )

    @staticmethod
    def _percentile(
        values: list[float],
        percentile: float,
    ) -> float:
        if not values:
            return 0.0

        ordered = sorted(
            values
        )

        index = int(
            round(
                (
                    len(ordered)
                    - 1
                )
                * percentile
            )
        )

        return float(
            ordered[
                index
            ]
        )

    def operation(
        self,
        operation: str,
    ) -> OperationTelemetry:
        with self._lock:
            samples = list(
                self._samples.get(
                    operation,
                    (),
                )
            )

        total = len(
            samples
        )

        successes = sum(
            1
            for sample
            in samples
            if sample.success
        )

        errors = (
            total
            - successes
        )

        latencies = [
            sample.latency_ms
            for sample
            in samples
        ]

        success_rate = (
            successes
            / total
            if total
            else 1.0
        )

        return OperationTelemetry(
            operation=operation,
            request_count=total,
            success_count=successes,
            error_count=errors,
            success_rate=(
                success_rate
            ),
            p50_ms=(
                self._percentile(
                    latencies,
                    0.50,
                )
            ),
            p95_ms=(
                self._percentile(
                    latencies,
                    0.95,
                )
            ),
            p99_ms=(
                self._percentile(
                    latencies,
                    0.99,
                )
            ),
        )

    def assess_slo(
        self,
        *,
        operation: str,
        success_target: float = 0.995,
        latency_target_p95_ms: float = 500.0,
    ) -> SLOAssessment:
        if not (
            0.0
            <= success_target
            <= 1.0
        ):
            raise ValueError(
                "success_target must be 0..1"
            )

        metrics = self.operation(
            operation
        )

        success_met = (
            metrics.success_rate
            >= success_target
        )

        latency_met = (
            metrics.p95_ms
            <= latency_target_p95_ms
        )

        return SLOAssessment(
            operation=operation,
            success_target=(
                success_target
            ),
            latency_target_p95_ms=(
                latency_target_p95_ms
            ),
            observed_success_rate=(
                metrics.success_rate
            ),
            observed_p95_ms=(
                metrics.p95_ms
            ),
            success_target_met=(
                success_met
            ),
            latency_target_met=(
                latency_met
            ),
            healthy=(
                success_met
                and latency_met
            ),
        )


# ============================================================
# SERVICE GATEWAY
# ============================================================


@dataclass(frozen=True)
class ServiceRequest:
    request_id: str
    tenant_id: str
    user_id: str
    operation: str
    payload: dict[str, Any]
    idempotency_key: str | None = None


@dataclass(frozen=True)
class MutationCommit:
    stream_id: str
    expected_version: int
    events: tuple[
        PendingEvent,
        ...
    ]
    response: dict[str, Any]


@dataclass(frozen=True)
class HandlerSpec:
    operation: str
    capability: str
    classification: DataClassification
    mutation: bool
    rate_limit: int
    rate_window_seconds: int
    circuit_name: str
    feature_flag: str | None
    handler: Callable[
        [
            ServiceRequest,
            SessionPrincipal,
        ],
        (
            MutationCommit
            | dict[str, Any]
        ),
    ]


@dataclass(frozen=True)
class ServiceResponse:
    request_id: str
    operation: str
    status: str
    data: dict[str, Any]
    cached: bool
    latency_ms: float


class ServiceGateway:
    """
    GOAT server command/query gateway.

    Security order:
      1. validate principal/request identity
      2. capability + device trust
      3. feature policy
      4. rate limiting
      5. circuit breaker
      6. durable idempotency for mutations
      7. domain handler
      8. atomic event + transactional outbox persistence
      9. persist idempotent response
      10. telemetry
    """

    def __init__(
        self,
        *,
        store: DurableStore,
        capability_gate: RuntimeCapabilityGate,
        telemetry: (
            TelemetryRegistry
            | None
        ) = None,
        rate_limiter: (
            FixedWindowRateLimiter
            | None
        ) = None,
        feature_flags: (
            FeatureFlagEngine
            | None
        ) = None,
    ) -> None:
        self.store = store

        self.capability_gate = (
            capability_gate
        )

        self.telemetry = (
            telemetry
            or TelemetryRegistry()
        )

        self.rate_limiter = (
            rate_limiter
            or FixedWindowRateLimiter()
        )

        self.feature_flags = (
            feature_flags
            or FeatureFlagEngine()
        )

        self._handlers = {}

        self._circuits = {}

    def register(
        self,
        spec: HandlerSpec,
    ) -> None:
        operation = _required(
            spec.operation,
            "operation",
        )

        if operation in self._handlers:
            raise ControlPlaneError(
                (
                    "handler already registered: "
                    + operation
                )
            )

        self._handlers[
            operation
        ] = spec

        self._circuits.setdefault(
            spec.circuit_name,
            CircuitBreaker(
                spec.circuit_name
            ),
        )

    def _spec(
        self,
        operation: str,
    ) -> HandlerSpec:
        try:
            return self._handlers[
                operation
            ]

        except KeyError as exc:
            raise HandlerNotFound(
                operation
            ) from exc

    def execute(
        self,
        *,
        request: ServiceRequest,
        principal: SessionPrincipal,
        platform: DevicePlatform,
        online: bool = True,
    ) -> ServiceResponse:
        started = (
            time.perf_counter()
        )

        success = False

        spec = self._spec(
            request.operation
        )

        try:
            if (
                request.tenant_id
                != principal.tenant_id
            ):
                raise GatewayRequestError(
                    "request tenant mismatch"
                )

            if (
                request.user_id
                != principal.user_id
            ):
                raise GatewayRequestError(
                    "request user mismatch"
                )

            self.capability_gate.require(
                principal=principal,
                capability=(
                    spec.capability
                ),
                classification=(
                    spec.classification
                ),
                online=online,
            )

            if spec.feature_flag:
                feature = (
                    self.feature_flags
                    .evaluate(
                        name=(
                            spec.feature_flag
                        ),
                        context=(
                            FeatureContext(
                                tenant_id=(
                                    principal
                                    .tenant_id
                                ),
                                user_id=(
                                    principal
                                    .user_id
                                ),
                                role=(
                                    principal.role
                                ),
                                device_id=(
                                    principal
                                    .device_id
                                ),
                                platform=(
                                    platform
                                ),
                            )
                        ),
                    )
                )

                if not feature.enabled:
                    raise FeatureDisabled(
                        (
                            spec.feature_flag
                            + ": "
                            + feature.reason
                        )
                    )

            self.rate_limiter.require(
                key=(
                    principal.tenant_id
                    + ":"
                    + principal.user_id
                    + ":"
                    + request.operation
                ),
                limit=(
                    spec.rate_limit
                ),
                window_seconds=(
                    spec
                    .rate_window_seconds
                ),
            )

            circuit = (
                self._circuits[
                    spec.circuit_name
                ]
            )

            circuit.before_call()

            if spec.mutation:
                if not request.idempotency_key:
                    raise GatewayRequestError(
                        "mutation requires idempotency key"
                    )

                idem = (
                    self.store
                    .begin_idempotent(
                        tenant_id=(
                            request.tenant_id
                        ),
                        scope=(
                            "api:"
                            + request.operation
                        ),
                        key=(
                            request
                            .idempotency_key
                        ),
                        request={
                            "operation":
                                request.operation,
                            "payload":
                                request.payload,
                            "user_id":
                                request.user_id,
                        },
                    )
                )

                if (
                    idem.existing
                    and idem.completed
                ):
                    circuit.success()

                    success = True

                    elapsed = (
                        (
                            time.perf_counter()
                            - started
                        )
                        * 1000.0
                    )

                    return ServiceResponse(
                        request_id=(
                            request.request_id
                        ),
                        operation=(
                            request.operation
                        ),
                        status="ok",
                        data=(
                            idem.response
                            or {}
                        ),
                        cached=True,
                        latency_ms=(
                            elapsed
                        ),
                    )

                if (
                    idem.existing
                    and not idem.completed
                ):
                    raise GatewayRequestError(
                        (
                            "matching request is "
                            "already in progress"
                        )
                    )

            try:
                outcome = (
                    spec.handler(
                        request,
                        principal,
                    )
                )

            except Exception:
                circuit.failure()
                raise

            if spec.mutation:
                if not isinstance(
                    outcome,
                    MutationCommit,
                ):
                    circuit.failure()

                    raise GatewayRequestError(
                        (
                            "mutation handler must "
                            "return MutationCommit"
                        )
                    )

                self.store.append_many(
                    tenant_id=(
                        request.tenant_id
                    ),
                    stream_id=(
                        outcome.stream_id
                    ),
                    expected_version=(
                        outcome
                        .expected_version
                    ),
                    events=(
                        outcome.events
                    ),
                    actor_id=(
                        principal.user_id
                    ),
                    device_id=(
                        principal.device_id
                    ),
                )

                self.store.complete_idempotent(
                    tenant_id=(
                        request.tenant_id
                    ),
                    scope=(
                        "api:"
                        + request.operation
                    ),
                    key=(
                        request
                        .idempotency_key
                    ),
                    response=(
                        outcome.response
                    ),
                )

                response_data = (
                    outcome.response
                )

            else:
                if not isinstance(
                    outcome,
                    dict,
                ):
                    circuit.failure()

                    raise GatewayRequestError(
                        (
                            "query handler must "
                            "return dict"
                        )
                    )

                response_data = (
                    outcome
                )

            circuit.success()

            success = True

            elapsed = (
                (
                    time.perf_counter()
                    - started
                )
                * 1000.0
            )

            return ServiceResponse(
                request_id=(
                    request.request_id
                ),
                operation=(
                    request.operation
                ),
                status="ok",
                data=(
                    response_data
                ),
                cached=False,
                latency_ms=(
                    elapsed
                ),
            )

        finally:
            elapsed = (
                (
                    time.perf_counter()
                    - started
                )
                * 1000.0
            )

            self.telemetry.record(
                operation=(
                    request.operation
                ),
                success=success,
                latency_ms=(
                    elapsed
                ),
            )


def service_request(
    *,
    tenant_id: str,
    user_id: str,
    operation: str,
    payload: dict[str, Any],
    idempotency_key: str | None = None,
) -> ServiceRequest:
    return ServiceRequest(
        request_id=_id(
            "api"
        ),
        tenant_id=tenant_id,
        user_id=user_id,
        operation=operation,
        payload=payload,
        idempotency_key=(
            idempotency_key
        ),
    )
