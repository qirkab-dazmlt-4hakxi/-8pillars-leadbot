from __future__ import annotations

from dataclasses import dataclass

from .models import (
    HealthLevel,
    QueuePressure,
)


@dataclass(frozen=True)
class QueuePressurePolicy:
    soft_limit: int = 100
    hard_limit: int = 1000

    def __post_init__(
        self,
    ) -> None:
        if self.soft_limit < 1:
            raise ValueError(
                "soft_limit must be >= 1"
            )

        if self.hard_limit <= self.soft_limit:
            raise ValueError(
                "hard_limit must exceed soft_limit"
            )

    def classify(
        self,
        pending: int,
    ) -> QueuePressure:
        if pending < 0:
            raise ValueError(
                "pending outbox cannot be negative"
            )

        if pending >= self.hard_limit:
            level = HealthLevel.CRITICAL

        elif pending >= self.soft_limit:
            level = HealthLevel.DEGRADED

        else:
            level = HealthLevel.HEALTHY

        return QueuePressure(
            pending=pending,
            soft_limit=self.soft_limit,
            hard_limit=self.hard_limit,
            level=level,
        )


class SystemHealthEvaluator:
    def classify(
        self,
        *,
        queue: QueuePressure,
        stale_workers: tuple[str, ...],
        open_circuits: tuple[str, ...],
        recovery_failures: tuple[str, ...],
    ) -> HealthLevel:
        if queue.level is HealthLevel.CRITICAL:
            return HealthLevel.CRITICAL

        if recovery_failures:
            return HealthLevel.CRITICAL

        if (
            queue.level is HealthLevel.DEGRADED
            or stale_workers
            or open_circuits
        ):
            return HealthLevel.DEGRADED

        return HealthLevel.HEALTHY
