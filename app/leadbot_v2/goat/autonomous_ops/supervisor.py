from __future__ import annotations

from datetime import (
    timedelta,
)

from leadbot_v2.goat.distributed_execution import (
    WorkerCycle,
)

from .health import (
    QueuePressurePolicy,
    SystemHealthEvaluator,
)

from .models import (
    OpsSnapshot,
    WorkerHeartbeat,
    normalize_time,
)


class AutonomousSupervisor:
    def __init__(
        self,
        *,
        tenant_id: str,
        execution_store,
        repository,
        circuit_manager,
        heartbeat_ttl: timedelta = timedelta(
            seconds=180
        ),
        queue_policy: QueuePressurePolicy | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.execution_store = execution_store
        self.repository = repository

        self.circuit_manager = (
            circuit_manager
        )

        self.heartbeat_ttl = (
            heartbeat_ttl
        )

        self.queue_policy = (
            queue_policy
            or QueuePressurePolicy()
        )

        self.health_evaluator = (
            SystemHealthEvaluator()
        )

    def heartbeat(
        self,
        worker,
        *,
        cycle: WorkerCycle | None = None,
        now=None,
    ) -> WorkerHeartbeat:
        timestamp = normalize_time(
            now
        )

        lease = worker.ensure_worker_lease(
            now=timestamp
        )

        cycle = cycle or WorkerCycle()

        heartbeat = WorkerHeartbeat(
            tenant_id=self.tenant_id,
            worker_id=worker.worker_id,
            instance_id=worker.instance_id,
            fencing_token=(
                lease.fencing_token
            ),
            observed_at=timestamp,
            expires_at=(
                timestamp
                + self.heartbeat_ttl
            ),
            claimed=cycle.claimed,
            completed=cycle.completed,
            failed=cycle.failed,
            stale=cycle.stale,
            replayed=cycle.replayed,
            wakes=cycle.wakes,
        )

        return self.repository.save_heartbeat(
            heartbeat
        )

    def stale_workers(
        self,
        *,
        now=None,
    ) -> tuple[str, ...]:
        timestamp = normalize_time(
            now
        )

        latest: dict[
            str,
            WorkerHeartbeat,
        ] = {}

        for heartbeat in (
            self.repository
            .list_heartbeats()
        ):
            current = latest.get(
                heartbeat.worker_id
            )

            if (
                current is None
                or heartbeat.observed_at
                > current.observed_at
            ):
                latest[
                    heartbeat.worker_id
                ] = heartbeat

        return tuple(
            sorted(
                worker_id
                for worker_id, heartbeat
                in latest.items()
                if heartbeat.expires_at
                <= timestamp
            )
        )

    def queue_pressure(
        self,
    ):
        health = self.execution_store.health()

        pending = int(
            health.pending_outbox_count
        )

        return self.queue_policy.classify(
            pending
        )

    def snapshot(
        self,
        *,
        recovery_failures=(),
        now=None,
    ) -> OpsSnapshot:
        timestamp = normalize_time(
            now
        )

        queue = self.queue_pressure()

        stale = self.stale_workers(
            now=timestamp
        )

        open_circuits = (
            self.circuit_manager
            .open_circuits()
        )

        failures = tuple(
            recovery_failures
        )

        health = (
            self.health_evaluator
            .classify(
                queue=queue,
                stale_workers=stale,
                open_circuits=open_circuits,
                recovery_failures=failures,
            )
        )

        return OpsSnapshot(
            tenant_id=self.tenant_id,
            observed_at=timestamp,
            health=health,
            pending_outbox=queue.pending,
            stale_workers=stale,
            open_circuits=open_circuits,
            recovery_failures=failures,
        )
