from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any


class GrowthError(RuntimeError):
    pass


class PublicationPolicyError(GrowthError):
    pass


class SearchIntent(str, Enum):
    INFORMATIONAL = "informational"
    COMMERCIAL = "commercial"
    TRANSACTIONAL = "transactional"
    NAVIGATIONAL = "navigational"
    LOCAL = "local"


class GrowthChannel(str, Enum):
    ORGANIC_SEARCH = "organic_search"
    LOCAL_SEARCH = "local_search"
    PAID_SEARCH = "paid_search"
    SOCIAL = "social"
    EMAIL = "email"
    REFERRAL = "referral"
    DIRECT = "direct"
    VIDEO = "video"
    PODCAST = "podcast"
    OUTDOOR = "outdoor"


class BrandRisk(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class PublicationState(str, Enum):
    DRAFT = "draft"
    READY_FOR_REVIEW = "ready_for_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"


class CreativeKind(str, Enum):
    PHOTO = "photo"
    VIDEO = "video"
    DRONE = "drone"
    GRAPHIC = "graphic"
    SLIDE = "slide"
    AUDIO = "audio"


@dataclass(frozen=True)
class PageDocument:
    page_id: str

    url: str

    title: str
    meta_description: str

    canonical_url: str | None

    h1_count: int

    word_count: int

    internal_link_count: int
    external_link_count: int

    image_count: int
    images_without_alt: int

    indexable: bool

    response_status: int

    load_time_ms: float

    structured_data_types: tuple[
        str,
        ...,
    ] = ()

    text: str = ""


@dataclass(frozen=True)
class SEOFinding:
    finding_id: str

    severity: BrandRisk

    page_id: str

    message: str

    score_impact: float


@dataclass(frozen=True)
class SEOAudit:
    page_id: str

    score: float

    findings: tuple[
        SEOFinding,
        ...,
    ]


@dataclass(frozen=True)
class KeywordOpportunity:
    keyword: str

    intent: SearchIntent

    estimated_demand: float
    business_value: float
    competition: float
    current_visibility: float
    local_relevance: float

    score: float


@dataclass(frozen=True)
class LocalMarket:
    market_id: str

    name: str

    demand: float
    competition: float
    serviceability: float
    average_project_value: Decimal
    strategic_value: float

    score: float


@dataclass(frozen=True)
class ContentBrief:
    brief_id: str

    primary_keyword: str

    intent: SearchIntent

    title: str

    target_questions: tuple[
        str,
        ...,
    ]

    required_entities: tuple[
        str,
        ...,
    ]

    recommended_sections: tuple[
        str,
        ...,
    ]

    conversion_goal: str

    minimum_evidence_items: int


@dataclass(frozen=True)
class PublicMention:
    mention_id: str

    subject: str

    source_name: str
    source_url: str

    published_at: datetime

    title: str
    text: str

    is_public: bool = True

    metadata: dict[
        str,
        Any,
    ] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class ReputationFinding:
    mention_id: str

    sentiment_score: float

    risk: BrandRisk

    issue_terms: tuple[
        str,
        ...,
    ]

    response_required: bool

    reason: str


@dataclass(frozen=True)
class CompetitorSignal:
    competitor_id: str

    business_name: str

    signal_type: str

    source_name: str

    observed_at: datetime

    strength: float

    description: str


@dataclass(frozen=True)
class CampaignEconomics:
    campaign_id: str

    spend: Decimal
    revenue: Decimal
    contribution_profit: Decimal

    leads: int
    qualified_leads: int
    customers: int

    cac: Decimal | None
    cpl: Decimal | None
    qualified_cpl: Decimal | None

    roas: float | None
    mer: float | None

    contribution_roas: float | None


@dataclass(frozen=True)
class AttributionTouch:
    customer_id: str

    timestamp: datetime

    channel: GrowthChannel

    campaign_id: str | None

    value: Decimal = Decimal(
        "0.00"
    )


@dataclass(frozen=True)
class AttributionResult:
    model: str

    credits: dict[
        str,
        float,
    ]


@dataclass(frozen=True)
class ExperimentArm:
    arm_id: str
    name: str

    trials: int = 0
    conversions: int = 0


@dataclass(frozen=True)
class ExperimentDecision:
    winner_arm_id: str | None

    posterior_means: dict[
        str,
        float,
    ]

    evidence_strength: float

    ready_to_promote: bool


@dataclass(frozen=True)
class CreativeAsset:
    asset_id: str

    kind: CreativeKind

    filename: str

    width: int | None = None
    height: int | None = None

    duration_seconds: float | None = None

    has_audio: bool = False
    has_captions: bool = False

    rights_confirmed: bool = False

    metadata: dict[
        str,
        Any,
    ] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class ProductionShot:
    shot_id: str

    kind: CreativeKind

    description: str

    duration_seconds: float | None

    required: bool


@dataclass(frozen=True)
class ProductionPlan:
    plan_id: str

    campaign_name: str

    objective: str

    shots: tuple[
        ProductionShot,
        ...,
    ]

    deliverables: tuple[
        str,
        ...,
    ]

    required_claim_evidence: tuple[
        str,
        ...,
    ]


@dataclass(frozen=True)
class PublicationProposal:
    proposal_id: str

    channel: GrowthChannel

    content_hash: str

    state: PublicationState

    brand_risk: BrandRisk

    claims: tuple[
        str,
        ...,
    ]

    evidence_refs: tuple[
        str,
        ...,
    ]

    approved_by: str | None = None


@dataclass(frozen=True)
class GrowthDecision:
    action: str

    confidence: float

    expected_value: float

    risk: BrandRisk

    requires_human_approval: bool

    reason: str


def utcnow(
) -> datetime:
    return datetime.now(
        timezone.utc
    )
