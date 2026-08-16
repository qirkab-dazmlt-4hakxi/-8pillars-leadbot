from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

from .models import (
    CircuitSnapshot,
    CircuitState,
    SchedulerState,
    WorkerHeartbeat,
    normalize_time,
)


WORKER_HEARTBEAT_ENTITY = "goat.ops.worker_heartbeat"
CIRCUIT_ENTITY = "goat.ops.circuit"
SCHEDULER_ENTITY = "goat.ops.scheduler"
SCHEDULER_ID = "autonomous-ops"


def _dt(
    value: datetime | None,
) -> str | None:
    if value is None:
        return None

    return normalize_time(
        value
    ).isoformat()


def _parse_dt(
    value: str | None,
) -> datetime | None:
    if value is None:
        return None

    return normalize_time(
        datetime.fromisoformat(
            value
        )
    )


class OpsRepository:
    def __init__(
        self,
        store,
        *,
        tenant_id: str,
        actor_id: str = "goat-autonomous-ops",
    ) -> None:
        if not tenant_id.strip():
            raise ValueError(
                "tenant_id cannot be blank"
            )

        self.store = store
        self.tenant_id = tenant_id
        self.actor_id = actor_id

    def _upsert(
        self,
        *,
        entity_type: str,
        entity_id: str,
        payload: dict[str, Any],
    ):
        current = self.store.get_entity(
            tenant_id=self.tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )

        expected_version = (
            None
            if current is None
            else int(current.version)
        )

        return self.store.put_entity(
            tenant_id=self.tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
            actor_id=self.actor_id,
            expected_version=expected_version,
        )

    def save_heartbeat(
        self,
        heartbeat: WorkerHeartbeat,
    ) -> WorkerHeartbeat:
        if heartbeat.tenant_id != self.tenant_id:
            raise ValueError(
                "heartbeat tenant boundary violation"
            )

        entity_id = (
            f"{heartbeat.worker_id}:"
            f"{heartbeat.instance_id}"
        )

        self._upsert(
            entity_type=WORKER_HEARTBEAT_ENTITY,
            entity_id=entity_id,
            payload={
                "tenant_id":
                    heartbeat.tenant_id,
                "worker_id":
                    heartbeat.worker_id,
                "instance_id":
                    heartbeat.instance_id,
                "fencing_token":
                    heartbeat.fencing_token,
                "observed_at":
                    _dt(
                        heartbeat.observed_at
                    ),
                "expires_at":
                    _dt(
                        heartbeat.expires_at
                    ),
                "claimed":
                    heartbeat.claimed,
                "completed":
                    heartbeat.completed,
                "failed":
                    heartbeat.failed,
                "stale":
                    heartbeat.stale,
                "replayed":
                    heartbeat.replayed,
                "wakes":
                    heartbeat.wakes,
            },
        )

        return heartbeat

    def list_heartbeats(
        self,
    ) -> tuple[WorkerHeartbeat, ...]:
        records = self.store.list_entities(
            tenant_id=self.tenant_id,
            entity_type=WORKER_HEARTBEAT_ENTITY,
            include_deleted=False,
        )

        result: list[
            WorkerHeartbeat
        ] = []

        for record in records:
            payload = dict(
                record.payload
            )

            observed_at = _parse_dt(
                payload[
                    "observed_at"
                ]
            )

            expires_at = _parse_dt(
                payload[
                    "expires_at"
                ]
            )

            if (
                observed_at is None
                or expires_at is None
            ):
                raise ValueError(
                    "heartbeat timestamp missing"
                )

            result.append(
                WorkerHeartbeat(
                    tenant_id=self.tenant_id,
                    worker_id=payload[
                        "worker_id"
                    ],
                    instance_id=payload[
                        "instance_id"
                    ],
                    fencing_token=int(
                        payload[
                            "fencing_token"
                        ]
                    ),
                    observed_at=observed_at,
                    expires_at=expires_at,
                    claimed=int(
                        payload.get(
                            "claimed",
                            0,
                        )
                    ),
                    completed=int(
                        payload.get(
                            "completed",
                            0,
                        )
                    ),
                    failed=int(
                        payload.get(
                            "failed",
                            0,
                        )
                    ),
                    stale=int(
                        payload.get(
                            "stale",
                            0,
                        )
                    ),
                    replayed=int(
                        payload.get(
                            "replayed",
                            0,
                        )
                    ),
                    wakes=int(
                        payload.get(
                            "wakes",
                            0,
                        )
                    ),
                )
            )

        return tuple(result)

    def load_circuit(
        self,
        name: str,
    ) -> CircuitSnapshot | None:
        record = self.store.get_entity(
            tenant_id=self.tenant_id,
            entity_type=CIRCUIT_ENTITY,
            entity_id=name,
        )

        if record is None:
            return None

        payload = dict(
            record.payload
        )

        return CircuitSnapshot(
            tenant_id=self.tenant_id,
            name=name,
            state=CircuitState(
                payload.get(
                    "state",
                    CircuitState.CLOSED.value,
                )
            ),
            failure_count=int(
                payload.get(
                    "failure_count",
                    0,
                )
            ),
            half_open_success_count=int(
                payload.get(
                    "half_open_success_count",
                    0,
                )
            ),
            opened_at=_parse_dt(
                payload.get(
                    "opened_at"
                )
            ),
            last_failure_at=_parse_dt(
                payload.get(
                    "last_failure_at"
                )
            ),
            revision=int(
                record.version
            ),
        )

    def save_circuit(
        self,
        snapshot: CircuitSnapshot,
    ) -> CircuitSnapshot:
        if snapshot.tenant_id != self.tenant_id:
            raise ValueError(
                "circuit tenant boundary violation"
            )

        record = self._upsert(
            entity_type=CIRCUIT_ENTITY,
            entity_id=snapshot.name,
            payload={
                "tenant_id":
                    snapshot.tenant_id,
                "name":
                    snapshot.name,
                "state":
                    snapshot.state.value,
                "failure_count":
                    snapshot.failure_count,
                "half_open_success_count":
                    snapshot
                    .half_open_success_count,
                "opened_at":
                    _dt(
                        snapshot.opened_at
                    ),
                "last_failure_at":
                    _dt(
                        snapshot.last_failure_at
                    ),
            },
        )

        return replace(
            snapshot,
            revision=int(
                record.version
            ),
        )

    def list_circuits(
        self,
    ) -> tuple[CircuitSnapshot, ...]:
        records = self.store.list_entities(
            tenant_id=self.tenant_id,
            entity_type=CIRCUIT_ENTITY,
            include_deleted=False,
        )

        result: list[
            CircuitSnapshot
        ] = []

        for record in records:
            payload = dict(
                record.payload
            )

            result.append(
                CircuitSnapshot(
                    tenant_id=self.tenant_id,
                    name=payload[
                        "name"
                    ],
                    state=CircuitState(
                        payload[
                            "state"
                        ]
                    ),
                    failure_count=int(
                        payload.get(
                            "failure_count",
                            0,
                        )
                    ),
                    half_open_success_count=int(
                        payload.get(
                            "half_open_success_count",
                            0,
                        )
                    ),
                    opened_at=_parse_dt(
                        payload.get(
                            "opened_at"
                        )
                    ),
                    last_failure_at=_parse_dt(
                        payload.get(
                            "last_failure_at"
                        )
                    ),
                    revision=int(
                        record.version
                    ),
                )
            )

        return tuple(result)

    def load_scheduler(
        self,
    ) -> SchedulerState:
        record = self.store.get_entity(
            tenant_id=self.tenant_id,
            entity_type=SCHEDULER_ENTITY,
            entity_id=SCHEDULER_ID,
        )

        if record is None:
            return SchedulerState(
                tenant_id=self.tenant_id
            )

        payload = dict(
            record.payload
        )

        return SchedulerState(
            tenant_id=self.tenant_id,
            cycle_count=int(
                payload.get(
                    "cycle_count",
                    0,
                )
            ),
            last_recovery_at=_parse_dt(
                payload.get(
                    "last_recovery_at"
                )
            ),
            last_health_at=_parse_dt(
                payload.get(
                    "last_health_at"
                )
            ),
            revision=int(
                record.version
            ),
        )

    def save_scheduler(
        self,
        state: SchedulerState,
    ) -> SchedulerState:
        if state.tenant_id != self.tenant_id:
            raise ValueError(
                "scheduler tenant boundary violation"
            )

        record = self._upsert(
            entity_type=SCHEDULER_ENTITY,
            entity_id=SCHEDULER_ID,
            payload={
                "tenant_id":
                    state.tenant_id,
                "cycle_count":
                    state.cycle_count,
                "last_recovery_at":
                    _dt(
                        state.last_recovery_at
                    ),
                "last_health_at":
                    _dt(
                        state.last_health_at
                    ),
            },
        )

        return replace(
            state,
            revision=int(
                record.version
            ),
        )
