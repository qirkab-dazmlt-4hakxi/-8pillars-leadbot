from __future__ import annotations

from collections import (
    defaultdict,
)

from .models import (
    LatencyBudget,
    LatencySnapshot,
)


def _percentile(
    values,
    q: float,
) -> float:
    if not values:
        return 0.0

    ordered = sorted(
        float(
            value
        )
        for value
        in values
    )

    position = (
        q
        * (
            len(
                ordered
            )
            - 1
        )
    )

    lower = int(
        position
    )

    upper = min(
        len(
            ordered
        )
        - 1,
        lower + 1,
    )

    fraction = (
        position
        - lower
    )

    return (
        ordered[
            lower
        ]
        * (
            1
            - fraction
        )
        + ordered[
            upper
        ]
        * fraction
    )


class LatencyMonitor:
    def __init__(
        self,
    ) -> None:
        self._samples = defaultdict(
            list
        )

        self._budgets: dict[
            str,
            LatencyBudget,
        ] = {}

    def set_budget(
        self,
        budget: LatencyBudget,
    ) -> None:
        if not (
            budget.p50_target_ms
            <= budget.p95_target_ms
            <= budget.p99_target_ms
        ):
            raise ValueError(
                "latency budget must be monotonic"
            )

        self._budgets[
            budget.operation
        ] = budget

    def observe(
        self,
        operation: str,
        latency_ms: float,
    ) -> None:
        if latency_ms < 0:
            raise ValueError(
                "latency cannot be negative"
            )

        bucket = self._samples[
            operation
        ]

        bucket.append(
            float(
                latency_ms
            )
        )

        if len(
            bucket
        ) > 10_000:
            del bucket[
                :
                len(
                    bucket
                )
                - 10_000
            ]

    def snapshot(
        self,
        operation: str,
    ) -> LatencySnapshot:
        values = self._samples.get(
            operation,
            [],
        )

        p50 = _percentile(
            values,
            0.50,
        )

        p95 = _percentile(
            values,
            0.95,
        )

        p99 = _percentile(
            values,
            0.99,
        )

        maximum = (
            max(
                values
            )
            if values
            else 0.0
        )

        budget = self._budgets.get(
            operation
        )

        within = (
            True
            if budget is None
            else (
                p50
                <= budget
                .p50_target_ms
                and p95
                <= budget
                .p95_target_ms
                and p99
                <= budget
                .p99_target_ms
            )
        )

        return LatencySnapshot(
            operation=(
                operation
            ),
            samples=len(
                values
            ),
            p50_ms=p50,
            p95_ms=p95,
            p99_ms=p99,
            max_ms=(
                maximum
            ),
            within_budget=(
                within
            ),
        )
