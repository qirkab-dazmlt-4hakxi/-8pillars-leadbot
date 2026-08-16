from __future__ import annotations

import hashlib
import json

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class WorkflowControlError(RuntimeError):
    pass


class WorkflowDefinitionError(WorkflowControlError):
    pass


class WorkflowInvariantError(WorkflowControlError):
    pass


class ApprovalError(WorkflowControlError):
    pass


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPENSATING = "compensating"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    QUARANTINED = "quarantined"


class StepStatus(str, Enum):
    PENDING = "pending"
    WAITING_APPROVAL = "waiting_approval"
    RUNNING = "running"
    WAITING_RETRY = "waiting_retry"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class ApprovalStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class CompensationStatus(str, Enum):
    NONE = "none"
    PENDING = "pending"
    RUNNING = "running"
    WAITING_RETRY = "waiting_retry"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class FailureClass(str, Enum):
    TRANSIENT = "transient"
    RATE_LIMIT = "rate_limit"
    EXTERNAL = "external"
    TIMEOUT = "timeout"
    VALIDATION = "validation"
    AUTHORIZATION = "authorization"
    INTEGRITY = "integrity"
    DEPENDENCY = "dependency"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class ActionRisk(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class EffectKind(str, Enum):
    RUN_STEP = "run_step"
    REQUEST_APPROVAL = "request_approval"
    RUN_COMPENSATION = "run_compensation"
    ESCALATE = "escalate"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_time(value: datetime | None) -> datetime:
    result = value or utcnow()

    if result.tzinfo is None:
        raise WorkflowInvariantError(
            "workflow timestamps must be timezone-aware"
        )

    return result.astimezone(timezone.utc)


def _json_default(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value

    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()

    if is_dataclass(value):
        return asdict(value)

    raise TypeError(
        f"unsupported canonical-json value: {type(value)!r}"
    )


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        default=_json_default,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def stable_hash(value: Any) -> str:
    return hashlib.sha256(
        canonical_json(value).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 5.0
    multiplier: float = 2.0
    max_delay_seconds: float = 300.0
    jitter_fraction: float = 0.10

    retryable: frozenset[FailureClass] = field(
        default_factory=lambda: frozenset(
            {
                FailureClass.TRANSIENT,
                FailureClass.RATE_LIMIT,
                FailureClass.EXTERNAL,
                FailureClass.TIMEOUT,
            }
        )
    )

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise WorkflowDefinitionError(
                "max_attempts must be >= 1"
            )

        if self.base_delay_seconds < 0:
            raise WorkflowDefinitionError(
                "base_delay_seconds cannot be negative"
            )

        if self.multiplier < 1:
            raise WorkflowDefinitionError(
                "retry multiplier must be >= 1"
            )

        if self.max_delay_seconds < self.base_delay_seconds:
            raise WorkflowDefinitionError(
                "max_delay_seconds cannot be below base delay"
            )

        if not 0 <= self.jitter_fraction <= 0.50:
            raise WorkflowDefinitionError(
                "jitter_fraction must be between 0 and 0.50"
            )

    def delay_seconds(
        self,
        *,
        workflow_id: str,
        step_id: str,
        attempt: int,
        compensation: bool = False,
    ) -> float:
        exponent = max(0, attempt - 1)

        raw = min(
            self.max_delay_seconds,
            self.base_delay_seconds
            * (self.multiplier ** exponent),
        )

        if raw == 0 or self.jitter_fraction == 0:
            return float(raw)

        seed = stable_hash(
            {
                "workflow_id": workflow_id,
                "step_id": step_id,
                "attempt": attempt,
                "compensation": compensation,
            }
        )

        bucket = int(seed[:8], 16) / 0xFFFFFFFF

        offset = (
            (bucket * 2.0) - 1.0
        ) * self.jitter_fraction

        value = raw * (1.0 + offset)

        return max(
            0.0,
            min(self.max_delay_seconds, value),
        )


@dataclass(frozen=True)
class StepSpec:
    step_id: str
    action: str

    dependencies: tuple[str, ...] = ()

    timeout_seconds: float = 300.0

    retry_policy: RetryPolicy = field(
        default_factory=RetryPolicy
    )

    side_effect: bool = False
    risk: ActionRisk = ActionRisk.LOW

    requires_approval: bool = False
    irreversible: bool = False

    compensation_action: str | None = None

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if not self.step_id.strip():
            raise WorkflowDefinitionError(
                "step_id cannot be blank"
            )

        if not self.action.strip():
            raise WorkflowDefinitionError(
                f"action cannot be blank for step {self.step_id}"
            )

        if self.timeout_seconds <= 0:
            raise WorkflowDefinitionError(
                f"timeout must be positive for {self.step_id}"
            )

        if self.irreversible and self.compensation_action:
            raise WorkflowDefinitionError(
                f"{self.step_id}: irreversible step cannot "
                "declare compensation"
            )


@dataclass(frozen=True)
class WorkflowSpec:
    name: str
    version: int
    steps: tuple[StepSpec, ...]

    max_parallelism: int = 4

    labels: Mapping[str, str] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise WorkflowDefinitionError(
                "workflow name cannot be blank"
            )

        if self.version < 1:
            raise WorkflowDefinitionError(
                "workflow version must be >= 1"
            )

        if not self.steps:
            raise WorkflowDefinitionError(
                "workflow must contain at least one step"
            )

        if self.max_parallelism < 1:
            raise WorkflowDefinitionError(
                "max_parallelism must be >= 1"
            )

    @property
    def key(self) -> tuple[str, int]:
        return self.name, self.version

    def step_map(self) -> dict[str, StepSpec]:
        return {
            step.step_id: step
            for step in self.steps
        }


@dataclass
class StepRuntime:
    step_id: str

    status: StepStatus = StepStatus.PENDING
    attempt: int = 0

    started_at: datetime | None = None
    deadline_at: datetime | None = None
    completed_at: datetime | None = None
    next_attempt_at: datetime | None = None

    active_effect_id: str | None = None

    approval_status: ApprovalStatus = (
        ApprovalStatus.NOT_REQUIRED
    )

    approval_id: str | None = None
    approved_by: str | None = None

    output: dict[str, Any] | None = None

    last_error: str | None = None
    last_failure_class: FailureClass | None = None

    compensation_status: CompensationStatus = (
        CompensationStatus.NONE
    )

    compensation_attempt: int = 0

    compensation_effect_id: str | None = None

    compensation_next_attempt_at: datetime | None = None


@dataclass
class WorkflowState:
    workflow_id: str
    tenant_id: str

    spec_name: str
    spec_version: int

    status: WorkflowStatus

    created_at: datetime
    updated_at: datetime

    step_runs: dict[str, StepRuntime]

    revision: int = 0

    completed_order: list[str] = field(
        default_factory=list
    )

    processed_effect_ids: dict[str, bool] = field(
        default_factory=dict
    )

    cancel_requested: bool = False
    pause_reason: str | None = None

    failure_reason: str | None = None
    quarantine_reason: str | None = None

    terminal_after_compensation: WorkflowStatus | None = None

    escalation_emitted: bool = False

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class Effect:
    effect_id: str
    workflow_id: str
    tenant_id: str

    kind: EffectKind
    step_id: str | None
    action: str

    idempotency_key: str

    payload: Mapping[str, Any]

    not_before: datetime
    deadline_at: datetime | None

    risk: ActionRisk = ActionRisk.LOW
    requires_approval: bool = False
