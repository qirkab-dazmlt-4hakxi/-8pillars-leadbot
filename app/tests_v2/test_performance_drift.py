import unittest

from leadbot_v2.core.performance_monitor import (
    PerformanceDriftMonitor,
    PerformanceSample,
)


def sample(
    precision=.90,
    contactable=.80,
    qualified=.70,
    conversion=.50,
    revenue=100.0,
):
    return PerformanceSample(
        precision=precision,
        contactable_rate=contactable,
        qualified_rate=qualified,
        conversion_rate=conversion,
        revenue_per_lead=revenue,
    )


class PerformanceDriftTests(unittest.TestCase):

    def monitor(self):
        return PerformanceDriftMonitor(
            baseline_window=4,
            recent_window=2,
        )

    def test_insufficient_history_is_safe(self):
        m = self.monitor()
        m.add(sample())

        result = m.assess()

        self.assertFalse(result.drifting)
        self.assertEqual(result.severity, "INFO")

    def test_stable_performance_does_not_trigger(self):
        m = self.monitor()

        for _ in range(6):
            m.add(sample())

        result = m.assess()

        self.assertFalse(result.drifting)
        self.assertEqual(result.severity, "INFO")

    def test_single_metric_degradation_warns(self):
        m = self.monitor()

        for _ in range(4):
            m.add(sample(precision=.90))

        for _ in range(2):
            m.add(sample(precision=.70))

        result = m.assess()

        self.assertTrue(result.drifting)
        self.assertEqual(result.severity, "WARNING")
        self.assertTrue(
            any("precision" in reason for reason in result.reasons)
        )

    def test_multi_metric_degradation_escalates(self):
        m = self.monitor()

        for _ in range(4):
            m.add(sample(
                precision=.90,
                conversion=.50,
                revenue=100.0,
            ))

        for _ in range(2):
            m.add(sample(
                precision=.60,
                conversion=.30,
                revenue=55.0,
            ))

        result = m.assess()

        self.assertTrue(result.drifting)
        self.assertEqual(result.severity, "ERROR")
        self.assertGreaterEqual(len(result.reasons), 2)

    def test_invalid_metric_is_rejected(self):
        with self.assertRaises(ValueError):
            sample(precision=1.50)


if __name__ == "__main__":
    unittest.main()
