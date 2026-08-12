import unittest

from leadbot_v2.core.assurance import (
    AssuranceCoordinator,
    AssuranceDecision,
    AssuranceSeverity,
    AssuranceSignal,
    SystemDisposition,
)


class AssuranceCoordinatorTests(unittest.TestCase):

    def setUp(self):
        self.coordinator = AssuranceCoordinator(minimum_confidence=0.50)

    def signal(
        self,
        *,
        source="test",
        component="performance",
        severity=AssuranceSeverity.INFO,
        reason="synthetic test signal",
        confidence=1.0,
        action=None,
    ):
        return AssuranceSignal(
            source=source,
            component=component,
            severity=severity,
            reason=reason,
            confidence=confidence,
            recommended_action=action,
        )

    def test_no_signals_continues(self):
        result = self.coordinator.evaluate([])

        self.assertEqual(result.disposition, SystemDisposition.CONTINUE)
        self.assertEqual(result.severity, AssuranceSeverity.INFO)
        self.assertFalse(result.requires_human_review)

    def test_warning_degrades(self):
        result = self.coordinator.evaluate([
            self.signal(
                severity=AssuranceSeverity.WARNING,
                reason="precision drift",
            )
        ])

        self.assertEqual(result.disposition, SystemDisposition.DEGRADE)
        self.assertIn("deprioritize", result.actions)

    def test_single_error_quarantines(self):
        result = self.coordinator.evaluate([
            self.signal(
                component="performance",
                severity=AssuranceSeverity.ERROR,
                reason="major conversion collapse",
            )
        ])

        self.assertEqual(result.disposition, SystemDisposition.QUARANTINE)
        self.assertIn("quarantine", result.actions)

    def test_security_error_forces_safe_mode(self):
        result = self.coordinator.evaluate([
            self.signal(
                component="security",
                severity=AssuranceSeverity.ERROR,
                reason="integrity violation detected",
            )
        ])

        self.assertEqual(result.disposition, SystemDisposition.SAFE_MODE)
        self.assertTrue(result.requires_human_review)
        self.assertIn("safe_mode", result.actions)
        self.assertIn("human_review", result.actions)

    def test_integrity_error_forces_safe_mode(self):
        result = self.coordinator.evaluate([
            self.signal(
                component="integrity",
                severity=AssuranceSeverity.ERROR,
                reason="required module validation failed",
            )
        ])

        self.assertEqual(result.disposition, SystemDisposition.SAFE_MODE)

    def test_multiple_error_domains_force_safe_mode(self):
        result = self.coordinator.evaluate([
            self.signal(
                component="performance",
                severity=AssuranceSeverity.ERROR,
                reason="precision collapse",
            ),
            self.signal(
                component="source_health",
                severity=AssuranceSeverity.ERROR,
                reason="multiple source failures",
            ),
        ])

        self.assertEqual(result.disposition, SystemDisposition.SAFE_MODE)
        self.assertTrue(result.requires_human_review)

    def test_critical_signal_halts(self):
        result = self.coordinator.evaluate([
            self.signal(
                component="tenant_isolation",
                severity=AssuranceSeverity.CRITICAL,
                reason="cross-tenant isolation violation",
            )
        ])

        self.assertEqual(result.disposition, SystemDisposition.HALT)
        self.assertIn("halt", result.actions)
        self.assertIn("human_review", result.actions)
        self.assertTrue(result.requires_human_review)

    def test_low_confidence_signal_is_ignored(self):
        result = self.coordinator.evaluate([
            self.signal(
                component="security",
                severity=AssuranceSeverity.CRITICAL,
                reason="weak anomaly",
                confidence=0.20,
            )
        ])

        self.assertEqual(result.disposition, SystemDisposition.CONTINUE)
        self.assertEqual(result.signal_count, 0)

    def test_unsafe_requested_action_never_executes(self):
        result = self.coordinator.evaluate([
            self.signal(
                severity=AssuranceSeverity.WARNING,
                reason="malicious action request",
                action="delete_everything",
            )
        ])

        self.assertNotIn("delete_everything", result.actions)
        self.assertIn("human_review", result.actions)
        self.assertTrue(result.requires_human_review)

    def test_duplicate_actions_are_deduplicated(self):
        result = self.coordinator.evaluate([
            self.signal(
                severity=AssuranceSeverity.WARNING,
                reason="drift one",
                action="deprioritize",
            ),
            self.signal(
                severity=AssuranceSeverity.WARNING,
                reason="drift two",
                action="deprioritize",
            ),
        ])

        self.assertEqual(result.actions.count("deprioritize"), 1)

    def test_invalid_confidence_rejected(self):
        with self.assertRaises(ValueError):
            self.signal(confidence=1.50)


if __name__ == "__main__":
    unittest.main()
