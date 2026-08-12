import unittest
from types import SimpleNamespace

from leadbot_v2.core.assurance import (
    AssuranceSeverity,
    AssuranceSignal,
    SystemDisposition,
)
from leadbot_v2.core.assurance_runtime import AssuranceRuntime
from leadbot_v2.core.autonomic import SystemMode
from leadbot_v2.core.performance_monitor import DriftAssessment


def status(mode, events=None):
    return SimpleNamespace(
        mode=mode,
        events=list(events or []),
    )


class AssuranceRuntimeTests(unittest.TestCase):

    def setUp(self):
        self.runtime = AssuranceRuntime()

    def test_normal_system_continues(self):
        result = self.runtime.evaluate(
            status=status(SystemMode.NORMAL)
        )

        self.assertEqual(
            result.decision.disposition,
            SystemDisposition.CONTINUE,
        )

    def test_warning_drift_degrades(self):
        drift = DriftAssessment(
            drifting=True,
            severity="WARNING",
            reasons=["precision degraded 15%"],
        )

        result = self.runtime.evaluate(
            status=status(SystemMode.NORMAL),
            drift=drift,
        )

        self.assertEqual(
            result.decision.disposition,
            SystemDisposition.DEGRADE,
        )
        self.assertIn("deprioritize", result.decision.actions)

    def test_error_drift_quarantines(self):
        drift = DriftAssessment(
            drifting=True,
            severity="ERROR",
            reasons=[
                "precision degraded",
                "conversion degraded",
            ],
        )

        result = self.runtime.evaluate(
            status=status(SystemMode.NORMAL),
            drift=drift,
        )

        self.assertEqual(
            result.decision.disposition,
            SystemDisposition.QUARANTINE,
        )

    def test_safe_mode_cannot_be_downgraded(self):
        drift = DriftAssessment(
            drifting=True,
            severity="WARNING",
            reasons=["minor revenue drift"],
        )

        result = self.runtime.evaluate(
            status=status(SystemMode.SAFE),
            drift=drift,
        )

        self.assertEqual(
            result.decision.disposition,
            SystemDisposition.SAFE_MODE,
        )
        self.assertTrue(result.decision.requires_human_review)

    def test_halted_mode_dominates_everything(self):
        drift = DriftAssessment(
            drifting=True,
            severity="WARNING",
            reasons=["minor precision drift"],
        )

        result = self.runtime.evaluate(
            status=status(SystemMode.HALTED),
            drift=drift,
        )

        self.assertEqual(
            result.decision.disposition,
            SystemDisposition.HALT,
        )
        self.assertEqual(
            result.decision.severity,
            AssuranceSeverity.CRITICAL,
        )
        self.assertIn("halt", result.decision.actions)
        self.assertTrue(result.decision.requires_human_review)

    def test_external_security_signal_forces_safe_mode(self):
        threat = AssuranceSignal(
            source="security_monitor",
            component="security",
            severity=AssuranceSeverity.ERROR,
            reason="credential misuse anomaly",
            recommended_action="quarantine",
        )

        result = self.runtime.evaluate(
            status=status(SystemMode.NORMAL),
            extra_signals=[threat],
        )

        self.assertEqual(
            result.decision.disposition,
            SystemDisposition.SAFE_MODE,
        )

    def test_external_critical_signal_halts(self):
        threat = AssuranceSignal(
            source="tenant_guard",
            component="tenant_isolation",
            severity=AssuranceSeverity.CRITICAL,
            reason="cross-tenant boundary violation",
            recommended_action="halt",
        )

        result = self.runtime.evaluate(
            status=status(SystemMode.NORMAL),
            extra_signals=[threat],
        )

        self.assertEqual(
            result.decision.disposition,
            SystemDisposition.HALT,
        )

    def test_unknown_event_action_becomes_human_review(self):
        event = SimpleNamespace(
            component="source",
            action="destroy_database",
            reason="synthetic hostile action",
            severity="WARNING",
        )

        result = self.runtime.evaluate(
            status=status(SystemMode.DEGRADED, [event]),
        )

        self.assertNotIn(
            "destroy_database",
            result.decision.actions,
        )
        self.assertIn(
            "human_review",
            result.decision.actions,
        )


if __name__ == "__main__":
    unittest.main()
