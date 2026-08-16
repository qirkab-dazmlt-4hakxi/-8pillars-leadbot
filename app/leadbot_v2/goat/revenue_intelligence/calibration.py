from __future__ import annotations

from dataclasses import dataclass

from .models import (
    clamp01,
)


@dataclass(frozen=True)
class CalibrationSnapshot:
    count: int
    brier_score: float
    mean_prediction: float
    empirical_rate: float
    calibration_gap: float


class ProbabilityCalibrationTracker:
    def __init__(
        self,
    ) -> None:
        self._observations: list[
            tuple[
                float,
                int,
            ]
        ] = []

    def observe(
        self,
        probability: float,
        outcome: bool,
    ) -> None:
        self._observations.append(
            (
                clamp01(
                    probability
                ),
                1
                if outcome
                else 0,
            )
        )

    def snapshot(
        self,
    ) -> CalibrationSnapshot:
        if not self._observations:
            return CalibrationSnapshot(
                count=0,
                brier_score=0.0,
                mean_prediction=0.0,
                empirical_rate=0.0,
                calibration_gap=0.0,
            )

        count = len(
            self._observations
        )

        brier = sum(
            (
                prediction
                - outcome
            ) ** 2
            for prediction, outcome
            in self._observations
        ) / count

        mean_prediction = sum(
            prediction
            for prediction, _
            in self._observations
        ) / count

        empirical = sum(
            outcome
            for _, outcome
            in self._observations
        ) / count

        return CalibrationSnapshot(
            count=count,
            brier_score=brier,
            mean_prediction=(
                mean_prediction
            ),
            empirical_rate=(
                empirical
            ),
            calibration_gap=abs(
                mean_prediction
                - empirical
            ),
        )
