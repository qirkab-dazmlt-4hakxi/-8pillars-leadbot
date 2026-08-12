from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PerformanceSample:
    precision: float
    contactable_rate: float
    qualified_rate: float
    conversion_rate: float
    revenue_per_lead: float

    def __post_init__(self) -> None:
        for name in (
            "precision",
            "contactable_rate",
            "qualified_rate",
            "conversion_rate",
        ):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")

        if self.revenue_per_lead < 0:
            raise ValueError("revenue_per_lead cannot be negative")


@dataclass(frozen=True)
class DriftAssessment:
    drifting: bool
    severity: str
    reasons: list[str] = field(default_factory=list)
    baseline: dict[str, float] = field(default_factory=dict)
    recent: dict[str, float] = field(default_factory=dict)


class PerformanceDriftMonitor:
    METRICS = (
        "precision",
        "contactable_rate",
        "qualified_rate",
        "conversion_rate",
        "revenue_per_lead",
    )

    def __init__(
        self,
        *,
        baseline_window: int = 50,
        recent_window: int = 10,
        precision_drop: float = 0.12,
        contactable_drop: float = 0.15,
        qualified_drop: float = 0.15,
        conversion_drop: float = 0.15,
        revenue_drop: float = 0.20,
    ) -> None:
        if baseline_window < 1 or recent_window < 1:
            raise ValueError("windows must be positive")

        self.baseline_window = baseline_window
        self.recent_window = recent_window
        self.samples = deque(maxlen=baseline_window + recent_window)

        self.thresholds = {
            "precision": precision_drop,
            "contactable_rate": contactable_drop,
            "qualified_rate": qualified_drop,
            "conversion_rate": conversion_drop,
            "revenue_per_lead": revenue_drop,
        }

    def add(self, sample: PerformanceSample) -> None:
        self.samples.append(sample)

    @staticmethod
    def _avg(samples, metric: str) -> float:
        return sum(getattr(s, metric) for s in samples) / len(samples)

    @staticmethod
    def _relative_drop(old: float, new: float) -> float:
        if old <= 0:
            return 0.0
        return max(0.0, (old - new) / old)

    def assess(self) -> DriftAssessment:
        needed = self.baseline_window + self.recent_window

        if len(self.samples) < needed:
            return DriftAssessment(
                drifting=False,
                severity="INFO",
                reasons=["insufficient history"],
            )

        values = list(self.samples)
        baseline_samples = values[: self.baseline_window]
        recent_samples = values[-self.recent_window :]

        baseline = {
            metric: self._avg(baseline_samples, metric)
            for metric in self.METRICS
        }
        recent = {
            metric: self._avg(recent_samples, metric)
            for metric in self.METRICS
        }

        reasons: list[str] = []

        for metric in self.METRICS:
            drop = self._relative_drop(baseline[metric], recent[metric])

            if drop >= self.thresholds[metric]:
                reasons.append(
                    f"{metric} degraded {drop:.1%} "
                    f"(baseline={baseline[metric]:.4f}, "
                    f"recent={recent[metric]:.4f})"
                )

        if not reasons:
            severity = "INFO"
        elif len(reasons) == 1:
            severity = "WARNING"
        else:
            severity = "ERROR"

        return DriftAssessment(
            drifting=bool(reasons),
            severity=severity,
            reasons=reasons,
            baseline=baseline,
            recent=recent,
        )
