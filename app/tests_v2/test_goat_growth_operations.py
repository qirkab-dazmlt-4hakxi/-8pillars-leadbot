from __future__ import annotations

import unittest

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

from leadbot_v2.goat.growth_intelligence import (
    BrandRisk,
    GrowthChannel,
    GrowthIntelligenceSystem,
    PublicationProposal,
    PublicationState,
    stable_hash,
)

from leadbot_v2.goat.growth_operations import (
    AdapterCapability,
    AdapterPage,
    AdapterRegistration,
    EnvironmentSecretResolver,
    ExternalPublicationState,
    GrowthOperationsRepository,
    GrowthOperationsService,
    MetricPoint,
    PublicationExecutionRequest,
    ReviewEvent,
    SimulatedGrowthAdapter,
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
    def __init__(self):
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

        current = self.entities.get(
            key
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
                current.version + 1
            )

        record = SimpleNamespace(
            version=version,
            payload=deepcopy(payload),
        )

        self.entities[key] = record

        return deepcopy(record)


def make_service(
    *,
    repository=None,
):
    growth = GrowthIntelligenceSystem(
        authorized_reputation_subjects=(
            "Twins Development",
        )
    )

    service = GrowthOperationsService(
        growth_system=growth,
        secret_resolver=(
            EnvironmentSecretResolver()
        ),
        reputation_subject=(
            "Twins Development"
        ),
        repository=repository,
    )

    adapter = SimulatedGrowthAdapter()

    service.registry.register(
        registration=(
            AdapterRegistration(
                adapter_name=(
                    adapter.adapter_name
                ),
                capabilities=frozenset(
                    {
                        AdapterCapability.SEARCH_READ,
                        AdapterCapability.ANALYTICS_READ,
                        AdapterCapability.REVIEWS_READ,
                        AdapterCapability.CONTENT_PUBLISH,
                        AdapterCapability.SOCIAL_PUBLISH,
                    }
                ),
            )
        ),
        adapter=adapter,
    )

    service.configure_adapter_rate_limit(
        adapter_name=(
            adapter.adapter_name
        ),
        capacity=10000,
        refill_per_second=10000,
    )

    return growth, service, adapter


class AdapterTests(unittest.TestCase):
    def test_adapter_health(self):
        _, service, adapter = (
            make_service()
        )

        health = service.registry.health(
            adapter.adapter_name
        )

        self.assertEqual(
            health.state.value,
            "healthy",
        )


class IngestionTests(unittest.TestCase):
    def test_cursor_and_duplicate_suppression(
        self,
    ):
        _, service, adapter = (
            make_service()
        )

        metric = MetricPoint(
            source="sim",
            metric_name="sessions",
            timestamp=NOW,
            value=100.0,
            dimensions={
                "channel": "organic"
            },
        )

        adapter.pages[
            (
                "analytics",
                None,
            )
        ] = AdapterPage(
            items=(
                metric,
                metric,
            ),
            next_cursor="done",
            has_more=False,
        )

        accepted = []

        result = service.ingest_stream(
            adapter_name=(
                adapter.adapter_name
            ),
            stream_name="analytics",
            capability=(
                AdapterCapability.ANALYTICS_READ
            ),
            handler=accepted.append,
        )

        self.assertEqual(
            result.accepted,
            1,
        )

        self.assertEqual(
            result.duplicates,
            1,
        )


class ReviewTests(unittest.TestCase):
    def test_review_enters_reputation_engine(
        self,
    ):
        _, service, _ = (
            make_service()
        )

        review = ReviewEvent(
            source="public-reviews",
            review_id="r1",
            location_id="location",
            author_display_name="Customer",
            rating=1.0,
            text=(
                "Poor unsafe unprofessional "
                "work and damage"
            ),
            published_at=NOW,
            public_url=(
                "https://example.com/review"
            ),
        )

        finding = service.reviews.handle(
            review
        )

        self.assertTrue(
            finding.response_required
        )


class PublishingTests(unittest.TestCase):
    def proposal(
        self,
        *,
        state,
    ):
        return PublicationProposal(
            proposal_id="proposal",
            channel=(
                GrowthChannel.ORGANIC_SEARCH
            ),
            content_hash=stable_hash(
                {
                    "text":
                        "approved content"
                }
            ),
            state=state,
            brand_risk=BrandRisk.LOW,
            claims=(),
            evidence_refs=(),
            approved_by=(
                "President"
                if state
                is PublicationState.APPROVED
                else None
            ),
        )

    def request(
        self,
        proposal,
        adapter_name,
    ):
        return PublicationExecutionRequest(
            request_id="request",
            adapter_name=adapter_name,
            external_channel="cms",
            proposal_id=(
                proposal.proposal_id
            ),
            content_hash=(
                proposal.content_hash
            ),
            payload={
                "title": "Page",
                "body":
                    "approved content",
            },
            created_at=NOW,
        )

    def test_unapproved_publication_blocked(
        self,
    ):
        _, service, adapter = (
            make_service()
        )

        proposal = self.proposal(
            state=(
                PublicationState
                .READY_FOR_REVIEW
            )
        )

        receipt = service.execute_publication(
            proposal=proposal,
            request=self.request(
                proposal,
                adapter.adapter_name,
            ),
            capability=(
                AdapterCapability.CONTENT_PUBLISH
            ),
        )

        self.assertEqual(
            receipt.state,
            ExternalPublicationState.BLOCKED,
        )

        self.assertEqual(
            len(adapter.publications),
            0,
        )

    def test_approved_publication_executes(
        self,
    ):
        _, service, adapter = (
            make_service()
        )

        proposal = self.proposal(
            state=(
                PublicationState.APPROVED
            )
        )

        receipt = service.execute_publication(
            proposal=proposal,
            request=self.request(
                proposal,
                adapter.adapter_name,
            ),
            capability=(
                AdapterCapability.CONTENT_PUBLISH
            ),
        )

        self.assertEqual(
            receipt.state,
            ExternalPublicationState.EXECUTED,
        )

        self.assertEqual(
            len(adapter.publications),
            1,
        )


class CrawlTests(unittest.TestCase):
    def test_bad_seo_schedules_fast_recheck(
        self,
    ):
        _, service, _ = make_service()

        low = service.crawls.schedule(
            url="https://example.com/bad",
            seo_score=40,
            now=NOW,
        )

        high = service.crawls.schedule(
            url="https://example.com/good",
            seo_score=95,
            now=NOW,
        )

        self.assertLess(
            low.due_at,
            high.due_at,
        )

        self.assertGreater(
            low.priority,
            high.priority,
        )


class CalendarTests(unittest.TestCase):
    def test_calendar_due_items(self):
        _, service, _ = make_service()

        service.calendar.schedule(
            title="Article",
            channel="website",
            scheduled_for=NOW,
            brief_id="brief",
        )

        due = service.calendar.due(
            now=NOW,
            horizon_hours=1,
        )

        self.assertEqual(
            len(due),
            1,
        )


class OptimizationTests(unittest.TestCase):
    def test_bad_seo_generates_proposal(
        self,
    ):
        growth, service, _ = (
            make_service()
        )

        from leadbot_v2.goat.growth_intelligence import (
            PageDocument,
        )

        page = PageDocument(
            page_id="bad",
            url="http://example.com",
            title="Bad",
            meta_description="Bad",
            canonical_url=None,
            h1_count=0,
            word_count=10,
            internal_link_count=0,
            external_link_count=0,
            image_count=3,
            images_without_alt=3,
            indexable=False,
            response_status=500,
            load_time_ms=6000,
        )

        audit = growth.audit_page(page)

        proposal = (
            service.optimization
            .propose_from_seo(audit)
        )

        self.assertIsNotNone(
            proposal
        )

        self.assertTrue(
            proposal
            .requires_human_approval
        )


class PersistenceTests(unittest.TestCase):
    def test_cursor_and_publication_receipt_persist(
        self,
    ):
        store = FakeStore()

        repository = (
            GrowthOperationsRepository(
                store,
                tenant_id="tenant",
            )
        )

        _, service, adapter = make_service(
            repository=repository
        )

        metric = MetricPoint(
            source="sim",
            metric_name="sessions",
            timestamp=NOW,
            value=10.0,
        )

        adapter.pages[
            (
                "analytics",
                None,
            )
        ] = AdapterPage(
            items=(metric,),
            next_cursor="cursor-1",
            has_more=False,
        )

        service.ingest_stream(
            adapter_name=(
                adapter.adapter_name
            ),
            stream_name="analytics",
            capability=(
                AdapterCapability.ANALYTICS_READ
            ),
            handler=lambda item: None,
        )

        proposal = PublicationProposal(
            proposal_id="approved",
            channel=(
                GrowthChannel.ORGANIC_SEARCH
            ),
            content_hash="hash",
            state=(
                PublicationState.APPROVED
            ),
            brand_risk=BrandRisk.LOW,
            claims=(),
            evidence_refs=(),
            approved_by="President",
        )

        request = PublicationExecutionRequest(
            request_id="persist-pub",
            adapter_name=(
                adapter.adapter_name
            ),
            external_channel="cms",
            proposal_id=(
                proposal.proposal_id
            ),
            content_hash="hash",
            payload={
                "body": "content"
            },
            created_at=NOW,
        )

        service.execute_publication(
            proposal=proposal,
            request=request,
            capability=(
                AdapterCapability.CONTENT_PUBLISH
            ),
        )

        entity_types = {
            key[1]
            for key
            in store.entities
        }

        self.assertIn(
            "goat.growth_ops.ingestion_cursor",
            entity_types,
        )

        self.assertIn(
            "goat.growth_ops.publication_receipt",
            entity_types,
        )


class StressTests(unittest.TestCase):
    def test_10000_crawl_plans(self):
        _, service, _ = make_service()

        for index in range(10000):
            task = service.crawls.schedule(
                url=(
                    f"https://example.com/"
                    f"page-{index}"
                ),
                seo_score=75,
                now=NOW,
            )

            self.assertGreater(
                task.priority,
                0,
            )


if __name__ == "__main__":
    unittest.main()
