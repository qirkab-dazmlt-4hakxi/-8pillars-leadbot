from __future__ import annotations

from dataclasses import replace

from .canonical import (
    stable_hash,
)

from .models import (
    EntityEdge,
    EntityNode,
    RelationType,
    clamp01,
    ensure_utc,
)


class RevenueKnowledgeGraph:
    """
    Small deterministic graph kernel.

    Production storage can later move to PostgreSQL/pgvector without
    changing the semantic contract.
    """

    def __init__(
        self,
    ) -> None:
        self._nodes: dict[
            str,
            EntityNode,
        ] = {}

        self._edges: dict[
            str,
            EntityEdge,
        ] = {}

    def upsert_node(
        self,
        *,
        node_id: str,
        entity_type: str,
        canonical_key: str,
        attributes: dict,
        confidence: float,
        now=None,
    ) -> EntityNode:
        timestamp = ensure_utc(
            now
        )

        current = self._nodes.get(
            node_id
        )

        if current is None:
            node = EntityNode(
                node_id=node_id,
                entity_type=(
                    entity_type
                ),
                canonical_key=(
                    canonical_key
                ),
                attributes=dict(
                    attributes
                ),
                confidence=clamp01(
                    confidence
                ),
                updated_at=timestamp,
            )

        else:
            merged = dict(
                current.attributes
            )

            for key, value in (
                attributes.items()
            ):
                if value not in {
                    None,
                    "",
                }:
                    merged[
                        key
                    ] = value

            node = replace(
                current,
                canonical_key=(
                    canonical_key
                    or current.canonical_key
                ),
                attributes=merged,
                confidence=max(
                    current.confidence,
                    clamp01(
                        confidence
                    ),
                ),
                updated_at=timestamp,
            )

        self._nodes[
            node_id
        ] = node

        return node

    def add_edge(
        self,
        *,
        source_id: str,
        target_id: str,
        relation: RelationType,
        confidence: float,
        evidence_ids=(),
        now=None,
    ) -> EntityEdge:
        if source_id not in self._nodes:
            raise KeyError(
                source_id
            )

        if target_id not in self._nodes:
            raise KeyError(
                target_id
            )

        timestamp = ensure_utc(
            now
        )

        edge_id = stable_hash(
            {
                "source":
                    source_id,
                "target":
                    target_id,
                "relation":
                    relation.value,
            }
        )[:32]

        edge = EntityEdge(
            edge_id=edge_id,
            source_id=source_id,
            target_id=target_id,
            relation=relation,
            confidence=clamp01(
                confidence
            ),
            evidence_ids=tuple(
                evidence_ids
            ),
            created_at=timestamp,
        )

        self._edges[
            edge_id
        ] = edge

        return edge

    def node(
        self,
        node_id: str,
    ) -> EntityNode | None:
        return self._nodes.get(
            node_id
        )

    def neighbors(
        self,
        node_id: str,
        *,
        relation: RelationType | None = None,
    ) -> tuple[
        EntityNode,
        ...
    ]:
        result = []

        for edge in self._edges.values():
            if relation is not None and edge.relation is not relation:
                continue

            other_id = None

            if edge.source_id == node_id:
                other_id = (
                    edge.target_id
                )

            elif edge.target_id == node_id:
                other_id = (
                    edge.source_id
                )

            if (
                other_id
                and other_id
                in self._nodes
            ):
                result.append(
                    self._nodes[
                        other_id
                    ]
                )

        result.sort(
            key=lambda node:
                node.node_id
        )

        return tuple(
            result
        )

    def node_count(
        self,
    ) -> int:
        return len(
            self._nodes
        )

    def edge_count(
        self,
    ) -> int:
        return len(
            self._edges
        )
