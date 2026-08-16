from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta

from .models import (
    SchedulerState,
    normalize_time,
)


@dataclass(frozen=True)
class OpsCadence:
    recovery_interval_seconds: float = 30.0
    health_interval_seconds: float = 10.0

    def __post_init__(
        self,
    ) -> None:
        if self.recovery_interval_seconds <= 0:
            raise ValueError(
                "recovery interval must be positive"
            )

        if self.health_interval_seconds <= 0:
            raise ValueError(
                "health interval must be positive"
            )


class DurableOpsScheduler:
    def __init__(
        self,
        repository,
        *,
        cadence: OpsCadence | None = None,
    ) -> None:
        self.repository = repository

        self.cadence = (
            cadence or OpsCadence()
        )

    def load(
        self,
    ) -> SchedulerState:
        return self.repository.load_scheduler()

    def recovery_due(
        self,
        state: SchedulerState,
        *,
        now=None,
    ) -> bool:
        timestamp = normalize_time(
            now
        )

        if state.last_recovery_at is None:
            return True

        return timestamp >= (
            state.last_recovery_at
            + timedelta(
                seconds=(
                    self.cadence
                    .recovery_interval_seconds
                )
            )
        )

    def health_due(
        self,
        state: SchedulerState,
        *,
        now=None,
    ) -> bool:
        timestamp = normalize_time(
            now
        )

        if state.last_health_at is None:
            return True

        return timestamp >= (
            state.last_health_at
            + timedelta(
                seconds=(
                    self.cadence
                    .health_interval_seconds
                )
            )
        )

    def commit_cycle(
        self,
        state: SchedulerState,
        *,
        recovery_ran: bool,
        health_ran: bool,
        now=None,
    ) -> SchedulerState:
        timestamp = normalize_time(
            now
        )

        updated = replace(
            state,
            cycle_count=(
                state.cycle_count + 1
            ),
            last_recovery_at=(
                timestamp
                if recovery_ran
                else state.last_recovery_at
            ),
            last_health_at=(
                timestamp
                if health_ran
                else state.last_health_at
            ),
        )

        return self.repository.save_scheduler(
            updated
        )
