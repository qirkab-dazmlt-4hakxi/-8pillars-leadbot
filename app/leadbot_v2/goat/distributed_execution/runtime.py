from __future__ import annotations

from datetime import datetime, timezone

from leadbot_v2.goat.workflow_control import (
    CompensationStatus,
    Effect,
    EffectKind,
    FailureClass,
    StepStatus,
    WorkflowService,
    WorkflowSpec,
)

from .models import DispatchBatch

from .persistence import (
    EnterpriseWorkflowRepository,
    TenantBoundWorkflowRepository,
)

from .queue import DurableExecutionQueue


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DistributedWorkflowRuntime:
    """
    Durable bridge between deterministic workflow state and the
    enterprise execution outbox.

    Workflow state and execution transport deliberately remain
    separate boundaries. Reconciliation closes the crash window
    between durable state mutation and effect publication.
    """

    def __init__(
        self,
        *,
        tenant_id: str,
        state_store,
        execution_store,
        actor_id: str = "goat-distributed-runtime",
    ) -> None:
        if not tenant_id.strip():
            raise ValueError(
                "tenant_id cannot be blank"
            )

        self.tenant_id = tenant_id

        durable_repository = (
            EnterpriseWorkflowRepository(
                state_store,
                actor_id=actor_id,
            )
        )

        bound_repository = (
            TenantBoundWorkflowRepository(
                durable_repository,
                tenant_id=tenant_id,
            )
        )

        self.repository = bound_repository

        self.service = WorkflowService(
            bound_repository
        )

        self.execution_queue = DurableExecutionQueue(
            execution_store
        )

        self.execution_store = execution_store

        self._specs: dict[
            tuple[str, int],
            WorkflowSpec,
        ] = {}

    def register(
        self,
        spec: WorkflowSpec,
    ) -> None:
        self.service.register(spec)

        self._specs[spec.key] = spec

    def start(
        self,
        *,
        spec_name: str,
        spec_version: int,
        workflow_id: str,
        actor_id: str,
        metadata=None,
        now=None,
    ):
        return self.service.start(
            spec_name=spec_name,
            spec_version=spec_version,
            workflow_id=workflow_id,
            tenant_id=self.tenant_id,
            actor_id=actor_id,
            metadata=metadata,
            now=now,
        )

    def load(
        self,
        workflow_id: str,
    ):
        return self.repository.load(
            workflow_id
        )

    def advance(
        self,
        workflow_id: str,
        *,
        now=None,
    ) -> DispatchBatch:
        timestamp = now or _utcnow()

        state, effects = self.service.tick(
            workflow_id,
            now=timestamp,
        )

        outbox_ids: list[str] = []
        control_effect_ids: list[str] = []

        for effect in effects:
            if effect.kind in {
                EffectKind.RUN_STEP,
                EffectKind.RUN_COMPENSATION,
            }:
                outbox_ids.append(
                    self.execution_queue.enqueue_effect(
                        effect
                    )
                )

            else:
                control_effect_ids.append(
                    effect.effect_id
                )

        reconciled = self.reconcile(
            workflow_id
        )

        for outbox_id in reconciled.outbox_ids:
            if outbox_id not in outbox_ids:
                outbox_ids.append(outbox_id)

        wake_outbox_id = self._schedule_wake(
            state
        )

        return DispatchBatch(
            workflow_id=workflow_id,
            outbox_ids=tuple(outbox_ids),
            control_effect_ids=tuple(
                control_effect_ids
            ),
            wake_outbox_id=wake_outbox_id,
        )

    def complete_and_advance(
        self,
        *,
        workflow_id: str,
        effect_id: str,
        success: bool,
        actor_id: str,
        output=None,
        failure_class: FailureClass = FailureClass.UNKNOWN,
        error: str | None = None,
        now=None,
    ):
        timestamp = now or _utcnow()

        state, accepted = self.service.complete(
            workflow_id,
            effect_id=effect_id,
            success=success,
            actor_id=actor_id,
            output=output,
            failure_class=failure_class,
            error=error,
            now=timestamp,
        )

        batch = self.advance(
            workflow_id,
            now=timestamp,
        )

        return state, accepted, batch

    def effect_is_active(
        self,
        *,
        workflow_id: str,
        effect_id: str,
    ) -> bool:
        state = self.load(workflow_id)

        for runtime in state.step_runs.values():
            if (
                runtime.active_effect_id == effect_id
                and runtime.status
                is StepStatus.RUNNING
            ):
                return True

            if (
                runtime.compensation_effect_id
                == effect_id
                and runtime.compensation_status
                is CompensationStatus.RUNNING
            ):
                return True

        return False

    def reconcile(
        self,
        workflow_id: str,
    ) -> DispatchBatch:
        """
        Republish every execution effect that durable workflow state
        says is active.

        Outbox dedupe makes this safe after crashes, process restarts
        and repeated reconciliation sweeps.
        """

        state = self.load(workflow_id)

        spec = self._specs.get(
            (
                state.spec_name,
                state.spec_version,
            )
        )

        if spec is None:
            raise RuntimeError(
                "workflow specification is not registered: "
                f"{state.spec_name}:"
                f"{state.spec_version}"
            )

        step_map = spec.step_map()

        outbox_ids: list[str] = []

        for step_id, runtime in state.step_runs.items():
            step = step_map[step_id]

            if (
                runtime.status
                is StepStatus.RUNNING
                and runtime.active_effect_id
            ):
                effect = Effect(
                    effect_id=runtime.active_effect_id,
                    workflow_id=state.workflow_id,
                    tenant_id=state.tenant_id,
                    kind=EffectKind.RUN_STEP,
                    step_id=step_id,
                    action=step.action,
                    idempotency_key=(
                        f"workflow:"
                        f"{state.workflow_id}:"
                        f"{step_id}:"
                        f"{runtime.attempt}"
                    ),
                    payload={
                        "workflow_id": state.workflow_id,
                        "tenant_id": state.tenant_id,
                        "step_id": step_id,
                        "attempt": runtime.attempt,
                        "metadata": dict(
                            step.metadata
                        ),
                    },
                    not_before=(
                        runtime.started_at
                        or state.updated_at
                    ),
                    deadline_at=runtime.deadline_at,
                    risk=step.risk,
                    requires_approval=(
                        runtime.approval_status.value
                        == "approved"
                    ),
                )

                outbox_ids.append(
                    self.execution_queue.enqueue_effect(
                        effect
                    )
                )

            if (
                runtime.compensation_status
                is CompensationStatus.RUNNING
                and runtime.compensation_effect_id
                and step.compensation_action
            ):
                effect = Effect(
                    effect_id=(
                        runtime.compensation_effect_id
                    ),
                    workflow_id=state.workflow_id,
                    tenant_id=state.tenant_id,
                    kind=EffectKind.RUN_COMPENSATION,
                    step_id=step_id,
                    action=step.compensation_action,
                    idempotency_key=(
                        f"compensate:"
                        f"{state.workflow_id}:"
                        f"{step_id}:"
                        f"{runtime.compensation_attempt}"
                    ),
                    payload={
                        "workflow_id": state.workflow_id,
                        "tenant_id": state.tenant_id,
                        "step_id": step_id,
                        "attempt": (
                            runtime.compensation_attempt
                        ),
                        "original_output": dict(
                            runtime.output or {}
                        ),
                    },
                    not_before=state.updated_at,
                    deadline_at=None,
                    risk=step.risk,
                    requires_approval=False,
                )

                outbox_ids.append(
                    self.execution_queue.enqueue_effect(
                        effect
                    )
                )

        wake_outbox_id = self._schedule_wake(
            state
        )

        return DispatchBatch(
            workflow_id=workflow_id,
            outbox_ids=tuple(outbox_ids),
            wake_outbox_id=wake_outbox_id,
        )

    def _schedule_wake(
        self,
        state,
    ) -> str | None:
        candidates: list[
            tuple[datetime, str]
        ] = []

        for step_id, runtime in state.step_runs.items():
            if (
                runtime.status
                is StepStatus.WAITING_RETRY
                and runtime.next_attempt_at is not None
            ):
                candidates.append(
                    (
                        runtime.next_attempt_at,
                        f"retry:{step_id}",
                    )
                )

            if (
                runtime.compensation_status
                is CompensationStatus.WAITING_RETRY
                and runtime.compensation_next_attempt_at
                is not None
            ):
                candidates.append(
                    (
                        runtime.compensation_next_attempt_at,
                        f"compensation-retry:{step_id}",
                    )
                )

        if not candidates:
            return None

        available_at, reason = min(
            candidates,
            key=lambda item: item[0],
        )

        return self.execution_queue.enqueue_wake(
            workflow_id=state.workflow_id,
            tenant_id=state.tenant_id,
            available_at=available_at,
            reason=reason,
        )
