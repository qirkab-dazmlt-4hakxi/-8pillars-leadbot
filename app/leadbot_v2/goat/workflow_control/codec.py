from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from .models import (
    ApprovalStatus,
    CompensationStatus,
    FailureClass,
    StepRuntime,
    StepStatus,
    WorkflowState,
    WorkflowStatus,
    normalize_time,
)


def _dt(
    value: datetime | None,
) -> str | None:
    if value is None:
        return None

    return normalize_time(
        value
    ).isoformat()


def _parse_dt(
    value: str | None,
) -> datetime | None:
    if value is None:
        return None

    return normalize_time(
        datetime.fromisoformat(
            value
        )
    )


def state_to_dict(
    state: WorkflowState,
) -> dict[str, Any]:
    steps: dict[
        str,
        Any,
    ] = {}

    for step_id, runtime in (
        state.step_runs.items()
    ):
        steps[step_id] = {
            "step_id":
                runtime.step_id,
            "status":
                runtime.status.value,
            "attempt":
                runtime.attempt,
            "started_at":
                _dt(
                    runtime.started_at
                ),
            "deadline_at":
                _dt(
                    runtime.deadline_at
                ),
            "completed_at":
                _dt(
                    runtime.completed_at
                ),
            "next_attempt_at":
                _dt(
                    runtime.next_attempt_at
                ),
            "active_effect_id":
                runtime.active_effect_id,
            "approval_status":
                runtime.approval_status.value,
            "approval_id":
                runtime.approval_id,
            "approved_by":
                runtime.approved_by,
            "output":
                deepcopy(
                    runtime.output
                ),
            "last_error":
                runtime.last_error,
            "last_failure_class":
                (
                    runtime
                    .last_failure_class
                    .value
                    if runtime
                    .last_failure_class
                    else None
                ),
            "compensation_status":
                runtime
                .compensation_status
                .value,
            "compensation_attempt":
                runtime
                .compensation_attempt,
            "compensation_effect_id":
                runtime
                .compensation_effect_id,
            "compensation_next_attempt_at":
                _dt(
                    runtime
                    .compensation_next_attempt_at
                ),
        }

    return {
        "workflow_id":
            state.workflow_id,
        "tenant_id":
            state.tenant_id,
        "spec_name":
            state.spec_name,
        "spec_version":
            state.spec_version,
        "status":
            state.status.value,
        "created_at":
            _dt(
                state.created_at
            ),
        "updated_at":
            _dt(
                state.updated_at
            ),
        "step_runs":
            steps,
        "revision":
            state.revision,
        "completed_order":
            list(
                state.completed_order
            ),
        "processed_effect_ids":
            dict(
                state.processed_effect_ids
            ),
        "cancel_requested":
            state.cancel_requested,
        "pause_reason":
            state.pause_reason,
        "failure_reason":
            state.failure_reason,
        "quarantine_reason":
            state.quarantine_reason,
        "terminal_after_compensation":
            (
                state
                .terminal_after_compensation
                .value
                if state
                .terminal_after_compensation
                else None
            ),
        "escalation_emitted":
            state.escalation_emitted,
        "metadata":
            deepcopy(
                state.metadata
            ),
    }


def state_from_dict(
    payload: dict[str, Any],
) -> WorkflowState:
    step_runs: dict[
        str,
        StepRuntime,
    ] = {}

    for step_id, data in (
        payload["step_runs"].items()
    ):
        failure = data.get(
            "last_failure_class"
        )

        step_runs[step_id] = StepRuntime(
            step_id=data[
                "step_id"
            ],
            status=StepStatus(
                data["status"]
            ),
            attempt=int(
                data.get(
                    "attempt",
                    0,
                )
            ),
            started_at=_parse_dt(
                data.get(
                    "started_at"
                )
            ),
            deadline_at=_parse_dt(
                data.get(
                    "deadline_at"
                )
            ),
            completed_at=_parse_dt(
                data.get(
                    "completed_at"
                )
            ),
            next_attempt_at=_parse_dt(
                data.get(
                    "next_attempt_at"
                )
            ),
            active_effect_id=data.get(
                "active_effect_id"
            ),
            approval_status=ApprovalStatus(
                data.get(
                    "approval_status",
                    ApprovalStatus
                    .NOT_REQUIRED
                    .value,
                )
            ),
            approval_id=data.get(
                "approval_id"
            ),
            approved_by=data.get(
                "approved_by"
            ),
            output=deepcopy(
                data.get(
                    "output"
                )
            ),
            last_error=data.get(
                "last_error"
            ),
            last_failure_class=(
                FailureClass(
                    failure
                )
                if failure
                else None
            ),
            compensation_status=(
                CompensationStatus(
                    data.get(
                        "compensation_status",
                        CompensationStatus
                        .NONE
                        .value,
                    )
                )
            ),
            compensation_attempt=int(
                data.get(
                    "compensation_attempt",
                    0,
                )
            ),
            compensation_effect_id=(
                data.get(
                    "compensation_effect_id"
                )
            ),
            compensation_next_attempt_at=(
                _parse_dt(
                    data.get(
                        "compensation_next_attempt_at"
                    )
                )
            ),
        )

    terminal = payload.get(
        "terminal_after_compensation"
    )

    created_at = _parse_dt(
        payload[
            "created_at"
        ]
    )

    updated_at = _parse_dt(
        payload[
            "updated_at"
        ]
    )

    if (
        created_at is None
        or updated_at is None
    ):
        raise ValueError(
            "workflow timestamps cannot be null"
        )

    return WorkflowState(
        workflow_id=payload[
            "workflow_id"
        ],
        tenant_id=payload[
            "tenant_id"
        ],
        spec_name=payload[
            "spec_name"
        ],
        spec_version=int(
            payload[
                "spec_version"
            ]
        ),
        status=WorkflowStatus(
            payload[
                "status"
            ]
        ),
        created_at=created_at,
        updated_at=updated_at,
        step_runs=step_runs,
        revision=int(
            payload.get(
                "revision",
                0,
            )
        ),
        completed_order=list(
            payload.get(
                "completed_order",
                [],
            )
        ),
        processed_effect_ids=dict(
            payload.get(
                "processed_effect_ids",
                {},
            )
        ),
        cancel_requested=bool(
            payload.get(
                "cancel_requested",
                False,
            )
        ),
        pause_reason=payload.get(
            "pause_reason"
        ),
        failure_reason=payload.get(
            "failure_reason"
        ),
        quarantine_reason=payload.get(
            "quarantine_reason"
        ),
        terminal_after_compensation=(
            WorkflowStatus(
                terminal
            )
            if terminal
            else None
        ),
        escalation_emitted=bool(
            payload.get(
                "escalation_emitted",
                False,
            )
        ),
        metadata=deepcopy(
            payload.get(
                "metadata",
                {},
            )
        ),
    )
