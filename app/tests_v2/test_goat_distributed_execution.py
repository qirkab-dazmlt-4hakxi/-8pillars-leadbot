from __future__ import annotations

import unittest

from copy import deepcopy
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from types import SimpleNamespace

from leadbot_v2.goat.distributed_execution import (
    ActionRegistry,
    ActionResult,
    DistributedWorker,
    DistributedWorkflowRuntime,
)

from leadbot_v2.goat.workflow_control import (
    FailureClass,
    RetryPolicy,
    StepSpec,
    StepStatus,
    WorkflowConcurrencyConflict,
    WorkflowSpec,
    WorkflowStatus,
)


BASE = datetime(
    2026,
    8,
    16,
    3,
    30,
    tzinfo=timezone.utc,
)


class FakeOccError(RuntimeError):
    pass


class FakeStore:
    def __init__(
        self,
    ) -> None:
        self.entities = {}
        self.outbox = {}
        self.outbox_dedupe = {}
        self.idempotency = {}
        self.inbox = set()
        self.leases = {}

        self.next_outbox = 1
        self.next_fencing = 1

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

        current = self.entities.get(key)

        if (
            current is not None
            and expected_version is not None
            and current.version != expected_version
        ):
            raise FakeOccError(
                "optimistic concurrency conflict"
            )

        version = (
            1
            if current is None
            else current.version + 1
        )

        record = SimpleNamespace(
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            version=version,
            payload=deepcopy(payload),
        )

        self.entities[key] = record

        return deepcopy(record)

    def enqueue_outbox(
        self,
        *,
        tenant_id,
        topic,
        payload,
        aggregate_type=None,
        aggregate_id=None,
        dedupe_key=None,
        available_at=None,
    ):
        if (
            dedupe_key
            and dedupe_key in self.outbox_dedupe
        ):
            return self.outbox_dedupe[
                dedupe_key
            ]

        outbox_id = (
            f"o{self.next_outbox}"
        )

        self.next_outbox += 1

        message = SimpleNamespace(
            outbox_id=outbox_id,
            tenant_id=tenant_id,
            topic=topic,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=deepcopy(payload),
            attempts=0,
            available_at=(
                available_at or BASE
            ),
            locked_by=None,
            lease_expires_at=None,
        )

        self.outbox[outbox_id] = message

        if dedupe_key:
            self.outbox_dedupe[
                dedupe_key
            ] = outbox_id

        return outbox_id

    def claim_outbox(
        self,
        *,
        worker_id,
        limit=20,
        lease_seconds=60,
        now=None,
    ):
        timestamp = now or BASE

        claimed = []

        for message in list(
            self.outbox.values()
        ):
            if len(claimed) >= limit:
                break

            if message.available_at > timestamp:
                continue

            if (
                message.locked_by is not None
                and message.lease_expires_at
                is not None
                and message.lease_expires_at
                > timestamp
            ):
                continue

            message.locked_by = worker_id

            message.lease_expires_at = (
                timestamp
                + timedelta(
                    seconds=lease_seconds
                )
            )

            message.attempts += 1

            claimed.append(
                deepcopy(message)
            )

        return tuple(claimed)

    def complete_outbox(
        self,
        *,
        outbox_id,
        worker_id,
    ):
        message = self.outbox[
            outbox_id
        ]

        if message.locked_by != worker_id:
            raise RuntimeError(
                "outbox lease lost"
            )

        del self.outbox[
            outbox_id
        ]

    def fail_outbox(
        self,
        *,
        outbox_id,
        worker_id,
        max_attempts=5,
        now=None,
    ):
        message = self.outbox[
            outbox_id
        ]

        if message.locked_by != worker_id:
            raise RuntimeError(
                "outbox lease lost"
            )

        if message.attempts >= max_attempts:
            del self.outbox[
                outbox_id
            ]

            return

        message.locked_by = None
        message.lease_expires_at = None

        message.available_at = (
            now or BASE
        ) + timedelta(seconds=1)

    def record_inbox(
        self,
        *,
        tenant_id,
        consumer,
        message_id,
        payload,
    ):
        key = (
            tenant_id,
            consumer,
            message_id,
        )

        if key in self.inbox:
            return False

        self.inbox.add(key)

        return True

    def save_idempotency(
        self,
        *,
        tenant_id,
        scope,
        key,
        request_payload,
        response_payload,
        ttl=timedelta(days=1),
    ):
        identity = (
            tenant_id,
            scope,
            key,
        )

        self.idempotency[
            identity
        ] = {
            "request": deepcopy(
                request_payload
            ),
            "response": deepcopy(
                response_payload
            ),
        }

    def get_idempotency(
        self,
        *,
        tenant_id,
        scope,
        key,
        request_payload,
        now=None,
    ):
        item = self.idempotency.get(
            (
                tenant_id,
                scope,
                key,
            )
        )

        if item is None:
            return None

        if item["request"] != request_payload:
            raise RuntimeError(
                "idempotency payload conflict"
            )

        return deepcopy(
            item["response"]
        )

    def acquire_lease(
        self,
        *,
        lease_name,
        owner_id,
        ttl,
        now=None,
    ):
        timestamp = now or BASE

        current = self.leases.get(
            lease_name
        )

        if (
            current is not None
            and current.expires_at > timestamp
            and current.owner_id != owner_id
        ):
            raise RuntimeError(
                "lease busy"
            )

        token = self.next_fencing
        self.next_fencing += 1

        lease = SimpleNamespace(
            lease_name=lease_name,
            owner_id=owner_id,
            fencing_token=token,
            expires_at=(
                timestamp + ttl
            ),
        )

        self.leases[
            lease_name
        ] = lease

        return deepcopy(lease)

    def renew_lease(
        self,
        *,
        lease_name,
        owner_id,
        fencing_token,
        ttl,
        now=None,
    ):
        timestamp = now or BASE

        current = self.leases[
            lease_name
        ]

        if (
            current.owner_id != owner_id
            or current.fencing_token
            != fencing_token
            or current.expires_at <= timestamp
        ):
            raise RuntimeError(
                "lease lost"
            )

        current.expires_at = (
            timestamp + ttl
        )

        return deepcopy(current)


def retry_policy(
    attempts=3,
    delay=1,
):
    return RetryPolicy(
        max_attempts=attempts,
        base_delay_seconds=delay,
        multiplier=2,
        max_delay_seconds=30,
        jitter_fraction=0,
    )


def one_step_spec(
    *,
    retry_attempts=3,
):
    return WorkflowSpec(
        name="distributed",
        version=1,
        steps=(
            StepSpec(
                step_id="qualify",
                action="lead.qualify",
                retry_policy=retry_policy(
                    attempts=retry_attempts
                ),
            ),
        ),
    )


class RepositoryTests(
    unittest.TestCase
):
    def test_state_survives_runtime_restart(
        self,
    ):
        state_store = FakeStore()
        queue_store = FakeStore()

        runtime1 = DistributedWorkflowRuntime(
            tenant_id="t1",
            state_store=state_store,
            execution_store=queue_store,
        )

        runtime1.register(
            one_step_spec()
        )

        runtime1.start(
            spec_name="distributed",
            spec_version=1,
            workflow_id="w1",
            actor_id="owner",
            now=BASE,
        )

        runtime1.advance(
            "w1",
            now=BASE,
        )

        runtime2 = DistributedWorkflowRuntime(
            tenant_id="t1",
            state_store=state_store,
            execution_store=queue_store,
        )

        runtime2.register(
            one_step_spec()
        )

        restored = runtime2.load(
            "w1"
        )

        self.assertEqual(
            restored.status,
            WorkflowStatus.RUNNING,
        )

        self.assertEqual(
            restored.step_runs[
                "qualify"
            ].attempt,
            1,
        )

    def test_occ_conflict_maps_to_workflow_error(
        self,
    ):
        state_store = FakeStore()
        queue_store = FakeStore()

        runtime = DistributedWorkflowRuntime(
            tenant_id="t1",
            state_store=state_store,
            execution_store=queue_store,
        )

        runtime.register(
            one_step_spec()
        )

        runtime.start(
            spec_name="distributed",
            spec_version=1,
            workflow_id="w1",
            actor_id="owner",
            now=BASE,
        )

        first = runtime.load("w1")
        second = runtime.load("w1")

        first.metadata["a"] = 1

        runtime.repository.save(
            first,
            expected_revision=first.revision,
        )

        second.metadata["b"] = 2

        with self.assertRaises(
            WorkflowConcurrencyConflict
        ):
            runtime.repository.save(
                second,
                expected_revision=(
                    second.revision
                ),
            )


class QueueTests(
    unittest.TestCase
):
    def test_reconciliation_is_deduplicated(
        self,
    ):
        state_store = FakeStore()
        queue_store = FakeStore()

        runtime = DistributedWorkflowRuntime(
            tenant_id="t1",
            state_store=state_store,
            execution_store=queue_store,
        )

        runtime.register(
            one_step_spec()
        )

        runtime.start(
            spec_name="distributed",
            spec_version=1,
            workflow_id="w1",
            actor_id="owner",
            now=BASE,
        )

        first = runtime.advance(
            "w1",
            now=BASE,
        )

        second = runtime.reconcile(
            "w1"
        )

        self.assertEqual(
            len(first.outbox_ids),
            1,
        )

        self.assertEqual(
            first.outbox_ids[0],
            second.outbox_ids[0],
        )

        self.assertEqual(
            len(queue_store.outbox),
            1,
        )


class WorkerTests(
    unittest.TestCase
):
    def build(
        self,
        *,
        retry_attempts=3,
    ):
        state_store = FakeStore()
        queue_store = FakeStore()

        runtime = DistributedWorkflowRuntime(
            tenant_id="t1",
            state_store=state_store,
            execution_store=queue_store,
        )

        runtime.register(
            one_step_spec(
                retry_attempts=retry_attempts
            )
        )

        registry = ActionRegistry()

        worker = DistributedWorker(
            worker_id="worker-a",
            runtime=runtime,
            execution_store=queue_store,
            actions=registry,
            instance_id="instance-a",
        )

        return (
            runtime,
            state_store,
            queue_store,
            registry,
            worker,
        )

    def test_successful_execution(
        self,
    ):
        (
            runtime,
            _,
            queue_store,
            registry,
            worker,
        ) = self.build()

        calls = []

        def handler(context):
            calls.append(context)

            return ActionResult.ok(
                {
                    "score": 95,
                }
            )

        registry.register(
            "lead.qualify",
            handler,
        )

        runtime.start(
            spec_name="distributed",
            spec_version=1,
            workflow_id="w1",
            actor_id="owner",
            now=BASE,
        )

        runtime.advance(
            "w1",
            now=BASE,
        )

        cycle = worker.run_once(
            now=BASE
        )

        state = runtime.load(
            "w1"
        )

        self.assertEqual(
            cycle.completed,
            1,
        )

        self.assertEqual(
            len(calls),
            1,
        )

        self.assertEqual(
            state.status,
            WorkflowStatus.SUCCEEDED,
        )

        self.assertEqual(
            len(queue_store.outbox),
            0,
        )

    def test_idempotent_result_replay_does_not_reexecute(
        self,
    ):
        (
            runtime,
            _,
            queue_store,
            registry,
            worker,
        ) = self.build()

        calls = []

        def handler(context):
            calls.append(
                context.effect_id
            )

            return ActionResult.ok(
                {
                    "ok": True,
                }
            )

        registry.register(
            "lead.qualify",
            handler,
        )

        runtime.start(
            spec_name="distributed",
            spec_version=1,
            workflow_id="w1",
            actor_id="owner",
            now=BASE,
        )

        runtime.advance(
            "w1",
            now=BASE,
        )

        message = next(
            iter(
                queue_store.outbox.values()
            )
        )

        request_payload = {
            "effect_id": message.payload[
                "effect_id"
            ],
            "workflow_id": "w1",
            "step_id": "qualify",
            "action": "lead.qualify",
            "idempotency_key": message.payload[
                "idempotency_key"
            ],
            "payload": dict(
                message.payload[
                    "payload"
                ]
            ),
        }

        queue_store.save_idempotency(
            tenant_id="t1",
            scope="goat.workflow.execution",
            key=message.payload[
                "effect_id"
            ],
            request_payload=request_payload,
            response_payload=(
                ActionResult.ok(
                    {
                        "cached": True,
                    }
                ).to_dict()
            ),
        )

        cycle = worker.run_once(
            now=BASE
        )

        self.assertEqual(
            cycle.replayed,
            1,
        )

        self.assertEqual(
            calls,
            [],
        )

        self.assertEqual(
            runtime.load(
                "w1"
            ).status,
            WorkflowStatus.SUCCEEDED,
        )

    def test_transient_failure_creates_durable_wake(
        self,
    ):
        (
            runtime,
            _,
            queue_store,
            registry,
            worker,
        ) = self.build(
            retry_attempts=2
        )

        registry.register(
            "lead.qualify",
            lambda context: (
                ActionResult.failed(
                    failure_class=(
                        FailureClass.TRANSIENT
                    ),
                    error="temporary",
                )
            ),
        )

        runtime.start(
            spec_name="distributed",
            spec_version=1,
            workflow_id="w1",
            actor_id="owner",
            now=BASE,
        )

        runtime.advance(
            "w1",
            now=BASE,
        )

        worker.run_once(
            now=BASE
        )

        state = runtime.load(
            "w1"
        )

        self.assertEqual(
            state.step_runs[
                "qualify"
            ].status,
            StepStatus.WAITING_RETRY,
        )

        topics = {
            message.topic
            for message
            in queue_store.outbox.values()
        }

        self.assertIn(
            "goat.workflow.wake",
            topics,
        )

    def test_stale_effect_is_suppressed(
        self,
    ):
        (
            runtime,
            _,
            queue_store,
            registry,
            worker,
        ) = self.build()

        calls = []

        registry.register(
            "lead.qualify",
            lambda context: (
                calls.append(context)
                or ActionResult.ok()
            ),
        )

        runtime.start(
            spec_name="distributed",
            spec_version=1,
            workflow_id="w1",
            actor_id="owner",
            now=BASE,
        )

        runtime.advance(
            "w1",
            now=BASE,
        )

        state = runtime.load("w1")

        effect_id = state.step_runs[
            "qualify"
        ].active_effect_id

        self.assertIsNotNone(
            effect_id
        )

        # Simulate a workflow decision making the old message stale.
        state.step_runs[
            "qualify"
        ].active_effect_id = None

        state.step_runs[
            "qualify"
        ].status = StepStatus.FAILED

        state.status = WorkflowStatus.FAILED

        runtime.repository.save(
            state,
            expected_revision=state.revision,
        )

        cycle = worker.run_once(
            now=BASE
        )

        self.assertEqual(
            cycle.stale,
            1,
        )

        self.assertEqual(
            calls,
            [],
        )

    def test_worker_has_fencing_token(
        self,
    ):
        (
            _,
            _,
            _,
            _,
            worker,
        ) = self.build()

        lease = worker.ensure_worker_lease(
            now=BASE
        )

        self.assertGreater(
            lease.fencing_token,
            0,
        )

    def test_unregistered_action_fails_workflow_not_transport(
        self,
    ):
        (
            runtime,
            _,
            _,
            _,
            worker,
        ) = self.build(
            retry_attempts=1
        )

        runtime.start(
            spec_name="distributed",
            spec_version=1,
            workflow_id="w1",
            actor_id="owner",
            now=BASE,
        )

        runtime.advance(
            "w1",
            now=BASE,
        )

        cycle = worker.run_once(
            now=BASE
        )

        self.assertEqual(
            cycle.completed,
            1,
        )

        self.assertEqual(
            runtime.load(
                "w1"
            ).status,
            WorkflowStatus.FAILED,
        )


if __name__ == "__main__":
    unittest.main()
