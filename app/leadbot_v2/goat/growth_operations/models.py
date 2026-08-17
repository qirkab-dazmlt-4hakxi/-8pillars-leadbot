from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any


class GrowthOperationsError(RuntimeError):
    pass


class AdapterPolicyError(GrowthOperationsError):
    pass


class PublicationExecutionError(GrowthOperationsError):
    pass


class AdapterCapability(str, Enum):
    SEARCH_READ = "search.read"
    ANALYTICS_READ = "analytics.read"
    LOCAL_LISTINGS_READ = "local_listings.read"
    REVIEWS_READ = "reviews.read"
    CONTENT_PUBLISH = "content.publish"
    SOCIAL_PUBLISH = "social.publish"


class AdapterHealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class ExternalPublicationState(str, Enum):
    QUEUED = "queued"
    BLOCKED = "blocked"
    EXECUTED = "executed"
    FAILED = "failed"


class OptimizationKind(str, Enum):
    SEO_FIX = "seo_fix"
    CONTENT = "content"
    LOCAL_LISTING = "local_listing"
    REPUTATION = "reputation"
    CAMPAIGN = "campaign"
    CREATIVE = "creative"


@dataclass(frozen=True)
class SecretRef:
    name: str


@dataclass(frozen=True)
class AdapterRegistration:
    adapter_name: str
    capabilities: frozenset[AdapterCapability]
    secret_refs: tuple[SecretRef, ...] = ()
    enabled: bool = True


@dataclass(frozen=True)
class AdapterHealth:
    adapter_name: str
    state: AdapterHealthState
    message: str = ""


@dataclass(frozen=True)
class MetricPoint:
    source: str
    metric_name: str
    timestamp: datetime
    value: float
    dimensions: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchQueryMetric:
    source: str
    query: str
    page_url: str
    impressions: int
    clicks: int
    average_position: float
    observed_on: date


@dataclass(frozen=True)
class LocalListingSnapshot:
    source: str
    location_id: str
    business_name: str
    address: str
    phone: str | None
    website: str | None
    primary_category: str | None
    updated_at: datetime


@dataclass(frozen=True)
class ReviewEvent:
    source: str
    review_id: str
    location_id: str | None
    author_display_name: str | None
    rating: float | None
    text: str
    published_at: datetime
    public_url: str | None


@dataclass(frozen=True)
class AdapterPage:
    items: tuple[Any, ...]
    next_cursor: str | None
    has_more: bool


@dataclass(frozen=True)
class IngestionCursor:
    adapter_name: str
    stream_name: str
    cursor: str | None
    updated_at: datetime


@dataclass(frozen=True)
class IngestionResult:
    adapter_name: str
    stream_name: str
    items_seen: int
    accepted: int
    duplicates: int
    next_cursor: str | None


@dataclass(frozen=True)
class CrawlTask:
    task_id: str
    url: str
    due_at: datetime
    priority: int
    reason: str


@dataclass(frozen=True)
class ContentCalendarItem:
    item_id: str
    title: str
    channel: str
    scheduled_for: datetime
    brief_id: str | None
    campaign_id: str | None
    status: str = "planned"


@dataclass(frozen=True)
class PublicationExecutionRequest:
    request_id: str
    adapter_name: str
    external_channel: str
    proposal_id: str
    content_hash: str
    payload: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class PublicationReceipt:
    request_id: str
    adapter_name: str
    external_id: str | None
    state: ExternalPublicationState
    executed_at: datetime | None
    message: str


@dataclass(frozen=True)
class GrowthTouch:
    customer_id: str
    timestamp: datetime
    channel: str
    campaign_id: str | None
    source: str
    external_reference: str | None = None


@dataclass(frozen=True)
class OptimizationProposal:
    proposal_id: str
    kind: OptimizationKind
    title: str
    expected_value: float
    confidence: float
    risk: float
    requires_human_approval: bool
    evidence_refs: tuple[str, ...]
    reason: str


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
