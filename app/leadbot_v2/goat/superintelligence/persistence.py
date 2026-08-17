from __future__ import annotations

from .models import (
    Decision,
    Outcome,
)


DECISION_ENTITY = (
    "goat.superintelligence.decision"
)

OUTCOME_ENTITY = (
    "goat.superintelligence.outcome"
)


class SuperintelligenceRepository:
    def __init__(
        self,
        store,
        *,
        tenant_id: str,
        actor_id: str = (
            "goat-superintelligence"
        ),
    ) -> None:
        self.store = store

        self.tenant_id = (
            tenant_id
        )

        self.actor_id = (
            actor_id
        )

    def _upsert(
        self,
        entity_type: str,
        entity_id: str,
        payload: dict,
    ):
        current = self.store.get_entity(
            tenant_id=(
                self.tenant_id
            ),
            entity_type=(
                entity_type
            ),
            entity_id=(
                entity_id
            ),
        )

        expected = (
            None
            if current is None
            else int(
                current.version
            )
        )

        return self.store.put_entity(
            tenant_id=(
                self.tenant_id
            ),
            entity_type=(
                entity_type
            ),
            entity_id=(
                entity_id
            ),
            payload=payload,
            actor_id=(
                self.actor_id
            ),
            expected_version=(
                expected
            ),
        )

    def save_decision(
        self,
        decision: Decision,
    ) -> None:
        self._upsert(
            DECISION_ENTITY,
            decision.decision_id,
            {
                "decision_id":
                    decision
                    .decision_id,
                "recommendation":
                    decision
                    .recommendation,
                "confidence":
                    decision
                    .confidence,
                "risk":
                    decision
                    .risk.value,
                "autonomy_level":
                    int(
                        decision
                        .autonomy_level
                    ),
                "requires_human_approval":
                    decision
                    .requires_human_approval,
                "alternatives":
                    list(
                        decision
                        .alternatives
                    ),
                "unknowns":
                    list(
                        decision
                        .unknowns
                    ),
                "metadata":
                    dict(
                        decision
                        .metadata
                    ),
            },
        )

    def save_outcome(
        self,
        outcome: Outcome,
    ) -> None:
        self._upsert(
            OUTCOME_ENTITY,
            outcome.decision_id,
            {
                "decision_id":
                    outcome
                    .decision_id,
                "actual_value":
                    outcome
                    .actual_value,
                "success":
                    outcome
                    .success,
                "observed_at":
                    outcome
                    .observed_at
                    .isoformat(),
                "notes":
                    outcome.notes,
            },
        )
