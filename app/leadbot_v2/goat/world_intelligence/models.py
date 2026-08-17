from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class WorldIntelligenceError(RuntimeError):
    pass


class EvidenceIntegrityError(WorldIntelligenceError):
    pass


class SourcePolicyError(WorldIntelligenceError):
    pass


class KnowledgeConflictError(WorldIntelligenceError):
    pass


class SourceAuthority(str, Enum):
    OFFICIAL = "official"
    PRIMARY = "primary"
    PROFESSIONAL = "professional"
    REPUTABLE_SECONDARY = "reputable_secondary"
    COMMUNITY = "community"
    UNVERIFIED = "unverified"


class EvidenceStatus(str, Enum):
    ACCEPTED = "accepted"
    QUARANTINED = "quarantined"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"


class FactState(str, Enum):
    ACTIVE = "active"
    CONTESTED = "contested"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


class SignalDomain(str, Enum):
    ENGINEERING = "engineering"
    CONSTRUCTION = "construction"
    BUILDING_CODE = "building_code"
    SAFETY = "safety"
    WEATHER = "weather"
    MATERIALS = "materials"
    FINANCE = "finance"
    ECONOMICS = "economics"
    SECURITIES = "securities"
    ENERGY = "energy"
    OIL_GAS = "oil_gas"
    GEOLOGY = "geology"
    WATER = "water"
    LAND = "land"
    AGRICULTURE = "agriculture"
    TECHNOLOGY = "technology"
    LEGAL_REGULATORY = "legal_regulatory"
    NEWS = "news"


class RefreshCadence(str, Enum):
    IMMEDIATE = "immediate"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"


class SourceHealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    QUARANTINED = "quarantined"


@dataclass(frozen=True)
class SourceDefinition:
    source_id: str

    name: str

    authority: SourceAuthority

    domains: frozenset[
        SignalDomain,
    ]

    public_information_only: bool = True

    official_jurisdictions: tuple[
        str,
        ...,
    ] = ()

    base_confidence: float = 0.5

    enabled: bool = True


@dataclass(frozen=True)
class EvidenceEnvelope:
    evidence_id: str

    source_id: str

    domain: SignalDomain

    subject: str
    predicate: str
    value: Any

    jurisdiction: str | None

    source_url: str | None

    published_at: datetime | None
    acquired_at: datetime

    valid_from: datetime | None = None
    valid_until: datetime | None = None

    confidence: float = 0.5

    status: EvidenceStatus = EvidenceStatus.ACCEPTED

    content_hash: str = ""
    previous_hash: str | None = None
    chain_hash: str = ""

    metadata: dict[
        str,
        Any,
    ] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class KnowledgeFact:
    fact_id: str

    domain: SignalDomain

    subject: str
    predicate: str
    value: Any

    jurisdiction: str | None

    authority: SourceAuthority

    confidence: float

    evidence_ids: tuple[
        str,
        ...,
    ]

    state: FactState

    valid_from: datetime | None
    valid_until: datetime | None

    first_seen_at: datetime
    last_confirmed_at: datetime

    supersedes_fact_id: str | None = None


@dataclass(frozen=True)
class Contradiction:
    contradiction_id: str

    subject: str
    predicate: str
    jurisdiction: str | None

    fact_ids: tuple[
        str,
        ...,
    ]

    severity: float

    reason: str


@dataclass(frozen=True)
class SourceHealth:
    source_id: str

    state: SourceHealthState

    success_rate: float

    consecutive_failures: int

    last_success_at: datetime | None

    last_failure_at: datetime | None


@dataclass(frozen=True)
class WorldSignal:
    signal_id: str

    domain: SignalDomain

    name: str

    timestamp: datetime

    value: float

    unit: str | None

    geography: str | None

    source_id: str

    confidence: float

    metadata: dict[
        str,
        Any,
    ] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class RefreshPolicy:
    domain: SignalDomain

    cadence: RefreshCadence

    freshness_seconds: int

    full_audit_cadence: RefreshCadence = (
        RefreshCadence.QUARTERLY
    )

    require_primary_for_high_impact: bool = True


@dataclass(frozen=True)
class RefreshTask:
    task_id: str

    domain: SignalDomain

    source_id: str | None

    due_at: datetime

    full_audit: bool

    priority: int

    reason: str


@dataclass(frozen=True)
class FreshnessAssessment:
    age_seconds: float

    freshness_score: float

    stale: bool

    expired: bool


@dataclass(frozen=True)
class KnowledgeDecision:
    fact: KnowledgeFact | None

    contradictions: tuple[
        Contradiction,
        ...,
    ]

    usable: bool

    reason: str


def utcnow() -> datetime:
    return datetime.now(
        timezone.utc
    )
