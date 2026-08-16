from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from .models import (
    ActionKind,
    LearningSignal,
    OutcomeEvent,
    OutcomeType,
    SourceType,
)


POSITIVE = frozenset(
    {
        OutcomeType.RESPONDED,
        OutcomeType.APPOINTMENT,
        OutcomeType.ESTIMATE,
        OutcomeType.WON,
    }
)

NEGATIVE = frozenset(
    {
        OutcomeType.LOST,
        OutcomeType.DISQUALIFIED,
        OutcomeType.GHOSTED,
    }
)


@dataclass
class BetaPosterior:
    alpha: float = 2.0
    beta: float = 2.0

    recent_mean: float = 0.50
    recent_alpha: float = 0.12

    observations: int = 0

    def observe(
        self,
        success: bool,
    ) -> None:
        value = (
            1.0
            if success
            else 0.0
        )

        if success:
            self.alpha += 1.0

        else:
            self.beta += 1.0

        if self.observations == 0:
            self.recent_mean = value

        else:
            self.recent_mean = (
                self.recent_alpha
                * value
                + (
                    1.0
                    - self.recent_alpha
                )
                * self.recent_mean
            )

        self.observations += 1

    @property
    def mean(
        self,
    ) -> float:
        return (
            self.alpha
            / (
                self.alpha
                + self.beta
            )
        )

    @property
    def sample_size(
        self,
    ) -> float:
        return max(
            0.0,
            self.alpha
            + self.beta
            - 4.0,
        )

    @property
    def drift_score(
        self,
    ) -> float:
        n = max(
            1.0,
            self.sample_size,
        )

        variance = max(
            1e-9,
            self.mean
            * (
                1.0
                - self.mean
            )
            / n,
        )

        standard_error = sqrt(
            variance
        )

        denominator = max(
            0.05,
            standard_error * 3.0,
        )

        return min(
            1.0,
            abs(
                self.recent_mean
                - self.mean
            )
            / denominator,
        )


class AdaptiveRevenueMemory:
    def __init__(
        self,
    ) -> None:
        self._sources: dict[
            SourceType,
            BetaPosterior,
        ] = {}

        self._actions: dict[
            ActionKind,
            BetaPosterior,
        ] = {}

    def source_model(
        self,
        source: SourceType,
    ) -> BetaPosterior:
        return self._sources.setdefault(
            source,
            BetaPosterior(),
        )

    def action_model(
        self,
        action: ActionKind,
    ) -> BetaPosterior:
        return self._actions.setdefault(
            action,
            BetaPosterior(),
        )

    def source_reliability(
        self,
        source: SourceType,
    ) -> float:
        value = (
            self.source_model(
                source
            ).mean
        )

        return max(
            0.25,
            min(
                0.90,
                value,
            ),
        )

    def action_quality(
        self,
        action: ActionKind,
    ) -> float:
        value = (
            self.action_model(
                action
            ).mean
        )

        return max(
            0.25,
            min(
                0.90,
                value,
            ),
        )

    def observe(
        self,
        event: OutcomeEvent,
    ) -> None:
        if event.outcome in POSITIVE:
            success = True

        elif event.outcome in NEGATIVE:
            success = False

        else:
            return

        self.source_model(
            event.source_type
        ).observe(
            success
        )

        if event.action_kind is not None:
            self.action_model(
                event.action_kind
            ).observe(
                success
            )

    def source_signal(
        self,
        source: SourceType,
    ) -> LearningSignal:
        model = self.source_model(
            source
        )

        return LearningSignal(
            key=(
                f"source:"
                f"{source.value}"
            ),
            posterior_mean=(
                model.mean
            ),
            sample_size=(
                model.sample_size
            ),
            successes=(
                model.alpha - 2.0
            ),
            failures=(
                model.beta - 2.0
            ),
            drift_score=(
                model.drift_score
            ),
        )

    def action_signal(
        self,
        action: ActionKind,
    ) -> LearningSignal:
        model = self.action_model(
            action
        )

        return LearningSignal(
            key=(
                f"action:"
                f"{action.value}"
            ),
            posterior_mean=(
                model.mean
            ),
            sample_size=(
                model.sample_size
            ),
            successes=(
                model.alpha - 2.0
            ),
            failures=(
                model.beta - 2.0
            ),
            drift_score=(
                model.drift_score
            ),
        )
