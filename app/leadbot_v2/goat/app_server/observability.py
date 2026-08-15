from __future__ import annotations

import math
import threading
import time

from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class MetricSnapshot:
    counters: dict[
        str,
        int,
    ]

    gauges: dict[
        str,
        float,
    ]

    histogram_counts: dict[
        str,
        int,
    ]

    histogram_totals: dict[
        str,
        float,
    ]


class MetricsRegistry:
    """
    Lightweight in-process metrics registry.

    Production exporters can bridge this to OpenTelemetry,
    Prometheus or another observability backend.
    """

    def __init__(
        self,
    ) -> None:
        self._lock = (
            threading.RLock()
        )

        self._counters = (
            defaultdict(int)
        )

        self._gauges = (
            defaultdict(float)
        )

        self._hist_count = (
            defaultdict(int)
        )

        self._hist_total = (
            defaultdict(float)
        )

    def increment(
        self,
        name: str,
        amount: int = 1,
    ) -> None:
        with self._lock:
            self._counters[
                str(name)
            ] += int(
                amount
            )

    def gauge(
        self,
        name: str,
        value: float,
    ) -> None:
        value = float(
            value
        )

        if not math.isfinite(
            value
        ):
            raise ValueError(
                "gauge must be finite"
            )

        with self._lock:
            self._gauges[
                str(name)
            ] = value

    def observe(
        self,
        name: str,
        value: float,
    ) -> None:
        value = float(
            value
        )

        if (
            not math.isfinite(
                value
            )
            or value < 0
        ):
            raise ValueError(
                "observation invalid"
            )

        with self._lock:
            self._hist_count[
                str(name)
            ] += 1

            self._hist_total[
                str(name)
            ] += value

    def snapshot(
        self,
    ) -> MetricSnapshot:
        with self._lock:
            return MetricSnapshot(
                counters=dict(
                    self._counters
                ),
                gauges=dict(
                    self._gauges
                ),
                histogram_counts=dict(
                    self._hist_count
                ),
                histogram_totals=dict(
                    self._hist_total
                ),
            )


class Timer:
    def __init__(
        self,
        registry: MetricsRegistry,
        metric: str,
    ) -> None:
        self.registry = (
            registry
        )

        self.metric = (
            metric
        )

        self.started = 0.0

    def __enter__(
        self,
    ) -> "Timer":
        self.started = (
            time.monotonic()
        )

        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ) -> None:
        elapsed = max(
            0.0,
            time.monotonic()
            - self.started,
        )

        self.registry.observe(
            self.metric,
            elapsed,
        )
