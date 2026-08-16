from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from typing import Any

from .graph import (
    dependencies_satisfied,
    topological_order,
    validate_spec,
)
from .models import (
    ActionRisk,
    ApprovalError,
    ApprovalStatus,
    CompensationStatus,
    Effect,
    EffectKind,
    FailureClass,
    StepRuntime,
    StepStatus,
    WorkflowInvariantError,
    WorkflowSpec,
    WorkflowState,
    WorkflowStatus,
    normalize_time,
    stable_hash,
)
from .policy import (
    ExecutionPolicy,
    PolicyResult,
)
from .recovery import (
    BoundedRecoveryPlanner,
    RecoveryAction,
)


TERMINAL = {
    WorkflowStatus.SUCCEEDED,
    WorkflowStatus.FAILED,
    WorkflowStatus.CANCELLED,
}


class WorkflowEngine:
    def __init__(
        self,
        spec: WorkflowSpec,
        *,
        policy: ExecutionPolicy | None = None,
        recovery: BoundedRecoveryPlanner | None = None,
    ) -> None:
        validate_spec(spec)

        self.spec = spec

        self.policy = (
            policy or ExecutionPolicy()
        )

        self.recovery = (
            recovery or BoundedRecoveryPlanner()
        )

        self._steps = spec.step_map()

        self._order = topological_order(
            spec
        )

    def new_state(
        self,
        *,
        workflow_id: str,
        tenant_id: str,
        now=None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowState:
        if not workflow_id.strip():
            raise WorkflowInvariantError(
                "workflow_id cannot be blank"
            )

        if not tenant_id.strip():
            raise WorkflowInvariantError(
                "tenant_id cannot be blank"
            )

        timestamp = normalize_time(now)

        step_runs: dict[str, StepRuntime] = {}

        for step in self.spec.steps:
            step_runs[step.step_id] = StepRuntime(
                step_id=step.step_id,
                approval_status=(
                    ApprovalStatus.PENDING
                    if step.requires_approval
                    else ApprovalStatus.NOT_REQUIRED
                ),
            )

        return WorkflowState(
            workflow_id=workflow_id,
            tenant_id=tenant_id,
            spec_name=self.spec.name,
            spec_version=self.spec.version,
            status=WorkflowStatus.PENDING,
            created_at=timestamp,
            updated_at=timestamp,
            step_runs=step_runs,
            metadata=deepcopy(
                metadata or {}
            ),
        )

    def tick(
        self,
        state: WorkflowState,
        *,
        now=None,
    ) -> list[Effect]:
        timestamp = normalize_time(now)

        self._assert_state(state)

        if state.status in TERMINAL:
            return []

        if state.status is WorkflowStatus.QUARANTINED:
            return self._quarantine_escalation(
                state,
                timestamp,
            )

        if state.status is WorkflowStatus.PAUSED:
            return []

        if state.status is WorkflowStatus.PENDING:
            state.status = WorkflowStatus.RUNNING
            self._touch(
                state,
                timestamp,
            )

        if state.cancel_requested:
            self._begin_cancel(
                state,
                timestamp,
            )

        if state.status is WorkflowStatus.COMPENSATING:
            return self._schedule_compensation(
                state,
                timestamp,
            )

        self._expire_timeouts(
            state,
            timestamp,
        )

        if state.status is WorkflowStatus.QUARANTINED:
            return self._quarantine_escalation(
                state,
                timestamp,
            )

        if state.status is WorkflowStatus.COMPENSATING:
            return self._schedule_compensation(
                state,
                timestamp,
            )

        if state.status in TERMINAL:
            return []

        effects: list[Effect] = []

        active = sum(
            1
            for runtime
            in state.step_runs.values()
            if runtime.status
            is StepStatus.RUNNING
        )

        capacity = (
            self.policy.effective_parallelism(
                self.spec
            )
            - active
        )

        if capacity <= 0:
            return []

        succeeded = {
            step_id
            for step_id, runtime
            in state.step_runs.items()
            if runtime.status
            is StepStatus.SUCCEEDED
        }

        for step_id in self._order:
            runtime = state.step_runs[
                step_id
            ]

            step = self._steps[
                step_id
            ]

            if (
                runtime.status
                is StepStatus.WAITING_RETRY
            ):
                if (
                    runtime.next_attempt_at
                    is None
                    or timestamp
                    < runtime.next_attempt_at
                ):
                    continue

                runtime.status = (
                    StepStatus.PENDING
                )

                runtime.next_attempt_at = None

                self._touch(
                    state,
                    timestamp,
                )

            if (
                runtime.status
                is not StepStatus.PENDING
            ):
                continue

            if not dependencies_satisfied(
                self.spec,
                step_id=step_id,
                succeeded=succeeded,
            ):
                continue

            decision = self.policy.evaluate(
                spec=self.spec,
                state=state,
                step=step,
            )

            if decision.result is PolicyResult.DENY:
                runtime.status = StepStatus.FAILED

                runtime.last_failure_class = (
                    FailureClass.AUTHORIZATION
                )

                runtime.last_error = (
                    decision.reason
                )

                state.failure_reason = (
                    f"{step_id}: "
                    f"{decision.reason}"
                )

                escalation = (
                    self._make_escalation(
                        state=state,
                        step_id=step_id,
                        reason=decision.reason,
                        timestamp=timestamp,
                    )
                )

                self._begin_compensation(
                    state,
                    timestamp,
                    target=WorkflowStatus.FAILED,
                    reason=state.failure_reason,
                )

                effects.append(
                    escalation
                )

                break

            approval_required = (
                decision.result
                is PolicyResult.REQUIRE_APPROVAL
            )

            if (
                approval_required
                and runtime.approval_status
                is not ApprovalStatus.APPROVED
            ):
                runtime.status = (
                    StepStatus.WAITING_APPROVAL
                )

                runtime.approval_status = (
                    ApprovalStatus.PENDING
                )

                if runtime.approval_id is None:
                    runtime.approval_id = (
                        stable_hash(
                            {
                                "workflow_id":
                                    state.workflow_id,
                                "step_id":
                                    step_id,
                                "spec":
                                    self.spec.key,
                                "purpose":
                                    "approval",
                            }
                        )[:32]
                    )

                effect = Effect(
                    effect_id=stable_hash(
                        {
                            "workflow_id":
                                state.workflow_id,
                            "step_id":
                                step_id,
                            "approval_id":
                                runtime.approval_id,
                            "kind":
                                EffectKind
                                .REQUEST_APPROVAL
                                .value,
                        }
                    ),
                    workflow_id=(
                        state.workflow_id
                    ),
                    tenant_id=(
                        state.tenant_id
                    ),
                    kind=(
                        EffectKind.REQUEST_APPROVAL
                    ),
                    step_id=step_id,
                    action=(
                        "workflow.request_approval"
                    ),
                    idempotency_key=(
                        f"approval:"
                        f"{state.workflow_id}:"
                        f"{step_id}:"
                        f"{runtime.approval_id}"
                    ),
                    payload={
                        "approval_id":
                            runtime.approval_id,
                        "workflow_id":
                            state.workflow_id,
                        "step_id":
                            step_id,
                        "action":
                            step.action,
                        "risk":
                            step.risk.value,
                        "reason":
                            decision.reason,
                    },
                    not_before=timestamp,
                    deadline_at=None,
                    risk=step.risk,
                    requires_approval=True,
                )

                effects.append(effect)

                self._touch(
                    state,
                    timestamp,
                )

                continue

            if capacity <= 0:
                break

            effect = self._start_step(
                state=state,
                step_id=step_id,
                timestamp=timestamp,
            )

            effects.append(effect)

            capacity -= 1

        self._refresh_success(
            state,
            timestamp,
        )

        return effects

    def approve(
        self,
        state: WorkflowState,
        *,
        step_id: str,
        approver_id: str,
        approval_id: str,
        now=None,
    ) -> None:
        timestamp = normalize_time(now)

        self._assert_state(state)

        if state.status in TERMINAL:
            raise ApprovalError(
                "terminal workflow cannot be approved"
            )

        if step_id not in self._steps:
            raise ApprovalError(
                f"unknown step: {step_id}"
            )

        runtime = state.step_runs[
            step_id
        ]

        if (
            runtime.status
            is not StepStatus.WAITING_APPROVAL
        ):
            raise ApprovalError(
                f"{step_id} is not awaiting approval"
            )

        if (
            runtime.approval_id
            != approval_id
        ):
            raise ApprovalError(
                "approval token mismatch"
            )

        if not approver_id.strip():
            raise ApprovalError(
                "approver_id cannot be blank"
            )

        runtime.approval_status = (
            ApprovalStatus.APPROVED
        )

        runtime.approved_by = (
            approver_id
        )

        runtime.status = (
            StepStatus.PENDING
        )

        self._touch(
            state,
            timestamp,
        )

    def reject(
        self,
        state: WorkflowState,
        *,
        step_id: str,
        approver_id: str,
        approval_id: str,
        reason: str,
        now=None,
    ) -> None:
        timestamp = normalize_time(now)

        self._assert_state(state)

        runtime = state.step_runs.get(
            step_id
        )

        if runtime is None:
            raise ApprovalError(
                f"unknown step: {step_id}"
            )

        if (
            runtime.status
            is not StepStatus.WAITING_APPROVAL
        ):
            raise ApprovalError(
                f"{step_id} is not awaiting approval"
            )

        if runtime.approval_id != approval_id:
            raise ApprovalError(
                "approval token mismatch"
            )

        if not approver_id.strip():
            raise ApprovalError(
                "approver_id cannot be blank"
            )

        runtime.approval_status = (
            ApprovalStatus.REJECTED
        )

        runtime.approved_by = (
            approver_id
        )

        runtime.status = (
            StepStatus.FAILED
        )

        runtime.last_failure_class = (
            FailureClass.AUTHORIZATION
        )

        runtime.last_error = (
            reason or "approval rejected"
        )

        state.failure_reason = (
            f"{step_id}: approval rejected: "
            f"{runtime.last_error}"
        )

        self._begin_compensation(
            state,
            timestamp,
            target=WorkflowStatus.FAILED,
            reason=state.failure_reason,
        )

    def complete_effect(
        self,
        state: WorkflowState,
        *,
        effect_id: str,
        success: bool,
        output: dict[str, Any] | None = None,
        failure_class: FailureClass = (
            FailureClass.UNKNOWN
        ),
        error: str | None = None,
        now=None,
    ) -> bool:
        timestamp = normalize_time(now)

        self._assert_state(state)

        if (
            effect_id
            in state.processed_effect_ids
        ):
            return False

        for step_id, runtime in (
            state.step_runs.items()
        ):
            if (
                runtime.active_effect_id
                == effect_id
            ):
                state.processed_effect_ids[
                    effect_id
                ] = True

                runtime.active_effect_id = None
                runtime.deadline_at = None

                if success:
                    runtime.status = (
                        StepStatus.SUCCEEDED
                    )

                    runtime.completed_at = (
                        timestamp
                    )

                    runtime.output = deepcopy(
                        output or {}
                    )

                    runtime.last_error = None

                    runtime.last_failure_class = (
                        None
                    )

                    if (
                        step_id
                        not in state.completed_order
                    ):
                        state.completed_order.append(
                            step_id
                        )

                    self._touch(
                        state,
                        timestamp,
                    )

                    self._refresh_success(
                        state,
                        timestamp,
                    )

                else:
                    self._fail_step(
                        state=state,
                        step_id=step_id,
                        failure_class=(
                            failure_class
                        ),
                        error=(
                            error
                            or "step execution failed"
                        ),
                        timestamp=timestamp,
                    )

                return True

            if (
                runtime.compensation_effect_id
                == effect_id
            ):
                state.processed_effect_ids[
                    effect_id
                ] = True

                runtime.compensation_effect_id = (
                    None
                )

                if success:
                    runtime.compensation_status = (
                        CompensationStatus.SUCCEEDED
                    )

                    self._touch(
                        state,
                        timestamp,
                    )

                    self._finish_compensation_if_done(
                        state,
                        timestamp,
                    )

                else:
                    self._fail_compensation(
                        state=state,
                        step_id=step_id,
                        failure_class=(
                            failure_class
                        ),
                        error=(
                            error
                            or "compensation failed"
                        ),
                        timestamp=timestamp,
                    )

                return True

        raise WorkflowInvariantError(
            f"unknown or inactive effect: {effect_id}"
        )

    def cancel(
        self,
        state: WorkflowState,
        *,
        reason: str,
        now=None,
    ) -> None:
        timestamp = normalize_time(now)

        self._assert_state(state)

        if state.status in TERMINAL:
            return

        if (
            state.status
            is WorkflowStatus.QUARANTINED
        ):
            return

        state.cancel_requested = True

        if reason:
            state.failure_reason = reason

        self._begin_cancel(
            state,
            timestamp,
        )

    def pause(
        self,
        state: WorkflowState,
        *,
        reason: str,
        now=None,
    ) -> None:
        timestamp = normalize_time(now)

        self._assert_state(state)

        if state.status in TERMINAL:
            return

        if state.status in {
            WorkflowStatus.COMPENSATING,
            WorkflowStatus.QUARANTINED,
        }:
            raise WorkflowInvariantError(
                "cannot pause compensation or quarantine"
            )

        state.status = (
            WorkflowStatus.PAUSED
        )

        state.pause_reason = (
            reason or "operator pause"
        )

        self._touch(
            state,
            timestamp,
        )

    def resume(
        self,
        state: WorkflowState,
        *,
        now=None,
    ) -> None:
        timestamp = normalize_time(now)

        self._assert_state(state)

        if (
            state.status
            is not WorkflowStatus.PAUSED
        ):
            raise WorkflowInvariantError(
                "only paused workflow may resume"
            )

        state.status = (
            WorkflowStatus.RUNNING
        )

        state.pause_reason = None

        self._touch(
            state,
            timestamp,
        )

    def quarantine(
        self,
        state: WorkflowState,
        *,
        reason: str,
        now=None,
    ) -> None:
        timestamp = normalize_time(now)

        self._assert_state(state)

        state.status = (
            WorkflowStatus.QUARANTINED
        )

        state.quarantine_reason = (
            reason or "manual quarantine"
        )

        state.escalation_emitted = False

        self._touch(
            state,
            timestamp,
        )

    def _assert_state(
        self,
        state: WorkflowState,
    ) -> None:
        if (
            state.spec_name
            != self.spec.name
        ):
            raise WorkflowInvariantError(
                "workflow specification name mismatch"
            )

        if (
            state.spec_version
            != self.spec.version
        ):
            raise WorkflowInvariantError(
                "workflow specification version mismatch"
            )

        if (
            set(state.step_runs)
            != set(self._steps)
        ):
            raise WorkflowInvariantError(
                "workflow step state does not match spec"
            )

    def _start_step(
        self,
        *,
        state: WorkflowState,
        step_id: str,
        timestamp,
    ) -> Effect:
        step = self._steps[
            step_id
        ]

        runtime = state.step_runs[
            step_id
        ]

        runtime.attempt += 1

        runtime.status = (
            StepStatus.RUNNING
        )

        runtime.started_at = (
            timestamp
        )

        runtime.completed_at = None
        runtime.next_attempt_at = None

        runtime.deadline_at = (
            timestamp
            + timedelta(
                seconds=step.timeout_seconds
            )
        )

        effect_id = stable_hash(
            {
                "workflow_id":
                    state.workflow_id,
                "step_id":
                    step_id,
                "attempt":
                    runtime.attempt,
                "kind":
                    EffectKind.RUN_STEP.value,
            }
        )

        runtime.active_effect_id = (
            effect_id
        )

        self._touch(
            state,
            timestamp,
        )

        return Effect(
            effect_id=effect_id,
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
                "workflow_id":
                    state.workflow_id,
                "tenant_id":
                    state.tenant_id,
                "step_id":
                    step_id,
                "attempt":
                    runtime.attempt,
                "metadata":
                    dict(step.metadata),
            },
            not_before=timestamp,
            deadline_at=runtime.deadline_at,
            risk=step.risk,
            requires_approval=(
                runtime.approval_status
                is ApprovalStatus.APPROVED
            ),
        )

    def _fail_step(
        self,
        *,
        state: WorkflowState,
        step_id: str,
        failure_class: FailureClass,
        error: str,
        timestamp,
    ) -> None:
        step = self._steps[
            step_id
        ]

        runtime = state.step_runs[
            step_id
        ]

        runtime.active_effect_id = None
        runtime.deadline_at = None

        runtime.last_error = error

        runtime.last_failure_class = (
            failure_class
        )

        reversible = any(
            self._steps[
                completed
            ].compensation_action
            for completed
            in state.completed_order
        )

        decision = self.recovery.decide(
            failure_class=failure_class,
            attempt=runtime.attempt,
            max_attempts=(
                step.retry_policy.max_attempts
            ),
            retryable=(
                step.retry_policy.retryable
            ),
            reversible=reversible,
        )

        if (
            decision.action
            is RecoveryAction.RETRY
        ):
            delay = (
                step.retry_policy.delay_seconds(
                    workflow_id=(
                        state.workflow_id
                    ),
                    step_id=step_id,
                    attempt=runtime.attempt,
                )
            )

            runtime.status = (
                StepStatus.WAITING_RETRY
            )

            runtime.next_attempt_at = (
                timestamp
                + timedelta(
                    seconds=delay
                )
            )

            self._touch(
                state,
                timestamp,
            )

            return

        if (
            decision.action
            is RecoveryAction.QUARANTINE
        ):
            runtime.status = (
                StepStatus.FAILED
            )

            state.status = (
                WorkflowStatus.QUARANTINED
            )

            state.quarantine_reason = (
                f"{step_id}: {error}"
            )

            state.failure_reason = (
                f"{step_id}: {error}"
            )

            state.escalation_emitted = False

            self._touch(
                state,
                timestamp,
            )

            return

        runtime.status = (
            StepStatus.FAILED
        )

        state.failure_reason = (
            f"{step_id}: "
            f"{failure_class.value}: "
            f"{error}"
        )

        self._begin_compensation(
            state,
            timestamp,
            target=WorkflowStatus.FAILED,
            reason=state.failure_reason,
        )

    def _expire_timeouts(
        self,
        state: WorkflowState,
        timestamp,
    ) -> None:
        for step_id in self._order:
            runtime = state.step_runs[
                step_id
            ]

            if (
                runtime.status
                is not StepStatus.RUNNING
            ):
                continue

            if runtime.deadline_at is None:
                continue

            if (
                timestamp
                < runtime.deadline_at
            ):
                continue

            if runtime.active_effect_id:
                state.processed_effect_ids[
                    runtime.active_effect_id
                ] = True

            self._fail_step(
                state=state,
                step_id=step_id,
                failure_class=(
                    FailureClass.TIMEOUT
                ),
                error=(
                    "step execution deadline exceeded"
                ),
                timestamp=timestamp,
            )

            if state.status in {
                WorkflowStatus.COMPENSATING,
                WorkflowStatus.QUARANTINED,
                WorkflowStatus.FAILED,
            }:
                return

    def _begin_cancel(
        self,
        state: WorkflowState,
        timestamp,
    ) -> None:
        if (
            state.status
            is WorkflowStatus.COMPENSATING
        ):
            return

        for runtime in (
            state.step_runs.values()
        ):
            if (
                runtime.status
                is StepStatus.RUNNING
            ):
                if runtime.active_effect_id:
                    state.processed_effect_ids[
                        runtime.active_effect_id
                    ] = True

                runtime.active_effect_id = None
                runtime.deadline_at = None

                runtime.status = (
                    StepStatus.SKIPPED
                )

            elif runtime.status in {
                StepStatus.PENDING,
                StepStatus.WAITING_RETRY,
                StepStatus.WAITING_APPROVAL,
            }:
                runtime.status = (
                    StepStatus.SKIPPED
                )

        self._begin_compensation(
            state,
            timestamp,
            target=WorkflowStatus.CANCELLED,
            reason=(
                state.failure_reason
                or "workflow cancelled"
            ),
        )

    def _begin_compensation(
        self,
        state: WorkflowState,
        timestamp,
        *,
        target: WorkflowStatus,
        reason: str,
    ) -> None:
        if (
            state.status
            is WorkflowStatus.COMPENSATING
        ):
            return

        state.failure_reason = reason

        state.terminal_after_compensation = (
            target
        )

        any_compensation = False

        for step_id in reversed(
            state.completed_order
        ):
            step = self._steps[
                step_id
            ]

            runtime = state.step_runs[
                step_id
            ]

            if not step.compensation_action:
                continue

            if (
                runtime.compensation_status
                is CompensationStatus.NONE
            ):
                runtime.compensation_status = (
                    CompensationStatus.PENDING
                )

            if (
                runtime.compensation_status
                is not CompensationStatus.SUCCEEDED
            ):
                any_compensation = True

        if any_compensation:
            state.status = (
                WorkflowStatus.COMPENSATING
            )
        else:
            state.status = target

        self._touch(
            state,
            timestamp,
        )

    def _schedule_compensation(
        self,
        state: WorkflowState,
        timestamp,
    ) -> list[Effect]:
        for runtime in (
            state.step_runs.values()
        ):
            if (
                runtime.compensation_status
                is CompensationStatus.RUNNING
            ):
                return []

        for step_id in reversed(
            state.completed_order
        ):
            runtime = state.step_runs[
                step_id
            ]

            step = self._steps[
                step_id
            ]

            if not step.compensation_action:
                continue

            if (
                runtime.compensation_status
                is CompensationStatus.WAITING_RETRY
            ):
                if (
                    runtime.compensation_next_attempt_at
                    is None
                    or timestamp
                    < runtime.compensation_next_attempt_at
                ):
                    continue

                runtime.compensation_status = (
                    CompensationStatus.PENDING
                )

            if (
                runtime.compensation_status
                is not CompensationStatus.PENDING
            ):
                continue

            runtime.compensation_attempt += 1

            runtime.compensation_status = (
                CompensationStatus.RUNNING
            )

            runtime.compensation_next_attempt_at = (
                None
            )

            effect_id = stable_hash(
                {
                    "workflow_id":
                        state.workflow_id,
                    "step_id":
                        step_id,
                    "attempt":
                        runtime.compensation_attempt,
                    "kind":
                        EffectKind
                        .RUN_COMPENSATION
                        .value,
                }
            )

            runtime.compensation_effect_id = (
                effect_id
            )

            self._touch(
                state,
                timestamp,
            )

            return [
                Effect(
                    effect_id=effect_id,
                    workflow_id=(
                        state.workflow_id
                    ),
                    tenant_id=(
                        state.tenant_id
                    ),
                    kind=(
                        EffectKind.RUN_COMPENSATION
                    ),
                    step_id=step_id,
                    action=(
                        step.compensation_action
                    ),
                    idempotency_key=(
                        f"compensate:"
                        f"{state.workflow_id}:"
                        f"{step_id}:"
                        f"{runtime.compensation_attempt}"
                    ),
                    payload={
                        "workflow_id":
                            state.workflow_id,
                        "tenant_id":
                            state.tenant_id,
                        "step_id":
                            step_id,
                        "attempt":
                            runtime.compensation_attempt,
                        "original_output":
                            deepcopy(
                                runtime.output
                                or {}
                            ),
                    },
                    not_before=timestamp,
                    deadline_at=None,
                    risk=step.risk,
                    requires_approval=False,
                )
            ]

        self._finish_compensation_if_done(
            state,
            timestamp,
        )

        return []

    def _fail_compensation(
        self,
        *,
        state: WorkflowState,
        step_id: str,
        failure_class: FailureClass,
        error: str,
        timestamp,
    ) -> None:
        step = self._steps[
            step_id
        ]

        runtime = state.step_runs[
            step_id
        ]

        decision = self.recovery.decide(
            failure_class=failure_class,
            attempt=(
                runtime.compensation_attempt
            ),
            max_attempts=(
                step.retry_policy.max_attempts
            ),
            retryable=(
                step.retry_policy.retryable
            ),
            reversible=False,
        )

        if (
            decision.action
            is RecoveryAction.RETRY
        ):
            delay = (
                step.retry_policy.delay_seconds(
                    workflow_id=(
                        state.workflow_id
                    ),
                    step_id=step_id,
                    attempt=(
                        runtime.compensation_attempt
                    ),
                    compensation=True,
                )
            )

            runtime.compensation_status = (
                CompensationStatus.WAITING_RETRY
            )

            runtime.compensation_next_attempt_at = (
                timestamp
                + timedelta(
                    seconds=delay
                )
            )

            self._touch(
                state,
                timestamp,
            )

            return

        runtime.compensation_status = (
            CompensationStatus.FAILED
        )

        state.status = (
            WorkflowStatus.QUARANTINED
        )

        state.quarantine_reason = (
            f"compensation failure for "
            f"{step_id}: {error}"
        )

        state.escalation_emitted = False

        self._touch(
            state,
            timestamp,
        )

    def _finish_compensation_if_done(
        self,
        state: WorkflowState,
        timestamp,
    ) -> None:
        relevant = [
            state.step_runs[step_id]
            for step_id
            in state.completed_order
            if self._steps[
                step_id
            ].compensation_action
        ]

        if not relevant:
            state.status = (
                state.terminal_after_compensation
                or WorkflowStatus.FAILED
            )

            self._touch(
                state,
                timestamp,
            )

            return

        if any(
            runtime.compensation_status
            is CompensationStatus.FAILED
            for runtime in relevant
        ):
            state.status = (
                WorkflowStatus.QUARANTINED
            )

            if not state.quarantine_reason:
                state.quarantine_reason = (
                    "one or more compensations failed"
                )

            state.escalation_emitted = False

            self._touch(
                state,
                timestamp,
            )

            return

        if all(
            runtime.compensation_status
            is CompensationStatus.SUCCEEDED
            for runtime in relevant
        ):
            state.status = (
                state.terminal_after_compensation
                or WorkflowStatus.FAILED
            )

            self._touch(
                state,
                timestamp,
            )

    def _refresh_success(
        self,
        state: WorkflowState,
        timestamp,
    ) -> None:
        if state.status not in {
            WorkflowStatus.RUNNING,
            WorkflowStatus.PENDING,
        }:
            return

        if all(
            runtime.status
            is StepStatus.SUCCEEDED
            for runtime
            in state.step_runs.values()
        ):
            state.status = (
                WorkflowStatus.SUCCEEDED
            )

            self._touch(
                state,
                timestamp,
            )

    def _make_escalation(
        self,
        *,
        state: WorkflowState,
        step_id: str | None,
        reason: str,
        timestamp,
    ) -> Effect:
        effect_id = stable_hash(
            {
                "workflow_id":
                    state.workflow_id,
                "step_id":
                    step_id,
                "reason":
                    reason,
                "kind":
                    EffectKind.ESCALATE.value,
            }
        )

        return Effect(
            effect_id=effect_id,
            workflow_id=state.workflow_id,
            tenant_id=state.tenant_id,
            kind=EffectKind.ESCALATE,
            step_id=step_id,
            action="workflow.escalate",
            idempotency_key=(
                f"escalate:"
                f"{state.workflow_id}:"
                f"{step_id or 'workflow'}:"
                f"{effect_id[:16]}"
            ),
            payload={
                "workflow_id":
                    state.workflow_id,
                "step_id":
                    step_id,
                "reason":
                    reason,
            },
            not_before=timestamp,
            deadline_at=None,
            risk=ActionRisk.CRITICAL,
            requires_approval=True,
        )

    def _quarantine_escalation(
        self,
        state: WorkflowState,
        timestamp,
    ) -> list[Effect]:
        if state.escalation_emitted:
            return []

        state.escalation_emitted = True

        self._touch(
            state,
            timestamp,
        )

        return [
            self._make_escalation(
                state=state,
                step_id=None,
                reason=(
                    state.quarantine_reason
                    or "workflow quarantined"
                ),
                timestamp=timestamp,
            )
        ]

    @staticmethod
    def _touch(
        state: WorkflowState,
        timestamp,
    ) -> None:
        state.updated_at = timestamp
