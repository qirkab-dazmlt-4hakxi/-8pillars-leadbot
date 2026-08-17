from __future__ import annotations

import math

from .models import (
    FreshnessAssessment,
)


class FreshnessEngine:
    def assess(
        self,
        *,
        timestamp,
        now,
        freshness_seconds,
        hard_expiry_multiplier=4.0,
    ):
        age_seconds = max(
            0.0,
            (
                now
                - timestamp
            ).total_seconds(),
        )

        freshness_seconds = max(
            1.0,
            float(
                freshness_seconds
            ),
        )

        freshness_score = math.pow(
            0.5,
            age_seconds
            / freshness_seconds,
        )

        stale = (
            age_seconds
            > freshness_seconds
        )

        expired = (
            age_seconds
            > (
                freshness_seconds
                * hard_expiry_multiplier
            )
        )

        return FreshnessAssessment(
            age_seconds=(
                age_seconds
            ),
            freshness_score=max(
                0.0,
                min(
                    1.0,
                    freshness_score,
                ),
            ),
            stale=stale,
            expired=expired,
        )
