from __future__ import annotations

from dataclasses import dataclass
from math import log


@dataclass(frozen=True)
class DriftSnapshot:
    psi: float
    level: str


def _distribution(
    values,
    *,
    buckets=10,
):
    counts = [
        0
        for _ in range(
            buckets
        )
    ]

    if not values:
        return [
            1.0 / buckets
            for _ in range(
                buckets
            )
        ]

    for value in values:
        value = max(
            0.0,
            min(
                0.999999,
                float(
                    value
                ),
            ),
        )

        index = min(
            buckets - 1,
            int(
                value
                * buckets
            ),
        )

        counts[
            index
        ] += 1

    total = sum(
        counts
    )

    return [
        max(
            1e-6,
            count / total,
        )
        for count
        in counts
    ]


class PopulationDriftMonitor:
    def compare(
        self,
        baseline,
        current,
        *,
        buckets=10,
    ) -> DriftSnapshot:
        expected = _distribution(
            baseline,
            buckets=buckets,
        )

        actual = _distribution(
            current,
            buckets=buckets,
        )

        psi = sum(
            (
                actual_value
                - expected_value
            )
            * log(
                actual_value
                / expected_value
            )
            for expected_value, actual_value
            in zip(
                expected,
                actual,
            )
        )

        if psi >= 0.25:
            level = "material"

        elif psi >= 0.10:
            level = "watch"

        else:
            level = "stable"

        return DriftSnapshot(
            psi=psi,
            level=level,
        )
