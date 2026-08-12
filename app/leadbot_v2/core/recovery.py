from __future__ import annotations

from dataclasses import dataclass

from leadbot_v2.core.source_health import (
    CircuitState,
    SourceCircuitBreaker,
)


@dataclass
class RecoveryDecision:
    action: str
    source: str
    reason: str


class RecoveryPolicy:
    def __init__(
        self,
        breaker: SourceCircuitBreaker,
    ) -> None:
        self.breaker = breaker

    def evaluate(
        self,
        source: str,
    ) -> RecoveryDecision:
        health = self.breaker.get(source)

        if health.state == CircuitState.OPEN:
            return RecoveryDecision(
                action="failover",
                source=source,
                reason=(
                    f"circuit open after "
                    f"{health.consecutive_failures} consecutive failures"
                ),
            )

        if health.state == CircuitState.HALF_OPEN:
            return RecoveryDecision(
                action="probe",
                source=source,
                reason="cooldown expired; controlled recovery probe allowed",
            )

        if health.latency_ms_ema >= 8000:
            return RecoveryDecision(
                action="deprioritize",
                source=source,
                reason="latency exceeds healthy operating threshold",
            )

        return RecoveryDecision(
            action="continue",
            source=source,
            reason="source operating normally",
        )
