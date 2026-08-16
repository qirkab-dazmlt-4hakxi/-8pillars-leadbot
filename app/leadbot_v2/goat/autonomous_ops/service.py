from __future__ import annotations

from .circuit import (
    CircuitBreakerManager,
)
from .health import (
    QueuePressurePolicy,
)
from .models import (
    OpsCycleResult,
    RecoverySweepResult,
    normalize_time,
)
from .persistence import (
    OpsRepository,
)
from .recovery import (
    RecoverySweeper,
)
from .scheduler import (
    DurableOpsScheduler,
    OpsCadence,
)
from .supervisor import (
    AutonomousSupervisor,
)


class AutonomousOperationsControlPlane:
    """
    Supervisory plane above the hardened distributed runtime.

    It does not modify workflow-control, persistence, or distributed
    execution internals. It observes and drives them through their
    public contracts.
    """

    def __init__(
        self,
        *,
        tenant_id: str,
        runtime,
        state_store,
        execution_store,
        actor_id: str = "goat-autonomous-ops",
        cadence: OpsCadence | None = None,
        queue_policy: QueuePressurePolicy | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.runtime = runtime

        self.repository = OpsRepository(
            state_store,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )

        self.circuits = CircuitBreakerManager(
            self.repository
        )

        self.recovery = RecoverySweeper(
            tenant_id=tenant_id,
            state_store=state_store,
            runtime=runtime,
        )

        self.supervisor = AutonomousSupervisor(
            tenant_id=tenant_id,
            execution_store=execution_store,
            repository=self.repository,
            circuit_manager=self.circuits,
            queue_policy=queue_policy,
        )

        self.scheduler = DurableOpsScheduler(
            self.repository,
            cadence=cadence,
        )

    def run_worker(
        self,
        worker,
        *,
        now=None,
    ):
        timestamp = normalize_time(
            now
        )

        cycle = worker.run_once(
            now=timestamp
        )

        self.supervisor.heartbeat(
            worker,
            cycle=cycle,
            now=timestamp,
        )

        return cycle

    def run_cycle(
        self,
        *,
        workers=(),
        now=None,
    ) -> OpsCycleResult:
        timestamp = normalize_time(
            now
        )

        scheduler_state = (
            self.scheduler.load()
        )

        worker_cycles: list[
            tuple[str, object]
        ] = []

        for worker in workers:
            cycle = self.run_worker(
                worker,
                now=timestamp,
            )

            worker_cycles.append(
                (
                    worker.worker_id,
                    cycle,
                )
            )

        recovery_due = (
            self.scheduler.recovery_due(
                scheduler_state,
                now=timestamp,
            )
        )

        health_due = (
            self.scheduler.health_due(
                scheduler_state,
                now=timestamp,
            )
        )

        recovery_result: (
            RecoverySweepResult | None
        ) = None

        if recovery_due:
            recovery_result = (
                self.recovery.run()
            )

        recovery_failures = (
            ()
            if recovery_result is None
            else recovery_result.failures
        )

        snapshot = (
            self.supervisor.snapshot(
                recovery_failures=(
                    recovery_failures
                ),
                now=timestamp,
            )
        )

        self.scheduler.commit_cycle(
            scheduler_state,
            recovery_ran=recovery_due,
            health_ran=health_due,
            now=timestamp,
        )

        return OpsCycleResult(
            snapshot=snapshot,
            recovery=recovery_result,
            worker_cycles=tuple(
                worker_cycles
            ),
        )
