from __future__ import annotations

from .adapters import GrowthAdapterRegistry
from .attribution import AttributionBridge
from .calendar import ContentCalendar
from .crawl import CrawlPlanner
from .ingestion import (
    GrowthIngestionState,
    GrowthStreamIngestor,
)
from .optimization import (
    GrowthOptimizationEngine,
)
from .publishing import PublicationExecutor
from .rate_limit import TokenBucketLimiter
from .reviews import ReviewReputationBridge


class GrowthOperationsService:
    def __init__(
        self,
        *,
        growth_system,
        secret_resolver,
        reputation_subject,
        repository=None,
    ) -> None:
        self.growth_system = growth_system
        self.repository = repository

        self.registry = GrowthAdapterRegistry(
            secret_resolver=secret_resolver
        )

        self.rate_limiter = (
            TokenBucketLimiter()
        )

        self.ingestion_state = (
            GrowthIngestionState()
        )

        self.ingestor = GrowthStreamIngestor(
            registry=self.registry,
            state=self.ingestion_state,
            rate_limiter=self.rate_limiter,
        )

        self.crawls = CrawlPlanner()
        self.calendar = ContentCalendar()

        self.reviews = ReviewReputationBridge(
            subject=reputation_subject,
            growth_system=growth_system,
        )

        self.publisher = PublicationExecutor(
            registry=self.registry,
            growth_system=growth_system,
        )

        self.attribution = AttributionBridge()

        self.optimization = (
            GrowthOptimizationEngine()
        )

    def configure_adapter_rate_limit(
        self,
        *,
        adapter_name,
        capacity,
        refill_per_second,
    ):
        self.rate_limiter.configure(
            key=adapter_name,
            capacity=capacity,
            refill_per_second=(
                refill_per_second
            ),
        )

    def ingest_stream(
        self,
        *,
        adapter_name,
        stream_name,
        capability,
        handler,
    ):
        result = self.ingestor.ingest(
            adapter_name=adapter_name,
            stream_name=stream_name,
            capability=capability,
            item_handler=handler,
        )

        if self.repository:
            cursor = (
                self.ingestion_state.cursor(
                    adapter_name=adapter_name,
                    stream_name=stream_name,
                )
            )

            if cursor:
                self.repository.save_cursor(
                    cursor
                )

        return result

    def execute_publication(
        self,
        *,
        proposal,
        request,
        capability,
    ):
        receipt = self.publisher.execute(
            proposal=proposal,
            request=request,
            capability=capability,
        )

        if self.repository:
            self.repository.save_publication_receipt(
                receipt
            )

        return receipt
