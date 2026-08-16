from __future__ import annotations

from dataclasses import dataclass

from .models import (
    ActorType,
    CanonicalLead,
    DecisionTier,
)


@dataclass(frozen=True)
class RevenuePolicy:
    minimum_intent: float = 0.30

    qualify_fit: float = 0.48
    priority_fit: float = 0.70
    executive_expected_value: float = 0.20

    maximum_spam: float = 0.55
    duplicate_threshold: float = 0.72


class RevenuePolicyEngine:
    def __init__(
        self,
        policy: RevenuePolicy | None = None,
    ) -> None:
        self.policy = (
            policy
            or RevenuePolicy()
        )

    def decide(
        self,
        lead: CanonicalLead,
    ) -> tuple[
        DecisionTier,
        tuple[str, ...],
    ]:
        features = lead.features
        score = lead.score

        reject = []

        if (
            features.spam_probability
            >= self.policy.maximum_spam
        ):
            reject.append(
                "spam-probability"
            )

        if (
            lead.actor_type
            in {
                ActorType.COMPETITOR,
                ActorType.VENDOR,
                ActorType.SPAM,
            }
        ):
            reject.append(
                "non-buyer-actor"
            )

        if (
            features.concrete_intent
            < self.policy.minimum_intent
        ):
            reject.append(
                "insufficient-concrete-intent"
            )

        if (
            features.geographic_fit
            <= 0.0
        ):
            reject.append(
                "outside-service-area"
            )

        if (
            lead.duplicate_of
            and features
            .duplicate_probability
            >= self.policy
            .duplicate_threshold
        ):
            reject.append(
                "canonical-duplicate"
            )

        if reject:
            return (
                DecisionTier.REJECT,
                tuple(
                    reject
                ),
            )

        if (
            score.expected_value_index
            >= self.policy
            .executive_expected_value
            and score
            .project_value_probability
            >= 0.75
        ):
            return (
                DecisionTier.EXECUTIVE,
                (),
            )

        if (
            score.fit_probability
            >= self.policy.priority_fit
            and score
            .response_probability
            >= 0.55
        ):
            return (
                DecisionTier.PRIORITY,
                (),
            )

        if (
            score.fit_probability
            >= self.policy.qualify_fit
        ):
            return (
                DecisionTier.QUALIFY,
                (),
            )

        return (
            DecisionTier.WATCH,
            (),
        )
