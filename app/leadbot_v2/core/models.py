from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LeadStage(str, Enum):
    DISCOVERED = "discovered"
    ENRICHED = "enriched"
    QUALIFIED = "qualified"
    CONTACT_READY = "contact_ready"
    CONTACTED = "contacted"
    ENGAGED = "engaged"
    APPOINTMENT_SET = "appointment_set"
    WON = "won"
    LOST = "lost"
    REJECTED = "rejected"


class Contactability(str, Enum):
    NONE = "none"
    SOURCE_ONLY = "source_only"
    PUBLIC_DM = "public_dm"
    EMAIL = "email"
    PHONE = "phone"
    MULTI_CHANNEL = "multi_channel"


class LeadType(str, Enum):
    HOMEOWNER = "homeowner"
    COMMERCIAL = "commercial"
    GC_SUBCONTRACT = "gc_subcontract"
    UNKNOWN = "unknown"


class EvidenceType(str, Enum):
    BUYER_INTENT = "buyer_intent"
    CONCRETE_SCOPE = "concrete_scope"
    LOCATION = "location"
    CONTACT = "contact"
    URGENCY = "urgency"
    PROJECT_VALUE = "project_value"
    IDENTITY = "identity"
    FRESHNESS = "freshness"
    NEGATIVE = "negative"


@dataclass(frozen=True)
class Evidence:
    kind: EvidenceType
    text: str
    confidence: float
    source_url: str | None = None
    observed_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Evidence confidence must be between 0.0 and 1.0")


@dataclass
class ContactRoute:
    channel: str
    value: str
    verified_public: bool = False
    confidence: float = 0.0
    source_url: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Contact confidence must be between 0.0 and 1.0")


@dataclass
class IntelligenceScores:
    buyer_intent: float = 0.0
    concrete_scope: float = 0.0
    location: float = 0.0
    contactability: float = 0.0
    freshness: float = 0.0
    urgency: float = 0.0
    source_trust: float = 0.0
    estimated_conversion: float = 0.0
    overall: float = 0.0

    def validate(self) -> None:
        for name, value in vars(self).items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0.0 and 1.0")


@dataclass
class ProjectEstimate:
    scope: str | None = None
    square_feet_low: int | None = None
    square_feet_high: int | None = None
    value_low: float | None = None
    value_high: float | None = None
    desired_start: str | None = None
    urgency_text: str | None = None


@dataclass
class LeadIntelligenceRecord:
    # Identity
    lead_id: str = field(default_factory=lambda: str(uuid4()))
    fingerprint: str | None = None

    # Source
    source: str = ""
    source_url: str = ""
    source_query: str | None = None
    discovered_at: datetime = field(default_factory=utc_now)
    published_at: datetime | None = None

    # Raw evidence
    title: str = ""
    raw_text: str = ""
    author_name: str | None = None
    author_username: str | None = None
    author_profile_url: str | None = None

    # Geography
    city: str | None = None
    state: str | None = None
    neighborhood: str | None = None
    project_address: str | None = None

    # Classification
    lead_type: LeadType = LeadType.UNKNOWN
    stage: LeadStage = LeadStage.DISCOVERED

    # Intelligence
    scores: IntelligenceScores = field(default_factory=IntelligenceScores)
    evidence: list[Evidence] = field(default_factory=list)
    contacts: list[ContactRoute] = field(default_factory=list)
    project: ProjectEstimate = field(default_factory=ProjectEstimate)

    # Decisioning
    rejection_reason: str | None = None
    qualification_reason: str | None = None
    recommended_action: str | None = None

    # Learning + provenance
    tags: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)

    def build_fingerprint(self) -> str:
        normalized = "|".join(
            [
                self.source.strip().lower(),
                self.source_url.strip().lower(),
                self.title.strip().lower(),
                self.raw_text.strip().lower(),
            ]
        )
        self.fingerprint = sha256(normalized.encode("utf-8")).hexdigest()
        return self.fingerprint

    def add_evidence(
        self,
        kind: EvidenceType,
        text: str,
        confidence: float,
        source_url: str | None = None,
    ) -> None:
        self.evidence.append(
            Evidence(
                kind=kind,
                text=text,
                confidence=confidence,
                source_url=source_url or self.source_url or None,
            )
        )

    def add_contact(
        self,
        channel: str,
        value: str,
        *,
        verified_public: bool,
        confidence: float,
        source_url: str | None = None,
    ) -> None:
        self.contacts.append(
            ContactRoute(
                channel=channel,
                value=value,
                verified_public=verified_public,
                confidence=confidence,
                source_url=source_url or self.source_url or None,
            )
        )

    @property
    def has_actionable_contact(self) -> bool:
        return any(
            c.verified_public
            and c.confidence >= 0.70
            and c.channel in {"phone", "email", "dm", "profile"}
            for c in self.contacts
        )

    @property
    def can_alert(self) -> bool:
        return (
            self.stage in {
                LeadStage.QUALIFIED,
                LeadStage.CONTACT_READY,
                LeadStage.CONTACTED,
                LeadStage.ENGAGED,
                LeadStage.APPOINTMENT_SET,
            }
            and self.has_actionable_contact
            and self.scores.buyer_intent >= 0.70
            and self.scores.concrete_scope >= 0.70
            and self.rejection_reason is None
        )

    def validate(self) -> None:
        self.scores.validate()

        if not self.source:
            raise ValueError("source is required")

        if not self.source_url:
            raise ValueError("source_url is required")

        if not self.fingerprint:
            self.build_fingerprint()

        if self.stage == LeadStage.REJECTED and not self.rejection_reason:
            raise ValueError("Rejected leads require rejection_reason")
