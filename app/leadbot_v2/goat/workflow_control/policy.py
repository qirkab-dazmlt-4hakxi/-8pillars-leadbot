from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .models import (
    ActionRisk,
    StepSpec,
    StepStatus,
    WorkflowSpec,
    WorkflowState,
)


class PolicyResult(str, Enum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


@dataclass(frozen=True)
class PolicyDecision:
    result: PolicyResult
    reason: str


@dataclass(frozen=True)
class ExecutionPolicy:
    max_parallelism: int = 8

    max_side_effects_per_workflow: int = 100

    approval_risks: frozenset[ActionRisk] = field(
        default_factory=lambda: frozenset(
            {
                ActionRisk.HIGH,
                ActionRisk.CRITICAL,
            }
        )
    )

    denied_risks: frozenset[ActionRisk] = field(
        default_factory=frozenset
    )

    blocked_action_prefixes: tuple[str, ...] = ()

    require_approval_for_irreversible: bool = True

    def __post_init__(self) -> None:
        if self.max_parallelism < 1:
            raise ValueError(
                "max_parallelism must be >= 1"
            )

        if self.max_side_effects_per_workflow < 1:
            raise ValueError(
                "max_side_effects_per_workflow must be >= 1"
            )

    def effective_parallelism(
        self,
        spec: WorkflowSpec,
    ) -> int:
        return min(
            self.max_parallelism,
            spec.max_parallelism,
        )

    def evaluate(
        self,
        *,
        spec: WorkflowSpec,
        state: WorkflowState,
        step: StepSpec,
    ) -> PolicyDecision:
        if any(
            step.action.startswith(prefix)
            for prefix in self.blocked_action_prefixes
        ):
            return PolicyDecision(
                PolicyResult.DENY,
                "action blocked by execution policy",
            )

        if step.risk in self.denied_risks:
            return PolicyDecision(
                PolicyResult.DENY,
                f"risk class denied: {step.risk.value}",
            )

        if step.side_effect:
            step_map = spec.step_map()

            started_side_effects = sum(
                1
                for step_id, runtime
                in state.step_runs.items()
                if step_map[step_id].side_effect
                and runtime.status
                in {
                    StepStatus.RUNNING,
                    StepStatus.SUCCEEDED,
                    StepStatus.FAILED,
                }
            )

            runtime = state.step_runs[
                step.step_id
            ]

            not_started = (
                runtime.attempt == 0
                and runtime.status
                in {
                    StepStatus.PENDING,
                    StepStatus.WAITING_APPROVAL,
                }
            )

            if (
                not_started
                and started_side_effects
                >= self.max_side_effects_per_workflow
            ):
                return PolicyDecision(
                    PolicyResult.DENY,
                    "workflow side-effect budget exhausted",
                )

        if step.requires_approval:
            return PolicyDecision(
                PolicyResult.REQUIRE_APPROVAL,
                "step explicitly requires approval",
            )

        if (
            step.irreversible
            and self.require_approval_for_irreversible
        ):
            return PolicyDecision(
                PolicyResult.REQUIRE_APPROVAL,
                "irreversible side effect requires approval",
            )

        if step.risk in self.approval_risks:
            return PolicyDecision(
                PolicyResult.REQUIRE_APPROVAL,
                f"{step.risk.value} risk requires approval",
            )

        return PolicyDecision(
            PolicyResult.ALLOW,
            "allowed",
        )
