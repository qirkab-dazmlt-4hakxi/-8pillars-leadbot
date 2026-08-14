from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class EntityState(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class OpportunityStage(str, Enum):
    NEW = "new"
    QUALIFYING = "qualifying"
    ESTIMATING = "estimating"
    BID_READY = "bid_ready"
    SUBMITTED = "submitted"
    NEGOTIATION = "negotiation"
    WON = "won"
    LOST = "lost"
    NO_BID = "no_bid"


class ProjectState(str, Enum):
    PRECONSTRUCTION = "preconstruction"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETE = "complete"
    CLOSED = "closed"


TERMINAL_OPPORTUNITY_STAGES = frozenset({
    OpportunityStage.WON,
    OpportunityStage.LOST,
    OpportunityStage.NO_BID,
})


@dataclass(frozen=True)
class EntityRef:
    entity_type: str
    entity_id: str


@dataclass(frozen=True)
class BaseEntity:
    entity_id: str
    tenant_id: str
    business_unit_id: str
    created_at: datetime
    updated_at: datetime
    version: int = 1
    state: EntityState = EntityState.ACTIVE

    def __post_init__(self) -> None:
        if not self.entity_id.strip():
            raise ValueError("entity_id required")
        if not self.tenant_id.strip():
            raise ValueError("tenant_id required")
        if not self.business_unit_id.strip():
            raise ValueError("business_unit_id required")
        if self.version < 1:
            raise ValueError("version must be >= 1")


@dataclass(frozen=True)
class Contact(BaseEntity):
    display_name: str = ""
    company_name: str | None = None
    email: str | None = None
    phone: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class Lead(BaseEntity):
    title: str = ""
    source: str = ""
    contact_id: str | None = None
    owner_user_id: str | None = None
    description: str = ""
    next_action: str = ""
    next_action_due_at: datetime | None = None
    qualification_score: float | None = None
    source_url: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.title.strip():
            raise ValueError("lead title required")
        if not self.source.strip():
            raise ValueError("lead source required")


@dataclass(frozen=True)
class Opportunity(BaseEntity):
    title: str = ""
    lead_id: str | None = None
    contact_id: str | None = None
    owner_user_id: str | None = None
    stage: OpportunityStage = OpportunityStage.NEW
    estimated_value_cents: int | None = None
    estimated_gross_profit_cents: int | None = None
    bid_due_at: datetime | None = None
    next_action: str = ""
    next_action_due_at: datetime | None = None
    lost_reason: str | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.title.strip():
            raise ValueError("opportunity title required")
        if (
            self.estimated_value_cents is not None
            and self.estimated_value_cents < 0
        ):
            raise ValueError("estimated value cannot be negative")


@dataclass(frozen=True)
class Project(BaseEntity):
    name: str = ""
    opportunity_id: str | None = None
    contact_id: str | None = None
    project_manager_user_id: str | None = None
    project_state: ProjectState = ProjectState.PRECONSTRUCTION
    contract_value_cents: int | None = None
    budget_cents: int | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.name.strip():
            raise ValueError("project name required")


@dataclass(frozen=True)
class SpineEvent:
    event_id: str
    tenant_id: str
    aggregate_type: str
    aggregate_id: str
    sequence: int
    event_type: str
    actor_id: str
    occurred_at: datetime
    correlation_id: str
    causation_id: str | None
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("event sequence must be >= 1")
        if not self.event_type.strip():
            raise ValueError("event_type required")
        if not self.actor_id.strip():
            raise ValueError("actor_id required")


def make_event(
    *,
    tenant_id: str,
    aggregate_type: str,
    aggregate_id: str,
    sequence: int,
    event_type: str,
    actor_id: str,
    payload: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> SpineEvent:
    return SpineEvent(
        event_id=new_id("evt"),
        tenant_id=tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        sequence=sequence,
        event_type=event_type,
        actor_id=actor_id,
        occurred_at=utc_now(),
        correlation_id=correlation_id or new_id("corr"),
        causation_id=causation_id,
        payload=dict(payload or {}),
    )
