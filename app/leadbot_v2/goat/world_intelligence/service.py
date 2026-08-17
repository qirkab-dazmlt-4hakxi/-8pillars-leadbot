from __future__ import annotations

from .contradictions import (
    ContradictionDetector,
)

from .freshness import (
    FreshnessEngine,
)

from .ingestion import (
    EvidenceIngestionGate,
)

from .knowledge import (
    WorldKnowledgeGraph,
)

from .policy import (
    default_refresh_policies,
)

from .provenance import (
    EvidenceChain,
)

from .refresh import (
    KnowledgeRefreshPlanner,
)

from .signals import (
    PublicMarketInformationPolicy,
    WorldSignalEngine,
)

from .sources import (
    SourceHealthTracker,
    SourceRegistry,
)


class WorldIntelligenceService:
    def __init__(
        self,
        *,
        repository=None,
        policies=None,
    ) -> None:
        self.repository = repository

        self.policies = (
            policies
            or default_refresh_policies()
        )

        self.sources = (
            SourceRegistry()
        )

        self.source_health = (
            SourceHealthTracker()
        )

        self.evidence_chain = (
            EvidenceChain()
        )

        self.ingestion = (
            EvidenceIngestionGate(
                source_registry=(
                    self.sources
                ),
                source_health=(
                    self.source_health
                ),
                chain=(
                    self.evidence_chain
                ),
            )
        )

        self.freshness = (
            FreshnessEngine()
        )

        self.knowledge = (
            WorldKnowledgeGraph(
                freshness_engine=(
                    self.freshness
                ),
                policies=(
                    self.policies
                ),
            )
        )

        self.contradictions = (
            ContradictionDetector()
        )

        self.signals = (
            WorldSignalEngine()
        )

        self.market_policy = (
            PublicMarketInformationPolicy()
        )

        self.refresh = (
            KnowledgeRefreshPlanner(
                policies=(
                    self.policies
                )
            )
        )

    def register_source(
        self,
        source,
    ):
        self.sources.register(
            source
        )

    def ingest_evidence(
        self,
        evidence,
    ):
        sealed = (
            self.ingestion
            .ingest(
                evidence
            )
        )

        if sealed is None:
            return None

        source = self.sources.get(
            sealed.source_id
        )

        fact = (
            self.knowledge
            .derive_fact(
                evidence=sealed,
                authority=(
                    source.authority
                ),
            )
        )

        if self.repository:
            self.repository.save_evidence(
                sealed
            )

            if fact:
                self.repository.save_fact(
                    fact
                )

        return (
            sealed,
            fact,
        )

    def current_contradictions(
        self,
    ):
        contradictions = (
            self.contradictions
            .detect(
                self.knowledge
                .all_facts()
            )
        )

        if self.repository:
            for item in contradictions:
                self.repository.save_contradiction(
                    item
                )

        return contradictions

    def resolve_fact(
        self,
        *,
        domain,
        subject,
        predicate,
        jurisdiction,
        now,
        high_impact=False,
    ):
        contradictions = (
            self.current_contradictions()
        )

        return (
            self.knowledge
            .resolve(
                domain=domain,
                subject=subject,
                predicate=predicate,
                jurisdiction=jurisdiction,
                now=now,
                contradictions=(
                    contradictions
                ),
                high_impact=(
                    high_impact
                ),
            )
        )

    def ingest_market_signal(
        self,
        *,
        metadata,
        **kwargs,
    ):
        self.market_policy.validate(
            metadata
        )

        signal = (
            self.signals
            .normalize(
                metadata=metadata,
                **kwargs,
            )
        )

        if self.repository:
            self.repository.save_signal(
                signal
            )

        return signal
