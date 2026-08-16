from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from .models import (
    CircuitConfig,
    CircuitSnapshot,
    CircuitState,
    normalize_time,
)


class CircuitBreakerManager:
    def __init__(
        self,
        repository,
        *,
        config: CircuitConfig | None = None,
    ) -> None:
        self.repository = repository

        self.config = (
            config or CircuitConfig()
        )

    def _load(
        self,
        name: str,
    ) -> CircuitSnapshot:
        if not name.strip():
            raise ValueError(
                "circuit name cannot be blank"
            )

        existing = self.repository.load_circuit(
            name
        )

        if existing is not None:
            return existing

        return CircuitSnapshot(
            tenant_id=self.repository.tenant_id,
            name=name,
        )

    def allow(
        self,
        name: str,
        *,
        now=None,
    ) -> bool:
        timestamp = normalize_time(
            now
        )

        snapshot = self._load(
            name
        )

        if snapshot.state is CircuitState.CLOSED:
            return True

        if snapshot.state is CircuitState.HALF_OPEN:
            return True

        if snapshot.opened_at is None:
            return False

        reopen_at = (
            snapshot.opened_at
            + timedelta(
                seconds=(
                    self.config
                    .recovery_timeout_seconds
                )
            )
        )

        if timestamp < reopen_at:
            return False

        snapshot = replace(
            snapshot,
            state=CircuitState.HALF_OPEN,
            half_open_success_count=0,
        )

        self.repository.save_circuit(
            snapshot
        )

        return True

    def record_failure(
        self,
        name: str,
        *,
        now=None,
    ) -> CircuitSnapshot:
        timestamp = normalize_time(
            now
        )

        snapshot = self._load(
            name
        )

        failures = (
            snapshot.failure_count + 1
        )

        should_open = (
            snapshot.state
            is CircuitState.HALF_OPEN
            or failures
            >= self.config.failure_threshold
        )

        if should_open:
            updated = replace(
                snapshot,
                state=CircuitState.OPEN,
                failure_count=failures,
                half_open_success_count=0,
                opened_at=timestamp,
                last_failure_at=timestamp,
            )

        else:
            updated = replace(
                snapshot,
                failure_count=failures,
                last_failure_at=timestamp,
            )

        return self.repository.save_circuit(
            updated
        )

    def record_success(
        self,
        name: str,
        *,
        now=None,
    ) -> CircuitSnapshot:
        normalize_time(now)

        snapshot = self._load(
            name
        )

        if snapshot.state is CircuitState.CLOSED:
            updated = replace(
                snapshot,
                failure_count=0,
            )

            return self.repository.save_circuit(
                updated
            )

        if snapshot.state is CircuitState.OPEN:
            return snapshot

        successes = (
            snapshot.half_open_success_count
            + 1
        )

        if (
            successes
            >= self.config
            .half_open_success_threshold
        ):
            updated = replace(
                snapshot,
                state=CircuitState.CLOSED,
                failure_count=0,
                half_open_success_count=0,
                opened_at=None,
            )

        else:
            updated = replace(
                snapshot,
                half_open_success_count=successes,
            )

        return self.repository.save_circuit(
            updated
        )

    def open_circuits(
        self,
    ) -> tuple[str, ...]:
        return tuple(
            sorted(
                circuit.name
                for circuit
                in self.repository.list_circuits()
                if circuit.state
                is CircuitState.OPEN
            )
        )
