from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from leadbot_v2.goat.workflow_control import FailureClass


EXECUTION_TOPIC = "goat.workflow.execute"
WAKE_TOPIC = "goat.workflow.wake"
IDEMPOTENCY_SCOPE = "goat.workflow.execution"
INBOX_CONSUMER = "goat.workflow.worker"


@dataclass(frozen=True)
class ActionContext:
    workflow_id: str
    tenant_id: str
    step_id: str
    effect_id: str

    action: str
    attempt: int

    idempotency_key: str

    worker_id: str
    worker_instance_id: str
    fencing_token: int

    payload: dict[str, Any]


@dataclass(frozen=True)
class ActionResult:
    success: bool

    output: dict[str, Any] = field(
        default_factory=dict
    )

    failure_class: FailureClass = FailureClass.UNKNOWN

    error: str | None = None

    @classmethod
    def ok(
        cls,
        output: dict[str, Any] | None = None,
    ) -> "ActionResult":
        return cls(
            success=True,
            output=output or {},
        )

    @classmethod
    def failed(
        cls,
        *,
        failure_class: FailureClass,
        error: str,
        output: dict[str, Any] | None = None,
    ) -> "ActionResult":
        return cls(
            success=False,
            output=output or {},
            failure_class=failure_class,
            error=error,
        )

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": dict(self.output),
            "failure_class": self.failure_class.value,
            "error": self.error,
        }

    @classmethod
    def from_dict(
        cls,
        payload: dict[str, Any],
    ) -> "ActionResult":
        return cls(
            success=bool(payload["success"]),
            output=dict(
                payload.get("output", {})
            ),
            failure_class=FailureClass(
                payload.get(
                    "failure_class",
                    FailureClass.UNKNOWN.value,
                )
            ),
            error=payload.get("error"),
        )


@dataclass(frozen=True)
class DispatchBatch:
    workflow_id: str

    outbox_ids: tuple[str, ...] = ()
    control_effect_ids: tuple[str, ...] = ()

    wake_outbox_id: str | None = None


@dataclass(frozen=True)
class WorkerCycle:
    claimed: int = 0
    completed: int = 0
    failed: int = 0

    stale: int = 0
    replayed: int = 0
    wakes: int = 0


@dataclass
class WorkerLeaseState:
    lease_name: str
    owner_id: str

    fencing_token: int

    expires_at: datetime
