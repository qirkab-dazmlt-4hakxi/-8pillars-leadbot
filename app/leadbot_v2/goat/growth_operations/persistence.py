from __future__ import annotations

from leadbot_v2.goat.growth_intelligence import (
    stable_hash,
)


INGESTION_CURSOR_ENTITY = (
    "goat.growth_ops.ingestion_cursor"
)

PUBLICATION_RECEIPT_ENTITY = (
    "goat.growth_ops.publication_receipt"
)

OPTIMIZATION_PROPOSAL_ENTITY = (
    "goat.growth_ops.optimization_proposal"
)


class GrowthOperationsRepository:
    def __init__(
        self,
        store,
        *,
        tenant_id,
        actor_id="goat-growth-operations",
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
            else int(current.version)
        )

        return self.store.put_entity(
            tenant_id=self.tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
            actor_id=self.actor_id,
            expected_version=expected,
        )

    def save_cursor(
        self,
        cursor,
    ):
        entity_id = stable_hash(
            {
                "adapter_name":
                    cursor.adapter_name,
                "stream_name":
                    cursor.stream_name,
            }
        )[:32]

        return self._upsert(
            entity_type=(
                INGESTION_CURSOR_ENTITY
            ),
            entity_id=entity_id,
            payload={
                "adapter_name":
                    cursor.adapter_name,
                "stream_name":
                    cursor.stream_name,
                "cursor":
                    cursor.cursor,
                "updated_at":
                    cursor.updated_at.isoformat(),
            },
        )

    def save_publication_receipt(
        self,
        receipt,
    ):
        return self._upsert(
            entity_type=(
                PUBLICATION_RECEIPT_ENTITY
            ),
            entity_id=(
                receipt.request_id
            ),
            payload={
                "request_id":
                    receipt.request_id,
                "adapter_name":
                    receipt.adapter_name,
                "external_id":
                    receipt.external_id,
                "state":
                    receipt.state.value,
                "executed_at":
                    (
                        receipt.executed_at
                        .isoformat()
                        if receipt.executed_at
                        else None
                    ),
                "message":
                    receipt.message,
            },
        )

    def save_optimization_proposal(
        self,
        proposal,
    ):
        return self._upsert(
            entity_type=(
                OPTIMIZATION_PROPOSAL_ENTITY
            ),
            entity_id=(
                proposal.proposal_id
            ),
            payload={
                "proposal_id":
                    proposal.proposal_id,
                "kind":
                    proposal.kind.value,
                "title":
                    proposal.title,
                "expected_value":
                    proposal.expected_value,
                "confidence":
                    proposal.confidence,
                "risk":
                    proposal.risk,
                "requires_human_approval":
                    proposal
                    .requires_human_approval,
                "evidence_refs":
                    list(
                        proposal.evidence_refs
                    ),
                "reason":
                    proposal.reason,
            },
        )
