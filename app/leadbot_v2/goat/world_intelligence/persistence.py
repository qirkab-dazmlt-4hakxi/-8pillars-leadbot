from __future__ import annotations

from .canonical import (
    stable_hash,
)


EVIDENCE_ENTITY = (
    "goat.world.evidence"
)

FACT_ENTITY = (
    "goat.world.fact"
)

CONTRADICTION_ENTITY = (
    "goat.world.contradiction"
)

SIGNAL_ENTITY = (
    "goat.world.signal"
)

REFRESH_TASK_ENTITY = (
    "goat.world.refresh_task"
)

SOURCE_HEALTH_ENTITY = (
    "goat.world.source_health"
)


class WorldRepository:
    def __init__(
        self,
        store,
        *,
        tenant_id,
        actor_id="goat-world-intelligence",
    ) -> None:
        self.store = store
        self.tenant_id = tenant_id
        self.actor_id = actor_id

    def _upsert(
        self,
        *,
        entity_type,
        entity_id,
        payload,
    ):
        current = self.store.get_entity(
            tenant_id=self.tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )

        expected = (
            None
            if current is None
            else int(
                current.version
            )
        )

        return self.store.put_entity(
            tenant_id=self.tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
            actor_id=self.actor_id,
            expected_version=expected,
        )

    def save_evidence(
        self,
        evidence,
    ):
        return self._upsert(
            entity_type=(
                EVIDENCE_ENTITY
            ),
            entity_id=(
                evidence.evidence_id
            ),
            payload={
                "source_id":
                    evidence.source_id,

                "domain":
                    evidence.domain.value,

                "subject":
                    evidence.subject,

                "predicate":
                    evidence.predicate,

                "value":
                    evidence.value,

                "jurisdiction":
                    evidence.jurisdiction,

                "source_url":
                    evidence.source_url,

                "published_at":
                    (
                        evidence.published_at
                        .isoformat()
                        if evidence.published_at
                        else None
                    ),

                "acquired_at":
                    evidence.acquired_at
                    .isoformat(),

                "confidence":
                    evidence.confidence,

                "status":
                    evidence.status.value,

                "content_hash":
                    evidence.content_hash,

                "previous_hash":
                    evidence.previous_hash,

                "chain_hash":
                    evidence.chain_hash,

                "metadata":
                    evidence.metadata,
            },
        )

    def save_fact(
        self,
        fact,
    ):
        return self._upsert(
            entity_type=(
                FACT_ENTITY
            ),
            entity_id=(
                fact.fact_id
            ),
            payload={
                "domain":
                    fact.domain.value,

                "subject":
                    fact.subject,

                "predicate":
                    fact.predicate,

                "value":
                    fact.value,

                "jurisdiction":
                    fact.jurisdiction,

                "authority":
                    fact.authority.value,

                "confidence":
                    fact.confidence,

                "evidence_ids":
                    list(
                        fact.evidence_ids
                    ),

                "state":
                    fact.state.value,

                "first_seen_at":
                    fact.first_seen_at
                    .isoformat(),

                "last_confirmed_at":
                    fact.last_confirmed_at
                    .isoformat(),
            },
        )

    def save_contradiction(
        self,
        contradiction,
    ):
        return self._upsert(
            entity_type=(
                CONTRADICTION_ENTITY
            ),
            entity_id=(
                contradiction
                .contradiction_id
            ),
            payload={
                "subject":
                    contradiction.subject,

                "predicate":
                    contradiction.predicate,

                "jurisdiction":
                    contradiction.jurisdiction,

                "fact_ids":
                    list(
                        contradiction.fact_ids
                    ),

                "severity":
                    contradiction.severity,

                "reason":
                    contradiction.reason,
            },
        )

    def save_signal(
        self,
        signal,
    ):
        return self._upsert(
            entity_type=(
                SIGNAL_ENTITY
            ),
            entity_id=(
                signal.signal_id
            ),
            payload={
                "domain":
                    signal.domain.value,

                "name":
                    signal.name,

                "timestamp":
                    signal.timestamp.isoformat(),

                "value":
                    signal.value,

                "unit":
                    signal.unit,

                "geography":
                    signal.geography,

                "source_id":
                    signal.source_id,

                "confidence":
                    signal.confidence,

                "metadata":
                    signal.metadata,
            },
        )

    def save_refresh_task(
        self,
        task,
    ):
        return self._upsert(
            entity_type=(
                REFRESH_TASK_ENTITY
            ),
            entity_id=(
                task.task_id
            ),
            payload={
                "domain":
                    task.domain.value,

                "source_id":
                    task.source_id,

                "due_at":
                    task.due_at
                    .isoformat(),

                "full_audit":
                    task.full_audit,

                "priority":
                    task.priority,

                "reason":
                    task.reason,
            },
        )
