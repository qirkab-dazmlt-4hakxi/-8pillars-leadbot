from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .models import FailureClass


class RecoveryAction(str, Enum):
    RETRY = "retry"
    COMPENSATE = "compensate"
    FAIL = "fail"
    QUARANTINE = "quarantine"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class RecoveryDecision:
    action: RecoveryAction
    reason: str


class BoundedRecoveryPlanner:
    """
    Autonomous recovery is deliberately bounded.

    GOAT may retry known transient failures,
    compensate previously committed reversible work,
    quarantine integrity failures, or escalate.

    It may not weaken authorization, rewrite its own
    policy, bypass approval, or silently ignore integrity.
    """

    def decide(
        self,
        *,
        failure_class: FailureClass,
        attempt: int,
        max_attempts: int,
        retryable: frozenset[FailureClass],
        reversible: bool,
    ) -> RecoveryDecision:
        if failure_class is FailureClass.INTEGRITY:
            return RecoveryDecision(
                RecoveryAction.QUARANTINE,
                "integrity failure requires human investigation",
            )

        if failure_class is FailureClass.AUTHORIZATION:
            return RecoveryDecision(
                RecoveryAction.ESCALATE,
                "authorization failure is not autonomously bypassed",
            )

        if (
            failure_class in retryable
            and attempt < max_attempts
        ):
            return RecoveryDecision(
                RecoveryAction.RETRY,
                "bounded retry permitted",
            )

        if reversible:
            return RecoveryDecision(
                RecoveryAction.COMPENSATE,
                "retry unavailable; compensate committed work",
            )

        return RecoveryDecision(
            RecoveryAction.FAIL,
            "no safe autonomous recovery remains",
        )
