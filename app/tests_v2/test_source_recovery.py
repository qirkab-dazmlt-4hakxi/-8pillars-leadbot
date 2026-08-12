import unittest

from leadbot_v2.core.recovery import RecoveryPolicy
from leadbot_v2.core.source_health import (
    CircuitState,
    SourceCircuitBreaker,
)


class SourceRecoveryTests(unittest.TestCase):

    def test_three_failures_open_circuit(self):
        b = SourceCircuitBreaker(
            failure_threshold=3,
            cooldown_seconds=60,
        )

        for _ in range(3):
            b.record_failure(
                "reddit",
                error="403 blocked",
            )

        self.assertEqual(
            b.get("reddit").state,
            CircuitState.OPEN,
        )

        decision = RecoveryPolicy(b).evaluate("reddit")
        self.assertEqual(decision.action, "failover")

    def test_success_clears_failure_streak(self):
        b = SourceCircuitBreaker(
            failure_threshold=3,
        )

        b.record_failure("brave", error="timeout")
        b.record_failure("brave", error="timeout")

        b.record_success(
            "brave",
            latency_ms=240,
        )

        self.assertEqual(
            b.get("brave").consecutive_failures,
            0,
        )

    def test_high_latency_deprioritizes(self):
        b = SourceCircuitBreaker()

        b.record_success(
            "slow_source",
            latency_ms=9000,
        )

        decision = RecoveryPolicy(b).evaluate(
            "slow_source"
        )

        self.assertEqual(
            decision.action,
            "deprioritize",
        )

    def test_fast_reliable_source_ranks_first(self):
        b = SourceCircuitBreaker()

        for _ in range(5):
            b.record_success(
                "fast",
                latency_ms=200,
            )

        for _ in range(5):
            b.record_success(
                "slow",
                latency_ms=2000,
            )

        ranked = b.ranked_available_sources(
            ["slow", "fast"]
        )

        self.assertEqual(ranked[0], "fast")


if __name__ == "__main__":
    unittest.main()
