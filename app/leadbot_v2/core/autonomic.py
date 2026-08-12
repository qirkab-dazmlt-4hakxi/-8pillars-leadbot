from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from leadbot_v2.core.integrity import (
    IntegrityReport,
    SystemIntegrityGuardian,
)
from leadbot_v2.core.recovery import RecoveryPolicy
from leadbot_v2.core.incident_store import IncidentStore
from leadbot_v2.core.source_health import (
    SourceCircuitBreaker,
)


class SystemMode(str, Enum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    SAFE = "safe"
    HALTED = "halted"


@dataclass
class AutonomicEvent:
    component: str
    action: str
    reason: str
    severity: str


@dataclass
class AutonomicStatus:
    mode: SystemMode
    integrity: IntegrityReport
    events: list[AutonomicEvent] = field(
        default_factory=list
    )


class AutonomicSupervisor:
    def __init__(
        self,
        breaker: SourceCircuitBreaker,
    ) -> None:
        self.breaker = breaker
        self.integrity = SystemIntegrityGuardian()
        self.recovery = RecoveryPolicy(breaker)

    def evaluate(self) -> AutonomicStatus:
        report = self.integrity.run()
        events: list[AutonomicEvent] = []

        if not report.healthy:
            for issue in report.issues:
                events.append(
                    AutonomicEvent(
                        component=issue.component,
                        action="block_startup",
                        reason=issue.message,
                        severity=issue.severity,
                    )
                )

            return AutonomicStatus(
                mode=SystemMode.HALTED,
                integrity=report,
                events=events,
            )

        degraded = False

        for source in self.breaker.sources:
            decision = self.recovery.evaluate(
                source
            )

            if decision.action == "failover":
                degraded = True

                events.append(
                    AutonomicEvent(
                        component=source,
                        action="failover",
                        reason=decision.reason,
                        severity="ERROR",
                    )
                )

            elif decision.action == "deprioritize":
                degraded = True

                events.append(
                    AutonomicEvent(
                        component=source,
                        action="deprioritize",
                        reason=decision.reason,
                        severity="WARNING",
                    )
                )

            elif decision.action == "probe":
                events.append(
                    AutonomicEvent(
                        component=source,
                        action="probe",
                        reason=decision.reason,
                        severity="INFO",
                    )
                )

        return AutonomicStatus(
            mode=(
                SystemMode.DEGRADED
                if degraded
                else SystemMode.NORMAL
            ),
            integrity=report,
            events=events,
        )


@dataclass
class RecoveryAction:
    component: str
    action: str
    reason: str
    allowed: bool


class RecoveryController:
    SAFE_ACTIONS = {
        "failover",
        "deprioritize",
        "probe",
        "retry",
        "quarantine",
        "rollback_config",
    }

    def decide(
        self,
        event: AutonomicEvent,
    ) -> RecoveryAction:
        allowed = event.action in self.SAFE_ACTIONS

        return RecoveryAction(
            component=event.component,
            action=event.action,
            reason=event.reason,
            allowed=allowed,
        )


class EventJournal:
    def __init__(self) -> None:
        self.events: list[AutonomicEvent] = []

    def record(
        self,
        event: AutonomicEvent,
    ) -> None:
        self.events.append(event)

    def recent(
        self,
        limit: int = 50,
    ) -> list[AutonomicEvent]:
        return self.events[-limit:]


class ManagedAutonomicSupervisor(
    AutonomicSupervisor
):
    def __init__(
        self,
        breaker: SourceCircuitBreaker,
    ) -> None:
        super().__init__(breaker)

        self.controller = RecoveryController()
        self.journal = EventJournal()
        self.incidents = IncidentStore()

    def evaluate_and_plan(
        self,
    ) -> tuple[
        AutonomicStatus,
        list[RecoveryAction],
    ]:
        status = self.evaluate()
        actions: list[RecoveryAction] = []

        for event in status.events:
            self.journal.record(event)

            incident = self.incidents.record(
                component=event.component,
                action=event.action,
                reason=event.reason,
                severity=event.severity,
            )

            action = self.controller.decide(
                event
            )

            # Escalation ladder:
            # 1-2 occurrences: normal bounded recovery
            # 3-5 occurrences: quarantine/deprioritize
            # 6+ occurrences: require human review
            if incident.count >= 6:
                action = RecoveryAction(
                    component=event.component,
                    action="human_review",
                    reason=(
                        f"repeated incident threshold reached "
                        f"({incident.count} occurrences): "
                        f"{event.reason}"
                    ),
                    allowed=False,
                )

            elif incident.count >= 3:
                action = RecoveryAction(
                    component=event.component,
                    action="quarantine",
                    reason=(
                        f"recurring fault "
                        f"({incident.count} occurrences): "
                        f"{event.reason}"
                    ),
                    allowed=True,
                )

            actions.append(action)

        return status, actions
