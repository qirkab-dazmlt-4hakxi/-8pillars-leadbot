from __future__ import annotations

from dataclasses import dataclass
from math import exp
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from leadbot_v2.core.source_health import SourceHealth


@dataclass(frozen=True)
class FaultAssessment:
    reliability_score: float
    penalty: float
    chronic: bool
    reason: str


class FaultLearningPolicy:
    def __init__(
        self,
        *,
        chronic_failure_rate: float = 0.35,
        minimum_samples: int = 8,
    ) -> None:
        self.chronic_failure_rate = chronic_failure_rate
        self.minimum_samples = minimum_samples

    def assess(
        self,
        health: SourceHealth,
    ) -> FaultAssessment:
        total = max(health.total_requests, 1)
        failure_rate = health.failures / total

        chronic = (
            health.total_requests >= self.minimum_samples
            and failure_rate >= self.chronic_failure_rate
        )

        reliability = max(
            0.0,
            min(
                1.0,
                1.0
                - failure_rate
                - min(health.consecutive_failures * 0.08, 0.40),
            ),
        )

        latency_penalty = min(
            health.latency_ms_ema / 12000.0,
            0.30,
        )

        penalty = min(
            1.0,
            (1.0 - reliability) + latency_penalty,
        )

        if chronic:
            reason = (
                f"chronic instability: "
                f"{health.failures}/{health.total_requests} failures"
            )
        elif health.consecutive_failures:
            reason = (
                f"transient instability: "
                f"{health.consecutive_failures} consecutive failures"
            )
        else:
            reason = "source operating within learned baseline"

        return FaultAssessment(
            reliability_score=reliability,
            penalty=penalty,
            chronic=chronic,
            reason=reason,
        )

    def priority_multiplier(
        self,
        health: SourceHealth,
    ) -> float:
        assessment = self.assess(health)

        # Smoothly suppress unreliable sources without permanently
        # blacklisting them.
        return max(
            0.10,
            exp(-2.25 * assessment.penalty),
        )
