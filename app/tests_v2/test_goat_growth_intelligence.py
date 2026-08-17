from __future__ import annotations

import unittest

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from leadbot_v2.goat.growth_intelligence import (
    AttributionEngine,
    AttributionTouch,
    BayesianExperiment,
    BrandRisk,
    CompetitorSignal,
    CompetitorSignalAnalyzer,
    CreativeAsset,
    CreativeAssetValidator,
    CreativeKind,
    ExperimentArm,
    GrowthChannel,
    GrowthIntelligenceSystem,
    GrowthRepository,
    KeywordOpportunityEngine,
    LocalMarketScorer,
    MarketingEconomics,
    PageDocument,
    PublicationPolicy,
    PublicationPolicyError,
    PublicationProposal,
    PublicationState,
    PublicMention,
    SearchIntent,
    install_growth_experts,
    stable_hash,
)

from leadbot_v2.goat.superintelligence import (
    AutonomyLevel,
    CognitiveKernel,
)


NOW = datetime(
    2026,
    8,
    17,
    12,
    0,
    tzinfo=timezone.utc,
)


class FakeStore:
    def __init__(
        self,
    ):
        self.entities = {}

    def get_entity(
        self,
        *,
        tenant_id,
        entity_type,
        entity_id,
        include_deleted=False,
    ):
        return deepcopy(
            self.entities.get(
                (
                    tenant_id,
                    entity_type,
                    entity_id,
                )
            )
        )

    def put_entity(
        self,
        *,
        tenant_id,
        entity_type,
        entity_id,
        payload,
        actor_id,
        expected_version=None,
    ):
        key = (
            tenant_id,
            entity_type,
            entity_id,
        )

        current = (
            self.entities.get(
                key
            )
        )

        if current is None:
            if expected_version is not None:
                raise RuntimeError(
                    "version conflict"
                )

            version = 1

        else:
            if (
                current.version
                != expected_version
            ):
                raise RuntimeError(
                    "version conflict"
                )

            version = (
                current.version
                + 1
            )

        record = SimpleNamespace(
            version=version,
            payload=deepcopy(
                payload
            ),
        )

        self.entities[
            key
        ] = record

        return deepcopy(
            record
        )


class SEOTests(
    unittest.TestCase
):
    def test_good_page_scores_high(
        self,
    ):
        system = (
            GrowthIntelligenceSystem()
        )

        page = PageDocument(
            page_id="home",
            url="https://example.com/",
            title=(
                "Commercial Concrete Contractor "
                "for Complex Texas Projects"
            ),
            meta_description=(
                "Concrete construction, estimating, "
                "site planning and project delivery "
                "for commercial projects across Texas."
            ),
            canonical_url=(
                "https://example.com/"
            ),
            h1_count=1,
            word_count=1200,
            internal_link_count=12,
            external_link_count=3,
            image_count=10,
            images_without_alt=0,
            indexable=True,
            response_status=200,
            load_time_ms=900,
            structured_data_types=(
                "Organization",
                "LocalBusiness",
            ),
        )

        audit = system.audit_page(
            page
        )

        self.assertGreaterEqual(
            audit.score,
            90.0,
        )

    def test_bad_page_surfaces_issues(
        self,
    ):
        system = (
            GrowthIntelligenceSystem()
        )

        page = PageDocument(
            page_id="bad",
            url="http://example.com/",
            title="Bad",
            meta_description="Thin",
            canonical_url=None,
            h1_count=3,
            word_count=50,
            internal_link_count=0,
            external_link_count=0,
            image_count=5,
            images_without_alt=5,
            indexable=False,
            response_status=500,
            load_time_ms=6000,
        )

        audit = system.audit_page(
            page
        )

        self.assertLess(
            audit.score,
            50.0,
        )

        self.assertGreater(
            len(
                audit.findings
            ),
            5,
        )


class KeywordTests(
    unittest.TestCase
):
    def test_high_value_local_keyword_prioritized(
        self,
    ):
        engine = (
            KeywordOpportunityEngine()
        )

        weak = engine.score(
            keyword="concrete history",
            intent=(
                SearchIntent.INFORMATIONAL
            ),
            estimated_demand=0.8,
            business_value=0.2,
            competition=0.8,
            current_visibility=0.1,
            local_relevance=0.1,
        )

        strong = engine.score(
            keyword=(
                "commercial concrete "
                "contractor fort worth"
            ),
            intent=(
                SearchIntent.LOCAL
            ),
            estimated_demand=0.7,
            business_value=1.0,
            competition=0.5,
            current_visibility=0.2,
            local_relevance=1.0,
        )

        ranked = engine.rank(
            (
                weak,
                strong,
            )
        )

        self.assertEqual(
            ranked[
                0
            ].keyword,
            strong.keyword,
        )


class LocalMarketTests(
    unittest.TestCase
):
    def test_serviceable_high_value_market_ranks_higher(
        self,
    ):
        scorer = (
            LocalMarketScorer()
        )

        a = scorer.score(
            market_id="a",
            name="Market A",
            demand=0.8,
            competition=0.4,
            serviceability=0.95,
            average_project_value=(
                Decimal(
                    "200000"
                )
            ),
            strategic_value=0.9,
        )

        b = scorer.score(
            market_id="b",
            name="Market B",
            demand=0.8,
            competition=0.4,
            serviceability=0.3,
            average_project_value=(
                Decimal(
                    "30000"
                )
            ),
            strategic_value=0.3,
        )

        self.assertEqual(
            scorer.rank(
                (
                    a,
                    b,
                )
            )[
                0
            ].market_id,
            "a",
        )


class ContentTests(
    unittest.TestCase
):
    def test_content_brief_is_deterministic(
        self,
    ):
        system = (
            GrowthIntelligenceSystem()
        )

        kwargs = dict(
            primary_keyword=(
                "commercial concrete contractor"
            ),
            intent=(
                SearchIntent.LOCAL
            ),
            market_name="Fort Worth",
            services=(
                "foundations",
                "paving",
            ),
            questions=(
                "How long does a commercial pour take?",
            ),
            entities=(
                "concrete",
                "reinforcement",
            ),
            conversion_goal=(
                "request estimate"
            ),
        )

        first = (
            system.create_content_brief(
                **kwargs
            )
        )

        second = (
            system.create_content_brief(
                **kwargs
            )
        )

        self.assertEqual(
            first.brief_id,
            second.brief_id,
        )


class ReputationTests(
    unittest.TestCase
):
    def test_negative_public_mention_surfaces_risk(
        self,
    ):
        system = (
            GrowthIntelligenceSystem(
                authorized_reputation_subjects=(
                    "Twins Development",
                )
            )
        )

        mention = PublicMention(
            mention_id="mention-1",
            subject="Twins Development",
            source_name="Public Site",
            source_url="https://example.com/a",
            published_at=NOW,
            title="Complaint",
            text=(
                "A complaint alleged unsafe and "
                "unprofessional work and damage."
            ),
            is_public=True,
        )

        finding = (
            system.evaluate_reputation(
                mention
            )
        )

        self.assertIn(
            finding.risk,
            {
                BrandRisk.MODERATE,
                BrandRisk.HIGH,
            },
        )

        self.assertTrue(
            finding.response_required
        )

    def test_unauthorized_subject_rejected(
        self,
    ):
        system = (
            GrowthIntelligenceSystem(
                authorized_reputation_subjects=(
                    "Twins Development",
                )
            )
        )

        mention = PublicMention(
            mention_id="mention-2",
            subject="Random Person",
            source_name="Public Site",
            source_url="https://example.com",
            published_at=NOW,
            title="Text",
            text="Text",
        )

        with self.assertRaises(
            ValueError
        ):
            system.evaluate_reputation(
                mention
            )


class CompetitorTests(
    unittest.TestCase
):
    def test_business_signals_grouped(
        self,
    ):
        analyzer = (
            CompetitorSignalAnalyzer()
        )

        rows = (
            CompetitorSignal(
                competitor_id="c1",
                business_name="Competitor",
                signal_type="search_visibility",
                source_name="public",
                observed_at=NOW,
                strength=0.8,
                description="visibility",
            ),

            CompetitorSignal(
                competitor_id="c1",
                business_name="Competitor",
                signal_type="content",
                source_name="public",
                observed_at=NOW,
                strength=0.6,
                description="content",
            ),
        )

        summary = analyzer.summarize(
            rows
        )

        self.assertEqual(
            summary[
                0
            ][
                "signal_count"
            ],
            2,
        )


class EconomicsTests(
    unittest.TestCase
):
    def test_marketing_economics(
        self,
    ):
        economics = (
            MarketingEconomics()
            .calculate(
                campaign_id="campaign",
                spend=10000,
                revenue=100000,
                contribution_profit=30000,
                leads=100,
                qualified_leads=20,
                customers=5,
            )
        )

        self.assertEqual(
            economics.cac,
            Decimal(
                "2000.00"
            ),
        )

        self.assertEqual(
            economics.cpl,
            Decimal(
                "100.00"
            ),
        )

        self.assertAlmostEqual(
            economics.roas,
            10.0,
        )

        self.assertAlmostEqual(
            economics.contribution_roas,
            3.0,
        )


class AttributionTests(
    unittest.TestCase
):
    def test_linear_attribution_sums_to_one(
        self,
    ):
        touches = (
            AttributionTouch(
                customer_id="customer",
                timestamp=(
                    NOW
                    - timedelta(
                        days=10
                    )
                ),
                channel=(
                    GrowthChannel
                    .ORGANIC_SEARCH
                ),
                campaign_id="seo",
            ),

            AttributionTouch(
                customer_id="customer",
                timestamp=NOW,
                channel=(
                    GrowthChannel.EMAIL
                ),
                campaign_id="email",
            ),
        )

        credits = (
            AttributionEngine()
            .attribute(
                touches,
                model="linear",
            )
        )

        self.assertAlmostEqual(
            sum(
                credits.values()
            ),
            1.0,
        )


class ExperimentTests(
    unittest.TestCase
):
    def test_evidence_gated_promotion(
        self,
    ):
        experiment = (
            BayesianExperiment(
                minimum_trials_per_arm=50,
                minimum_margin=0.02,
            )
        )

        experiment.add_arm(
            ExperimentArm(
                arm_id="a",
                name="A",
            )
        )

        experiment.add_arm(
            ExperimentArm(
                arm_id="b",
                name="B",
            )
        )

        experiment.update(
            arm_id="a",
            trials=100,
            conversions=30,
        )

        experiment.update(
            arm_id="b",
            trials=100,
            conversions=15,
        )

        decision = (
            experiment.decide()
        )

        self.assertTrue(
            decision.ready_to_promote
        )

        self.assertEqual(
            decision.winner_arm_id,
            "a",
        )


class CreativeTests(
    unittest.TestCase
):
    def test_unlicensed_asset_rejected_by_quality_guard(
        self,
    ):
        asset = CreativeAsset(
            asset_id="video",
            kind=(
                CreativeKind.VIDEO
            ),
            filename="video.mp4",
            width=1920,
            height=1080,
            duration_seconds=30,
            has_audio=True,
            has_captions=False,
            rights_confirmed=False,
        )

        findings = (
            CreativeAssetValidator()
            .validate(
                asset
            )
        )

        self.assertIn(
            "usage rights not confirmed",
            findings,
        )

        self.assertIn(
            "spoken video should include captions",
            findings,
        )

    def test_studio_plan_contains_vertical_and_master(
        self,
    ):
        system = (
            GrowthIntelligenceSystem()
        )

        plan = (
            system.creative
            .create_plan(
                campaign_name="Concrete",
                objective="generate leads",
                include_drone=True,
            )
        )

        self.assertIn(
            "16:9 master",
            plan.deliverables,
        )

        self.assertIn(
            "9:16 vertical cut",
            plan.deliverables,
        )


class PublicationPolicyTests(
    unittest.TestCase
):
    def test_publication_requires_approval(
        self,
    ):
        proposal = (
            PublicationProposal(
                proposal_id="p1",
                channel=(
                    GrowthChannel
                    .ORGANIC_SEARCH
                ),
                content_hash=(
                    stable_hash(
                        {
                            "content":
                                "page"
                        }
                    )
                ),
                state=(
                    PublicationState.DRAFT
                ),
                brand_risk=(
                    BrandRisk.LOW
                ),
                claims=(
                    "Completed Project A",
                ),
                evidence_refs=(
                    "project-record-a",
                ),
            )
        )

        policy = (
            PublicationPolicy()
        )

        ready = (
            policy.ready_for_review(
                proposal
            )
        )

        self.assertFalse(
            policy.can_publish(
                ready
            )
        )

        approved = policy.approve(
            ready,
            approver="President",
        )

        self.assertTrue(
            policy.can_publish(
                approved
            )
        )

    def test_claim_without_evidence_fails(
        self,
    ):
        proposal = (
            PublicationProposal(
                proposal_id="p2",
                channel=(
                    GrowthChannel.SOCIAL
                ),
                content_hash="hash",
                state=(
                    PublicationState.DRAFT
                ),
                brand_risk=(
                    BrandRisk.LOW
                ),
                claims=(
                    "Best contractor in Texas",
                ),
                evidence_refs=(),
            )
        )

        with self.assertRaises(
            PublicationPolicyError
        ):
            PublicationPolicy().ready_for_review(
                proposal
            )


class PersistenceTests(
    unittest.TestCase
):
    def test_seo_and_content_persist(
        self,
    ):
        store = FakeStore()

        repository = (
            GrowthRepository(
                store,
                tenant_id="tenant",
            )
        )

        system = (
            GrowthIntelligenceSystem(
                repository=repository
            )
        )

        page = PageDocument(
            page_id="home",
            url="https://example.com",
            title=(
                "Commercial Concrete Contractor "
                "for Texas Construction"
            ),
            meta_description=(
                "Commercial concrete construction and "
                "estimating services for Texas projects."
            ),
            canonical_url=(
                "https://example.com"
            ),
            h1_count=1,
            word_count=500,
            internal_link_count=5,
            external_link_count=1,
            image_count=3,
            images_without_alt=0,
            indexable=True,
            response_status=200,
            load_time_ms=1000,
        )

        system.audit_page(
            page
        )

        system.create_content_brief(
            primary_keyword=(
                "commercial concrete contractor"
            ),
            intent=(
                SearchIntent.LOCAL
            ),
            market_name="Dallas",
            services=(
                "concrete",
            ),
            questions=(),
            entities=(
                "concrete",
            ),
            conversion_goal=(
                "request estimate"
            ),
        )

        entity_types = {
            key[
                1
            ]
            for key
            in store.entities
        }

        self.assertIn(
            "goat.growth.seo_audit",
            entity_types,
        )

        self.assertIn(
            "goat.growth.content_brief",
            entity_types,
        )


class SuperintelligenceIntegrationTests(
    unittest.TestCase
):
    def test_growth_experts_surface_bad_economics(
        self,
    ):
        kernel = (
            CognitiveKernel()
        )

        install_growth_experts(
            kernel
        )

        decision = kernel.reason(
            domain="growth_strategy",
            question=(
                "Should campaign continue?"
            ),
            context={
                "contribution_roas":
                    0.60,

                "seo_score":
                    45,

                "brand_risk":
                    "low",
            },
            evidence=(
                "campaign-economics",
                "seo-audit",
            ),
            requested_autonomy=(
                AutonomyLevel.RECOMMEND
            ),
        )

        self.assertEqual(
            decision.recommendation,
            "corrective_action",
        )


class StressTests(
    unittest.TestCase
):
    def test_10000_keyword_scores(
        self,
    ):
        engine = (
            KeywordOpportunityEngine()
        )

        for index in range(
            10000
        ):
            opportunity = (
                engine.score(
                    keyword=(
                        f"commercial concrete "
                        f"contractor {index}"
                    ),
                    intent=(
                        SearchIntent.LOCAL
                    ),
                    estimated_demand=0.8,
                    business_value=0.9,
                    competition=0.5,
                    current_visibility=0.2,
                    local_relevance=1.0,
                )
            )

            self.assertGreater(
                opportunity.score,
                0.5,
            )


if __name__ == "__main__":
    unittest.main()
