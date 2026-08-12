import unittest

from leadbot_v2.core.source_health import (
    SourceCircuitBreaker,
)


class FaultLearningTests(unittest.TestCase):

    def test_flaky_source_loses_priority(self):
        b = SourceCircuitBreaker(
            failure_threshold=10,
        )

        for _ in range(10):
            b.record_success(
                "healthy",
                latency_ms=200,
            )

        for _ in range(5):
            b.record_success(
                "flaky",
                latency_ms=500,
            )

        for _ in range(5):
            b.record_failure(
                "flaky",
                error="timeout",
            )

        ranked = b.ranked_available_sources(
            ["flaky", "healthy"]
        )

        self.assertEqual(ranked[0], "healthy")

    def test_recovered_source_improves(self):
        b = SourceCircuitBreaker(
            failure_threshold=20,
        )

        for _ in range(4):
            b.record_failure(
                "recovering",
                error="temporary failure",
            )

        before = (
            b.fault_learning
            .priority_multiplier(
                b.get("recovering")
            )
        )

        for _ in range(20):
            b.record_success(
                "recovering",
                latency_ms=250,
            )

        after = (
            b.fault_learning
            .priority_multiplier(
                b.get("recovering")
            )
        )

        self.assertGreater(after, before)

    def test_chronic_failures_detected(self):
        b = SourceCircuitBreaker(
            failure_threshold=20,
        )

        for _ in range(6):
            b.record_failure(
                "bad_source",
                error="failure",
            )

        for _ in range(4):
            b.record_success(
                "bad_source",
                latency_ms=500,
            )

        assessment = (
            b.fault_learning
            .assess(
                b.get("bad_source")
            )
        )

        self.assertTrue(assessment.chronic)


if __name__ == "__main__":
    unittest.main()
