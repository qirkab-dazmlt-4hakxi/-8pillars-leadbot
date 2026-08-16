from __future__ import annotations

from copy import deepcopy
from typing import Any

from .audit import HashChainJournal
from .engine import WorkflowEngine
from .models import (
    FailureClass,
    WorkflowSpec,
    WorkflowState,
    normalize_time,
)
from .policy import ExecutionPolicy
from .repository import (
    WorkflowRepository,
)


class WorkflowSpecNotRegistered(
    RuntimeError
):
    pass


class WorkflowSpecAlreadyRegistered(
    RuntimeError
):
    pass


class WorkflowService:
    def __init__(
        self,
        repository: WorkflowRepository,
        *,
        policy: ExecutionPolicy | None = None,
        journal: HashChainJournal | None = None,
    ) -> None:
        self.repository = (
            repository
        )

        self.policy = (
            policy
            or ExecutionPolicy()
        )

        self.journal = (
            journal
            or HashChainJournal()
        )

        self._specs: dict[
            tuple[str, int],
            WorkflowSpec,
        ] = {}

    def register(
        self,
        spec: WorkflowSpec,
    ) -> None:
        key = spec.key

        existing = self._specs.get(
            key
        )

        if existing is not None:
            if existing != spec:
                raise WorkflowSpecAlreadyRegistered(
                    f"{key!r} already registered "
                    "with different definition"
                )

            return

        WorkflowEngine(
            spec,
            policy=self.policy,
        )

        self._specs[
            key
        ] = spec

    def start(
        self,
        *,
        spec_name: str,
        spec_version: int,
        workflow_id: str,
        tenant_id: str,
        actor_id: str,
        metadata: dict[str, Any] | None = None,
        now=None,
    ) -> WorkflowState:
        timestamp = normalize_time(
            now
        )

        spec = self._spec(
            spec_name,
            spec_version,
        )

        engine = WorkflowEngine(
            spec,
            policy=self.policy,
        )

        state = engine.new_state(
            workflow_id=workflow_id,
            tenant_id=tenant_id,
            metadata=metadata,
            now=timestamp,
        )

        stored = self.repository.create(
            state
        )

        self.journal.append(
            workflow_id=workflow_id,
            tenant_id=tenant_id,
            event_type=(
                "workflow.started"
            ),
            actor_id=actor_id,
            payload={
                "spec_name":
                    spec_name,
                "spec_version":
                    spec_version,
            },
            occurred_at=timestamp,
        )

        return stored

    def tick(
        self,
        workflow_id: str,
        *,
        actor_id: str = "goat-runtime",
        now=None,
    ):
        timestamp = normalize_time(
            now
        )

        state = self.repository.load(
            workflow_id
        )

        before = deepcopy(
            state
        )

        engine = self._engine(
            state
        )

        effects = engine.tick(
            state,
            now=timestamp,
        )

        stored = self._save_if_changed(
            before,
            state,
        )

        if effects or stored != before:
            self.journal.append(
                workflow_id=(
                    stored.workflow_id
                ),
                tenant_id=(
                    stored.tenant_id
                ),
                event_type=(
                    "workflow.tick"
                ),
                actor_id=actor_id,
                payload={
                    "status":
                        stored.status.value,
                    "effects":
                        [
                            effect.effect_id
                            for effect
                            in effects
                        ],
                },
                occurred_at=timestamp,
            )

        return stored, effects

    def complete(
        self,
        workflow_id: str,
        *,
        effect_id: str,
        success: bool,
        actor_id: str,
        output: dict[str, Any] | None = None,
        failure_class: FailureClass = (
            FailureClass.UNKNOWN
        ),
        error: str | None = None,
        now=None,
    ) -> tuple[
        WorkflowState,
        bool,
    ]:
        timestamp = normalize_time(
            now
        )

        state = self.repository.load(
            workflow_id
        )

        before = deepcopy(
            state
        )

        engine = self._engine(
            state
        )

        accepted = engine.complete_effect(
            state,
            effect_id=effect_id,
            success=success,
            output=output,
            failure_class=failure_class,
            error=error,
            now=timestamp,
        )

        stored = self._save_if_changed(
            before,
            state,
        )

        self.journal.append(
            workflow_id=(
                stored.workflow_id
            ),
            tenant_id=(
                stored.tenant_id
            ),
            event_type=(
                "workflow.effect.completed"
                if success
                else "workflow.effect.failed"
            ),
            actor_id=actor_id,
            payload={
                "effect_id":
                    effect_id,
                "accepted":
                    accepted,
                "status":
                    stored.status.value,
                "failure_class":
                    (
                        None
                        if success
                        else failure_class.value
                    ),
            },
            occurred_at=timestamp,
        )

        return stored, accepted

    def approve(
        self,
        workflow_id: str,
        *,
        step_id: str,
        approval_id: str,
        approver_id: str,
        now=None,
    ) -> WorkflowState:
        timestamp = normalize_time(
            now
        )

        state = self.repository.load(
            workflow_id
        )

        before = deepcopy(
            state
        )

        self._engine(
            state
        ).approve(
            state,
            step_id=step_id,
            approver_id=approver_id,
            approval_id=approval_id,
            now=timestamp,
        )

        stored = self._save_if_changed(
            before,
            state,
        )

        self.journal.append(
            workflow_id=(
                stored.workflow_id
            ),
            tenant_id=(
                stored.tenant_id
            ),
            event_type=(
                "workflow.approved"
            ),
            actor_id=approver_id,
            payload={
                "step_id":
                    step_id,
                "approval_id":
                    approval_id,
            },
            occurred_at=timestamp,
        )

        return stored

    def reject(
        self,
        workflow_id: str,
        *,
        step_id: str,
        approval_id: str,
        approver_id: str,
        reason: str,
        now=None,
    ) -> WorkflowState:
        timestamp = normalize_time(
            now
        )

        state = self.repository.load(
            workflow_id
        )

        before = deepcopy(
            state
        )

        self._engine(
            state
        ).reject(
            state,
            step_id=step_id,
            approver_id=approver_id,
            approval_id=approval_id,
            reason=reason,
            now=timestamp,
        )

        stored = self._save_if_changed(
            before,
            state,
        )

        self.journal.append(
            workflow_id=(
                stored.workflow_id
            ),
            tenant_id=(
                stored.tenant_id
            ),
            event_type=(
                "workflow.rejected"
            ),
            actor_id=approver_id,
            payload={
                "step_id":
                    step_id,
                "reason":
                    reason,
            },
            occurred_at=timestamp,
        )

        return stored

    def cancel(
        self,
        workflow_id: str,
        *,
        actor_id: str,
        reason: str,
        now=None,
    ) -> WorkflowState:
        timestamp = normalize_time(
            now
        )

        state = self.repository.load(
            workflow_id
        )

        before = deepcopy(
            state
        )

        self._engine(
            state
        ).cancel(
            state,
            reason=reason,
            now=timestamp,
        )

        stored = self._save_if_changed(
            before,
            state,
        )

        self.journal.append(
            workflow_id=(
                stored.workflow_id
            ),
            tenant_id=(
                stored.tenant_id
            ),
            event_type=(
                "workflow.cancelled"
            ),
            actor_id=actor_id,
            payload={
                "reason":
                    reason,
                "status":
                    stored.status.value,
            },
            occurred_at=timestamp,
        )

        return stored

    def pause(
        self,
        workflow_id: str,
        *,
        actor_id: str,
        reason: str,
        now=None,
    ) -> WorkflowState:
        timestamp = normalize_time(
            now
        )

        state = self.repository.load(
            workflow_id
        )

        before = deepcopy(
            state
        )

        self._engine(
            state
        ).pause(
            state,
            reason=reason,
            now=timestamp,
        )

        stored = self._save_if_changed(
            before,
            state,
        )

        self.journal.append(
            workflow_id=(
                stored.workflow_id
            ),
            tenant_id=(
                stored.tenant_id
            ),
            event_type=(
                "workflow.paused"
            ),
            actor_id=actor_id,
            payload={
                "reason":
                    reason,
            },
            occurred_at=timestamp,
        )

        return stored

    def resume(
        self,
        workflow_id: str,
        *,
        actor_id: str,
        now=None,
    ) -> WorkflowState:
        timestamp = normalize_time(
            now
        )

        state = self.repository.load(
            workflow_id
        )

        before = deepcopy(
            state
        )

        self._engine(
            state
        ).resume(
            state,
            now=timestamp,
        )

        stored = self._save_if_changed(
            before,
            state,
        )

        self.journal.append(
            workflow_id=(
                stored.workflow_id
            ),
            tenant_id=(
                stored.tenant_id
            ),
            event_type=(
                "workflow.resumed"
            ),
            actor_id=actor_id,
            payload={},
            occurred_at=timestamp,
        )

        return stored

    def _spec(
        self,
        name: str,
        version: int,
    ) -> WorkflowSpec:
        try:
            return self._specs[
                (
                    name,
                    version,
                )
            ]

        except KeyError as exc:
            raise WorkflowSpecNotRegistered(
                f"{name}:{version}"
            ) from exc

    def _engine(
        self,
        state: WorkflowState,
    ) -> WorkflowEngine:
        return WorkflowEngine(
            self._spec(
                state.spec_name,
                state.spec_version,
            ),
            policy=self.policy,
        )

    def _save_if_changed(
        self,
        before: WorkflowState,
        after: WorkflowState,
    ) -> WorkflowState:
        if before == after:
            return before

        return self.repository.save(
            after,
            expected_revision=(
                before.revision
            ),
        )
