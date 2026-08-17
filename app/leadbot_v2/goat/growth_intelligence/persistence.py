from __future__ import annotations

from .canonical import (
    stable_hash,
)


SEO_AUDIT_ENTITY = (
    "goat.growth.seo_audit"
)

CONTENT_BRIEF_ENTITY = (
    "goat.growth.content_brief"
)

REPUTATION_FINDING_ENTITY = (
    "goat.growth.reputation_finding"
)

EXPERIMENT_DECISION_ENTITY = (
    "goat.growth.experiment_decision"
)


class GrowthRepository:
    def __init__(
        self,
        store,
        *,
        tenant_id: str,
        actor_id: str = (
            "goat-growth-intelligence"
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
        *,
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

    def save_seo_audit(
        self,
        audit,
    ) -> None:
        self._upsert(
            entity_type=(
                SEO_AUDIT_ENTITY
            ),
            entity_id=(
                audit.page_id
            ),
            payload={
                "page_id":
                    audit.page_id,

                "score":
                    audit.score,

                "findings": [
                    {
                        "finding_id":
                            finding.finding_id,

                        "severity":
                            finding.severity.value,

                        "message":
                            finding.message,

                        "score_impact":
                            finding.score_impact,
                    }
                    for finding
                    in audit.findings
                ],
            },
        )

    def save_content_brief(
        self,
        brief,
    ) -> None:
        self._upsert(
            entity_type=(
                CONTENT_BRIEF_ENTITY
            ),
            entity_id=(
                brief.brief_id
            ),
            payload={
                "brief_id":
                    brief.brief_id,

                "primary_keyword":
                    brief.primary_keyword,

                "intent":
                    brief.intent.value,

                "title":
                    brief.title,

                "target_questions":
                    list(
                        brief.target_questions
                    ),

                "required_entities":
                    list(
                        brief.required_entities
                    ),

                "recommended_sections":
                    list(
                        brief.recommended_sections
                    ),

                "conversion_goal":
                    brief.conversion_goal,

                "minimum_evidence_items":
                    brief.minimum_evidence_items,
            },
        )

    def save_reputation_finding(
        self,
        finding,
    ) -> None:
        self._upsert(
            entity_type=(
                REPUTATION_FINDING_ENTITY
            ),
            entity_id=(
                finding.mention_id
            ),
            payload={
                "mention_id":
                    finding.mention_id,

                "sentiment_score":
                    finding.sentiment_score,

                "risk":
                    finding.risk.value,

                "issue_terms":
                    list(
                        finding.issue_terms
                    ),

                "response_required":
                    finding.response_required,

                "reason":
                    finding.reason,
            },
        )

    def save_experiment_decision(
        self,
        *,
        experiment_id: str,
        decision,
    ) -> None:
        entity_id = stable_hash(
            {
                "experiment_id":
                    experiment_id,

                "winner":
                    decision.winner_arm_id,

                "means":
                    decision.posterior_means,
            }
        )[:32]

        self._upsert(
            entity_type=(
                EXPERIMENT_DECISION_ENTITY
            ),
            entity_id=(
                entity_id
            ),
            payload={
                "experiment_id":
                    experiment_id,

                "winner_arm_id":
                    decision.winner_arm_id,

                "posterior_means":
                    decision.posterior_means,

                "evidence_strength":
                    decision.evidence_strength,

                "ready_to_promote":
                    decision.ready_to_promote,
            },
        )
