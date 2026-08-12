import tempfile
import unittest
from pathlib import Path

from leadbot_v2.core.autonomic import (
    AutonomicEvent,
    EventJournal,
    RecoveryController,
    RecoveryAction,
)
from leadbot_v2.core.incident_store import IncidentStore


class EscalationHarness:
    def __init__(self, path):
        self.journal = EventJournal()
        self.controller = RecoveryController()
        self.incidents = IncidentStore(path)

    def handle(self, event):
        self.journal.record(event)

        incident = self.incidents.record(
            component=event.component,
            action=event.action,
            reason=event.reason,
            severity=event.severity,
        )

        action = self.controller.decide(event)

        if incident.count >= 6:
            return RecoveryAction(
                component=event.component,
                action="human_review",
                reason=f"repeated incident threshold reached ({incident.count})",
                allowed=False,
            )

        if incident.count >= 3:
            return RecoveryAction(
                component=event.component,
                action="quarantine",
                reason=f"recurring fault ({incident.count})",
                allowed=True,
            )

        return action


class AutonomicEscalationTests(unittest.TestCase):

    def test_repeated_fault_escalates(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "incidents.json"
            h = EscalationHarness(path)

            e = AutonomicEvent(
                component="brave:web",
                action="failover",
                reason="timeout",
                severity="ERROR",
            )

            a1 = h.handle(e)
            a2 = h.handle(e)
            a3 = h.handle(e)

            self.assertEqual(a1.action, "failover")
            self.assertEqual(a2.action, "failover")
            self.assertEqual(a3.action, "quarantine")

    def test_human_review_at_six(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "incidents.json"
            h = EscalationHarness(path)

            e = AutonomicEvent(
                component="reddit",
                action="failover",
                reason="403",
                severity="ERROR",
            )

            action = None

            for _ in range(6):
                action = h.handle(e)

            self.assertIsNotNone(action)
            self.assertEqual(action.action, "human_review")
            self.assertFalse(action.allowed)

    def test_incident_persists_across_restart(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "incidents.json"

            h1 = EscalationHarness(path)

            e = AutonomicEvent(
                component="source-x",
                action="failover",
                reason="failure",
                severity="ERROR",
            )

            h1.handle(e)
            h1.handle(e)

            h2 = EscalationHarness(path)
            a3 = h2.handle(e)

            self.assertEqual(a3.action, "quarantine")


if __name__ == "__main__":
    unittest.main()
