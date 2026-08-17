from __future__ import annotations

from .attribution import (
    AttributionEngine,
)

from .competitor import (
    CompetitorSignalAnalyzer,
)

from .content import (
    ContentPlanner,
    ContentQualityGuard,
)

from .creative import (
    CreativeAssetValidator,
    CreativeStudioPlanner,
)

from .economics import (
    MarketingEconomics,
)

from .local_market import (
    LocalMarketScorer,
)

from .policy import (
    PublicationPolicy,
)

from .reputation import (
    ReputationMonitor,
)

from .seo import (
    KeywordOpportunityEngine,
    TechnicalSEOAuditor,
)


class GrowthIntelligenceSystem:
    def __init__(
        self,
        *,
        authorized_reputation_subjects=(),
        repository=None,
    ) -> None:
        self.repository = (
            repository
        )

        self.seo = (
            TechnicalSEOAuditor()
        )

        self.keywords = (
            KeywordOpportunityEngine()
        )

        self.local_markets = (
            LocalMarketScorer()
        )

        self.content = (
            ContentPlanner()
        )

        self.content_quality = (
            ContentQualityGuard()
        )

        self.reputation = (
            ReputationMonitor(
                authorized_subjects=(
                    authorized_reputation_subjects
                )
            )
        )

        self.competitors = (
            CompetitorSignalAnalyzer()
        )

        self.economics = (
            MarketingEconomics()
        )

        self.attribution = (
            AttributionEngine()
        )

        self.creative = (
            CreativeStudioPlanner()
        )

        self.creative_validator = (
            CreativeAssetValidator()
        )

        self.publication = (
            PublicationPolicy(
                require_human_approval=True
            )
        )

    def audit_page(
        self,
        page,
    ):
        audit = self.seo.audit(
            page
        )

        if self.repository:
            self.repository.save_seo_audit(
                audit
            )

        return audit

    def create_content_brief(
        self,
        **kwargs,
    ):
        brief = (
            self.content
            .create_brief(
                **kwargs
            )
        )

        if self.repository:
            self.repository.save_content_brief(
                brief
            )

        return brief

    def evaluate_reputation(
        self,
        mention,
    ):
        finding = (
            self.reputation
            .evaluate(
                mention
            )
        )

        if self.repository:
            self.repository.save_reputation_finding(
                finding
            )

        return finding
