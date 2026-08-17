from __future__ import annotations

import random

from statistics import (
    fmean,
)

from .models import (
    SimulationSummary,
)


def _quantile(
    sorted_values,
    q: float,
) -> float:
    if not sorted_values:
        raise ValueError(
            "no values"
        )

    if len(
        sorted_values
    ) == 1:
        return float(
            sorted_values[
                0
            ]
        )

    position = (
        q
        * (
            len(
                sorted_values
            )
            - 1
        )
    )

    lower = int(
        position
    )

    upper = min(
        len(
            sorted_values
        )
        - 1,
        lower + 1,
    )

    fraction = (
        position
        - lower
    )

    return float(
        sorted_values[
            lower
        ]
        * (
            1.0
            - fraction
        )
        + sorted_values[
            upper
        ]
        * fraction
    )


class MonteCarloSimulator:
    def run(
        self,
        model,
        *,
        simulations: int = 10_000,
        seed: int = 0,
    ) -> SimulationSummary:
        if simulations < 100:
            raise ValueError(
                "simulations must be at least 100"
            )

        rng = random.Random(
            seed
        )

        values = [
            float(
                model(
                    rng
                )
            )
            for _
            in range(
                simulations
            )
        ]

        values.sort()

        below_zero = (
            sum(
                value < 0.0
                for value
                in values
            )
            / len(
                values
            )
        )

        return SimulationSummary(
            simulations=(
                simulations
            ),
            mean=fmean(
                values
            ),
            p05=_quantile(
                values,
                0.05,
            ),
            p50=_quantile(
                values,
                0.50,
            ),
            p95=_quantile(
                values,
                0.95,
            ),
            minimum=(
                values[0]
            ),
            maximum=(
                values[-1]
            ),
            probability_below_zero=(
                below_zero
            ),
            seed=seed,
        )
