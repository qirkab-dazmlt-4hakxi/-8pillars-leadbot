from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from .bayesian import (
    AdaptiveRevenueMemory,
)

from .canonical import (
    canonical_key,
    normalize_email,
    normalize_phone,
    normalize_postal,
    normalize_state,
    normalize_text,
    normalize_uri,
    stable_hash,
)

from .entity_resolution import (
    EntityResolver,
)

from .geography import (
    ServiceArea,
)

from .intent import (
    IntentHypothesisEngine,
)

from .knowledge_graph import (
    RevenueKnowledgeGraph,
)

from .models import (
    ActorType,
    CanonicalLead,
    DecisionTier,
    FeatureVector,
    LeadCandidate,
    OutcomeEvent,
    OutcomeType,
    ProjectType,
    RelationType,
    RevenueDecision,
    clamp01,
    ensure_utc,
)

from .planner import (
    NextBestActionPlanner,
)

from .policy import (
    RevenuePolicyEngine,
)

from .provenance import (
    EvidenceLedger,
)

from .scoring import (
    RevenueScoringModel,
)

from .simulation import (
    RevenueValueSimulator,
)


class RevenueIntelligenceEngine:
    def __init__(
        self,
        *,
        service_area: ServiceArea | None = None,
        memory: AdaptiveRevenueMemory | None = None,
        repository=None,
    ) -> None:
        self.service_area = (
            service_area
            or ServiceArea()
        )

        self.memory = (
            memory
            or AdaptiveRevenueMemory()
        )

        self.repository = repository

        self.provenance = (
            EvidenceLedger()
        )

        self.intent = (
            IntentHypothesisEngine()
        )

        self.resolver = (
            EntityResolver()
        )

        self.scoring = (
            RevenueScoringModel()
        )

        self.policy = (
            RevenuePolicyEngine()
        )

        self.planner = (
            NextBestActionPlanner(
                self.memory
            )
        )

        self.graph = (
            RevenueKnowledgeGraph()
        )

        self.simulator = (
            RevenueValueSimulator()
        )

    def evaluate(
        self,
        candidate: LeadCandidate,
        *,
        existing=(),
        now=None,
    ) -> RevenueDecision:
        timestamp = ensure_utc(
            now
            or candidate.observed_at
        )

        normalized = replace(
            candidate,
            raw_text=normalize_text(
                candidate.raw_text
            ),
            observed_at=ensure_utc(
                candidate.observed_at
            ),
            source_uri=normalize_uri(
                candidate.source_uri
            ),
            phone=normalize_phone(
                candidate.phone
            ),
            email=normalize_email(
                candidate.email
            ),
            state=normalize_state(
                candidate.state
            ),
            postal_code=normalize_postal(
                candidate.postal_code
            ),
        )

        evidence = (
            self.provenance.append(
                normalized
            )
        )

        actor_hypotheses = (
            self.intent
            .actor_hypotheses(
                normalized
            )
        )

        project_hypotheses = (
            self.intent
            .project_hypotheses(
                normalized
            )
        )

        actor_type = (
            self.intent.actor_type(
                normalized
            )
        )

        project_type = (
            self.intent.project_type(
                normalized
            )
        )

        duplicate, duplicate_probability = (
            self.resolver.best_match(
                normalized,
                tuple(
                    existing
                ),
            )
        )

        geography = (
            self.service_area.assess(
                normalized
            )
        )

        contactability = (
            self._contactability(
                normalized
            )
        )

        specificity = (
            self._specificity(
                normalized,
                project_type,
            )
        )

        project_value = (
            self._project_value(
                normalized,
                project_type,
            )
        )

        recency = self._recency(
            normalized.observed_at,
            timestamp,
        )

        homeowner_probability = (
            self._hypothesis_probability(
                actor_hypotheses,
                ActorType
                .HOMEOWNER
                .value,
            )
        )

        contractor_probability = (
            self._hypothesis_probability(
                actor_hypotheses,
                ActorType
                .GENERAL_CONTRACTOR
                .value,
            )
        )

        competitor_probability = (
            self._hypothesis_probability(
                actor_hypotheses,
                ActorType
                .COMPETITOR
                .value,
            )
        )

        concrete_intent = (
            self.intent
            .concrete_intent(
                normalized
            )
        )

        urgency = (
            self.intent.urgency(
                normalized
            )
        )

        spam = (
            self.intent
            .spam_probability(
                normalized
            )
        )

        source_reliability = (
            self.memory
            .source_reliability(
                normalized.source_type
            )
        )

        evidence_quality = clamp01(
            (
                evidence.confidence
                + specificity
                + contactability
                + source_reliability
            )
            / 4.0
        )

        features = FeatureVector(
            concrete_intent=(
                concrete_intent
            ),
            urgency=urgency,
            geographic_fit=(
                geography.score
            ),
            homeowner_probability=(
                homeowner_probability
            ),
            contractor_probability=(
                contractor_probability
            ),
            competitor_probability=(
                competitor_probability
            ),
            contactability=(
                contactability
            ),
            source_reliability=(
                source_reliability
            ),
            evidence_quality=(
                evidence_quality
            ),
            specificity=(
                specificity
            ),
            project_value_signal=(
                project_value
            ),
            spam_probability=spam,
            duplicate_probability=(
                duplicate_probability
            ),
            recency=recency,
        )

        score = self.scoring.score(
            features
        )

        lead_id = (
            duplicate.lead_id
            if duplicate
            else stable_hash(
                {
                    "candidate_id":
                        normalized
                        .candidate_id,
                    "source":
                        normalized
                        .source_type
                        .value,
                    "phone":
                        normalized.phone,
                    "email":
                        normalized.email,
                    "uri":
                        normalized
                        .source_uri,
                    "observed_at":
                        normalized
                        .observed_at,
                }
            )[:32]
        )

        evidence_ids = (
            tuple(
                duplicate
                .evidence_ids
            )
            if duplicate
            else ()
        ) + (
            evidence.evidence_id,
        )

        lead = CanonicalLead(
            lead_id=lead_id,
            candidate_id=(
                normalized.candidate_id
            ),
            source_type=(
                normalized.source_type
            ),
            actor_type=actor_type,
            project_type=project_type,
            name=normalized.name,
            company=normalized.company,
            phone=normalized.phone,
            email=normalized.email,
            social_handle=(
                normalized.social_handle
            ),
            street=normalized.street,
            city=normalized.city,
            state=normalized.state,
            postal_code=(
                normalized.postal_code
            ),
            source_uri=(
                normalized.source_uri
            ),
            raw_text=(
                normalized.raw_text
            ),
            created_at=(
                duplicate.created_at
                if duplicate
                else timestamp
            ),
            updated_at=timestamp,
            features=features,
            score=score,
            evidence_ids=(
                evidence_ids
            ),
            duplicate_of=(
                duplicate.lead_id
                if duplicate
                else None
            ),
            metadata={
                **normalized.metadata,
                "geography_reasons":
                    list(
                        geography.reasons
                    ),
            },
        )

        tier, rejection_reasons = (
            self.policy.decide(
                lead
            )
        )

        action = self.planner.plan(
            lead,
            tier,
        )

        self._update_graph(
            lead,
            evidence.evidence_id,
            now=timestamp,
        )

        if self.repository is not None:
            self.repository.save(
                lead
            )

        return RevenueDecision(
            lead=lead,
            tier=tier,
            action=action,
            actor_hypotheses=(
                actor_hypotheses
            ),
            project_hypotheses=(
                project_hypotheses
            ),
            rejection_reasons=(
                rejection_reasons
            ),
        )

    def observe_outcome(
        self,
        event: OutcomeEvent,
    ) -> None:
        self.memory.observe(
            event
        )

    def simulate_value(
        self,
        decision: RevenueDecision,
        *,
        nominal_project_value: float,
        gross_margin_ratio: float = 0.30,
        trials: int = 1000,
        seed: int = 1,
    ):
        return self.simulator.simulate(
            decision.lead.score,
            nominal_project_value=(
                nominal_project_value
            ),
            gross_margin_ratio=(
                gross_margin_ratio
            ),
            trials=trials,
            seed=seed,
        )

    @staticmethod
    def _hypothesis_probability(
        hypotheses,
        label: str,
    ) -> float:
        for hypothesis in hypotheses:
            if hypothesis.label == label:
                return (
                    hypothesis
                    .probability
                )

        return 0.0

    @staticmethod
    def _contactability(
        candidate: LeadCandidate,
    ) -> float:
        score = 0.0

        if candidate.phone:
            score += 0.45

        if candidate.email:
            score += 0.30

        if candidate.social_handle:
            score += 0.15

        if candidate.source_uri:
            score += 0.10

        return clamp01(
            score
        )

    @staticmethod
    def _specificity(
        candidate: LeadCandidate,
        project_type: ProjectType,
    ) -> float:
        score = 0.0

        if (
            project_type
            is not ProjectType.UNKNOWN
        ):
            score += 0.35

        if candidate.street:
            score += 0.15

        if candidate.city:
            score += 0.10

        if candidate.postal_code:
            score += 0.10

        if candidate.budget_hint:
            score += 0.15

        text = (
            candidate.raw_text
            .lower()
        )

        for marker in (
            "square feet",
            "sq ft",
            "yards",
            "yard",
            "feet",
            "inches",
        ):
            if marker in text:
                score += 0.10
                break

        return clamp01(
            score
        )

    @staticmethod
    def _project_value(
        candidate: LeadCandidate,
        project_type: ProjectType,
    ) -> float:
        base = {
            ProjectType.FOUNDATION:
                0.90,
            ProjectType.SLAB:
                0.74,
            ProjectType.DRIVEWAY:
                0.70,
            ProjectType.RETAINING_WALL:
                0.72,
            ProjectType.POOL_DECK:
                0.67,
            ProjectType.PATIO:
                0.55,
            ProjectType.SIDEWALK:
                0.42,
            ProjectType.STEPS:
                0.38,
            ProjectType.FLATWORK:
                0.58,
            ProjectType.REPAIR:
                0.32,
            ProjectType.DEMO_REPLACE:
                0.72,
            ProjectType.SITE_CONCRETE:
                0.82,
            ProjectType.COMMERCIAL_CONCRETE:
                0.88,
            ProjectType.UNKNOWN:
                0.30,
        }[
            project_type
        ]

        if candidate.budget_hint:
            if (
                candidate.budget_hint
                >= 50_000
            ):
                base += 0.16

            elif (
                candidate.budget_hint
                >= 20_000
            ):
                base += 0.10

            elif (
                candidate.budget_hint
                >= 10_000
            ):
                base += 0.05

        return clamp01(
            base
        )

    @staticmethod
    def _recency(
        observed_at: datetime,
        now: datetime,
    ) -> float:
        delta = max(
            0.0,
            (
                now
                - observed_at
            ).total_seconds(),
        )

        hours = (
            delta / 3600.0
        )

        if hours <= 1:
            return 1.0

        if hours <= 6:
            return 0.90

        if hours <= 24:
            return 0.75

        if hours <= 72:
            return 0.55

        if hours <= 168:
            return 0.35

        return 0.15

    def _update_graph(
        self,
        lead: CanonicalLead,
        evidence_id: str,
        *,
        now,
    ) -> None:
        lead_node = self.graph.upsert_node(
            node_id=(
                f"lead:{lead.lead_id}"
            ),
            entity_type="lead",
            canonical_key=lead.lead_id,
            attributes={
                "name":
                    lead.name,
                "company":
                    lead.company,
                "phone":
                    lead.phone,
                "email":
                    lead.email,
                "actor_type":
                    lead.actor_type.value,
                "project_type":
                    lead.project_type.value,
            },
            confidence=(
                lead.score.confidence
            ),
            now=now,
        )

        project_node_id = (
            f"project-type:"
            f"{lead.project_type.value}"
        )

        self.graph.upsert_node(
            node_id=project_node_id,
            entity_type=(
                "project_type"
            ),
            canonical_key=(
                lead.project_type.value
            ),
            attributes={
                "project_type":
                    lead.project_type.value,
            },
            confidence=(
                lead.features
                .concrete_intent
            ),
            now=now,
        )

        self.graph.add_edge(
            source_id=(
                lead_node.node_id
            ),
            target_id=(
                project_node_id
            ),
            relation=(
                RelationType
                .INTERESTED_IN
            ),
            confidence=(
                lead.features
                .concrete_intent
            ),
            evidence_ids=(
                evidence_id,
            ),
            now=now,
        )
