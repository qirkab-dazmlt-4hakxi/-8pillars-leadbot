from __future__ import annotations

from dataclasses import dataclass, field

from leadbot_v2.core.assurance import (
    AssuranceCoordinator,
    AssuranceDecision,
    AssuranceSeverity,
    AssuranceSignal,
)
from leadbot_v2.core.autonomic import AutonomicStatus, SystemMode
from leadbot_v2.core.performance_monitor import DriftAssessment


@dataclass(frozen=True)
class AssuranceRuntimeResult:
    decision: AssuranceDecision
    signals: tuple[AssuranceSignal, ...] = field(default_factory=tuple)


class AssuranceRuntime:
    """
    Aggregates independent subsystem findings without granting arbitrary
    execution authority.

    The runtime observes. The AssuranceCoordinator arbitrates.
    Recovery/execution remains inside bounded controllers.
    """

    SEVERITY_MAP = {
        "INFO": AssuranceSeverity.INFO,
        "WARNING": AssuranceSeverity.WARNING,
        "ERROR": AssuranceSeverity.ERROR,
        "CRITICAL": AssuranceSeverity.CRITICAL,
    }

    def __init__(
        self,
        coordinator: AssuranceCoordinator | None = None,
    ) -> None:
        self.coordinator = coordinator or AssuranceCoordinator()

    def _autonomic_signals(
        self,
        status: AutonomicStatus,
    ) -> list[AssuranceSignal]:
        signals: list[AssuranceSignal] = []

        # Existing integrity guardian already owns HALTED semantics.
        # Never permit another subsystem to silently downgrade that state.
        if status.mode == SystemMode.HALTED:
            signals.append(
                AssuranceSignal(
                    source="autonomic_supervisor",
                    component="integrity",
                    severity=AssuranceSeverity.CRITICAL,
                    reason="autonomic supervisor entered HALTED mode",
                    recommended_action="halt",
                )
            )

        elif status.mode == SystemMode.SAFE:
            signals.append(
                AssuranceSignal(
                    source="autonomic_supervisor",
                    component="integrity",
                    severity=AssuranceSeverity.ERROR,
                    reason="autonomic supervisor entered SAFE mode",
                    recommended_action="safe_mode",
                )
            )

        elif status.mode == SystemMode.DEGRADED and not status.events:
            signals.append(
                AssuranceSignal(
                    source="autonomic_supervisor",
                    component="source_health",
                    severity=AssuranceSeverity.WARNING,
                    reason="system degraded without explicit event",
                    recommended_action="deprioritize",
                )
            )

        for event in status.events:
            severity = self.SEVERITY_MAP.get(
                str(event.severity).upper(),
                AssuranceSeverity.WARNING,
            )

            action = event.action
            if action not in AssuranceCoordinator.SAFE_ACTIONS:
                action = "human_review"

            signals.append(
                AssuranceSignal(
                    source="autonomic_event",
                    component=event.component,
                    severity=severity,
                    reason=event.reason,
                    recommended_action=action,
                )
            )

        return signals

    def _performance_signals(
        self,
        drift: DriftAssessment | None,
    ) -> list[AssuranceSignal]:
        if drift is None or not drift.drifting:
            return []

        severity = self.SEVERITY_MAP.get(
            drift.severity.upper(),
            AssuranceSeverity.WARNING,
        )

        action = (
            "quarantine"
            if severity >= AssuranceSeverity.ERROR
            else "deprioritize"
        )

        return [
            AssuranceSignal(
                source="performance_drift",
                component="performance",
                severity=severity,
                reason=reason,
                recommended_action=action,
            )
            for reason in drift.reasons
        ]

    def evaluate(
        self,
        *,
        status: AutonomicStatus,
        drift: DriftAssessment | None = None,
        extra_signals: list[AssuranceSignal] | None = None,
    ) -> AssuranceRuntimeResult:
        signals: list[AssuranceSignal] = []

        signals.extend(self._autonomic_signals(status))
        signals.extend(self._performance_signals(drift))

        if extra_signals:
            signals.extend(extra_signals)

        decision = self.coordinator.evaluate(signals)

        return AssuranceRuntimeResult(
            decision=decision,
            signals=tuple(signals),
        )
