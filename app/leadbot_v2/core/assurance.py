from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, Enum


class AssuranceSeverity(IntEnum):
    INFO = 0
    WARNING = 1
    ERROR = 2
    CRITICAL = 3


class SystemDisposition(str, Enum):
    CONTINUE = "continue"
    DEGRADE = "degrade"
    QUARANTINE = "quarantine"
    SAFE_MODE = "safe_mode"
    HALT = "halt"


@dataclass(frozen=True)
class AssuranceSignal:
    source: str
    component: str
    severity: AssuranceSeverity
    reason: str
    confidence: float = 1.0
    recommended_action: str | None = None
    evidence_id: str | None = None

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("source is required")

        if not self.component.strip():
            raise ValueError("component is required")

        if not self.reason.strip():
            raise ValueError("reason is required")

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class AssuranceDecision:
    disposition: SystemDisposition
    severity: AssuranceSeverity
    actions: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    affected_components: tuple[str, ...] = ()
    requires_human_review: bool = False
    signal_count: int = 0


class AssuranceCoordinator:
    """
    Deterministic supervisory arbitration layer.

    It does not execute recovery itself. It converts independent subsystem
    findings into a bounded, auditable decision for the autonomic control plane.
    """

    SAFE_ACTIONS = frozenset({
        "continue",
        "probe",
        "retry",
        "deprioritize",
        "failover",
        "quarantine",
        "rollback_config",
        "safe_mode",
        "halt",
        "human_review",
    })

    HIGH_ASSURANCE_COMPONENTS = frozenset({
        "security",
        "integrity",
        "identity",
        "authorization",
        "secrets",
        "tenant_isolation",
    })

    def __init__(self, *, minimum_confidence: float = 0.50) -> None:
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be between 0 and 1")

        self.minimum_confidence = minimum_confidence

    def evaluate(
        self,
        signals: list[AssuranceSignal],
    ) -> AssuranceDecision:

        active = [
            signal
            for signal in signals
            if signal.confidence >= self.minimum_confidence
        ]

        if not active:
            return AssuranceDecision(
                disposition=SystemDisposition.CONTINUE,
                severity=AssuranceSeverity.INFO,
                actions=("continue",),
            )

        highest = max(signal.severity for signal in active)

        components = tuple(sorted({
            signal.component for signal in active
        }))

        reasons = tuple(
            f"{signal.source}:{signal.component}: {signal.reason}"
            for signal in active
        )

        requested_actions: list[str] = []

        for signal in active:
            action = signal.recommended_action

            if action and action in self.SAFE_ACTIONS:
                requested_actions.append(action)

            elif action:
                requested_actions.append("human_review")

        error_components = {
            signal.component
            for signal in active
            if signal.severity >= AssuranceSeverity.ERROR
        }

        protected_failure = any(
            signal.component in self.HIGH_ASSURANCE_COMPONENTS
            and signal.severity >= AssuranceSeverity.ERROR
            for signal in active
        )

        critical = any(
            signal.severity == AssuranceSeverity.CRITICAL
            for signal in active
        )

        if critical:
            disposition = SystemDisposition.HALT
            requested_actions.extend(("halt", "human_review"))

        elif protected_failure:
            disposition = SystemDisposition.SAFE_MODE
            requested_actions.extend(("safe_mode", "human_review"))

        elif len(error_components) >= 2:
            disposition = SystemDisposition.SAFE_MODE
            requested_actions.extend(("safe_mode", "human_review"))

        elif highest == AssuranceSeverity.ERROR:
            disposition = SystemDisposition.QUARANTINE
            requested_actions.append("quarantine")

        elif highest == AssuranceSeverity.WARNING:
            disposition = SystemDisposition.DEGRADE
            requested_actions.append("deprioritize")

        else:
            disposition = SystemDisposition.CONTINUE
            requested_actions.append("continue")

        # Preserve deterministic ordering while removing duplicates.
        actions = tuple(dict.fromkeys(requested_actions))

        requires_human_review = (
            "human_review" in actions
            or disposition in {
                SystemDisposition.SAFE_MODE,
                SystemDisposition.HALT,
            }
        )

        return AssuranceDecision(
            disposition=disposition,
            severity=highest,
            actions=actions,
            reasons=reasons,
            affected_components=components,
            requires_human_review=requires_human_review,
            signal_count=len(active),
        )
