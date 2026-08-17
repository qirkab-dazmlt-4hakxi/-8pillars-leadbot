from __future__ import annotations

from collections import (
    defaultdict,
)

from .models import (
    ExpertOpinion,
    Outcome,
)


class ExpertWeightLearner:
    def __init__(
        self,
        *,
        learning_rate: float = 0.05,
        minimum_weight: float = 0.20,
        maximum_weight: float = 3.0,
    ) -> None:
        if not (
            0
            < learning_rate
            <= 1
        ):
            raise ValueError(
                "learning_rate must be in (0, 1]"
            )

        self.learning_rate = float(
            learning_rate
        )

        self.minimum_weight = float(
            minimum_weight
        )

        self.maximum_weight = float(
            maximum_weight
        )

        self._weights = defaultdict(
            lambda: 1.0
        )

    def weight(
        self,
        expert_id: str,
    ) -> float:
        return float(
            self._weights[
                expert_id
            ]
        )

    def weights(
        self,
    ) -> dict[
        str,
        float,
    ]:
        return dict(
            self._weights
        )

    def update(
        self,
        opinions: tuple[
            ExpertOpinion,
            ...,
        ],
        outcome: Outcome,
        *,
        expected_answer=None,
    ) -> dict[
        str,
        float,
    ]:
        for opinion in opinions:
            if expected_answer is None:
                agreement = (
                    1.0
                    if outcome.success
                    else 0.0
                )

            else:
                agreement = (
                    1.0
                    if opinion.answer
                    == expected_answer
                    else 0.0
                )

            confidence = max(
                0.0,
                min(
                    1.0,
                    opinion.confidence,
                ),
            )

            signed = (
                (
                    2.0
                    * agreement
                )
                - 1.0
            ) * confidence

            current = (
                self._weights[
                    opinion.expert_id
                ]
            )

            updated = (
                current
                * (
                    1.0
                    + self.learning_rate
                    * signed
                )
            )

            self._weights[
                opinion.expert_id
            ] = min(
                self.maximum_weight,
                max(
                    self.minimum_weight,
                    updated,
                ),
            )

        return self.weights()
