from __future__ import annotations

import math

from .models import (
    FeatureVector,
    ScoreCard,
    clamp01,
)


def sigmoid(
    value: float,
) -> float:
    value = max(
        -20.0,
        min(
            20.0,
            value,
        ),
    )

    return (
        1.0
        / (
            1.0
            + math.exp(
                -value
            )
        )
    )


class RevenueScoringModel:
    """
    Interpretable probability model.

    AI can later suggest coefficients, but production coefficients remain
    explicit, reviewable and regression-testable.
    """

    def score(
        self,
        features: FeatureVector,
    ) -> ScoreCard:
        fit = sigmoid(
            -2.25
            + 2.75
            * features.concrete_intent
            + 1.20
            * features.geographic_fit
            + 0.90
            * features.homeowner_probability
            + 0.60
            * features.contractor_probability
            + 0.70
            * features.specificity
            + 0.55
            * features.source_reliability
            + 0.45
            * features.contactability
            + 0.35
            * features.recency
            - 1.70
            * features.competitor_probability
            - 2.20
            * features.spam_probability
            - 1.35
            * features.duplicate_probability
        )

        response = sigmoid(
            -2.20
            + 1.40
            * features.concrete_intent
            + 1.30
            * features.contactability
            + 0.95
            * features.urgency
            + 0.70
            * features.source_reliability
            + 0.50
            * features.specificity
            - 1.25
            * features.spam_probability
        )

        appointment = sigmoid(
            -2.60
            + 1.25
            * fit
            + 1.05
            * response
            + 0.85
            * features.urgency
            + 0.70
            * features.geographic_fit
            + 0.45
            * features.specificity
        )

        win = sigmoid(
            -2.80
            + 1.35
            * appointment
            + 0.95
            * fit
            + 0.65
            * features.project_value_signal
            + 0.40
            * features.source_reliability
        )

        project_value = sigmoid(
            -1.35
            + 1.45
            * features.project_value_signal
            + 0.75
            * features.specificity
            + 0.45
            * features.concrete_intent
        )

        expected_value = clamp01(
            fit
            * response
            * appointment
            * win
            * (
                0.55
                + 0.45
                * project_value
            )
        )

        confidence = clamp01(
            (
                features.evidence_quality
                + features.contactability
                + features.specificity
                + features.source_reliability
            )
            / 4.0
        )

        reasons = []

        if features.concrete_intent >= 0.60:
            reasons.append(
                "strong-concrete-intent"
            )

        if features.geographic_fit >= 0.80:
            reasons.append(
                "high-service-area-fit"
            )

        if features.urgency >= 0.50:
            reasons.append(
                "urgent-demand"
            )

        if features.contactability >= 0.70:
            reasons.append(
                "high-contactability"
            )

        if features.competitor_probability >= 0.45:
            reasons.append(
                "competitor-risk"
            )

        if features.spam_probability >= 0.40:
            reasons.append(
                "spam-risk"
            )

        if features.duplicate_probability >= 0.72:
            reasons.append(
                "duplicate-risk"
            )

        return ScoreCard(
            fit_probability=fit,
            response_probability=(
                response
            ),
            appointment_probability=(
                appointment
            ),
            win_probability=win,
            project_value_probability=(
                project_value
            ),
            expected_value_index=(
                expected_value
            ),
            confidence=confidence,
            reasons=tuple(
                reasons
            ),
        )
