from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import monotonic

from leadbot_v2.core.fault_learning import FaultLearningPolicy


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class SourceHealth:
    name: str
    state: CircuitState = CircuitState.CLOSED

    total_requests: int = 0
    successes: int = 0
    failures: int = 0
    consecutive_failures: int = 0

    latency_ms_ema: float = 0.0

    opened_at: float | None = None
    last_success_at: float | None = None
    last_failure_at: float | None = None

    last_error: str | None = None

    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 1.0
        return self.successes / self.total_requests

    @property
    def healthy(self) -> bool:
        return self.state != CircuitState.OPEN


class SourceCircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        cooldown_seconds: float = 60.0,
        latency_alpha: float = 0.20,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.latency_alpha = latency_alpha
        self.sources: dict[str, SourceHealth] = {}
        self.fault_learning = FaultLearningPolicy()

    def get(self, source: str) -> SourceHealth:
        if source not in self.sources:
            self.sources[source] = SourceHealth(name=source)

        return self.sources[source]

    def allow_request(self, source: str) -> bool:
        health = self.get(source)

        if health.state == CircuitState.CLOSED:
            return True

        if health.state == CircuitState.OPEN:
            if health.opened_at is None:
                return False

            elapsed = monotonic() - health.opened_at

            if elapsed >= self.cooldown_seconds:
                health.state = CircuitState.HALF_OPEN
                return True

            return False

        return True


    def record_success(
        self,
        source: str,
        *,
        latency_ms: float,
    ) -> SourceHealth:
        health = self.get(source)

        health.total_requests += 1
        health.successes += 1
        health.consecutive_failures = 0
        health.last_success_at = monotonic()
        health.last_error = None

        if health.latency_ms_ema <= 0:
            health.latency_ms_ema = latency_ms
        else:
            a = self.latency_alpha
            health.latency_ms_ema = (
                a * latency_ms
                + (1.0 - a) * health.latency_ms_ema
            )

        # A successful half-open probe closes the circuit.
        if health.state == CircuitState.HALF_OPEN:
            health.state = CircuitState.CLOSED
            health.opened_at = None

        return health

    def record_failure(
        self,
        source: str,
        *,
        error: Exception | str,
    ) -> SourceHealth:
        health = self.get(source)

        health.total_requests += 1
        health.failures += 1
        health.consecutive_failures += 1
        health.last_failure_at = monotonic()
        health.last_error = str(error)

        if (
            health.consecutive_failures
            >= self.failure_threshold
        ):
            health.state = CircuitState.OPEN
            health.opened_at = monotonic()

        return health

    def force_open(
        self,
        source: str,
        *,
        reason: str,
    ) -> SourceHealth:
        health = self.get(source)

        health.state = CircuitState.OPEN
        health.opened_at = monotonic()
        health.last_error = reason

        return health

    def reset(self, source: str) -> SourceHealth:
        health = self.get(source)

        health.state = CircuitState.CLOSED
        health.consecutive_failures = 0
        health.opened_at = None
        health.last_error = None

        return health

    def ranked_available_sources(
        self,
        sources: list[str],
    ) -> list[str]:
        available = [
            self.get(source)
            for source in sources
            if self.allow_request(source)
        ]

        def score(h: SourceHealth) -> tuple:
            learned = self.fault_learning.assess(h)
            multiplier = self.fault_learning.priority_multiplier(h)

            return (
                1 if h.state == CircuitState.CLOSED else 0,
                multiplier,
                learned.reliability_score,
                h.success_rate,
                -h.consecutive_failures,
                -h.latency_ms_ema,
            )

        available.sort(
            key=score,
            reverse=True,
        )

        return [h.name for h in available]
