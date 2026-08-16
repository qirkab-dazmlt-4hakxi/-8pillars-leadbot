from __future__ import annotations

import random

from .models import (
    ScoreCard,
    SimulationResult,
)


class RevenueValueSimulator:
    def simulate(
        self,
        score: ScoreCard,
        *,
        nominal_project_value: float,
        gross_margin_ratio: float = 0.30,
        trials: int = 1000,
        seed: int = 1,
    ) -> SimulationResult:
        if trials < 1:
            raise ValueError(
                "trials must be positive"
            )

        rng = random.Random(
            seed
        )

        values = []
        wins = 0

        for _ in range(
            trials
        ):
            responds = (
                rng.random()
                <= score
                .response_probability
            )

            appointment = (
                responds
                and rng.random()
                <= score
                .appointment_probability
            )

            won = (
                appointment
                and rng.random()
                <= score
                .win_probability
            )

            if won:
                wins += 1

                value_multiplier = (
                    0.75
                    + rng.random()
                    * 0.50
                )

                realized = (
                    nominal_project_value
                    * value_multiplier
                    * gross_margin_ratio
                )

            else:
                realized = 0.0

            values.append(
                realized
            )

        values.sort()

        def percentile(
            fraction: float,
        ) -> float:
            index = min(
                len(values) - 1,
                max(
                    0,
                    int(
                        fraction
                        * (
                            len(values) - 1
                        )
                    ),
                ),
            )

            return values[
                index
            ]

        return SimulationResult(
            trials=trials,
            mean_value=(
                sum(
                    values
                )
                / len(
                    values
                )
            ),
            p10_value=percentile(
                0.10
            ),
            p50_value=percentile(
                0.50
            ),
            p90_value=percentile(
                0.90
            ),
            win_rate=(
                wins / trials
            ),
            seed=seed,
        )
