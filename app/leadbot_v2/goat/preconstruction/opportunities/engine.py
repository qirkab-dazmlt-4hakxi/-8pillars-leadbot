from __future__ import annotations

import hashlib
import json
import math
import re
import uuid

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from leadbot_v2.goat.preconstruction.bid_packages.control import (
    PackageSource,
)


class OpportunityError(RuntimeError):
    pass


class OpportunityNotFound(OpportunityError):
    pass


class OpportunityConflict(OpportunityError):
    pass


class OpportunityBlocked(OpportunityError):
    pass


class OpportunityAuditError(OpportunityError):
    pass


class OpportunityState(str, Enum):
    DISCOVERED = "discovered"
    QUALIFYING = "qualifying"
    QUALIFIED = "qualified"
    REVIEW = "review"
    BID = "bid"
    NO_BID = "no_bid"
    PROMOTED = "promoted"
    CLOSED = "closed"


class OpportunitySource(str, Enum):
    BUILDING_CONNECTED = "building_connected"
    CONSTRUCT_CONNECT = "construct_connect"
    DODGE = "dodge"
    SAM_GOV = "sam_gov"
    GOVERNMENT = "government"
    DIRECT_GC = "direct_gc"
    CLIENT = "client"
    PUBLIC_WEB = "public_web"
    SOCIAL = "social"
    REFERRAL = "referral"
    INTERNAL = "internal"
    OTHER = "other"


class TradeScope(str, Enum):
    CONCRETE = "concrete"
    EARTHWORK = "earthwork"
    ELECTRICAL = "electrical"
    PLUMBING = "plumbing"
    MECHANICAL = "mechanical"
    MEP = "mep"
    STRUCTURAL = "structural"
    ARCHITECTURAL = "architectural"
    GENERAL_CONSTRUCTION = "general_construction"
    DEVELOPMENT = "development"
    OTHER = "other"


class ContactKind(str, Enum):
    PHONE = "phone"
    EMAIL = "email"
    PORTAL = "portal"
    PUBLIC_PROFILE = "public_profile"
    DIRECT_MESSAGE = "direct_message"
    OTHER = "other"


class DecisionDisposition(str, Enum):
    BID = "bid"
    REVIEW = "review"
    NO_BID = "no_bid"
    BLOCKED = "blocked"


class FindingSeverity(str, Enum):
    INFO = "info"
    REVIEW = "review"
    BLOCKER = "blocker"


class FollowUpKind(str, Enum):
    CONTACT_GC = "contact_gc"
    REQUEST_PLANS = "request_plans"
    REQUEST_SPECS = "request_specs"
    CONFIRM_SCOPE = "confirm_scope"
    VERIFY_DUE_DATE = "verify_due_date"
    PRICING_REVIEW = "pricing_review"
    CAPACITY_REVIEW = "capacity_review"
    EXECUTIVE_REVIEW = "executive_review"
    BID_FOLLOW_UP = "bid_follow_up"
    OTHER = "other"


@dataclass(frozen=True)
class ContactPath:
    kind: ContactKind
    value: str
    reachable: bool
    verified: bool
    public: bool
    source_ref: str | None = None


@dataclass(frozen=True)
class OpportunityEvidence:
    evidence_id: str
    label: str
    source_ref: str
    observed_at: datetime
    confidence: float


@dataclass(frozen=True)
class OpportunityFinding:
    code: str
    severity: FindingSeverity
    message: str
    source_ref: str | None = None


@dataclass(frozen=True)
class RelationshipProfile:
    organization_name: str
    invite_count: int = 0
    bid_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    paid_projects: int = 0
    payment_issue_count: int = 0
    response_count: int = 0
    positive_relationship_signals: int = 0
    negative_relationship_signals: int = 0

    @property
    def win_rate(self) -> float | None:
        denominator = (
            self.win_count
            + self.loss_count
        )

        if denominator <= 0:
            return None

        return (
            self.win_count
            / denominator
        )


@dataclass(frozen=True)
class CapacitySnapshot:
    estimator_hours_available: float
    estimator_hours_committed: float
    operations_capacity_percent: float
    active_bid_count: int
    max_active_bid_count: int

    @property
    def estimator_hours_remaining(self) -> float:
        return max(
            0.0,
            self.estimator_hours_available
            - self.estimator_hours_committed,
        )

    @property
    def estimator_utilization(self) -> float:
        if self.estimator_hours_available <= 0:
            return 1.0

        return min(
            1.0,
            max(
                0.0,
                self.estimator_hours_committed
                / self.estimator_hours_available,
            ),
        )


@dataclass(frozen=True)
class Opportunity:
    opportunity_id: str

    tenant_id: str
    business_unit_id: str

    source: OpportunitySource
    source_opportunity_id: str | None

    project_name: str
    city: str
    county: str | None
    state_region: str

    gc_name: str | None
    client_name: str | None

    requested_trades: tuple[
        TradeScope,
        ...
    ]

    scope_summary: str

    due_at: datetime | None

    estimated_bid_cents: int | None
    estimated_direct_cost_cents: int | None

    pursuit_hours_estimate: float

    contacts: tuple[
        ContactPath,
        ...
    ]

    evidence: tuple[
        OpportunityEvidence,
        ...
    ]

    state: OpportunityState

    promoted_package_id: str | None
    promoted_case_id: str | None

    created_at: datetime
    updated_at: datetime
    version: int


@dataclass(frozen=True)
class DecisionFactor:
    name: str
    score: float
    weight: float
    weighted_score: float
    explanation: str
    resolved: bool


@dataclass(frozen=True)
class EconomicAnalysis:
    estimated_bid_cents: int | None
    estimated_direct_cost_cents: int | None
    gross_profit_cents: int | None
    gross_margin_bps: int | None
    modeled_win_probability: float | None
    expected_gross_profit_cents: int | None
    pursuit_cost_cents: int | None
    expected_value_cents: int | None


@dataclass(frozen=True)
class BidDecision:
    opportunity_id: str

    disposition: DecisionDisposition

    score: float

    factors: tuple[
        DecisionFactor,
        ...
    ]

    findings: tuple[
        OpportunityFinding,
        ...
    ]

    economics: EconomicAnalysis

    recommended_pursuit_hours: float

    decided_at: datetime

    @property
    def blockers(
        self,
    ) -> tuple[
        OpportunityFinding,
        ...
    ]:
        return tuple(
            item
            for item
            in self.findings
            if (
                item.severity
                == FindingSeverity.BLOCKER
            )
        )

    @property
    def reviews(
        self,
    ) -> tuple[
        OpportunityFinding,
        ...
    ]:
        return tuple(
            item
            for item
            in self.findings
            if (
                item.severity
                == FindingSeverity.REVIEW
            )
        )


@dataclass(frozen=True)
class FollowUpTask:
    task_id: str
    opportunity_id: str
    kind: FollowUpKind
    description: str
    due_at: datetime
    assigned_role: str
    source_ref: str | None
    completed: bool = False
    completed_at: datetime | None = None
    completed_by: str | None = None


@dataclass(frozen=True)
class OpportunityAuditRecord:
    event_id: str
    opportunity_id: str
    sequence: int
    action: str
    actor_id: str
    occurred_at: datetime
    previous_hash: str
    payload_hash: str
    event_hash: str


@dataclass(frozen=True)
class OpportunityPortfolioItem:
    opportunity_id: str
    project_name: str
    gc_name: str | None
    city: str
    due_at: datetime | None
    state: OpportunityState
    disposition: DecisionDisposition | None
    score: float | None
    expected_value_cents: int | None
    open_task_count: int
    promoted_package_id: str | None
    promoted_case_id: str | None


@dataclass(frozen=True)
class OpportunityConfig:
    enabled_trades: frozenset[
        TradeScope
    ]

    preferred_cities: frozenset[
        str
    ]

    allowed_cities: frozenset[
        str
    ]

    min_bid_score: float = 72.0
    min_review_score: float = 52.0

    pursuit_labor_cost_per_hour_cents: int = 7500

    require_contact_path: bool = True

    require_scope: bool = True

    require_due_date: bool = True

    max_capacity_utilization: float = 0.92

    relationship_weight: float = 0.15
    trade_fit_weight: float = 0.20
    geography_weight: float = 0.10
    deadline_weight: float = 0.10
    economics_weight: float = 0.25
    capacity_weight: float = 0.10
    evidence_weight: float = 0.10

    def __post_init__(self) -> None:
        weights = (
            self.relationship_weight
            + self.trade_fit_weight
            + self.geography_weight
            + self.deadline_weight
            + self.economics_weight
            + self.capacity_weight
            + self.evidence_weight
        )

        if not math.isclose(
            weights,
            1.0,
            abs_tol=0.0001,
        ):
            raise ValueError(
                "decision weights must total 1.0"
            )

        if not (
            0
            <= self.min_review_score
            <= self.min_bid_score
            <= 100
        ):
            raise ValueError(
                "invalid decision thresholds"
            )


def _now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def _new_id(
    prefix: str,
) -> str:
    return (
        prefix
        + "_"
        + uuid.uuid4().hex
    )


def _required(
    value: Any,
    field: str,
) -> str:
    result = str(
        value
        or ""
    ).strip()

    if not result:
        raise ValueError(
            f"{field} is required"
        )

    return result


def _aware(
    value: datetime | None,
    field: str,
) -> datetime | None:
    if value is None:
        return None

    if (
        value.tzinfo is None
        or value.utcoffset()
        is None
    ):
        raise ValueError(
            f"{field} must be timezone-aware"
        )

    return value


def _money_or_none(
    value: Any,
    field: str,
) -> int | None:
    if value is None:
        return None

    if isinstance(
        value,
        bool,
    ):
        raise ValueError(
            f"{field} cannot be boolean"
        )

    result = int(
        value
    )

    if result < 0:
        raise ValueError(
            f"{field} cannot be negative"
        )

    return result


def _confidence(
    value: Any,
) -> float:
    result = float(
        value
    )

    if not math.isfinite(
        result
    ):
        raise ValueError(
            "confidence must be finite"
        )

    if not (
        0.0
        <= result
        <= 1.0
    ):
        raise ValueError(
            "confidence must be 0..1"
        )

    return result


def _normalize_name(
    value: str | None,
) -> str:
    return re.sub(
        r"[^A-Z0-9]+",
        " ",
        str(
            value
            or ""
        ).upper(),
    ).strip()


def _stable(
    value: Any,
) -> Any:
    if isinstance(
        value,
        Enum,
    ):
        return value.value

    if isinstance(
        value,
        datetime,
    ):
        return value.isoformat()

    if isinstance(
        value,
        dict,
    ):
        return {
            str(key):
                _stable(
                    item
                )
            for key, item
            in sorted(
                value.items()
            )
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
            frozenset,
        ),
    ):
        return [
            _stable(
                item
            )
            for item
            in value
        ]

    if hasattr(
        value,
        "__dict__",
    ):
        return {
            key:
                _stable(
                    item
                )
            for key, item
            in sorted(
                vars(
                    value
                ).items()
            )
            if not key.startswith(
                "_"
            )
        }

    return value


def _hash(
    value: Any,
) -> str:
    body = json.dumps(
        _stable(
            value
        ),
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=True,
        default=str,
    ).encode(
        "utf-8"
    )

    return (
        hashlib
        .sha256(
            body
        )
        .hexdigest()
    )


def _source_to_package(
    source: OpportunitySource,
) -> PackageSource:
    mapping = {
        OpportunitySource.BUILDING_CONNECTED:
            PackageSource.BUILDING_CONNECTED,

        OpportunitySource.CONSTRUCT_CONNECT:
            PackageSource.CONSTRUCT_CONNECT,

        OpportunitySource.DODGE:
            PackageSource.DODGE,

        OpportunitySource.SAM_GOV:
            PackageSource.GOVERNMENT,

        OpportunitySource.GOVERNMENT:
            PackageSource.GOVERNMENT,

        OpportunitySource.DIRECT_GC:
            PackageSource.DIRECT_GC,

        OpportunitySource.CLIENT:
            PackageSource.CLIENT,

        OpportunitySource.PUBLIC_WEB:
            PackageSource.PUBLIC,

        OpportunitySource.SOCIAL:
            PackageSource.PUBLIC,

        OpportunitySource.REFERRAL:
            PackageSource.DIRECT_GC,

        OpportunitySource.INTERNAL:
            PackageSource.INTERNAL,

        OpportunitySource.OTHER:
            PackageSource.OTHER,
    }

    return mapping[
        source
    ]


class OpportunityIntelligenceService:
    """
    Deterministic bid-discovery and pursuit-decision control plane.

    No public-source adapter is implemented here. External systems must
    deliver lawfully obtained opportunity data through this normalization
    boundary.

    The engine refuses to fabricate:
      * pricing,
      * due dates,
      * scope,
      * contact paths,
      * economic value,
      * or relationship history.

    Unknown data remains explicitly unresolved.
    """

    def __init__(
        self,
        *,
        config: OpportunityConfig,
        package_control: Any | None = None,
        command_center: Any | None = None,
    ) -> None:
        self.config = config

        self.package_control = (
            package_control
        )

        self.command_center = (
            command_center
        )

        self._opportunities: dict[
            str,
            Opportunity,
        ] = {}

        self._decisions: dict[
            str,
            BidDecision,
        ] = {}

        self._tasks: dict[
            str,
            FollowUpTask,
        ] = {}

        self._audits: dict[
            str,
            list[
                OpportunityAuditRecord
            ],
        ] = {}

        self._fingerprints: dict[
            str,
            str,
        ] = {}

        self._source_keys: dict[
            tuple[
                OpportunitySource,
                str,
            ],
            str,
        ] = {}

    def get(
        self,
        opportunity_id: str,
    ) -> Opportunity:
        result = (
            self._opportunities.get(
                opportunity_id
            )
        )

        if result is None:
            raise OpportunityNotFound(
                opportunity_id
            )

        return result

    def decision(
        self,
        opportunity_id: str,
    ) -> BidDecision | None:
        self.get(
            opportunity_id
        )

        return self._decisions.get(
            opportunity_id
        )

    def tasks(
        self,
        opportunity_id: str,
        *,
        include_completed: bool = False,
    ) -> tuple[
        FollowUpTask,
        ...
    ]:
        self.get(
            opportunity_id
        )

        values = [
            task
            for task
            in self._tasks.values()
            if (
                task.opportunity_id
                == opportunity_id
                and (
                    include_completed
                    or not task.completed
                )
            )
        ]

        return tuple(
            sorted(
                values,
                key=lambda item:
                    (
                        item.due_at,
                        item.task_id,
                    ),
            )
        )

    def _fingerprint(
        self,
        *,
        project_name: str,
        city: str,
        gc_name: str | None,
        due_at: datetime | None,
    ) -> str:
        date_key = (
            due_at.date()
            .isoformat()
            if due_at
            else ""
        )

        return _hash(
            {
                "project":
                    _normalize_name(
                        project_name
                    ),
                "city":
                    _normalize_name(
                        city
                    ),
                "gc":
                    _normalize_name(
                        gc_name
                    ),
                "due_date":
                    date_key,
            }
        )

    def _audit(
        self,
        opportunity: Opportunity,
        *,
        action: str,
        actor_id: str,
        payload: dict[
            str,
            Any,
        ],
    ) -> None:
        records = (
            self._audits.setdefault(
                opportunity
                .opportunity_id,
                [],
            )
        )

        sequence = len(
            records
        ) + 1

        previous_hash = (
            records[-1]
            .event_hash
            if records
            else "GENESIS"
        )

        occurred_at = _now()

        payload_hash = _hash(
            payload
        )

        material = {
            "opportunity_id":
                opportunity
                .opportunity_id,
            "sequence":
                sequence,
            "action":
                action,
            "actor_id":
                actor_id,
            "occurred_at":
                occurred_at
                .isoformat(),
            "previous_hash":
                previous_hash,
            "payload_hash":
                payload_hash,
        }

        record = (
            OpportunityAuditRecord(
                event_id=(
                    _new_id(
                        "oevt"
                    )
                ),
                opportunity_id=(
                    opportunity
                    .opportunity_id
                ),
                sequence=(
                    sequence
                ),
                action=(
                    action
                ),
                actor_id=(
                    actor_id
                ),
                occurred_at=(
                    occurred_at
                ),
                previous_hash=(
                    previous_hash
                ),
                payload_hash=(
                    payload_hash
                ),
                event_hash=(
                    _hash(
                        material
                    )
                ),
            )
        )

        records.append(
            record
        )

    def verify_audit(
        self,
        opportunity_id: str,
    ) -> bool:
        self.get(
            opportunity_id
        )

        previous = "GENESIS"

        for expected, record in enumerate(
            self._audits.get(
                opportunity_id,
                (),
            ),
            1,
        ):
            if (
                record.sequence
                != expected
            ):
                raise OpportunityAuditError(
                    "audit sequence mismatch"
                )

            if (
                record.previous_hash
                != previous
            ):
                raise OpportunityAuditError(
                    "audit previous hash mismatch"
                )

            material = {
                "opportunity_id":
                    record
                    .opportunity_id,
                "sequence":
                    record.sequence,
                "action":
                    record.action,
                "actor_id":
                    record.actor_id,
                "occurred_at":
                    record
                    .occurred_at
                    .isoformat(),
                "previous_hash":
                    record
                    .previous_hash,
                "payload_hash":
                    record
                    .payload_hash,
            }

            if (
                _hash(
                    material
                )
                != record
                .event_hash
            ):
                raise OpportunityAuditError(
                    "audit event hash mismatch"
                )

            previous = (
                record.event_hash
            )

        return True

    def ingest(
        self,
        *,
        tenant_id: str,
        business_unit_id: str,
        source: OpportunitySource,
        project_name: str,
        city: str,
        requested_trades: tuple[
            TradeScope,
            ...
        ],
        scope_summary: str,
        actor_id: str,
        state_region: str = "TX",
        source_opportunity_id: str | None = None,
        county: str | None = None,
        gc_name: str | None = None,
        client_name: str | None = None,
        due_at: datetime | None = None,
        estimated_bid_cents: int | None = None,
        estimated_direct_cost_cents: int | None = None,
        pursuit_hours_estimate: float = 8.0,
        contacts: tuple[
            ContactPath,
            ...
        ] = (),
        evidence: tuple[
            OpportunityEvidence,
            ...
        ] = (),
    ) -> Opportunity:
        tenant_id = (
            _required(
                tenant_id,
                "tenant_id",
            )
        )

        business_unit_id = (
            _required(
                business_unit_id,
                "business_unit_id",
            )
        )

        project_name = (
            _required(
                project_name,
                "project_name",
            )
        )

        city = _required(
            city,
            "city",
        )

        actor_id = _required(
            actor_id,
            "actor_id",
        )

        scope_summary = str(
            scope_summary
            or ""
        ).strip()

        due_at = _aware(
            due_at,
            "due_at",
        )

        estimated_bid_cents = (
            _money_or_none(
                estimated_bid_cents,
                "estimated_bid_cents",
            )
        )

        estimated_direct_cost_cents = (
            _money_or_none(
                estimated_direct_cost_cents,
                "estimated_direct_cost_cents",
            )
        )

        pursuit_hours_estimate = float(
            pursuit_hours_estimate
        )

        if (
            not math.isfinite(
                pursuit_hours_estimate
            )
            or pursuit_hours_estimate
            < 0
        ):
            raise ValueError(
                "pursuit_hours_estimate "
                "must be finite and nonnegative"
            )

        normalized_trades = tuple(
            dict.fromkeys(
                requested_trades
            )
        )

        if source_opportunity_id:
            source_key = (
                source,
                str(
                    source_opportunity_id
                ),
            )

            existing_id = (
                self._source_keys.get(
                    source_key
                )
            )

            if existing_id:
                return self.get(
                    existing_id
                )

        fingerprint = (
            self._fingerprint(
                project_name=(
                    project_name
                ),
                city=city,
                gc_name=(
                    gc_name
                ),
                due_at=(
                    due_at
                ),
            )
        )

        existing = (
            self._fingerprints.get(
                fingerprint
            )
        )

        if existing:
            return self.get(
                existing
            )

        for contact in contacts:
            if not str(
                contact.value
            ).strip():
                raise ValueError(
                    "contact value required"
                )

        for item in evidence:
            _confidence(
                item.confidence
            )

        now = _now()

        opportunity = Opportunity(
            opportunity_id=(
                _new_id(
                    "opp"
                )
            ),
            tenant_id=(
                tenant_id
            ),
            business_unit_id=(
                business_unit_id
            ),
            source=source,
            source_opportunity_id=(
                source_opportunity_id
            ),
            project_name=(
                project_name
            ),
            city=city,
            county=county,
            state_region=(
                state_region
            ),
            gc_name=gc_name,
            client_name=(
                client_name
            ),
            requested_trades=(
                normalized_trades
            ),
            scope_summary=(
                scope_summary
            ),
            due_at=due_at,
            estimated_bid_cents=(
                estimated_bid_cents
            ),
            estimated_direct_cost_cents=(
                estimated_direct_cost_cents
            ),
            pursuit_hours_estimate=(
                pursuit_hours_estimate
            ),
            contacts=tuple(
                contacts
            ),
            evidence=tuple(
                evidence
            ),
            state=(
                OpportunityState
                .DISCOVERED
            ),
            promoted_package_id=None,
            promoted_case_id=None,
            created_at=now,
            updated_at=now,
            version=1,
        )

        self._opportunities[
            opportunity
            .opportunity_id
        ] = opportunity

        self._fingerprints[
            fingerprint
        ] = (
            opportunity
            .opportunity_id
        )

        if source_opportunity_id:
            self._source_keys[
                (
                    source,
                    str(
                        source_opportunity_id
                    ),
                )
            ] = (
                opportunity
                .opportunity_id
            )

        self._audit(
            opportunity,
            action=(
                "opportunity.ingested"
            ),
            actor_id=(
                actor_id
            ),
            payload={
                "source":
                    source.value,
                "project_name":
                    project_name,
                "city":
                    city,
                "gc_name":
                    gc_name or "",
                "due_at":
                    (
                        due_at
                        .isoformat()
                        if due_at
                        else ""
                    ),
            },
        )

        return opportunity

    @staticmethod
    def _relationship_score(
        profile: RelationshipProfile | None,
    ) -> tuple[
        float,
        str,
        bool,
    ]:
        if profile is None:
            return (
                50.0,
                "No relationship history; neutral score.",
                False,
            )

        score = 50.0

        if profile.invite_count:
            score += min(
                10.0,
                profile.invite_count
                * 1.0,
            )

        win_rate = (
            profile.win_rate
        )

        if win_rate is not None:
            score += (
                win_rate
                - 0.25
            ) * 30.0

        score += min(
            15.0,
            profile
            .positive_relationship_signals
            * 3.0,
        )

        score -= min(
            25.0,
            profile
            .negative_relationship_signals
            * 5.0,
        )

        score -= min(
            25.0,
            profile
            .payment_issue_count
            * 8.0,
        )

        score = max(
            0.0,
            min(
                100.0,
                score,
            ),
        )

        return (
            score,
            (
                "Relationship score based on "
                "historical invitations, wins, "
                "signals, and payment experience."
            ),
            True,
        )

    def _trade_fit(
        self,
        opportunity: Opportunity,
    ) -> tuple[
        float,
        str,
        bool,
    ]:
        requested = set(
            opportunity
            .requested_trades
        )

        if not requested:
            return (
                0.0,
                "Requested trade scope is unresolved.",
                False,
            )

        matched = (
            requested
            & set(
                self.config
                .enabled_trades
            )
        )

        ratio = (
            len(
                matched
            )
            / len(
                requested
            )
        )

        return (
            ratio
            * 100.0,
            (
                f"{len(matched)} of "
                f"{len(requested)} requested "
                "trade scopes are enabled."
            ),
            True,
        )

    def _geography_score(
        self,
        opportunity: Opportunity,
    ) -> tuple[
        float,
        str,
        bool,
    ]:
        city = (
            opportunity.city
            .strip()
            .lower()
        )

        preferred = {
            item
            .strip()
            .lower()
            for item
            in self.config
            .preferred_cities
        }

        allowed = {
            item
            .strip()
            .lower()
            for item
            in self.config
            .allowed_cities
        }

        if city in preferred:
            return (
                100.0,
                "Project is in a preferred market.",
                True,
            )

        if city in allowed:
            return (
                75.0,
                "Project is in an allowed market.",
                True,
            )

        if not allowed:
            return (
                50.0,
                "No geographic allowlist configured.",
                False,
            )

        return (
            15.0,
            "Project is outside configured markets.",
            True,
        )

    @staticmethod
    def _deadline_score(
        due_at: datetime | None,
        *,
        as_of: datetime,
    ) -> tuple[
        float,
        str,
        bool,
    ]:
        if due_at is None:
            return (
                0.0,
                "Bid deadline is unresolved.",
                False,
            )

        seconds = int(
            (
                due_at
                - as_of
            )
            .total_seconds()
        )

        if seconds <= 0:
            return (
                0.0,
                "Bid deadline has passed.",
                True,
            )

        hours = (
            seconds
            / 3600.0
        )

        if hours < 4:
            return (
                10.0,
                "Bid is due in less than four hours.",
                True,
            )

        if hours < 12:
            return (
                35.0,
                "Bid is due in less than twelve hours.",
                True,
            )

        if hours < 24:
            return (
                55.0,
                "Bid is due within twenty-four hours.",
                True,
            )

        if hours < 72:
            return (
                80.0,
                "Bid has a workable but compressed window.",
                True,
            )

        return (
            100.0,
            "Bid has a healthy pursuit window.",
            True,
        )

    def _capacity_score(
        self,
        opportunity: Opportunity,
        capacity: CapacitySnapshot | None,
    ) -> tuple[
        float,
        str,
        bool,
    ]:
        if capacity is None:
            return (
                50.0,
                "Capacity snapshot unavailable.",
                False,
            )

        if (
            capacity.max_active_bid_count
            <= 0
        ):
            return (
                0.0,
                "Configured bid capacity is zero.",
                True,
            )

        bid_utilization = (
            capacity.active_bid_count
            / capacity
            .max_active_bid_count
        )

        estimator_utilization = (
            capacity
            .estimator_utilization
        )

        utilization = max(
            bid_utilization,
            estimator_utilization,
        )

        if (
            capacity
            .estimator_hours_remaining
            < opportunity
            .pursuit_hours_estimate
        ):
            return (
                10.0,
                "Insufficient estimator hours remain.",
                True,
            )

        if (
            utilization
            >= self.config
            .max_capacity_utilization
        ):
            return (
                20.0,
                "Current pursuit capacity is near saturation.",
                True,
            )

        score = (
            100.0
            * (
                1.0
                - min(
                    1.0,
                    utilization,
                )
            )
        )

        score = max(
            25.0,
            min(
                100.0,
                score,
            ),
        )

        return (
            score,
            (
                "Capacity score derived from estimator "
                "hours and active-bid utilization."
            ),
            True,
        )

    @staticmethod
    def _evidence_score(
        opportunity: Opportunity,
    ) -> tuple[
        float,
        str,
        bool,
    ]:
        if not opportunity.evidence:
            return (
                20.0,
                "No structured source evidence attached.",
                False,
            )

        confidences = [
            _confidence(
                item.confidence
            )
            for item
            in opportunity.evidence
        ]

        average = (
            sum(
                confidences
            )
            / len(
                confidences
            )
        )

        quantity_factor = min(
            1.0,
            len(
                confidences
            )
            / 4.0,
        )

        score = (
            (
                average
                * 0.8
            )
            + (
                quantity_factor
                * 0.2
            )
        ) * 100.0

        return (
            score,
            (
                "Evidence score uses confidence "
                "and independent evidence count."
            ),
            True,
        )

    def _economics(
        self,
        opportunity: Opportunity,
        *,
        relationship_score: float,
        evidence_score: float,
    ) -> tuple[
        float,
        str,
        bool,
        EconomicAnalysis,
    ]:
        bid = (
            opportunity
            .estimated_bid_cents
        )

        direct = (
            opportunity
            .estimated_direct_cost_cents
        )

        pursuit_cost = int(
            round(
                opportunity
                .pursuit_hours_estimate
                * self.config
                .pursuit_labor_cost_per_hour_cents
            )
        )

        if (
            bid is None
            or direct is None
        ):
            analysis = (
                EconomicAnalysis(
                    estimated_bid_cents=(
                        bid
                    ),
                    estimated_direct_cost_cents=(
                        direct
                    ),
                    gross_profit_cents=None,
                    gross_margin_bps=None,
                    modeled_win_probability=None,
                    expected_gross_profit_cents=None,
                    pursuit_cost_cents=(
                        pursuit_cost
                    ),
                    expected_value_cents=None,
                )
            )

            return (
                50.0,
                (
                    "Pricing is unresolved; economic "
                    "score remains neutral."
                ),
                False,
                analysis,
            )

        gross_profit = (
            bid
            - direct
        )

        gross_margin_bps = (
            round(
                gross_profit
                * 10_000
                / bid
            )
            if bid
            else None
        )

        modeled_probability = (
            (
                relationship_score
                * 0.55
            )
            + (
                evidence_score
                * 0.25
            )
            + 20.0
        ) / 100.0

        modeled_probability = max(
            0.05,
            min(
                0.90,
                modeled_probability,
            ),
        )

        expected_gross_profit = int(
            round(
                gross_profit
                * modeled_probability
            )
        )

        expected_value = (
            expected_gross_profit
            - pursuit_cost
        )

        if gross_profit <= 0:
            score = 0.0

        elif (
            gross_margin_bps
            is not None
            and gross_margin_bps
            < 500
        ):
            score = 20.0

        elif expected_value <= 0:
            score = 35.0

        else:
            margin_percent = (
                gross_margin_bps
                / 100.0
                if gross_margin_bps
                is not None
                else 0.0
            )

            score = min(
                100.0,
                50.0
                + (
                    margin_percent
                    * 1.5
                )
                + min(
                    20.0,
                    expected_value
                    / 100_000.0,
                ),
            )

        analysis = (
            EconomicAnalysis(
                estimated_bid_cents=(
                    bid
                ),
                estimated_direct_cost_cents=(
                    direct
                ),
                gross_profit_cents=(
                    gross_profit
                ),
                gross_margin_bps=(
                    gross_margin_bps
                ),
                modeled_win_probability=(
                    modeled_probability
                ),
                expected_gross_profit_cents=(
                    expected_gross_profit
                ),
                pursuit_cost_cents=(
                    pursuit_cost
                ),
                expected_value_cents=(
                    expected_value
                ),
            )
        )

        return (
            score,
            (
                "Economic score uses estimated gross "
                "margin, modeled win probability, "
                "and pursuit cost."
            ),
            True,
            analysis,
        )

    def evaluate(
        self,
        *,
        opportunity_id: str,
        actor_id: str,
        relationship: (
            RelationshipProfile
            | None
        ) = None,
        capacity: (
            CapacitySnapshot
            | None
        ) = None,
        as_of: (
            datetime
            | None
        ) = None,
    ) -> BidDecision:
        opportunity = (
            self.get(
                opportunity_id
            )
        )

        actor_id = _required(
            actor_id,
            "actor_id",
        )

        as_of = (
            _aware(
                as_of,
                "as_of",
            )
            if as_of
            is not None
            else _now()
        )

        findings = []

        reachable_contacts = tuple(
            contact
            for contact
            in opportunity.contacts
            if (
                contact.reachable
                and contact.verified
            )
        )

        if (
            self.config
            .require_contact_path
            and not reachable_contacts
        ):
            findings.append(
                OpportunityFinding(
                    code=(
                        "CONTACT_PATH_UNRESOLVED"
                    ),
                    severity=(
                        FindingSeverity
                        .BLOCKER
                    ),
                    message=(
                        "No verified reachable "
                        "contact path is available."
                    ),
                )
            )

        if (
            self.config
            .require_scope
            and not opportunity
            .scope_summary
        ):
            findings.append(
                OpportunityFinding(
                    code=(
                        "SCOPE_UNRESOLVED"
                    ),
                    severity=(
                        FindingSeverity
                        .BLOCKER
                    ),
                    message=(
                        "Opportunity scope is unresolved."
                    ),
                )
            )

        if (
            not opportunity
            .requested_trades
        ):
            findings.append(
                OpportunityFinding(
                    code=(
                        "TRADE_SCOPE_UNRESOLVED"
                    ),
                    severity=(
                        FindingSeverity
                        .BLOCKER
                    ),
                    message=(
                        "No requested trade scope "
                        "has been identified."
                    ),
                )
            )

        if (
            self.config
            .require_due_date
            and opportunity
            .due_at
            is None
        ):
            findings.append(
                OpportunityFinding(
                    code=(
                        "BID_DUE_DATE_UNRESOLVED"
                    ),
                    severity=(
                        FindingSeverity
                        .BLOCKER
                    ),
                    message=(
                        "Bid deadline is unresolved."
                    ),
                )
            )

        if (
            opportunity.due_at
            is not None
            and opportunity
            .due_at
            <= as_of
        ):
            findings.append(
                OpportunityFinding(
                    code=(
                        "BID_DUE_DATE_PASSED"
                    ),
                    severity=(
                        FindingSeverity
                        .BLOCKER
                    ),
                    message=(
                        "Bid deadline has passed."
                    ),
                )
            )

        (
            relationship_score,
            relationship_reason,
            relationship_resolved,
        ) = self._relationship_score(
            relationship
        )

        (
            trade_score,
            trade_reason,
            trade_resolved,
        ) = self._trade_fit(
            opportunity
        )

        (
            geography_score,
            geography_reason,
            geography_resolved,
        ) = self._geography_score(
            opportunity
        )

        (
            deadline_score,
            deadline_reason,
            deadline_resolved,
        ) = self._deadline_score(
            opportunity
            .due_at,
            as_of=as_of,
        )

        (
            capacity_score,
            capacity_reason,
            capacity_resolved,
        ) = self._capacity_score(
            opportunity,
            capacity,
        )

        (
            evidence_score,
            evidence_reason,
            evidence_resolved,
        ) = self._evidence_score(
            opportunity
        )

        (
            economics_score,
            economics_reason,
            economics_resolved,
            economics,
        ) = self._economics(
            opportunity,
            relationship_score=(
                relationship_score
            ),
            evidence_score=(
                evidence_score
            ),
        )

        factor_inputs = (
            (
                "relationship",
                relationship_score,
                self.config
                .relationship_weight,
                relationship_reason,
                relationship_resolved,
            ),
            (
                "trade_fit",
                trade_score,
                self.config
                .trade_fit_weight,
                trade_reason,
                trade_resolved,
            ),
            (
                "geography",
                geography_score,
                self.config
                .geography_weight,
                geography_reason,
                geography_resolved,
            ),
            (
                "deadline",
                deadline_score,
                self.config
                .deadline_weight,
                deadline_reason,
                deadline_resolved,
            ),
            (
                "economics",
                economics_score,
                self.config
                .economics_weight,
                economics_reason,
                economics_resolved,
            ),
            (
                "capacity",
                capacity_score,
                self.config
                .capacity_weight,
                capacity_reason,
                capacity_resolved,
            ),
            (
                "evidence",
                evidence_score,
                self.config
                .evidence_weight,
                evidence_reason,
                evidence_resolved,
            ),
        )

        factors = tuple(
            DecisionFactor(
                name=name,
                score=round(
                    score,
                    4,
                ),
                weight=weight,
                weighted_score=round(
                    score
                    * weight,
                    4,
                ),
                explanation=reason,
                resolved=resolved,
            )
            for (
                name,
                score,
                weight,
                reason,
                resolved,
            )
            in factor_inputs
        )

        score = round(
            sum(
                factor
                .weighted_score
                for factor
                in factors
            ),
            4,
        )

        unresolved = tuple(
            factor
            for factor
            in factors
            if not factor.resolved
        )

        if unresolved:
            findings.append(
                OpportunityFinding(
                    code=(
                        "DECISION_DATA_INCOMPLETE"
                    ),
                    severity=(
                        FindingSeverity
                        .REVIEW
                    ),
                    message=(
                        "One or more bid-decision "
                        "factors are unresolved."
                    ),
                )
            )

        enabled_trade_match = bool(
            set(
                opportunity
                .requested_trades
            )
            & set(
                self.config
                .enabled_trades
            )
        )

        if not enabled_trade_match:
            findings.append(
                OpportunityFinding(
                    code=(
                        "NO_ENABLED_TRADE_MATCH"
                    ),
                    severity=(
                        FindingSeverity
                        .BLOCKER
                    ),
                    message=(
                        "Opportunity does not match "
                        "an enabled business trade."
                    ),
                )
            )

        if (
            capacity is not None
            and capacity
            .estimator_hours_remaining
            < opportunity
            .pursuit_hours_estimate
        ):
            findings.append(
                OpportunityFinding(
                    code=(
                        "ESTIMATING_CAPACITY_SHORTFALL"
                    ),
                    severity=(
                        FindingSeverity
                        .REVIEW
                    ),
                    message=(
                        "Estimated pursuit hours exceed "
                        "remaining estimator capacity."
                    ),
                )
            )

        if (
            economics
            .gross_profit_cents
            is not None
            and economics
            .gross_profit_cents
            <= 0
        ):
            findings.append(
                OpportunityFinding(
                    code=(
                        "NONPOSITIVE_GROSS_PROFIT"
                    ),
                    severity=(
                        FindingSeverity
                        .BLOCKER
                    ),
                    message=(
                        "Estimated gross profit is "
                        "not positive."
                    ),
                )
            )

        findings_tuple = tuple(
            findings
        )

        blockers = tuple(
            item
            for item
            in findings_tuple
            if (
                item.severity
                == FindingSeverity
                .BLOCKER
            )
        )

        reviews = tuple(
            item
            for item
            in findings_tuple
            if (
                item.severity
                == FindingSeverity
                .REVIEW
            )
        )

        if blockers:
            disposition = (
                DecisionDisposition
                .BLOCKED
            )

        elif (
            score
            >= self.config
            .min_bid_score
            and not reviews
        ):
            disposition = (
                DecisionDisposition.BID
            )

        elif (
            score
            >= self.config
            .min_review_score
        ):
            disposition = (
                DecisionDisposition.REVIEW
            )

        else:
            disposition = (
                DecisionDisposition.NO_BID
            )

        decision = BidDecision(
            opportunity_id=(
                opportunity_id
            ),
            disposition=(
                disposition
            ),
            score=score,
            factors=factors,
            findings=(
                findings_tuple
            ),
            economics=(
                economics
            ),
            recommended_pursuit_hours=(
                opportunity
                .pursuit_hours_estimate
            ),
            decided_at=as_of,
        )

        self._decisions[
            opportunity_id
        ] = decision

        next_state = {
            DecisionDisposition.BID:
                OpportunityState.BID,

            DecisionDisposition.REVIEW:
                OpportunityState.REVIEW,

            DecisionDisposition.NO_BID:
                OpportunityState.NO_BID,

            DecisionDisposition.BLOCKED:
                OpportunityState.REVIEW,
        }[
            disposition
        ]

        updated = replace(
            opportunity,
            state=next_state,
            updated_at=_now(),
            version=(
                opportunity.version
                + 1
            ),
        )

        self._opportunities[
            opportunity_id
        ] = updated

        self._audit(
            updated,
            action=(
                "opportunity.evaluated"
            ),
            actor_id=(
                actor_id
            ),
            payload={
                "score":
                    score,
                "disposition":
                    disposition.value,
                "blockers":
                    len(
                        blockers
                    ),
                "reviews":
                    len(
                        reviews
                    ),
                "expected_value_cents":
                    (
                        economics
                        .expected_value_cents
                    ),
            },
        )

        return decision

    def schedule_follow_through(
        self,
        *,
        opportunity_id: str,
        actor_id: str,
        as_of: datetime | None = None,
    ) -> tuple[
        FollowUpTask,
        ...
    ]:
        opportunity = (
            self.get(
                opportunity_id
            )
        )

        actor_id = _required(
            actor_id,
            "actor_id",
        )

        as_of = (
            _aware(
                as_of,
                "as_of",
            )
            if as_of
            is not None
            else _now()
        )

        decision = (
            self._decisions.get(
                opportunity_id
            )
        )

        existing_kinds = {
            task.kind
            for task
            in self.tasks(
                opportunity_id,
                include_completed=(
                    False
                ),
            )
        }

        planned = []

        def add(
            kind: FollowUpKind,
            description: str,
            delay: timedelta,
            role: str,
            source_ref: str | None = None,
        ) -> None:
            if kind in existing_kinds:
                return

            task = FollowUpTask(
                task_id=(
                    _new_id(
                        "oft"
                    )
                ),
                opportunity_id=(
                    opportunity_id
                ),
                kind=kind,
                description=(
                    description
                ),
                due_at=(
                    as_of
                    + delay
                ),
                assigned_role=(
                    role
                ),
                source_ref=(
                    source_ref
                ),
            )

            self._tasks[
                task.task_id
            ] = task

            planned.append(
                task
            )

            existing_kinds.add(
                kind
            )

        verified_contact = next(
            (
                contact
                for contact
                in opportunity.contacts
                if (
                    contact.reachable
                    and contact.verified
                )
            ),
            None,
        )

        if verified_contact is None:
            add(
                FollowUpKind
                .CONTACT_GC,
                (
                    "Resolve a verified contact "
                    "path for this opportunity."
                ),
                timedelta(
                    minutes=15
                ),
                "sales",
            )

        if (
            opportunity
            .due_at
            is None
        ):
            add(
                FollowUpKind
                .VERIFY_DUE_DATE,
                (
                    "Confirm authoritative bid "
                    "due date and timezone."
                ),
                timedelta(
                    minutes=15
                ),
                "estimating",
            )

        if (
            not opportunity
            .scope_summary
            or not opportunity
            .requested_trades
        ):
            add(
                FollowUpKind
                .CONFIRM_SCOPE,
                (
                    "Confirm buyer-side scope and "
                    "requested trades."
                ),
                timedelta(
                    minutes=30
                ),
                "estimating",
            )

        if (
            decision is not None
            and not decision
            .economics
            .expected_value_cents
        ):
            add(
                FollowUpKind
                .PRICING_REVIEW,
                (
                    "Resolve preliminary project "
                    "pricing and pursuit economics."
                ),
                timedelta(
                    hours=1
                ),
                "estimating",
            )

        if (
            decision is not None
            and decision.disposition
            in {
                DecisionDisposition
                .REVIEW,
                DecisionDisposition
                .BLOCKED,
            }
        ):
            add(
                FollowUpKind
                .EXECUTIVE_REVIEW,
                (
                    "Review unresolved bid/no-bid "
                    "decision factors."
                ),
                timedelta(
                    hours=2
                ),
                "executive",
            )

        if (
            decision is not None
            and decision.disposition
            == DecisionDisposition
            .BID
        ):
            add(
                FollowUpKind
                .REQUEST_PLANS,
                (
                    "Confirm current authoritative "
                    "plans/addenda/specifications."
                ),
                timedelta(
                    minutes=30
                ),
                "estimating",
            )

        self._audit(
            opportunity,
            action=(
                "opportunity.follow_through_planned"
            ),
            actor_id=(
                actor_id
            ),
            payload={
                "new_task_count":
                    len(
                        planned
                    ),
                "task_kinds":
                    [
                        task.kind.value
                        for task
                        in planned
                    ],
            },
        )

        return tuple(
            planned
        )

    def complete_task(
        self,
        *,
        task_id: str,
        actor_id: str,
    ) -> FollowUpTask:
        task = self._tasks.get(
            task_id
        )

        if task is None:
            raise KeyError(
                task_id
            )

        if task.completed:
            return task

        updated = replace(
            task,
            completed=True,
            completed_at=_now(),
            completed_by=(
                actor_id
            ),
        )

        self._tasks[
            task_id
        ] = updated

        opportunity = self.get(
            task.opportunity_id
        )

        self._audit(
            opportunity,
            action=(
                "opportunity.task_completed"
            ),
            actor_id=(
                actor_id
            ),
            payload={
                "task_id":
                    task_id,
                "kind":
                    task.kind.value,
            },
        )

        return updated

    def promote_to_bid(
        self,
        *,
        opportunity_id: str,
        actor_id: str,
        allow_review_override: bool = False,
    ) -> tuple[
        Any,
        Any,
    ]:
        opportunity = (
            self.get(
                opportunity_id
            )
        )

        decision = (
            self._decisions.get(
                opportunity_id
            )
        )

        if decision is None:
            raise OpportunityBlocked(
                "opportunity must be evaluated "
                "before promotion"
            )

        if (
            decision.disposition
            != DecisionDisposition.BID
            and not allow_review_override
        ):
            raise OpportunityBlocked(
                "only BID opportunities may "
                "be promoted automatically"
            )

        if decision.blockers:
            raise OpportunityBlocked(
                "decision blockers remain"
            )

        if (
            self.package_control
            is None
            or self.command_center
            is None
        ):
            raise OpportunityBlocked(
                "bid-package and command-center "
                "services are required"
            )

        if opportunity.promoted_package_id:
            package = (
                self.package_control
                .get_package(
                    opportunity
                    .promoted_package_id
                )
            )

            case = (
                self.command_center
                .create_case(
                    package_id=(
                        opportunity
                        .promoted_package_id
                    ),
                    actor_id=(
                        actor_id
                    ),
                )
            )

            return (
                package,
                case,
            )

        package = (
            self.package_control
            .create_package(
                tenant_id=(
                    opportunity
                    .tenant_id
                ),
                business_unit_id=(
                    opportunity
                    .business_unit_id
                ),
                opportunity_id=(
                    opportunity
                    .opportunity_id
                ),
                project_name=(
                    opportunity
                    .project_name
                ),
                city=(
                    opportunity.city
                ),
                source=(
                    _source_to_package(
                        opportunity
                        .source
                    )
                ),
                invited_by=(
                    opportunity
                    .gc_name
                ),
                gc_name=(
                    opportunity
                    .gc_name
                ),
                client_name=(
                    opportunity
                    .client_name
                ),
                due_at=(
                    opportunity
                    .due_at
                ),
                created_by=(
                    actor_id
                ),
            )
        )

        case = (
            self.command_center
            .create_case(
                package_id=(
                    package.package_id
                ),
                actor_id=(
                    actor_id
                ),
            )
        )

        updated = replace(
            opportunity,
            state=(
                OpportunityState
                .PROMOTED
            ),
            promoted_package_id=(
                package.package_id
            ),
            promoted_case_id=(
                case.case_id
            ),
            updated_at=_now(),
            version=(
                opportunity.version
                + 1
            ),
        )

        self._opportunities[
            opportunity_id
        ] = updated

        self._audit(
            updated,
            action=(
                "opportunity.promoted_to_bid"
            ),
            actor_id=(
                actor_id
            ),
            payload={
                "package_id":
                    package
                    .package_id,
                "case_id":
                    case.case_id,
            },
        )

        return (
            package,
            case,
        )

    def portfolio(
        self,
    ) -> tuple[
        OpportunityPortfolioItem,
        ...
    ]:
        result = []

        for opportunity in (
            self._opportunities
            .values()
        ):
            decision = (
                self._decisions.get(
                    opportunity
                    .opportunity_id
                )
            )

            open_tasks = len(
                self.tasks(
                    opportunity
                    .opportunity_id
                )
            )

            result.append(
                OpportunityPortfolioItem(
                    opportunity_id=(
                        opportunity
                        .opportunity_id
                    ),
                    project_name=(
                        opportunity
                        .project_name
                    ),
                    gc_name=(
                        opportunity
                        .gc_name
                    ),
                    city=(
                        opportunity.city
                    ),
                    due_at=(
                        opportunity
                        .due_at
                    ),
                    state=(
                        opportunity.state
                    ),
                    disposition=(
                        decision.disposition
                        if decision
                        else None
                    ),
                    score=(
                        decision.score
                        if decision
                        else None
                    ),
                    expected_value_cents=(
                        decision
                        .economics
                        .expected_value_cents
                        if decision
                        else None
                    ),
                    open_task_count=(
                        open_tasks
                    ),
                    promoted_package_id=(
                        opportunity
                        .promoted_package_id
                    ),
                    promoted_case_id=(
                        opportunity
                        .promoted_case_id
                    ),
                )
            )

        return tuple(
            sorted(
                result,
                key=lambda item:
                    (
                        item.due_at
                        is None,
                        item.due_at
                        or datetime.max.replace(
                            tzinfo=(
                                timezone.utc
                            )
                        ),
                        -(
                            item.score
                            or 0
                        ),
                        item.project_name,
                    ),
            )
        )
