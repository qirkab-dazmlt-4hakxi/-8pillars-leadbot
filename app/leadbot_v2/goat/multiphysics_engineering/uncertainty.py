from __future__ import annotations

import math
import random

from .models import (
    EngineeringModelError,
    UncertaintyResult,
)


def percentile(
    ordered,
    probability,
):
    if not ordered:
        raise ValueError(
            "percentile requires samples"
        )

    position = (
        probability
        * (
            len(ordered)
            - 1
        )
    )

    lower = int(
        math.floor(position)
    )

    upper = int(
        math.ceil(position)
    )

    if lower == upper:
        return ordered[lower]

    fraction = (
        position
        - lower
    )

    return (
        ordered[lower]
        * (1.0 - fraction)
        + ordered[upper]
        * fraction
    )


class UncertaintyEngine:
    def simulate(
        self,
        *,
        variables,
        evaluator,
        samples=5000,
        seed=1,
    ):
        if samples <= 0:
            raise EngineeringModelError(
                "samples must be positive"
            )

        variables = tuple(
            variables
        )

        rng = random.Random(
            int(seed)
        )

        results = []

        for _ in range(samples):
            sampled = {}

            for variable in variables:
                if (
                    variable
                    .standard_deviation
                    < 0
                ):
                    raise EngineeringModelError(
                        "standard deviation "
                        "cannot be negative"
                    )

                value = rng.gauss(
                    variable.mean,
                    variable
                    .standard_deviation,
                )

                if (
                    variable.minimum
                    is not None
                ):
                    value = max(
                        variable.minimum,
                        value,
                    )

                if (
                    variable.maximum
                    is not None
                ):
                    value = min(
                        variable.maximum,
                        value,
                    )

                sampled[
                    variable.name
                ] = value

            output = float(
                evaluator(sampled)
            )

            if not math.isfinite(
                output
            ):
                raise EngineeringModelError(
                    "uncertainty evaluator returned "
                    "non-finite value"
                )

            results.append(
                output
            )

        ordered = sorted(
            results
        )

        mean = (
            sum(results)
            / len(results)
        )

        variance = sum(
            (
                value
                - mean
            ) ** 2
            for value
            in results
        ) / max(
            1,
            len(results) - 1,
        )

        return UncertaintyResult(
            samples=samples,
            seed=int(seed),
            mean=mean,
            standard_deviation=(
                math.sqrt(
                    variance
                )
            ),
            p05=percentile(
                ordered,
                0.05,
            ),
            p50=percentile(
                ordered,
                0.50,
            ),
            p95=percentile(
                ordered,
                0.95,
            ),
            minimum=ordered[0],
            maximum=ordered[-1],
        )
