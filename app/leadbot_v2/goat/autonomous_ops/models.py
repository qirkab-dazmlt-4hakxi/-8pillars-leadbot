from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class OpsInvariantError(RuntimeError):
    pass


class HealthLevel(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


def normalize_time(
    value: datetime | None,
) -> datetime:
    result = value or datetime.now(
        timezone.utc
    )

    if result.tzinfo is None:
        raise OpsInvariantError(
            "operations timestamps must be timezone-aware"
        )

    return result.astimezone(
        timezone.utc
    )


@dataclass(frozen=True)
class WorkerHeartbeat:
    tenant_id: str

    worker_id: str
    instance_id: str

    fencing_token: int

    observed_at: datetime
    expires_at: datetime

    claimed: int = 0
    completed: int = 0
    failed: int = 0
    stale: int = 0
    replayed: int = 0
    wakes: int = 0


@dataclass(frozen=True)
class QueuePressure:
    pending: int

    soft_limit: int
    hard_limit: int

    level: HealthLevel


@dataclass(frozen=True)
class CircuitConfig:
    failure_threshold: int = 5

    recovery_timeout_seconds: float = 60.0

    half_open_success_threshold: int = 1

    def __post_init__(
        self,
    ) -> None:
        if self.failure_threshold < 1:
            raise OpsInvariantError(
                "failure_threshold must be >= 1"
            )

        if self.recovery_timeout_seconds <= 0:
            raise OpsInvariantError(
                "recovery timeout must be positive"
            )

        if self.half_open_success_threshold < 1:
            raise OpsInvariantError(
                "half-open success threshold must be >= 1"
            )


@dataclass(frozen=True)
class CircuitSnapshot:
    tenant_id: str
    name: str

    state: CircuitState = CircuitState.CLOSED

    failure_count: int = 0
    half_open_success_count: int = 0

    opened_at: datetime | None = None
    last_failure_at: datetime | None = None

    revision: int = 0


@dataclass(frozen=True)
class SchedulerState:
    tenant_id: str

    cycle_count: int = 0

    last_recovery_at: datetime | None = None
    last_health_at: datetime | None = None

    revision: int = 0


@dataclass(frozen=True)
class RecoverySweepResult:
    scanned: int = 0
    eligible: int = 0
    reconciled: int = 0

    failures: tuple[str, ...] = ()


@dataclass(frozen=True)
class OpsSnapshot:
    tenant_id: str

    observed_at: datetime

    health: HealthLevel

    pending_outbox: int

    stale_workers: tuple[str, ...] = ()

    open_circuits: tuple[str, ...] = ()

    recovery_failures: tuple[str, ...] = ()


@dataclass(frozen=True)
class OpsCycleResult:
    snapshot: OpsSnapshot

    recovery: RecoverySweepResult | None

    worker_cycles: tuple[
        tuple[str, object],
        ...
    ] = ()
