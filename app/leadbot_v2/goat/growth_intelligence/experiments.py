from __future__ import annotations

from dataclasses import replace

from .models import (
    ExperimentArm,
    ExperimentDecision,
)


class BayesianExperiment:
    """
    Beta-Bernoulli adaptive experiment.

    Promotion is evidence-gated rather than triggered by a single lucky
    conversion.
    """

    def __init__(
        self,
        *,
        minimum_trials_per_arm: int = 30,
        minimum_margin: float = 0.02,
    ) -> None:
        self.minimum_trials_per_arm = int(
            minimum_trials_per_arm
        )

        self.minimum_margin = float(
            minimum_margin
        )

        self._arms = {}

    def add_arm(
        self,
        arm: ExperimentArm,
    ) -> None:
        if arm.arm_id in self._arms:
            raise ValueError(
                "duplicate experiment arm"
            )

        self._arms[
            arm.arm_id
        ] = arm

    def update(
        self,
        *,
        arm_id: str,
        trials: int,
        conversions: int,
    ) -> None:
        if trials < 0:
            raise ValueError(
                "trials cannot be negative"
            )

        if conversions < 0:
            raise ValueError(
                "conversions cannot be negative"
            )

        if conversions > trials:
            raise ValueError(
                "conversions cannot exceed trials"
            )

        arm = self._arms[
            arm_id
        ]

        self._arms[
            arm_id
        ] = replace(
            arm,
            trials=(
                arm.trials
                + trials
            ),
            conversions=(
                arm.conversions
                + conversions
            ),
        )

    @staticmethod
    def posterior_mean(
        arm,
    ) -> float:
        alpha = (
            1
            + arm.conversions
        )

        beta = (
            1
            + arm.trials
            - arm.conversions
        )

        return (
            alpha
            / (
                alpha
                + beta
            )
        )

    def decide(
        self,
    ) -> ExperimentDecision:
        if len(
            self._arms
        ) < 2:
            return ExperimentDecision(
                winner_arm_id=None,
                posterior_means={},
                evidence_strength=0.0,
                ready_to_promote=False,
            )

        means = {
            arm_id:
                self.posterior_mean(
                    arm
                )
            for arm_id, arm
            in self._arms.items()
        }

        ranked = sorted(
            means.items(),
            key=lambda row: (
                row[
                    1
                ],
                row[
                    0
                ],
            ),
            reverse=True,
        )

        winner_id = ranked[
            0
        ][
            0
        ]

        margin = (
            ranked[
                0
            ][
                1
            ]
            - ranked[
                1
            ][
                1
            ]
        )

        minimum_trials = min(
            arm.trials
            for arm
            in self._arms.values()
        )

        evidence_strength = min(
            1.0,
            minimum_trials
            / max(
                1,
                self.minimum_trials_per_arm,
            ),
        )

        ready = (
            minimum_trials
            >= self.minimum_trials_per_arm
            and margin
            >= self.minimum_margin
        )

        return ExperimentDecision(
            winner_arm_id=(
                winner_id
                if ready
                else None
            ),
            posterior_means=(
                means
            ),
            evidence_strength=(
                evidence_strength
            ),
            ready_to_promote=(
                ready
            ),
        )
