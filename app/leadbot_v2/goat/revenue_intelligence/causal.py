from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ActionObservation:
    action_id: str
    action_kind: str
    occurred_at: datetime


@dataclass(frozen=True)
class AttributionCredit:
    action_id: str
    credit: float


class OutcomeAttributionEngine:
    """
    Deterministic recency-weighted attribution.

    This is intentionally labeled attribution rather than causal proof.
    Future causal models can replace it behind the same contract.
    """

    def attribute(
        self,
        actions: tuple[
            ActionObservation,
            ...
        ],
    ) -> tuple[
        AttributionCredit,
        ...
    ]:
        if not actions:
            return ()

        ordered = sorted(
            actions,
            key=lambda action:
                action.occurred_at
        )

        raw_weights = [
            float(
                index + 1
            )
            for index
            in range(
                len(
                    ordered
                )
            )
        ]

        total = sum(
            raw_weights
        )

        return tuple(
            AttributionCredit(
                action_id=action.action_id,
                credit=weight / total,
            )
            for action, weight
            in zip(
                ordered,
                raw_weights,
            )
        )
