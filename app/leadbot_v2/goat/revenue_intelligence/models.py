from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class RevenueIntelligenceError(RuntimeError):
    pass


class RevenueInvariantError(RevenueIntelligenceError):
    pass


class SourceType(str, Enum):
    BRAVE = "brave"
    GOOGLE = "google"
    NEXTDOOR = "nextdoor"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    WEBSITE = "website"
    MAP = "map"
    REFERRAL = "referral"
    MANUAL = "manual"
    PUBLIC_RECORD = "public_record"
    EMAIL = "email"
    PHONE = "phone"
    OTHER = "other"


class ActorType(str, Enum):
    HOMEOWNER = "homeowner"
    GENERAL_CONTRACTOR = "general_contractor"
    BUILDER = "builder"
    DEVELOPER = "developer"
    PROPERTY_MANAGER = "property_manager"
    MUNICIPALITY = "municipality"
    VENDOR = "vendor"
    COMPETITOR = "competitor"
    SPAM = "spam"
    UNKNOWN = "unknown"


class ProjectType(str, Enum):
    DRIVEWAY = "driveway"
    PATIO = "patio"
    FOUNDATION = "foundation"
    SLAB = "slab"
    SIDEWALK = "sidewalk"
    POOL_DECK = "pool_deck"
    RETAINING_WALL = "retaining_wall"
    STEPS = "steps"
    FLATWORK = "flatwork"
    REPAIR = "repair"
    DEMO_REPLACE = "demo_replace"
    COMMERCIAL_CONCRETE = "commercial_concrete"
    SITE_CONCRETE = "site_concrete"
    UNKNOWN = "unknown"


class DecisionTier(str, Enum):
    REJECT = "reject"
    WATCH = "watch"
    QUALIFY = "qualify"
    PRIORITY = "priority"
    EXECUTIVE = "executive"


class ActionKind(str, Enum):
    NO_ACTION = "no_action"
    RESEARCH = "research"
    HUMAN_REVIEW = "human_review"
    REQUEST_LOCATION = "request_location"
    REQUEST_SCOPE = "request_scope"
    CALL = "call"
    SMS = "sms"
    EMAIL = "email"
    APPOINTMENT = "appointment"
    ESTIMATE = "estimate"
    EXECUTIVE_REVIEW = "executive_review"


class OutcomeType(str, Enum):
    CONTACTED = "contacted"
    RESPONDED = "responded"
    APPOINTMENT = "appointment"
    ESTIMATE = "estimate"
    WON = "won"
    LOST = "lost"
    DISQUALIFIED = "disqualified"
    GHOSTED = "ghosted"


class RelationType(str, Enum):
    SAME_AS = "same_as"
    ASSOCIATED_WITH = "associated_with"
    LOCATED_AT = "located_at"
    INTERESTED_IN = "interested_in"
    GENERATED_BY = "generated_by"
    CONTACT_FOR = "contact_for"
    DUPLICATE_OF = "duplicate_of"
    RESULTED_IN = "resulted_in"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(
    value: datetime | None,
) -> datetime:
    value = value or utcnow()

    if value.tzinfo is None:
        raise RevenueInvariantError(
            "timestamp must be timezone-aware"
        )

    return value.astimezone(timezone.utc)


def clamp01(
    value: float,
) -> float:
    return max(
        0.0,
        min(
            1.0,
            float(value),
        ),
    )


@dataclass(frozen=True)
class LeadCandidate:
    candidate_id: str
    source_type: SourceType
    raw_text: str
    observed_at: datetime

    source_uri: str = ""

    name: str | None = None
    company: str | None = None

    phone: str | None = None
    email: str | None = None
    social_handle: str | None = None

    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None

    latitude: float | None = None
    longitude: float | None = None

    budget_hint: float | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str

    source_type: SourceType
    source_uri: str

    observed_at: datetime

    text: str

    confidence: float

    previous_hash: str
    evidence_hash: str

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class Hypothesis:
    label: str
    probability: float
    evidence: tuple[str, ...] = ()
    counter_evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class FeatureVector:
    concrete_intent: float
    urgency: float
    geographic_fit: float

    homeowner_probability: float
    contractor_probability: float
    competitor_probability: float

    contactability: float
    source_reliability: float
    evidence_quality: float
    specificity: float

    project_value_signal: float
    spam_probability: float
    duplicate_probability: float

    recency: float


@dataclass(frozen=True)
class ScoreCard:
    fit_probability: float
    response_probability: float
    appointment_probability: float
    win_probability: float

    project_value_probability: float

    expected_value_index: float

    confidence: float

    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class CanonicalLead:
    lead_id: str

    candidate_id: str
    source_type: SourceType

    actor_type: ActorType
    project_type: ProjectType

    name: str | None
    company: str | None

    phone: str | None
    email: str | None
    social_handle: str | None

    street: str | None
    city: str | None
    state: str | None
    postal_code: str | None

    source_uri: str
    raw_text: str

    created_at: datetime
    updated_at: datetime

    features: FeatureVector
    score: ScoreCard

    evidence_ids: tuple[str, ...]

    duplicate_of: str | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class ActionPlan:
    kind: ActionKind

    priority: int

    due_seconds: int

    reason: str

    requires_human_approval: bool = False


@dataclass(frozen=True)
class RevenueDecision:
    lead: CanonicalLead

    tier: DecisionTier

    action: ActionPlan

    actor_hypotheses: tuple[Hypothesis, ...]
    project_hypotheses: tuple[Hypothesis, ...]

    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class OutcomeEvent:
    lead_id: str

    source_type: SourceType

    outcome: OutcomeType

    occurred_at: datetime

    action_kind: ActionKind | None = None

    revenue: float | None = None
    gross_margin: float | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class LearningSignal:
    key: str

    posterior_mean: float
    sample_size: float

    successes: float
    failures: float

    drift_score: float


@dataclass(frozen=True)
class SimulationResult:
    trials: int

    mean_value: float
    p10_value: float
    p50_value: float
    p90_value: float

    win_rate: float

    seed: int


@dataclass(frozen=True)
class StrategyProposal:
    proposal_id: str

    parameter: str

    current_value: float
    proposed_value: float

    confidence: float
    expected_uplift: float

    sample_size: int

    shadow_required: bool
    canary_required: bool

    created_at: datetime

    reason: str


@dataclass(frozen=True)
class EntityNode:
    node_id: str

    entity_type: str

    canonical_key: str

    attributes: dict[str, Any]

    confidence: float

    updated_at: datetime


@dataclass(frozen=True)
class EntityEdge:
    edge_id: str

    source_id: str
    target_id: str

    relation: RelationType

    confidence: float

    evidence_ids: tuple[str, ...]

    created_at: datetime
