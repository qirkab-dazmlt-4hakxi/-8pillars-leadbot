from __future__ import annotations

from dataclasses import (
    dataclass,
)


@dataclass(frozen=True)
class CalibrationSnapshot:
    samples: int

    brier_score: float

    mean_confidence: float

    empirical_success_rate: float

    calibration_gap: float


class CalibrationMonitor:
    def __init__(
        self,
    ) -> None:
        self._samples: list[
            tuple[
                float,
                bool,
            ]
        ] = []

    def observe(
        self,
        confidence: float,
        success: bool,
    ) -> None:
        confidence = max(
            0.0,
            min(
                1.0,
                float(
                    confidence
                ),
            ),
        )

        self._samples.append(
            (
                confidence,
                bool(
                    success
                ),
            )
        )

    def snapshot(
        self,
    ) -> CalibrationSnapshot:
        if not self._samples:
            return CalibrationSnapshot(
                0,
                0.0,
                0.0,
                0.0,
                0.0,
            )

        count = len(
            self._samples
        )

        mean_confidence = (
            sum(
                confidence
                for confidence, _
                in self._samples
            )
            / count
        )

        success_rate = (
            sum(
                1.0
                if success
                else 0.0
                for _, success
                in self._samples
            )
            / count
        )

        brier = (
            sum(
                (
                    confidence
                    - (
                        1.0
                        if success
                        else 0.0
                    )
                ) ** 2
                for confidence, success
                in self._samples
            )
            / count
        )

        return CalibrationSnapshot(
            samples=count,
            brier_score=(
                brier
            ),
            mean_confidence=(
                mean_confidence
            ),
            empirical_success_rate=(
                success_rate
            ),
            calibration_gap=abs(
                mean_confidence
                - success_rate
            ),
        )
