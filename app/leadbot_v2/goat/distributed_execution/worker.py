from __future__ import annotations

import uuid

from datetime import datetime, timedelta, timezone

from leadbot_v2.goat.workflow_control import (
    FailureClass,
)

from .actions import (
    ActionRegistry,
    UnknownActionError,
)

from .models import (
    ActionContext,
    ActionResult,
    EXECUTION_TOPIC,
    IDEMPOTENCY_SCOPE,
    INBOX_CONSUMER,
    WAKE_TOPIC,
    WorkerCycle,
    WorkerLeaseState,
)

from .queue import effect_from_payload


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DistributedWorker:
    """
    Lease-protected worker.

    Fencing tokens are exposed to every action handler so external
    adapters can reject stale workers.

    Persistent idempotency closes the crash window between an action
    result and workflow-state acknowledgement.
    """

    def __init__(
        self,
        *,
        worker_id: str,
        runtime,
        execution_store,
        actions: ActionRegistry,
        instance_id: str | None = None,
        claim_limit: int = 20,
        claim_lease_seconds: int = 60,
        worker_lease_ttl: timedelta = timedelta(
            seconds=120
        ),
    ) -> None:
        if not worker_id.strip():
            raise ValueError(
                "worker_id cannot be blank"
            )

        self.worker_id = worker_id

        self.instance_id = (
            instance_id
            or uuid.uuid4().hex
        )

        self.runtime = runtime
        self.store = execution_store
        self.actions = actions

        self.claim_limit = claim_limit
        self.claim_lease_seconds = claim_lease_seconds
        self.worker_lease_ttl = worker_lease_ttl

        self._lease: WorkerLeaseState | None = None

    @property
    def claim_owner(
        self,
    ) -> str:
        return (
            f"{self.worker_id}:"
            f"{self.instance_id}"
        )

    def ensure_worker_lease(
        self,
        *,
        now=None,
    ) -> WorkerLeaseState:
        timestamp = now or _utcnow()

        lease_name = (
            "goat-worker:"
            f"{self.worker_id}"
        )

        if self._lease is None:
            lease = self.store.acquire_lease(
                lease_name=lease_name,
                owner_id=self.instance_id,
                ttl=self.worker_lease_ttl,
                now=timestamp,
            )

        else:
            lease = self.store.renew_lease(
                lease_name=lease_name,
                owner_id=self.instance_id,
                fencing_token=(
                    self._lease.fencing_token
                ),
                ttl=self.worker_lease_ttl,
                now=timestamp,
            )

        self._lease = WorkerLeaseState(
            lease_name=lease.lease_name,
            owner_id=lease.owner_id,
            fencing_token=int(
                lease.fencing_token
            ),
            expires_at=lease.expires_at,
        )

        return self._lease

    def run_once(
        self,
        *,
        now=None,
    ) -> WorkerCycle:
        timestamp = now or _utcnow()

        lease = self.ensure_worker_lease(
            now=timestamp
        )

        messages = self.store.claim_outbox(
            worker_id=self.claim_owner,
            limit=self.claim_limit,
            lease_seconds=self.claim_lease_seconds,
            now=timestamp,
        )

        claimed = len(messages)

        completed = 0
        failed = 0
        stale = 0
        replayed = 0
        wakes = 0

        for message in messages:
            try:
                if message.topic == WAKE_TOPIC:
                    self._process_wake(
                        message,
                        now=timestamp,
                    )

                    self.store.record_inbox(
                        tenant_id=message.tenant_id,
                        consumer=INBOX_CONSUMER,
                        message_id=message.outbox_id,
                        payload={
                            "topic": message.topic,
                            "aggregate_id": (
                                message.aggregate_id
                            ),
                        },
                    )

                    self.store.complete_outbox(
                        outbox_id=message.outbox_id,
                        worker_id=self.claim_owner,
                    )

                    completed += 1
                    wakes += 1

                    continue

                if message.topic != EXECUTION_TOPIC:
                    raise RuntimeError(
                        "unexpected topic in dedicated "
                        "execution store: "
                        f"{message.topic}"
                    )

                did_replay, was_stale = (
                    self._process_effect(
                        message,
                        fencing_token=(
                            lease.fencing_token
                        ),
                        now=timestamp,
                    )
                )

                self.store.record_inbox(
                    tenant_id=message.tenant_id,
                    consumer=INBOX_CONSUMER,
                    message_id=message.outbox_id,
                    payload={
                        "topic": message.topic,
                        "aggregate_id": (
                            message.aggregate_id
                        ),
                    },
                )

                self.store.complete_outbox(
                    outbox_id=message.outbox_id,
                    worker_id=self.claim_owner,
                )

                completed += 1

                if did_replay:
                    replayed += 1

                if was_stale:
                    stale += 1

            except Exception:
                self.store.fail_outbox(
                    outbox_id=message.outbox_id,
                    worker_id=self.claim_owner,
                    max_attempts=5,
                    now=timestamp,
                )

                failed += 1

        return WorkerCycle(
            claimed=claimed,
            completed=completed,
            failed=failed,
            stale=stale,
            replayed=replayed,
            wakes=wakes,
        )

    def _process_wake(
        self,
        message,
        *,
        now,
    ) -> None:
        payload = dict(message.payload)

        workflow_id = payload["workflow_id"]

        self.runtime.advance(
            workflow_id,
            now=now,
        )

    def _process_effect(
        self,
        message,
        *,
        fencing_token: int,
        now,
    ) -> tuple[bool, bool]:
        payload = dict(message.payload)

        effect = effect_from_payload(payload)

        # This expires timed-out effects before an old worker can act.
        self.runtime.advance(
            effect.workflow_id,
            now=now,
        )

        if not self.runtime.effect_is_active(
            workflow_id=effect.workflow_id,
            effect_id=effect.effect_id,
        ):
            return False, True

        request_payload = {
            "effect_id": effect.effect_id,
            "workflow_id": effect.workflow_id,
            "step_id": effect.step_id,
            "action": effect.action,
            "idempotency_key": effect.idempotency_key,
            "payload": dict(effect.payload),
        }

        cached = self.store.get_idempotency(
            tenant_id=effect.tenant_id,
            scope=IDEMPOTENCY_SCOPE,
            key=effect.effect_id,
            request_payload=request_payload,
            now=now,
        )

        replayed = cached is not None

        if cached is not None:
            result = ActionResult.from_dict(
                cached
            )

        else:
            context = ActionContext(
                workflow_id=effect.workflow_id,
                tenant_id=effect.tenant_id,
                step_id=effect.step_id or "",
                effect_id=effect.effect_id,
                action=effect.action,
                attempt=int(
                    effect.payload.get(
                        "attempt",
                        1,
                    )
                ),
                idempotency_key=(
                    effect.idempotency_key
                ),
                worker_id=self.worker_id,
                worker_instance_id=self.instance_id,
                fencing_token=fencing_token,
                payload=dict(effect.payload),
            )

            try:
                result = self.actions.execute(
                    context
                )

            except UnknownActionError as exc:
                result = ActionResult.failed(
                    failure_class=(
                        FailureClass.VALIDATION
                    ),
                    error=(
                        "unregistered action: "
                        f"{exc}"
                    ),
                )

            except Exception as exc:
                # Handler exceptions are reported into workflow
                # recovery rather than silently marooning a RUNNING
                # effect in the transport layer.
                result = ActionResult.failed(
                    failure_class=(
                        FailureClass.EXTERNAL
                    ),
                    error=(
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
                )

            self.store.save_idempotency(
                tenant_id=effect.tenant_id,
                scope=IDEMPOTENCY_SCOPE,
                key=effect.effect_id,
                request_payload=request_payload,
                response_payload=result.to_dict(),
            )

        self.runtime.complete_and_advance(
            workflow_id=effect.workflow_id,
            effect_id=effect.effect_id,
            success=result.success,
            actor_id=self.claim_owner,
            output=dict(result.output),
            failure_class=result.failure_class,
            error=result.error,
            now=now,
        )

        return replayed, False
