from __future__ import annotations

import unittest

from copy import deepcopy
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from types import SimpleNamespace

from leadbot_v2.goat.autonomous_ops import (
    AutonomousOperationsControlPlane,
    AutonomousSupervisor,
    CircuitBreakerManager,
    CircuitConfig,
    CircuitState,
    DurableOpsScheduler,
    HealthLevel,
    OpsCadence,
    OpsRepository,
    QueuePressurePolicy,
    RecoverySweeper,
)

from leadbot_v2.goat.distributed_execution import (
    WorkerCycle,
)


BASE = datetime(
    2026,
    8,
    16,
    4,
    30,
    tzinfo=timezone.utc,
)


class FakeStore:
    def __init__(
        self,
        *,
        pending=0,
    ) -> None:
        self.entities = {}
        self.pending = pending

    def get_entity(
        self,
        *,
        tenant_id,
        entity_type,
        entity_id,
        include_deleted=False,
    ):
        return deepcopy(
            self.entities.get(
                (
                    tenant_id,
                    entity_type,
                    entity_id,
                )
            )
        )

    def list_entities(
        self,
        *,
        tenant_id,
        entity_type,
        include_deleted=False,
    ):
        records = []

        for (
            row_tenant,
            row_type,
            _,
        ), record in self.entities.items():
            if (
                row_tenant == tenant_id
                and row_type == entity_type
            ):
                records.append(
                    deepcopy(record)
                )

        records.sort(
            key=lambda row: row.entity_id
        )

        return tuple(records)

    def put_entity(
        self,
        *,
        tenant_id,
        entity_type,
        entity_id,
        payload,
        actor_id,
        expected_version=None,
    ):
        key = (
            tenant_id,
            entity_type,
            entity_id,
        )

        current = self.entities.get(
            key
        )

        if current is None:
            if expected_version is not None:
                raise RuntimeError(
                    "expected version conflict"
                )

            version = 1

        else:
            if (
                expected_version
                != current.version
            ):
                raise RuntimeError(
                    "expected version conflict"
                )

            version = (
                current.version + 1
            )

        record = SimpleNamespace(
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            version=version,
            payload=deepcopy(
                payload
            ),
        )

        self.entities[
            key
        ] = record

        return deepcopy(
            record
        )

    def health(
        self,
    ):
        return SimpleNamespace(
            pending_outbox_count=(
                self.pending
            )
        )


class FakeRuntime:
    def __init__(
        self,
    ) -> None:
        self.reconciled = []

    def reconcile(
        self,
        workflow_id,
    ):
        self.reconciled.append(
            workflow_id
        )

        if workflow_id == "explode":
            raise RuntimeError(
                "simulated recovery failure"
            )

        return SimpleNamespace(
            workflow_id=workflow_id,
            outbox_ids=(),
        )


class FakeWorker:
    def __init__(
        self,
        *,
        worker_id="worker-a",
        instance_id="instance-a",
    ) -> None:
        self.worker_id = worker_id
        self.instance_id = instance_id

        self.fencing_token = 7

        self.runs = 0

    def ensure_worker_lease(
        self,
        *,
        now=None,
    ):
        return SimpleNamespace(
            lease_name=(
                f"goat-worker:"
                f"{self.worker_id}"
            ),
            owner_id=self.instance_id,
            fencing_token=(
                self.fencing_token
            ),
            expires_at=(
                now
                + timedelta(
                    seconds=120
                )
            ),
        )

    def run_once(
        self,
        *,
        now=None,
    ):
        self.runs += 1

        return WorkerCycle(
            claimed=3,
            completed=2,
            failed=1,
            stale=0,
            replayed=1,
            wakes=0,
        )


def put_workflow(
    store,
    *,
    workflow_id,
    status,
):
    store.put_entity(
        tenant_id="t1",
        entity_type="goat.workflow",
        entity_id=workflow_id,
        payload={
            "status": status,
        },
        actor_id="test",
    )


class HeartbeatTests(
    unittest.TestCase
):
    def test_heartbeat_is_durable(
        self,
    ):
        state_store = FakeStore()

        repository = OpsRepository(
            state_store,
            tenant_id="t1",
        )

        supervisor = AutonomousSupervisor(
            tenant_id="t1",
            execution_store=FakeStore(),
            repository=repository,
            circuit_manager=(
                CircuitBreakerManager(
                    repository
                )
            ),
        )

        worker = FakeWorker()

        heartbeat = supervisor.heartbeat(
            worker,
            cycle=WorkerCycle(
                claimed=5,
                completed=4,
                failed=1,
            ),
            now=BASE,
        )

        stored = (
            repository
            .list_heartbeats()
        )

        self.assertEqual(
            len(stored),
            1,
        )

        self.assertEqual(
            heartbeat.fencing_token,
            7,
        )

        self.assertEqual(
            stored[0].claimed,
            5,
        )

    def test_stale_worker_detection_uses_latest_instance(
        self,
    ):
        state_store = FakeStore()

        repository = OpsRepository(
            state_store,
            tenant_id="t1",
        )

        supervisor = AutonomousSupervisor(
            tenant_id="t1",
            execution_store=FakeStore(),
            repository=repository,
            circuit_manager=(
                CircuitBreakerManager(
                    repository
                )
            ),
            heartbeat_ttl=timedelta(
                seconds=30
            ),
        )

        old = FakeWorker(
            instance_id="old"
        )

        new = FakeWorker(
            instance_id="new"
        )

        supervisor.heartbeat(
            old,
            now=BASE,
        )

        supervisor.heartbeat(
            new,
            now=(
                BASE
                + timedelta(
                    seconds=20
                )
            ),
        )

        stale = supervisor.stale_workers(
            now=(
                BASE
                + timedelta(
                    seconds=35
                )
            )
        )

        self.assertEqual(
            stale,
            (),
        )

        stale = supervisor.stale_workers(
            now=(
                BASE
                + timedelta(
                    seconds=55
                )
            )
        )

        self.assertEqual(
            stale,
            (
                "worker-a",
            ),
        )


class QueuePressureTests(
    unittest.TestCase
):
    def test_pressure_levels(
        self,
    ):
        policy = QueuePressurePolicy(
            soft_limit=10,
            hard_limit=20,
        )

        self.assertEqual(
            policy.classify(
                0
            ).level,
            HealthLevel.HEALTHY,
        )

        self.assertEqual(
            policy.classify(
                10
            ).level,
            HealthLevel.DEGRADED,
        )

        self.assertEqual(
            policy.classify(
                20
            ).level,
            HealthLevel.CRITICAL,
        )


class CircuitTests(
    unittest.TestCase
):
    def build(
        self,
    ):
        repository = OpsRepository(
            FakeStore(),
            tenant_id="t1",
        )

        manager = CircuitBreakerManager(
            repository,
            config=CircuitConfig(
                failure_threshold=2,
                recovery_timeout_seconds=10,
                half_open_success_threshold=1,
            ),
        )

        return repository, manager

    def test_circuit_opens_blocks_half_opens_and_closes(
        self,
    ):
        _, manager = self.build()

        self.assertTrue(
            manager.allow(
                "twilio",
                now=BASE,
            )
        )

        first = manager.record_failure(
            "twilio",
            now=BASE,
        )

        self.assertEqual(
            first.state,
            CircuitState.CLOSED,
        )

        second = manager.record_failure(
            "twilio",
            now=BASE,
        )

        self.assertEqual(
            second.state,
            CircuitState.OPEN,
        )

        self.assertFalse(
            manager.allow(
                "twilio",
                now=(
                    BASE
                    + timedelta(
                        seconds=5
                    )
                ),
            )
        )

        self.assertTrue(
            manager.allow(
                "twilio",
                now=(
                    BASE
                    + timedelta(
                        seconds=10
                    )
                ),
            )
        )

        half = manager.repository.load_circuit(
            "twilio"
        )

        self.assertEqual(
            half.state,
            CircuitState.HALF_OPEN,
        )

        closed = manager.record_success(
            "twilio",
            now=(
                BASE
                + timedelta(
                    seconds=10
                )
            ),
        )

        self.assertEqual(
            closed.state,
            CircuitState.CLOSED,
        )

    def test_open_circuit_surfaces_in_health(
        self,
    ):
        repository, manager = self.build()

        manager.record_failure(
            "search",
            now=BASE,
        )

        manager.record_failure(
            "search",
            now=BASE,
        )

        supervisor = AutonomousSupervisor(
            tenant_id="t1",
            execution_store=FakeStore(),
            repository=repository,
            circuit_manager=manager,
        )

        snapshot = supervisor.snapshot(
            now=BASE,
        )

        self.assertEqual(
            snapshot.health,
            HealthLevel.DEGRADED,
        )

        self.assertEqual(
            snapshot.open_circuits,
            (
                "search",
            ),
        )


class RecoveryTests(
    unittest.TestCase
):
    def test_only_recoverable_workflows_reconciled(
        self,
    ):
        store = FakeStore()
        runtime = FakeRuntime()

        put_workflow(
            store,
            workflow_id="running",
            status="running",
        )

        put_workflow(
            store,
            workflow_id="retrying",
            status="running",
        )

        put_workflow(
            store,
            workflow_id="paused",
            status="paused",
        )

        put_workflow(
            store,
            workflow_id="quarantine",
            status="quarantined",
        )

        put_workflow(
            store,
            workflow_id="done",
            status="succeeded",
        )

        sweep = RecoverySweeper(
            tenant_id="t1",
            state_store=store,
            runtime=runtime,
        ).run()

        self.assertEqual(
            sweep.scanned,
            5,
        )

        self.assertEqual(
            sweep.eligible,
            2,
        )

        self.assertEqual(
            sweep.reconciled,
            2,
        )

        self.assertEqual(
            set(
                runtime.reconciled
            ),
            {
                "running",
                "retrying",
            },
        )

    def test_recovery_failure_reported_not_hidden(
        self,
    ):
        store = FakeStore()
        runtime = FakeRuntime()

        put_workflow(
            store,
            workflow_id="explode",
            status="running",
        )

        result = RecoverySweeper(
            tenant_id="t1",
            state_store=store,
            runtime=runtime,
        ).run()

        self.assertEqual(
            result.reconciled,
            0,
        )

        self.assertEqual(
            len(
                result.failures
            ),
            1,
        )


class SchedulerTests(
    unittest.TestCase
):
    def test_scheduler_cadence_is_durable(
        self,
    ):
        repository = OpsRepository(
            FakeStore(),
            tenant_id="t1",
        )

        scheduler = DurableOpsScheduler(
            repository,
            cadence=OpsCadence(
                recovery_interval_seconds=30,
                health_interval_seconds=10,
            ),
        )

        state = scheduler.load()

        self.assertTrue(
            scheduler.recovery_due(
                state,
                now=BASE,
            )
        )

        self.assertTrue(
            scheduler.health_due(
                state,
                now=BASE,
            )
        )

        state = scheduler.commit_cycle(
            state,
            recovery_ran=True,
            health_ran=True,
            now=BASE,
        )

        self.assertFalse(
            scheduler.recovery_due(
                state,
                now=(
                    BASE
                    + timedelta(
                        seconds=29
                    )
                ),
            )
        )

        self.assertTrue(
            scheduler.health_due(
                state,
                now=(
                    BASE
                    + timedelta(
                        seconds=10
                    )
                ),
            )
        )

        restored = (
            repository
            .load_scheduler()
        )

        self.assertEqual(
            restored.cycle_count,
            1,
        )


class ControlPlaneTests(
    unittest.TestCase
):
    def test_cycle_drives_worker_heartbeat_and_recovery(
        self,
    ):
        state_store = FakeStore()
        execution_store = FakeStore(
            pending=4
        )

        runtime = FakeRuntime()

        put_workflow(
            state_store,
            workflow_id="w1",
            status="running",
        )

        control = (
            AutonomousOperationsControlPlane(
                tenant_id="t1",
                runtime=runtime,
                state_store=state_store,
                execution_store=execution_store,
                cadence=OpsCadence(
                    recovery_interval_seconds=30,
                    health_interval_seconds=10,
                ),
                queue_policy=QueuePressurePolicy(
                    soft_limit=10,
                    hard_limit=20,
                ),
            )
        )

        worker = FakeWorker()

        result = control.run_cycle(
            workers=(
                worker,
            ),
            now=BASE,
        )

        self.assertEqual(
            worker.runs,
            1,
        )

        self.assertEqual(
            result.snapshot.health,
            HealthLevel.HEALTHY,
        )

        self.assertIsNotNone(
            result.recovery
        )

        self.assertEqual(
            result.recovery.reconciled,
            1,
        )

        self.assertEqual(
            len(
                control.repository
                .list_heartbeats()
            ),
            1,
        )

    def test_recovery_failure_makes_system_critical(
        self,
    ):
        state_store = FakeStore()
        execution_store = FakeStore()

        runtime = FakeRuntime()

        put_workflow(
            state_store,
            workflow_id="explode",
            status="running",
        )

        control = (
            AutonomousOperationsControlPlane(
                tenant_id="t1",
                runtime=runtime,
                state_store=state_store,
                execution_store=execution_store,
            )
        )

        result = control.run_cycle(
            now=BASE
        )

        self.assertEqual(
            result.snapshot.health,
            HealthLevel.CRITICAL,
        )

        self.assertEqual(
            len(
                result.snapshot
                .recovery_failures
            ),
            1,
        )

    def test_hard_queue_pressure_is_critical(
        self,
    ):
        state_store = FakeStore()
        execution_store = FakeStore(
            pending=100
        )

        control = (
            AutonomousOperationsControlPlane(
                tenant_id="t1",
                runtime=FakeRuntime(),
                state_store=state_store,
                execution_store=execution_store,
                queue_policy=QueuePressurePolicy(
                    soft_limit=10,
                    hard_limit=50,
                ),
            )
        )

        result = control.run_cycle(
            now=BASE
        )

        self.assertEqual(
            result.snapshot.health,
            HealthLevel.CRITICAL,
        )


if __name__ == "__main__":
    unittest.main()
