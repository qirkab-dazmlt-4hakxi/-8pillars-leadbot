from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from .models import (
    ActorType,
    CanonicalLead,
    FeatureVector,
    ProjectType,
    ScoreCard,
    SourceType,
)


LEAD_ENTITY_TYPE = "goat.revenue.lead"


class RevenueRepository:
    """
    Uses only the established enterprise persistence public contract:
      get_entity()
      put_entity()
      list_entities()
    """

    def __init__(
        self,
        store,
        *,
        tenant_id: str,
        actor_id: str = (
            "goat-revenue-intelligence"
        ),
    ) -> None:
        if not tenant_id.strip():
            raise ValueError(
                "tenant_id cannot be blank"
            )

        self.store = store
        self.tenant_id = tenant_id
        self.actor_id = actor_id

    def save(
        self,
        lead: CanonicalLead,
    ) -> CanonicalLead:
        current = self.store.get_entity(
            tenant_id=self.tenant_id,
            entity_type=(
                LEAD_ENTITY_TYPE
            ),
            entity_id=lead.lead_id,
        )

        expected_version = (
            None
            if current is None
            else int(
                current.version
            )
        )

        self.store.put_entity(
            tenant_id=self.tenant_id,
            entity_type=(
                LEAD_ENTITY_TYPE
            ),
            entity_id=lead.lead_id,
            payload=self._encode(
                lead
            ),
            actor_id=self.actor_id,
            expected_version=(
                expected_version
            ),
        )

        return lead

    def list(
        self,
    ) -> tuple[
        CanonicalLead,
        ...
    ]:
        records = self.store.list_entities(
            tenant_id=self.tenant_id,
            entity_type=(
                LEAD_ENTITY_TYPE
            ),
            include_deleted=False,
        )

        return tuple(
            self._decode(
                dict(
                    record.payload
                )
            )
            for record
            in records
        )

    @staticmethod
    def _encode(
        lead: CanonicalLead,
    ) -> dict[str, Any]:
        return {
            "lead_id":
                lead.lead_id,
            "candidate_id":
                lead.candidate_id,
            "source_type":
                lead.source_type.value,
            "actor_type":
                lead.actor_type.value,
            "project_type":
                lead.project_type.value,
            "name":
                lead.name,
            "company":
                lead.company,
            "phone":
                lead.phone,
            "email":
                lead.email,
            "social_handle":
                lead.social_handle,
            "street":
                lead.street,
            "city":
                lead.city,
            "state":
                lead.state,
            "postal_code":
                lead.postal_code,
            "source_uri":
                lead.source_uri,
            "raw_text":
                lead.raw_text,
            "created_at":
                lead.created_at.isoformat(),
            "updated_at":
                lead.updated_at.isoformat(),
            "features":
                asdict(
                    lead.features
                ),
            "score": {
                **asdict(
                    lead.score
                ),
                "reasons":
                    list(
                        lead.score
                        .reasons
                    ),
            },
            "evidence_ids":
                list(
                    lead.evidence_ids
                ),
            "duplicate_of":
                lead.duplicate_of,
            "metadata":
                dict(
                    lead.metadata
                ),
        }

    @staticmethod
    def _decode(
        payload: dict[str, Any],
    ) -> CanonicalLead:
        score_payload = dict(
            payload[
                "score"
            ]
        )

        score_payload[
            "reasons"
        ] = tuple(
            score_payload.get(
                "reasons",
                (),
            )
        )

        return CanonicalLead(
            lead_id=payload[
                "lead_id"
            ],
            candidate_id=payload[
                "candidate_id"
            ],
            source_type=SourceType(
                payload[
                    "source_type"
                ]
            ),
            actor_type=ActorType(
                payload[
                    "actor_type"
                ]
            ),
            project_type=ProjectType(
                payload[
                    "project_type"
                ]
            ),
            name=payload.get(
                "name"
            ),
            company=payload.get(
                "company"
            ),
            phone=payload.get(
                "phone"
            ),
            email=payload.get(
                "email"
            ),
            social_handle=payload.get(
                "social_handle"
            ),
            street=payload.get(
                "street"
            ),
            city=payload.get(
                "city"
            ),
            state=payload.get(
                "state"
            ),
            postal_code=payload.get(
                "postal_code"
            ),
            source_uri=payload.get(
                "source_uri",
                "",
            ),
            raw_text=payload.get(
                "raw_text",
                "",
            ),
            created_at=(
                datetime.fromisoformat(
                    payload[
                        "created_at"
                    ]
                )
            ),
            updated_at=(
                datetime.fromisoformat(
                    payload[
                        "updated_at"
                    ]
                )
            ),
            features=FeatureVector(
                **payload[
                    "features"
                ]
            ),
            score=ScoreCard(
                **score_payload
            ),
            evidence_ids=tuple(
                payload.get(
                    "evidence_ids",
                    (),
                )
            ),
            duplicate_of=(
                payload.get(
                    "duplicate_of"
                )
            ),
            metadata=dict(
                payload.get(
                    "metadata",
                    {},
                )
            ),
        )
