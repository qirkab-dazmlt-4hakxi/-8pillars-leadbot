from __future__ import annotations

import hashlib
import json
import math
import uuid

from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from enum import Enum, IntEnum
from typing import Any, Iterable, Sequence

from leadbot_v2.goat.persistence.durable import (
    DurableStore,
)


# ============================================================
# ERRORS
# ============================================================


class ExecutionError(RuntimeError):
    pass


class ProjectNotFound(ExecutionError):
    pass


class InvalidProjectState(ExecutionError):
    pass


class UnknownCostCode(ExecutionError):
    pass


class DuplicateMutationConflict(ExecutionError):
    pass


class CommitmentError(ExecutionError):
    pass


class ChangeEventError(ExecutionError):
    pass


class AuditIntegrityError(ExecutionError):
    pass


class FinancialValidationError(ExecutionError):
    pass


# ============================================================
# ENUMS
# ============================================================


class ExecutionStatus(str, Enum):
    AWARDED = "awarded"
    ACTIVE = "active"
    SUBSTANTIAL_COMPLETION = "substantial_completion"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class CostCategory(str, Enum):
    LABOR = "labor"
    MATERIAL = "material"
    EQUIPMENT = "equipment"
    SUBCONTRACT = "subcontract"
    FREIGHT = "freight"
    OTHER = "other"


class CommitmentType(str, Enum):
    PURCHASE_ORDER = "purchase_order"
    SUBCONTRACT = "subcontract"
    RENTAL = "rental"
    SERVICE = "service"
    OTHER = "other"


class CommitmentStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class ChangeEventStatus(str, Enum):
    IDENTIFIED = "identified"
    PRICING = "pricing"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    VOID = "void"


class MaterialReleaseStatus(str, Enum):
    PLANNED = "planned"
    RELEASED = "released"
    ORDERED = "ordered"
    PARTIAL = "partial"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class InterventionSeverity(IntEnum):
    INFO = 10
    REVIEW = 20
    HIGH = 30
    CRITICAL = 40


# ============================================================
# UTILITY
# ============================================================


def _now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def _id(prefix: str) -> str:
    return (
        prefix
        + "_"
        + uuid.uuid4().hex
    )


def _required(
    value: Any,
    field_name: str,
) -> str:
    result = str(
        value
        or ""
    ).strip()

    if not result:
        raise ValueError(
            f"{field_name} is required"
        )

    return result


def _money(
    value: int,
    field_name: str,
    *,
    allow_zero: bool = True,
) -> int:
    if isinstance(
        value,
        bool,
    ):
        raise FinancialValidationError(
            f"{field_name} must be integer cents"
        )

    if not isinstance(
        value,
        int,
    ):
        raise FinancialValidationError(
            f"{field_name} must be integer cents"
        )

    if (
        value < 0
        or (
            not allow_zero
            and value == 0
        )
    ):
        raise FinancialValidationError(
            f"{field_name} invalid"
        )

    return value


def _percent(
    value: float,
    field_name: str,
) -> float:
    value = float(
        value
    )

    if (
        not math.isfinite(
            value
        )
        or value < 0.0
        or value > 1.0
    ):
        raise ValueError(
            f"{field_name} must be between 0 and 1"
        )

    return value


def _json(
    value: Any,
) -> str:
    def normalize(item: Any) -> Any:
        if isinstance(
            item,
            Enum,
        ):
            return item.value

        if isinstance(
            item,
            (datetime, date),
        ):
            return item.isoformat()

        if isinstance(
            item,
            dict,
        ):
            return {
                str(k):
                    normalize(v)
                for k, v
                in sorted(
                    item.items()
                )
            }

        if isinstance(
            item,
            (
                list,
                tuple,
                set,
                frozenset,
            ),
        ):
            return [
                normalize(v)
                for v
                in item
            ]

        if hasattr(
            item,
            "__dict__",
        ):
            return normalize(
                vars(item)
            )

        return item

    return json.dumps(
        normalize(
            value
        ),
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=True,
        default=str,
    )


def _hash(
    value: Any,
) -> str:
    return hashlib.sha256(
        _json(
            value
        ).encode(
            "utf-8"
        )
    ).hexdigest()


def _safe_ratio(
    numerator: float,
    denominator: float,
) -> float | None:
    if abs(
        denominator
    ) < 1e-12:
        return None

    return (
        numerator
        / denominator
    )


# ============================================================
# AWARD / BUDGET
# ============================================================


@dataclass(frozen=True)
class AwardBudgetLine:
    cost_code: str
    name: str
    category: CostCategory
    budget_cents: int


@dataclass(frozen=True)
class AwardHandoff:
    tenant_id: str
    project_id: str

    estimate_id: str
    proposal_hash: str

    project_name: str

    original_contract_value_cents: int

    budget_lines: tuple[
        AwardBudgetLine,
        ...
    ]

    awarded_at: datetime


@dataclass
class BudgetLine:
    cost_code: str
    name: str
    category: CostCategory

    original_budget_cents: int
    approved_change_budget_cents: int = 0
    transferred_in_cents: int = 0
    transferred_out_cents: int = 0

    @property
    def current_budget_cents(
        self,
    ) -> int:
        return (
            self.original_budget_cents
            + self.approved_change_budget_cents
            + self.transferred_in_cents
            - self.transferred_out_cents
        )


# ============================================================
# COMMITMENTS
# ============================================================


@dataclass
class Commitment:
    commitment_id: str

    cost_code: str

    commitment_type: CommitmentType

    vendor_name: str

    description: str

    original_amount_cents: int

    approved_changes_cents: int = 0

    invoiced_cents: int = 0

    paid_cents: int = 0

    status: CommitmentStatus = (
        CommitmentStatus.DRAFT
    )

    created_at: datetime = field(
        default_factory=_now
    )

    approved_at: datetime | None = None

    @property
    def current_amount_cents(
        self,
    ) -> int:
        return (
            self.original_amount_cents
            + self.approved_changes_cents
        )

    @property
    def remaining_cents(
        self,
    ) -> int:
        return max(
            0,
            (
                self.current_amount_cents
                - self.invoiced_cents
            ),
        )


# ============================================================
# ACTUAL COST
# ============================================================


@dataclass(frozen=True)
class ActualCost:
    actual_id: str

    cost_code: str

    category: CostCategory

    amount_cents: int

    incurred_on: date

    description: str

    source_reference: str

    commitment_id: str | None

    created_at: datetime


# ============================================================
# PROGRESS / DAILY FIELD
# ============================================================


@dataclass(frozen=True)
class ProgressPoint:
    cost_code: str

    as_of: date

    percent_complete: float


@dataclass(frozen=True)
class PlannedProgressPoint:
    cost_code: str

    as_of: date

    planned_percent_complete: float


@dataclass(frozen=True)
class QuantityProduction:
    cost_code: str

    description: str

    quantity: float

    unit: str

    labor_hours: float

    planned_labor_hours_per_unit: (
        float
        | None
    ) = None


@dataclass(frozen=True)
class DailyLog:
    log_id: str

    project_id: str

    work_date: date

    submitted_by: str

    labor_hours: float

    equipment_hours: float

    production: tuple[
        QuantityProduction,
        ...
    ]

    constraints: tuple[
        str,
        ...
    ]

    safety_notes: tuple[
        str,
        ...
    ]

    weather_summary: str | None

    created_at: datetime


@dataclass(frozen=True)
class ProductivityAssessment:
    cost_code: str

    quantity: float

    actual_labor_hours: float

    earned_labor_hours: (
        float
        | None
    )

    efficiency_ratio: (
        float
        | None
    )


# ============================================================
# MATERIALS / PROCUREMENT
# ============================================================


@dataclass
class MaterialRelease:
    release_id: str

    cost_code: str

    description: str

    quantity: float

    unit: str

    required_on_site: date

    status: MaterialReleaseStatus = (
        MaterialReleaseStatus.PLANNED
    )

    committed_cents: int = 0

    released_on: date | None = None

    ordered_on: date | None = None

    delivered_on: date | None = None

    delivered_quantity: float = 0.0

    vendor_name: str | None = None


# ============================================================
# CHANGE EVENTS
# ============================================================


@dataclass
class ChangeEvent:
    change_id: str

    cost_code: str

    description: str

    status: ChangeEventStatus

    estimated_cost_exposure_cents: int

    requested_price_cents: int

    approved_cost_cents: int = 0

    approved_price_cents: int = 0

    schedule_impact_days: int = 0

    executed_at_risk: bool = False

    source_reference: str | None = None

    created_at: datetime = field(
        default_factory=_now
    )

    approved_at: datetime | None = None


# ============================================================
# BILLING / CASH
# ============================================================


@dataclass(frozen=True)
class BillingRecord:
    billing_id: str

    period_end: date

    gross_billed_cents: int

    retainage_held_cents: int

    collected_cents: int

    created_at: datetime


# ============================================================
# AUDIT CHAIN
# ============================================================


@dataclass(frozen=True)
class ExecutionAuditEvent:
    sequence: int

    event_id: str

    event_type: str

    actor_id: str

    occurred_at: datetime

    payload: dict[
        str,
        Any,
    ]

    payload_hash: str

    previous_hash: str

    event_hash: str


def _event_hash(
    *,
    sequence: int,
    event_id: str,
    event_type: str,
    actor_id: str,
    occurred_at: datetime,
    payload_hash: str,
    previous_hash: str,
) -> str:
    return _hash(
        {
            "sequence":
                sequence,
            "event_id":
                event_id,
            "event_type":
                event_type,
            "actor_id":
                actor_id,
            "occurred_at":
                occurred_at,
            "payload_hash":
                payload_hash,
            "previous_hash":
                previous_hash,
        }
    )


# ============================================================
# FORECAST
# ============================================================


@dataclass(frozen=True)
class CostCodeForecast:
    cost_code: str

    budget_cents: int

    actual_cost_cents: int

    open_commitment_cents: int

    percent_complete: float

    planned_percent_complete: float

    earned_value_cents: int

    planned_value_cents: int

    estimate_at_completion_cents: int

    estimate_to_complete_cents: int

    variance_at_completion_cents: int

    cpi: float | None

    spi: float | None


@dataclass(frozen=True)
class ProjectForecast:
    project_id: str

    as_of: date

    original_contract_value_cents: int

    approved_change_price_cents: int

    current_contract_value_cents: int

    original_budget_cents: int

    current_budget_cents: int

    actual_cost_cents: int

    open_commitment_cents: int

    estimate_to_complete_cents: int

    estimate_at_completion_cents: int

    forecast_gross_profit_cents: int

    forecast_margin_percent: float

    original_margin_percent: float

    margin_erosion_basis_points: int

    earned_value_cents: int

    planned_value_cents: int

    cpi: float | None

    spi: float | None

    overall_percent_complete: float

    planned_percent_complete: float

    unresolved_change_exposure_cents: int

    at_risk_change_exposure_cents: int

    gross_billed_cents: int

    retainage_held_cents: int

    collected_cents: int

    accounts_receivable_cents: int

    earned_revenue_cents: int

    overbilling_cents: int

    underbilling_cents: int

    cost_codes: tuple[
        CostCodeForecast,
        ...
    ]


# ============================================================
# EXECUTIVE INTERVENTION
# ============================================================


@dataclass(frozen=True)
class ExecutiveIntervention:
    intervention_id: str

    severity: InterventionSeverity

    code: str

    title: str

    evidence: str

    recommended_action: str


@dataclass(frozen=True)
class ProjectHealth:
    score: int

    interventions: tuple[
        ExecutiveIntervention,
        ...
    ]

    critical_count: int

    high_count: int

    review_count: int


# ============================================================
# PROJECT STATE
# ============================================================


@dataclass
class ProjectExecutionState:
    tenant_id: str
    project_id: str

    project_name: str

    estimate_id: str
    proposal_hash: str

    awarded_at: datetime

    status: ExecutionStatus

    original_contract_value_cents: int

    budget_lines: dict[
        str,
        BudgetLine,
    ]

    commitments: dict[
        str,
        Commitment,
    ] = field(
        default_factory=dict
    )

    actual_costs: list[
        ActualCost
    ] = field(
        default_factory=list
    )

    progress: list[
        ProgressPoint
    ] = field(
        default_factory=list
    )

    planned_progress: list[
        PlannedProgressPoint
    ] = field(
        default_factory=list
    )

    daily_logs: list[
        DailyLog
    ] = field(
        default_factory=list
    )

    material_releases: dict[
        str,
        MaterialRelease,
    ] = field(
        default_factory=dict
    )

    changes: dict[
        str,
        ChangeEvent,
    ] = field(
        default_factory=dict
    )

    billing: list[
        BillingRecord
    ] = field(
        default_factory=list
    )

    audit: list[
        ExecutionAuditEvent
    ] = field(
        default_factory=list
    )

    idempotency: dict[
        tuple[
            str,
            str,
        ],
        tuple[
            str,
            Any,
        ],
    ] = field(
        default_factory=dict
    )

    manual_etc: dict[
        str,
        int,
    ] = field(
        default_factory=dict
    )


# ============================================================
# SERVICE
# ============================================================


class AwardToExecutionService:
    def __init__(
        self,
    ) -> None:
        self._projects: dict[
            tuple[
                str,
                str,
            ],
            ProjectExecutionState,
        ] = {}

    def _key(
        self,
        tenant_id: str,
        project_id: str,
    ) -> tuple[
        str,
        str,
    ]:
        return (
            tenant_id,
            project_id,
        )

    def project(
        self,
        *,
        tenant_id: str,
        project_id: str,
    ) -> ProjectExecutionState:
        try:
            return self._projects[
                self._key(
                    tenant_id,
                    project_id,
                )
            ]

        except KeyError as exc:
            raise ProjectNotFound(
                project_id
            ) from exc

    @staticmethod
    def _require_mutable(
        project: ProjectExecutionState,
    ) -> None:
        if (
            project.status
            in {
                ExecutionStatus.CLOSED,
                ExecutionStatus.CANCELLED,
            }
        ):
            raise InvalidProjectState(
                (
                    "project is not mutable in "
                    + project.status.value
                )
            )

    @staticmethod
    def _cost_code(
        project: ProjectExecutionState,
        cost_code: str,
    ) -> BudgetLine:
        try:
            return project.budget_lines[
                cost_code
            ]

        except KeyError as exc:
            raise UnknownCostCode(
                cost_code
            ) from exc

    @staticmethod
    def _idem(
        *,
        project: ProjectExecutionState,
        action: str,
        idempotency_key: str | None,
        request: dict[str, Any],
    ) -> Any | None:
        if not idempotency_key:
            return None

        key = (
            action,
            idempotency_key,
        )

        request_hash = _hash(
            request
        )

        existing = (
            project.idempotency.get(
                key
            )
        )

        if existing is None:
            return None

        previous_hash, result = (
            existing
        )

        if (
            previous_hash
            != request_hash
        ):
            raise DuplicateMutationConflict(
                (
                    "idempotency key reused "
                    "with different request"
                )
            )

        return result

    @staticmethod
    def _save_idem(
        *,
        project: ProjectExecutionState,
        action: str,
        idempotency_key: str | None,
        request: dict[str, Any],
        result: Any,
    ) -> None:
        if not idempotency_key:
            return

        project.idempotency[
            (
                action,
                idempotency_key,
            )
        ] = (
            _hash(
                request
            ),
            result,
        )

    @staticmethod
    def _audit(
        project: ProjectExecutionState,
        *,
        event_type: str,
        actor_id: str,
        payload: dict[str, Any],
    ) -> ExecutionAuditEvent:
        sequence = (
            len(
                project.audit
            )
            + 1
        )

        event_id = _id(
            "exec_evt"
        )

        occurred_at = _now()

        payload_hash = _hash(
            payload
        )

        previous_hash = (
            project.audit[
                -1
            ].event_hash
            if project.audit
            else (
                "0" * 64
            )
        )

        event_hash = _event_hash(
            sequence=sequence,
            event_id=event_id,
            event_type=event_type,
            actor_id=actor_id,
            occurred_at=occurred_at,
            payload_hash=payload_hash,
            previous_hash=previous_hash,
        )

        event = (
            ExecutionAuditEvent(
                sequence=sequence,
                event_id=event_id,
                event_type=event_type,
                actor_id=actor_id,
                occurred_at=occurred_at,
                payload=dict(
                    payload
                ),
                payload_hash=payload_hash,
                previous_hash=previous_hash,
                event_hash=event_hash,
            )
        )

        project.audit.append(
            event
        )

        return event

    def create_from_award(
        self,
        *,
        handoff: AwardHandoff,
        actor_id: str,
    ) -> ProjectExecutionState:
        tenant_id = _required(
            handoff.tenant_id,
            "tenant_id",
        )

        project_id = _required(
            handoff.project_id,
            "project_id",
        )

        _required(
            handoff.estimate_id,
            "estimate_id",
        )

        _required(
            handoff.proposal_hash,
            "proposal_hash",
        )

        _required(
            handoff.project_name,
            "project_name",
        )

        _money(
            handoff
            .original_contract_value_cents,
            "original_contract_value_cents",
            allow_zero=False,
        )

        if not handoff.budget_lines:
            raise FinancialValidationError(
                "award requires budget lines"
            )

        key = self._key(
            tenant_id,
            project_id,
        )

        if key in self._projects:
            raise ExecutionError(
                "project already exists"
            )

        budget_lines = {}

        for item in (
            handoff.budget_lines
        ):
            code = _required(
                item.cost_code,
                "cost_code",
            )

            if code in budget_lines:
                raise FinancialValidationError(
                    (
                        "duplicate cost code: "
                        + code
                    )
                )

            amount = _money(
                item.budget_cents,
                "budget_cents",
            )

            budget_lines[
                code
            ] = BudgetLine(
                cost_code=code,
                name=_required(
                    item.name,
                    "budget name",
                ),
                category=(
                    item.category
                ),
                original_budget_cents=(
                    amount
                ),
            )

        project = (
            ProjectExecutionState(
                tenant_id=tenant_id,
                project_id=project_id,
                project_name=(
                    handoff
                    .project_name
                ),
                estimate_id=(
                    handoff
                    .estimate_id
                ),
                proposal_hash=(
                    handoff
                    .proposal_hash
                ),
                awarded_at=(
                    handoff.awarded_at
                ),
                status=(
                    ExecutionStatus
                    .AWARDED
                ),
                original_contract_value_cents=(
                    handoff
                    .original_contract_value_cents
                ),
                budget_lines=(
                    budget_lines
                ),
            )
        )

        self._projects[
            key
        ] = project

        self._audit(
            project,
            event_type=(
                "project.award_handoff_created"
            ),
            actor_id=actor_id,
            payload={
                "estimate_id":
                    handoff.estimate_id,
                "proposal_hash":
                    handoff.proposal_hash,
                "contract_value_cents":
                    handoff
                    .original_contract_value_cents,
                "budget_total_cents":
                    sum(
                        item
                        .budget_cents
                        for item
                        in handoff
                        .budget_lines
                    ),
            },
        )

        return project

    def activate(
        self,
        *,
        tenant_id: str,
        project_id: str,
        actor_id: str,
    ) -> ProjectExecutionState:
        project = self.project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        if (
            project.status
            != ExecutionStatus
            .AWARDED
        ):
            raise InvalidProjectState(
                "project must be awarded"
            )

        project.status = (
            ExecutionStatus.ACTIVE
        )

        self._audit(
            project,
            event_type=(
                "project.activated"
            ),
            actor_id=actor_id,
            payload={},
        )

        return project

    def transfer_budget(
        self,
        *,
        tenant_id: str,
        project_id: str,
        from_cost_code: str,
        to_cost_code: str,
        amount_cents: int,
        actor_id: str,
        idempotency_key: str | None = None,
    ) -> None:
        project = self.project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._require_mutable(
            project
        )

        amount_cents = _money(
            amount_cents,
            "amount_cents",
            allow_zero=False,
        )

        request = {
            "from":
                from_cost_code,
            "to":
                to_cost_code,
            "amount":
                amount_cents,
        }

        existing = self._idem(
            project=project,
            action="budget_transfer",
            idempotency_key=(
                idempotency_key
            ),
            request=request,
        )

        if existing is not None:
            return

        source = self._cost_code(
            project,
            from_cost_code,
        )

        target = self._cost_code(
            project,
            to_cost_code,
        )

        if (
            source.current_budget_cents
            < amount_cents
        ):
            raise FinancialValidationError(
                (
                    "budget transfer exceeds "
                    "source current budget"
                )
            )

        source.transferred_out_cents += (
            amount_cents
        )

        target.transferred_in_cents += (
            amount_cents
        )

        self._audit(
            project,
            event_type=(
                "budget.transferred"
            ),
            actor_id=actor_id,
            payload=request,
        )

        self._save_idem(
            project=project,
            action="budget_transfer",
            idempotency_key=(
                idempotency_key
            ),
            request=request,
            result=True,
        )

    # ========================================================
    # COMMITMENTS
    # ========================================================

    def create_commitment(
        self,
        *,
        tenant_id: str,
        project_id: str,
        cost_code: str,
        commitment_type: CommitmentType,
        vendor_name: str,
        description: str,
        amount_cents: int,
        actor_id: str,
        idempotency_key: str | None = None,
    ) -> Commitment:
        project = self.project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._require_mutable(
            project
        )

        self._cost_code(
            project,
            cost_code,
        )

        amount_cents = _money(
            amount_cents,
            "amount_cents",
            allow_zero=False,
        )

        request = {
            "cost_code":
                cost_code,
            "type":
                commitment_type.value,
            "vendor":
                vendor_name,
            "description":
                description,
            "amount_cents":
                amount_cents,
        }

        existing = self._idem(
            project=project,
            action="create_commitment",
            idempotency_key=(
                idempotency_key
            ),
            request=request,
        )

        if existing is not None:
            return existing

        commitment = Commitment(
            commitment_id=_id(
                "commit"
            ),
            cost_code=cost_code,
            commitment_type=(
                commitment_type
            ),
            vendor_name=_required(
                vendor_name,
                "vendor_name",
            ),
            description=_required(
                description,
                "description",
            ),
            original_amount_cents=(
                amount_cents
            ),
        )

        project.commitments[
            commitment.commitment_id
        ] = commitment

        self._audit(
            project,
            event_type=(
                "commitment.created"
            ),
            actor_id=actor_id,
            payload={
                "commitment_id":
                    commitment
                    .commitment_id,
                **request,
            },
        )

        self._save_idem(
            project=project,
            action="create_commitment",
            idempotency_key=(
                idempotency_key
            ),
            request=request,
            result=commitment,
        )

        return commitment

    def approve_commitment(
        self,
        *,
        tenant_id: str,
        project_id: str,
        commitment_id: str,
        actor_id: str,
    ) -> Commitment:
        project = self.project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._require_mutable(
            project
        )

        try:
            commitment = (
                project.commitments[
                    commitment_id
                ]
            )

        except KeyError as exc:
            raise CommitmentError(
                commitment_id
            ) from exc

        if (
            commitment.status
            != CommitmentStatus.DRAFT
        ):
            raise CommitmentError(
                (
                    "commitment must be draft"
                )
            )

        commitment.status = (
            CommitmentStatus.APPROVED
        )

        commitment.approved_at = (
            _now()
        )

        self._audit(
            project,
            event_type=(
                "commitment.approved"
            ),
            actor_id=actor_id,
            payload={
                "commitment_id":
                    commitment_id,
                "amount_cents":
                    commitment
                    .current_amount_cents,
            },
        )

        return commitment

    def add_commitment_change(
        self,
        *,
        tenant_id: str,
        project_id: str,
        commitment_id: str,
        amount_cents: int,
        actor_id: str,
        reason: str,
    ) -> Commitment:
        project = self.project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._require_mutable(
            project
        )

        amount_cents = _money(
            amount_cents,
            "amount_cents",
            allow_zero=False,
        )

        try:
            commitment = (
                project.commitments[
                    commitment_id
                ]
            )

        except KeyError as exc:
            raise CommitmentError(
                commitment_id
            ) from exc

        if (
            commitment.status
            != CommitmentStatus.APPROVED
        ):
            raise CommitmentError(
                (
                    "only approved commitments "
                    "may receive changes"
                )
            )

        commitment.approved_changes_cents += (
            amount_cents
        )

        self._audit(
            project,
            event_type=(
                "commitment.change_approved"
            ),
            actor_id=actor_id,
            payload={
                "commitment_id":
                    commitment_id,
                "amount_cents":
                    amount_cents,
                "reason":
                    _required(
                        reason,
                        "reason",
                    ),
            },
        )

        return commitment

    # ========================================================
    # ACTUAL COST
    # ========================================================

    def record_actual_cost(
        self,
        *,
        tenant_id: str,
        project_id: str,
        cost_code: str,
        category: CostCategory,
        amount_cents: int,
        incurred_on: date,
        description: str,
        source_reference: str,
        actor_id: str,
        commitment_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> ActualCost:
        project = self.project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._require_mutable(
            project
        )

        self._cost_code(
            project,
            cost_code,
        )

        amount_cents = _money(
            amount_cents,
            "amount_cents",
            allow_zero=False,
        )

        request = {
            "cost_code":
                cost_code,
            "category":
                category.value,
            "amount":
                amount_cents,
            "date":
                incurred_on,
            "description":
                description,
            "source":
                source_reference,
            "commitment_id":
                commitment_id,
        }

        existing = self._idem(
            project=project,
            action="actual_cost",
            idempotency_key=(
                idempotency_key
            ),
            request=request,
        )

        if existing is not None:
            return existing

        if commitment_id:
            try:
                commitment = (
                    project.commitments[
                        commitment_id
                    ]
                )

            except KeyError as exc:
                raise CommitmentError(
                    commitment_id
                ) from exc

            if (
                commitment.cost_code
                != cost_code
            ):
                raise CommitmentError(
                    (
                        "actual cost code does not "
                        "match commitment"
                    )
                )

            commitment.invoiced_cents += (
                amount_cents
            )

        actual = ActualCost(
            actual_id=_id(
                "actual"
            ),
            cost_code=cost_code,
            category=category,
            amount_cents=(
                amount_cents
            ),
            incurred_on=(
                incurred_on
            ),
            description=_required(
                description,
                "description",
            ),
            source_reference=(
                _required(
                    source_reference,
                    "source_reference",
                )
            ),
            commitment_id=(
                commitment_id
            ),
            created_at=_now(),
        )

        project.actual_costs.append(
            actual
        )

        self._audit(
            project,
            event_type=(
                "cost.actual_recorded"
            ),
            actor_id=actor_id,
            payload={
                "actual_id":
                    actual.actual_id,
                **request,
            },
        )

        self._save_idem(
            project=project,
            action="actual_cost",
            idempotency_key=(
                idempotency_key
            ),
            request=request,
            result=actual,
        )

        return actual

    # ========================================================
    # PROGRESS / FIELD
    # ========================================================

    def set_progress(
        self,
        *,
        tenant_id: str,
        project_id: str,
        cost_code: str,
        as_of: date,
        percent_complete: float,
        actor_id: str,
    ) -> ProgressPoint:
        project = self.project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._require_mutable(
            project
        )

        self._cost_code(
            project,
            cost_code,
        )

        percent_complete = _percent(
            percent_complete,
            "percent_complete",
        )

        previous = [
            item
            for item
            in project.progress
            if (
                item.cost_code
                == cost_code
                and item.as_of
                <= as_of
            )
        ]

        if previous:
            latest = max(
                previous,
                key=lambda item:
                    item.as_of,
            )

            if (
                percent_complete
                < latest.percent_complete
            ):
                raise ExecutionError(
                    (
                        "progress cannot move "
                        "backward"
                    )
                )

        point = ProgressPoint(
            cost_code=cost_code,
            as_of=as_of,
            percent_complete=(
                percent_complete
            ),
        )

        project.progress.append(
            point
        )

        self._audit(
            project,
            event_type=(
                "production.progress_updated"
            ),
            actor_id=actor_id,
            payload={
                "cost_code":
                    cost_code,
                "as_of":
                    as_of,
                "percent_complete":
                    percent_complete,
            },
        )

        return point

    def set_planned_progress(
        self,
        *,
        tenant_id: str,
        project_id: str,
        cost_code: str,
        as_of: date,
        planned_percent_complete: float,
        actor_id: str,
    ) -> PlannedProgressPoint:
        project = self.project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._require_mutable(
            project
        )

        self._cost_code(
            project,
            cost_code,
        )

        planned_percent_complete = (
            _percent(
                planned_percent_complete,
                "planned_percent_complete",
            )
        )

        point = (
            PlannedProgressPoint(
                cost_code=cost_code,
                as_of=as_of,
                planned_percent_complete=(
                    planned_percent_complete
                ),
            )
        )

        project.planned_progress.append(
            point
        )

        self._audit(
            project,
            event_type=(
                "schedule.planned_progress_updated"
            ),
            actor_id=actor_id,
            payload={
                "cost_code":
                    cost_code,
                "as_of":
                    as_of,
                "planned_percent":
                    planned_percent_complete,
            },
        )

        return point

    def record_daily_log(
        self,
        *,
        tenant_id: str,
        project_id: str,
        work_date: date,
        submitted_by: str,
        labor_hours: float,
        equipment_hours: float,
        production: Sequence[
            QuantityProduction
        ] = (),
        constraints: Sequence[
            str
        ] = (),
        safety_notes: Sequence[
            str
        ] = (),
        weather_summary: str | None = None,
        actor_id: str,
        idempotency_key: str | None = None,
    ) -> DailyLog:
        project = self.project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._require_mutable(
            project
        )

        labor_hours = float(
            labor_hours
        )

        equipment_hours = float(
            equipment_hours
        )

        if (
            not math.isfinite(
                labor_hours
            )
            or labor_hours < 0
        ):
            raise ValueError(
                "labor_hours invalid"
            )

        if (
            not math.isfinite(
                equipment_hours
            )
            or equipment_hours < 0
        ):
            raise ValueError(
                "equipment_hours invalid"
            )

        for item in production:
            self._cost_code(
                project,
                item.cost_code,
            )

            if (
                item.quantity < 0
                or item.labor_hours < 0
            ):
                raise ValueError(
                    "production values invalid"
                )

        request = {
            "work_date":
                work_date,
            "submitted_by":
                submitted_by,
            "labor_hours":
                labor_hours,
            "equipment_hours":
                equipment_hours,
            "production":
                tuple(
                    production
                ),
            "constraints":
                tuple(
                    constraints
                ),
            "safety_notes":
                tuple(
                    safety_notes
                ),
            "weather":
                weather_summary,
        }

        existing = self._idem(
            project=project,
            action="daily_log",
            idempotency_key=(
                idempotency_key
            ),
            request=request,
        )

        if existing is not None:
            return existing

        log = DailyLog(
            log_id=_id(
                "log"
            ),
            project_id=project_id,
            work_date=work_date,
            submitted_by=(
                _required(
                    submitted_by,
                    "submitted_by",
                )
            ),
            labor_hours=labor_hours,
            equipment_hours=(
                equipment_hours
            ),
            production=tuple(
                production
            ),
            constraints=tuple(
                str(item)
                for item
                in constraints
                if str(item).strip()
            ),
            safety_notes=tuple(
                str(item)
                for item
                in safety_notes
                if str(item).strip()
            ),
            weather_summary=(
                weather_summary
            ),
            created_at=_now(),
        )

        project.daily_logs.append(
            log
        )

        self._audit(
            project,
            event_type=(
                "field.daily_log_recorded"
            ),
            actor_id=actor_id,
            payload={
                "log_id":
                    log.log_id,
                **request,
            },
        )

        self._save_idem(
            project=project,
            action="daily_log",
            idempotency_key=(
                idempotency_key
            ),
            request=request,
            result=log,
        )

        return log

    def productivity(
        self,
        *,
        tenant_id: str,
        project_id: str,
        cost_code: str,
    ) -> ProductivityAssessment:
        project = self.project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._cost_code(
            project,
            cost_code,
        )

        quantity = 0.0

        actual_hours = 0.0

        earned_hours = 0.0

        has_plan = False

        for log in (
            project.daily_logs
        ):
            for item in (
                log.production
            ):
                if (
                    item.cost_code
                    != cost_code
                ):
                    continue

                quantity += (
                    item.quantity
                )

                actual_hours += (
                    item.labor_hours
                )

                if (
                    item
                    .planned_labor_hours_per_unit
                    is not None
                ):
                    has_plan = True

                    earned_hours += (
                        item.quantity
                        * item
                        .planned_labor_hours_per_unit
                    )

        efficiency = (
            _safe_ratio(
                earned_hours,
                actual_hours,
            )
            if has_plan
            else None
        )

        return (
            ProductivityAssessment(
                cost_code=cost_code,
                quantity=quantity,
                actual_labor_hours=(
                    actual_hours
                ),
                earned_labor_hours=(
                    earned_hours
                    if has_plan
                    else None
                ),
                efficiency_ratio=(
                    efficiency
                ),
            )
        )

    # ========================================================
    # MATERIAL RELEASE
    # ========================================================

    def create_material_release(
        self,
        *,
        tenant_id: str,
        project_id: str,
        cost_code: str,
        description: str,
        quantity: float,
        unit: str,
        required_on_site: date,
        committed_cents: int,
        actor_id: str,
    ) -> MaterialRelease:
        project = self.project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._require_mutable(
            project
        )

        self._cost_code(
            project,
            cost_code,
        )

        quantity = float(
            quantity
        )

        if (
            not math.isfinite(
                quantity
            )
            or quantity <= 0
        ):
            raise ValueError(
                "quantity must be positive"
            )

        release = (
            MaterialRelease(
                release_id=_id(
                    "release"
                ),
                cost_code=cost_code,
                description=_required(
                    description,
                    "description",
                ),
                quantity=quantity,
                unit=_required(
                    unit,
                    "unit",
                ),
                required_on_site=(
                    required_on_site
                ),
                committed_cents=(
                    _money(
                        committed_cents,
                        "committed_cents",
                    )
                ),
            )
        )

        project.material_releases[
            release.release_id
        ] = release

        self._audit(
            project,
            event_type=(
                "material.release_created"
            ),
            actor_id=actor_id,
            payload={
                "release_id":
                    release.release_id,
                "cost_code":
                    cost_code,
                "description":
                    description,
                "quantity":
                    quantity,
                "unit":
                    unit,
                "required_on_site":
                    required_on_site,
            },
        )

        return release

    def mark_material_ordered(
        self,
        *,
        tenant_id: str,
        project_id: str,
        release_id: str,
        ordered_on: date,
        vendor_name: str,
        actor_id: str,
    ) -> MaterialRelease:
        project = self.project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        try:
            release = (
                project.material_releases[
                    release_id
                ]
            )

        except KeyError as exc:
            raise ExecutionError(
                release_id
            ) from exc

        if (
            release.status
            in {
                MaterialReleaseStatus
                .DELIVERED,
                MaterialReleaseStatus
                .CANCELLED,
            }
        ):
            raise ExecutionError(
                "release cannot be ordered"
            )

        release.status = (
            MaterialReleaseStatus
            .ORDERED
        )

        release.ordered_on = (
            ordered_on
        )

        release.vendor_name = (
            _required(
                vendor_name,
                "vendor_name",
            )
        )

        self._audit(
            project,
            event_type=(
                "material.ordered"
            ),
            actor_id=actor_id,
            payload={
                "release_id":
                    release_id,
                "ordered_on":
                    ordered_on,
                "vendor":
                    vendor_name,
            },
        )

        return release

    def mark_material_delivered(
        self,
        *,
        tenant_id: str,
        project_id: str,
        release_id: str,
        delivered_on: date,
        delivered_quantity: float,
        actor_id: str,
    ) -> MaterialRelease:
        project = self.project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        try:
            release = (
                project.material_releases[
                    release_id
                ]
            )

        except KeyError as exc:
            raise ExecutionError(
                release_id
            ) from exc

        delivered_quantity = float(
            delivered_quantity
        )

        if delivered_quantity <= 0:
            raise ValueError(
                "delivered_quantity must be positive"
            )

        release.delivered_quantity += (
            delivered_quantity
        )

        release.delivered_on = (
            delivered_on
        )

        if (
            release.delivered_quantity
            >= release.quantity
        ):
            release.status = (
                MaterialReleaseStatus
                .DELIVERED
            )

        else:
            release.status = (
                MaterialReleaseStatus
                .PARTIAL
            )

        self._audit(
            project,
            event_type=(
                "material.delivered"
            ),
            actor_id=actor_id,
            payload={
                "release_id":
                    release_id,
                "delivered_on":
                    delivered_on,
                "delivered_quantity":
                    delivered_quantity,
                "total_delivered":
                    release
                    .delivered_quantity,
            },
        )

        return release

    # ========================================================
    # CHANGE EVENTS
    # ========================================================

    def create_change_event(
        self,
        *,
        tenant_id: str,
        project_id: str,
        cost_code: str,
        description: str,
        estimated_cost_exposure_cents: int,
        requested_price_cents: int,
        actor_id: str,
        schedule_impact_days: int = 0,
        executed_at_risk: bool = False,
        source_reference: str | None = None,
        idempotency_key: str | None = None,
    ) -> ChangeEvent:
        project = self.project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._require_mutable(
            project
        )

        self._cost_code(
            project,
            cost_code,
        )

        estimated_cost_exposure_cents = (
            _money(
                estimated_cost_exposure_cents,
                "estimated_cost_exposure_cents",
            )
        )

        requested_price_cents = _money(
            requested_price_cents,
            "requested_price_cents",
        )

        request = {
            "cost_code":
                cost_code,
            "description":
                description,
            "cost_exposure":
                estimated_cost_exposure_cents,
            "requested_price":
                requested_price_cents,
            "schedule_days":
                schedule_impact_days,
            "at_risk":
                executed_at_risk,
            "source":
                source_reference,
        }

        existing = self._idem(
            project=project,
            action="change_event",
            idempotency_key=(
                idempotency_key
            ),
            request=request,
        )

        if existing is not None:
            return existing

        change = ChangeEvent(
            change_id=_id(
                "change"
            ),
            cost_code=cost_code,
            description=_required(
                description,
                "description",
            ),
            status=(
                ChangeEventStatus
                .IDENTIFIED
            ),
            estimated_cost_exposure_cents=(
                estimated_cost_exposure_cents
            ),
            requested_price_cents=(
                requested_price_cents
            ),
            schedule_impact_days=int(
                schedule_impact_days
            ),
            executed_at_risk=bool(
                executed_at_risk
            ),
            source_reference=(
                source_reference
            ),
        )

        project.changes[
            change.change_id
        ] = change

        self._audit(
            project,
            event_type=(
                "change.identified"
            ),
            actor_id=actor_id,
            payload={
                "change_id":
                    change.change_id,
                **request,
            },
        )

        self._save_idem(
            project=project,
            action="change_event",
            idempotency_key=(
                idempotency_key
            ),
            request=request,
            result=change,
        )

        return change

    def set_change_status(
        self,
        *,
        tenant_id: str,
        project_id: str,
        change_id: str,
        status: ChangeEventStatus,
        actor_id: str,
    ) -> ChangeEvent:
        project = self.project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        try:
            change = (
                project.changes[
                    change_id
                ]
            )

        except KeyError as exc:
            raise ChangeEventError(
                change_id
            ) from exc

        if (
            change.status
            in {
                ChangeEventStatus
                .APPROVED,
                ChangeEventStatus
                .REJECTED,
                ChangeEventStatus
                .VOID,
            }
        ):
            raise ChangeEventError(
                "terminal change cannot transition"
            )

        allowed = {
            ChangeEventStatus
            .IDENTIFIED: {
                ChangeEventStatus
                .PRICING,
                ChangeEventStatus
                .SUBMITTED,
                ChangeEventStatus
                .VOID,
            },

            ChangeEventStatus
            .PRICING: {
                ChangeEventStatus
                .SUBMITTED,
                ChangeEventStatus
                .VOID,
            },

            ChangeEventStatus
            .SUBMITTED: {
                ChangeEventStatus
                .APPROVED,
                ChangeEventStatus
                .REJECTED,
            },
        }

        if (
            status
            not in allowed.get(
                change.status,
                set(),
            )
        ):
            raise ChangeEventError(
                (
                    f"invalid transition "
                    f"{change.status.value}"
                    f" -> "
                    f"{status.value}"
                )
            )

        change.status = status

        self._audit(
            project,
            event_type=(
                "change.status_changed"
            ),
            actor_id=actor_id,
            payload={
                "change_id":
                    change_id,
                "status":
                    status.value,
            },
        )

        return change

    def approve_change(
        self,
        *,
        tenant_id: str,
        project_id: str,
        change_id: str,
        approved_cost_cents: int,
        approved_price_cents: int,
        actor_id: str,
    ) -> ChangeEvent:
        project = self.project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._require_mutable(
            project
        )

        try:
            change = (
                project.changes[
                    change_id
                ]
            )

        except KeyError as exc:
            raise ChangeEventError(
                change_id
            ) from exc

        if (
            change.status
            != ChangeEventStatus
            .SUBMITTED
        ):
            raise ChangeEventError(
                "change must be submitted"
            )

        approved_cost_cents = (
            _money(
                approved_cost_cents,
                "approved_cost_cents",
            )
        )

        approved_price_cents = (
            _money(
                approved_price_cents,
                "approved_price_cents",
            )
        )

        change.approved_cost_cents = (
            approved_cost_cents
        )

        change.approved_price_cents = (
            approved_price_cents
        )

        change.status = (
            ChangeEventStatus.APPROVED
        )

        change.approved_at = (
            _now()
        )

        budget = self._cost_code(
            project,
            change.cost_code,
        )

        budget.approved_change_budget_cents += (
            approved_cost_cents
        )

        self._audit(
            project,
            event_type=(
                "change.approved"
            ),
            actor_id=actor_id,
            payload={
                "change_id":
                    change_id,
                "approved_cost_cents":
                    approved_cost_cents,
                "approved_price_cents":
                    approved_price_cents,
                "schedule_impact_days":
                    change
                    .schedule_impact_days,
            },
        )

        return change

    # ========================================================
    # ETC OVERRIDE
    # ========================================================

    def set_manual_etc(
        self,
        *,
        tenant_id: str,
        project_id: str,
        cost_code: str,
        etc_cents: int,
        actor_id: str,
        reason: str,
    ) -> None:
        project = self.project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        self._cost_code(
            project,
            cost_code,
        )

        etc_cents = _money(
            etc_cents,
            "etc_cents",
        )

        project.manual_etc[
            cost_code
        ] = etc_cents

        self._audit(
            project,
            event_type=(
                "forecast.etc_override"
            ),
            actor_id=actor_id,
            payload={
                "cost_code":
                    cost_code,
                "etc_cents":
                    etc_cents,
                "reason":
                    _required(
                        reason,
                        "reason",
                    ),
            },
        )

    # ========================================================
    # BILLING
    # ========================================================

    def record_billing(
        self,
        *,
        tenant_id: str,
        project_id: str,
        period_end: date,
        gross_billed_cents: int,
        retainage_held_cents: int,
        collected_cents: int,
        actor_id: str,
        idempotency_key: str | None = None,
    ) -> BillingRecord:
        project = self.project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        gross_billed_cents = _money(
            gross_billed_cents,
            "gross_billed_cents",
        )

        retainage_held_cents = _money(
            retainage_held_cents,
            "retainage_held_cents",
        )

        collected_cents = _money(
            collected_cents,
            "collected_cents",
        )

        if (
            retainage_held_cents
            > gross_billed_cents
        ):
            raise FinancialValidationError(
                "retainage exceeds gross billing"
            )

        if (
            collected_cents
            > gross_billed_cents
        ):
            raise FinancialValidationError(
                "collection exceeds gross billing"
            )

        request = {
            "period_end":
                period_end,
            "gross":
                gross_billed_cents,
            "retainage":
                retainage_held_cents,
            "collected":
                collected_cents,
        }

        existing = self._idem(
            project=project,
            action="billing",
            idempotency_key=(
                idempotency_key
            ),
            request=request,
        )

        if existing is not None:
            return existing

        billing = BillingRecord(
            billing_id=_id(
                "bill"
            ),
            period_end=period_end,
            gross_billed_cents=(
                gross_billed_cents
            ),
            retainage_held_cents=(
                retainage_held_cents
            ),
            collected_cents=(
                collected_cents
            ),
            created_at=_now(),
        )

        project.billing.append(
            billing
        )

        self._audit(
            project,
            event_type=(
                "billing.recorded"
            ),
            actor_id=actor_id,
            payload={
                "billing_id":
                    billing.billing_id,
                **request,
            },
        )

        self._save_idem(
            project=project,
            action="billing",
            idempotency_key=(
                idempotency_key
            ),
            request=request,
            result=billing,
        )

        return billing

    # ========================================================
    # FORECAST
    # ========================================================

    @staticmethod
    def _latest_progress(
        project: ProjectExecutionState,
        cost_code: str,
        as_of: date,
    ) -> float:
        eligible = [
            item
            for item
            in project.progress
            if (
                item.cost_code
                == cost_code
                and item.as_of
                <= as_of
            )
        ]

        if not eligible:
            return 0.0

        return max(
            eligible,
            key=lambda item:
                item.as_of,
        ).percent_complete

    @staticmethod
    def _latest_planned_progress(
        project: ProjectExecutionState,
        cost_code: str,
        as_of: date,
    ) -> float:
        eligible = [
            item
            for item
            in project
            .planned_progress
            if (
                item.cost_code
                == cost_code
                and item.as_of
                <= as_of
            )
        ]

        if not eligible:
            return 0.0

        return max(
            eligible,
            key=lambda item:
                item.as_of,
        ).planned_percent_complete

    def forecast(
        self,
        *,
        tenant_id: str,
        project_id: str,
        as_of: date,
    ) -> ProjectForecast:
        project = self.project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        actual_by_code = defaultdict(
            int
        )

        for actual in (
            project.actual_costs
        ):
            if actual.incurred_on <= as_of:
                actual_by_code[
                    actual.cost_code
                ] += (
                    actual.amount_cents
                )

        open_commitment_by_code = (
            defaultdict(
                int
            )
        )

        for commitment in (
            project.commitments
            .values()
        ):
            if (
                commitment.status
                != CommitmentStatus
                .APPROVED
            ):
                continue

            open_commitment_by_code[
                commitment.cost_code
            ] += (
                commitment.remaining_cents
            )

        cost_code_forecasts = []

        for (
            cost_code,
            budget,
        ) in sorted(
            project
            .budget_lines
            .items()
        ):
            budget_cents = (
                budget
                .current_budget_cents
            )

            actual_cents = (
                actual_by_code[
                    cost_code
                ]
            )

            open_commitment = (
                open_commitment_by_code[
                    cost_code
                ]
            )

            percent = (
                self
                ._latest_progress(
                    project,
                    cost_code,
                    as_of,
                )
            )

            planned = (
                self
                ._latest_planned_progress(
                    project,
                    cost_code,
                    as_of,
                )
            )

            earned_value = int(
                round(
                    budget_cents
                    * percent
                )
            )

            planned_value = int(
                round(
                    budget_cents
                    * planned
                )
            )

            if (
                cost_code
                in project.manual_etc
            ):
                etc = (
                    project.manual_etc[
                        cost_code
                    ]
                )

                eac = (
                    actual_cents
                    + etc
                )

            else:
                committed_floor = (
                    actual_cents
                    + open_commitment
                )

                if (
                    percent
                    >= 0.05
                    and actual_cents > 0
                ):
                    performance_eac = int(
                        round(
                            actual_cents
                            / percent
                        )
                    )

                else:
                    performance_eac = (
                        budget_cents
                    )

                eac = max(
                    actual_cents,
                    committed_floor,
                    performance_eac,
                )

                etc = max(
                    0,
                    eac
                    - actual_cents,
                )

            variance = (
                budget_cents
                - eac
            )

            cpi = (
                _safe_ratio(
                    earned_value,
                    actual_cents,
                )
                if actual_cents > 0
                else None
            )

            spi = (
                _safe_ratio(
                    earned_value,
                    planned_value,
                )
                if planned_value > 0
                else None
            )

            cost_code_forecasts.append(
                CostCodeForecast(
                    cost_code=cost_code,
                    budget_cents=(
                        budget_cents
                    ),
                    actual_cost_cents=(
                        actual_cents
                    ),
                    open_commitment_cents=(
                        open_commitment
                    ),
                    percent_complete=(
                        percent
                    ),
                    planned_percent_complete=(
                        planned
                    ),
                    earned_value_cents=(
                        earned_value
                    ),
                    planned_value_cents=(
                        planned_value
                    ),
                    estimate_at_completion_cents=(
                        eac
                    ),
                    estimate_to_complete_cents=(
                        etc
                    ),
                    variance_at_completion_cents=(
                        variance
                    ),
                    cpi=cpi,
                    spi=spi,
                )
            )

        original_budget = sum(
            item
            .original_budget_cents
            for item
            in project
            .budget_lines
            .values()
        )

        current_budget = sum(
            item
            .current_budget_cents
            for item
            in project
            .budget_lines
            .values()
        )

        actual_cost = sum(
            item.actual_cost_cents
            for item
            in cost_code_forecasts
        )

        open_commitment = sum(
            item.open_commitment_cents
            for item
            in cost_code_forecasts
        )

        etc = sum(
            item
            .estimate_to_complete_cents
            for item
            in cost_code_forecasts
        )

        eac = sum(
            item
            .estimate_at_completion_cents
            for item
            in cost_code_forecasts
        )

        approved_change_price = sum(
            item
            .approved_price_cents
            for item
            in project.changes.values()
            if (
                item.status
                == ChangeEventStatus
                .APPROVED
            )
        )

        current_contract = (
            project
            .original_contract_value_cents
            + approved_change_price
        )

        forecast_gp = (
            current_contract
            - eac
        )

        forecast_margin = (
            forecast_gp
            / current_contract
            if current_contract
            else 0.0
        )

        original_gp = (
            project
            .original_contract_value_cents
            - original_budget
        )

        original_margin = (
            original_gp
            / project
            .original_contract_value_cents
            if project
            .original_contract_value_cents
            else 0.0
        )

        margin_erosion_bps = int(
            round(
                (
                    original_margin
                    - forecast_margin
                )
                * 10000
            )
        )

        earned_value = sum(
            item.earned_value_cents
            for item
            in cost_code_forecasts
        )

        planned_value = sum(
            item.planned_value_cents
            for item
            in cost_code_forecasts
        )

        total_cpi = (
            _safe_ratio(
                earned_value,
                actual_cost,
            )
            if actual_cost
            else None
        )

        total_spi = (
            _safe_ratio(
                earned_value,
                planned_value,
            )
            if planned_value
            else None
        )

        total_weight = max(
            1,
            current_budget,
        )

        overall_percent = sum(
            item.budget_cents
            * item.percent_complete
            for item
            in cost_code_forecasts
        ) / total_weight

        planned_percent = sum(
            item.budget_cents
            * item
            .planned_percent_complete
            for item
            in cost_code_forecasts
        ) / total_weight

        unresolved_change_exposure = sum(
            item
            .estimated_cost_exposure_cents
            for item
            in project.changes.values()
            if (
                item.status
                not in {
                    ChangeEventStatus
                    .APPROVED,
                    ChangeEventStatus
                    .REJECTED,
                    ChangeEventStatus
                    .VOID,
                }
            )
        )

        at_risk_exposure = sum(
            item
            .estimated_cost_exposure_cents
            for item
            in project.changes.values()
            if (
                item.executed_at_risk
                and item.status
                not in {
                    ChangeEventStatus
                    .APPROVED,
                    ChangeEventStatus
                    .REJECTED,
                    ChangeEventStatus
                    .VOID,
                }
            )
        )

        gross_billed = sum(
            item.gross_billed_cents
            for item
            in project.billing
            if item.period_end <= as_of
        )

        retainage = sum(
            item.retainage_held_cents
            for item
            in project.billing
            if item.period_end <= as_of
        )

        collected = sum(
            item.collected_cents
            for item
            in project.billing
            if item.period_end <= as_of
        )

        ar = max(
            0,
            gross_billed
            - collected,
        )

        earned_revenue = int(
            round(
                current_contract
                * overall_percent
            )
        )

        net_billed = max(
            0,
            gross_billed
            - retainage,
        )

        overbilling = max(
            0,
            net_billed
            - earned_revenue,
        )

        underbilling = max(
            0,
            earned_revenue
            - net_billed,
        )

        return ProjectForecast(
            project_id=project_id,
            as_of=as_of,
            original_contract_value_cents=(
                project
                .original_contract_value_cents
            ),
            approved_change_price_cents=(
                approved_change_price
            ),
            current_contract_value_cents=(
                current_contract
            ),
            original_budget_cents=(
                original_budget
            ),
            current_budget_cents=(
                current_budget
            ),
            actual_cost_cents=(
                actual_cost
            ),
            open_commitment_cents=(
                open_commitment
            ),
            estimate_to_complete_cents=(
                etc
            ),
            estimate_at_completion_cents=(
                eac
            ),
            forecast_gross_profit_cents=(
                forecast_gp
            ),
            forecast_margin_percent=(
                forecast_margin
            ),
            original_margin_percent=(
                original_margin
            ),
            margin_erosion_basis_points=(
                margin_erosion_bps
            ),
            earned_value_cents=(
                earned_value
            ),
            planned_value_cents=(
                planned_value
            ),
            cpi=total_cpi,
            spi=total_spi,
            overall_percent_complete=(
                overall_percent
            ),
            planned_percent_complete=(
                planned_percent
            ),
            unresolved_change_exposure_cents=(
                unresolved_change_exposure
            ),
            at_risk_change_exposure_cents=(
                at_risk_exposure
            ),
            gross_billed_cents=(
                gross_billed
            ),
            retainage_held_cents=(
                retainage
            ),
            collected_cents=(
                collected
            ),
            accounts_receivable_cents=(
                ar
            ),
            earned_revenue_cents=(
                earned_revenue
            ),
            overbilling_cents=(
                overbilling
            ),
            underbilling_cents=(
                underbilling
            ),
            cost_codes=tuple(
                cost_code_forecasts
            ),
        )

    # ========================================================
    # EXECUTIVE HEALTH
    # ========================================================

    def executive_health(
        self,
        *,
        tenant_id: str,
        project_id: str,
        as_of: date,
    ) -> ProjectHealth:
        project = self.project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        forecast = self.forecast(
            tenant_id=tenant_id,
            project_id=project_id,
            as_of=as_of,
        )

        interventions = []

        def add(
            severity: InterventionSeverity,
            code: str,
            title: str,
            evidence: str,
            action: str,
        ) -> None:
            interventions.append(
                ExecutiveIntervention(
                    intervention_id=(
                        "intervention_"
                        + _hash(
                            {
                                "project":
                                    project_id,
                                "date":
                                    as_of,
                                "code":
                                    code,
                                "evidence":
                                    evidence,
                            }
                        )[:20]
                    ),
                    severity=severity,
                    code=code,
                    title=title,
                    evidence=evidence,
                    recommended_action=(
                        action
                    ),
                )
            )

        if (
            forecast
            .forecast_gross_profit_cents
            < 0
        ):
            add(
                InterventionSeverity
                .CRITICAL,
                "NEGATIVE_FORECAST_MARGIN",
                (
                    "Project is forecasting "
                    "a gross loss"
                ),
                (
                    "Forecast gross profit cents: "
                    f"{forecast.forecast_gross_profit_cents}"
                ),
                (
                    "Executive review of remaining "
                    "scope, commitments, change recovery "
                    "and production plan."
                ),
            )

        if (
            forecast
            .margin_erosion_basis_points
            >= 500
        ):
            add(
                InterventionSeverity.HIGH,
                "MARGIN_EROSION",
                (
                    "Forecast margin has materially "
                    "eroded"
                ),
                (
                    "Margin erosion bps: "
                    f"{forecast.margin_erosion_basis_points}"
                ),
                (
                    "Review cost-code forecast, "
                    "productivity, buyout and unresolved changes."
                ),
            )

        if (
            forecast.cpi
            is not None
            and forecast.cpi < 0.90
        ):
            add(
                InterventionSeverity.HIGH,
                "LOW_CPI",
                (
                    "Cost performance is below "
                    "target"
                ),
                (
                    f"CPI: {forecast.cpi:.3f}"
                ),
                (
                    "Investigate labor, material, "
                    "equipment and subcontract cost variance."
                ),
            )

        if (
            forecast.spi
            is not None
            and forecast.spi < 0.90
        ):
            add(
                InterventionSeverity.HIGH,
                "LOW_SPI",
                (
                    "Earned progress is behind "
                    "planned progress"
                ),
                (
                    f"SPI: {forecast.spi:.3f}"
                ),
                (
                    "Review critical activities, "
                    "crew capacity, constraints and material readiness."
                ),
            )

        if (
            forecast
            .at_risk_change_exposure_cents
            > 0
        ):
            add(
                InterventionSeverity.HIGH,
                "AT_RISK_CHANGE_WORK",
                (
                    "Work is being executed before "
                    "change approval"
                ),
                (
                    "At-risk cost exposure cents: "
                    f"{forecast.at_risk_change_exposure_cents}"
                ),
                (
                    "Escalate written authorization, "
                    "notice, pricing and documentation."
                ),
            )

        if (
            forecast
            .unresolved_change_exposure_cents
            > max(
                100_000,
                int(
                    forecast
                    .current_contract_value_cents
                    * 0.02
                ),
            )
        ):
            add(
                InterventionSeverity.HIGH,
                "UNRESOLVED_CHANGE_EXPOSURE",
                (
                    "Unresolved change exposure "
                    "is material"
                ),
                (
                    "Open exposure cents: "
                    f"{forecast.unresolved_change_exposure_cents}"
                ),
                (
                    "Accelerate pricing, notices, "
                    "owner/GC decisions and recovery strategy."
                ),
            )

        for item in (
            forecast.cost_codes
        ):
            if (
                item.actual_cost_cents
                + item.open_commitment_cents
                > item.budget_cents
            ):
                add(
                    InterventionSeverity.HIGH,
                    "OVERCOMMITTED_COST_CODE",
                    (
                        "Cost code commitments exceed "
                        "budget"
                    ),
                    (
                        f"{item.cost_code}: "
                        f"actual={item.actual_cost_cents}, "
                        f"open_commitment="
                        f"{item.open_commitment_cents}, "
                        f"budget={item.budget_cents}"
                    ),
                    (
                        "Review buyout, remaining scope, "
                        "budget transfer and forecast."
                    ),
                )

            productivity = (
                self.productivity(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    cost_code=(
                        item.cost_code
                    ),
                )
            )

            if (
                productivity
                .efficiency_ratio
                is not None
                and productivity
                .actual_labor_hours
                >= 8
                and productivity
                .efficiency_ratio
                < 0.80
            ):
                add(
                    InterventionSeverity.HIGH,
                    "LOW_FIELD_PRODUCTIVITY",
                    (
                        "Field productivity is below "
                        "planned labor efficiency"
                    ),
                    (
                        f"{item.cost_code}: "
                        f"efficiency="
                        f"{productivity.efficiency_ratio:.3f}"
                    ),
                    (
                        "Review crew composition, "
                        "means/methods, constraints and production target."
                    ),
                )

        late_material = [
            item
            for item
            in project
            .material_releases
            .values()
            if (
                item.required_on_site
                < as_of
                and item.status
                != MaterialReleaseStatus
                .DELIVERED
                and item.status
                != MaterialReleaseStatus
                .CANCELLED
            )
        ]

        if late_material:
            add(
                InterventionSeverity.HIGH,
                "LATE_MATERIAL",
                (
                    "Required material is not "
                    "fully delivered"
                ),
                (
                    f"{len(late_material)} "
                    "late material release(s)"
                ),
                (
                    "Escalate vendor status, "
                    "expedite, approved alternatives and schedule impact."
                ),
            )

        if (
            project.status
            == ExecutionStatus.ACTIVE
        ):
            eligible_logs = [
                item
                for item
                in project.daily_logs
                if item.work_date <= as_of
            ]

            if not eligible_logs:
                add(
                    InterventionSeverity.REVIEW,
                    "NO_DAILY_LOGS",
                    (
                        "No field daily logs are "
                        "recorded"
                    ),
                    (
                        "Active project has no "
                        "daily production evidence."
                    ),
                    (
                        "Require daily field reporting "
                        "and production capture."
                    ),
                )

            else:
                latest_log = max(
                    eligible_logs,
                    key=lambda item:
                        item.work_date,
                )

                age_days = (
                    as_of
                    - latest_log
                    .work_date
                ).days

                if age_days >= 4:
                    add(
                        InterventionSeverity.REVIEW,
                        "STALE_DAILY_LOGS",
                        (
                            "Field reporting is stale"
                        ),
                        (
                            f"Latest daily log is "
                            f"{age_days} day(s) old."
                        ),
                        (
                            "Restore daily reporting "
                            "before forecast confidence degrades."
                        ),
                    )

        if (
            forecast
            .accounts_receivable_cents
            > max(
                100_000,
                int(
                    forecast
                    .current_contract_value_cents
                    * 0.10
                ),
            )
        ):
            add(
                InterventionSeverity.REVIEW,
                "COLLECTION_EXPOSURE",
                (
                    "Accounts receivable exposure "
                    "is material"
                ),
                (
                    "AR cents: "
                    f"{forecast.accounts_receivable_cents}"
                ),
                (
                    "Review aging, retainage, "
                    "billing support and collection status."
                ),
            )

        deductions = {
            InterventionSeverity.INFO:
                1,
            InterventionSeverity.REVIEW:
                5,
            InterventionSeverity.HIGH:
                12,
            InterventionSeverity.CRITICAL:
                25,
        }

        score = max(
            0,
            100
            - sum(
                deductions[
                    item.severity
                ]
                for item
                in interventions
            ),
        )

        interventions.sort(
            key=lambda item: (
                -int(
                    item.severity
                ),
                item.code,
            )
        )

        return ProjectHealth(
            score=score,
            interventions=tuple(
                interventions
            ),
            critical_count=sum(
                1
                for item
                in interventions
                if item.severity
                == InterventionSeverity
                .CRITICAL
            ),
            high_count=sum(
                1
                for item
                in interventions
                if item.severity
                == InterventionSeverity
                .HIGH
            ),
            review_count=sum(
                1
                for item
                in interventions
                if item.severity
                == InterventionSeverity
                .REVIEW
            ),
        )

    # ========================================================
    # AUDIT VALIDATION
    # ========================================================

    def verify_audit_chain(
        self,
        *,
        tenant_id: str,
        project_id: str,
    ) -> bool:
        project = self.project(
            tenant_id=tenant_id,
            project_id=project_id,
        )

        expected_previous = (
            "0" * 64
        )

        for expected_sequence, event in enumerate(
            project.audit,
            start=1,
        ):
            if (
                event.sequence
                != expected_sequence
            ):
                raise AuditIntegrityError(
                    "audit sequence mismatch"
                )

            if (
                event.previous_hash
                != expected_previous
            ):
                raise AuditIntegrityError(
                    "audit previous hash mismatch"
                )

            if (
                _hash(
                    event.payload
                )
                != event.payload_hash
            ):
                raise AuditIntegrityError(
                    "audit payload hash mismatch"
                )

            calculated = _event_hash(
                sequence=(
                    event.sequence
                ),
                event_id=(
                    event.event_id
                ),
                event_type=(
                    event.event_type
                ),
                actor_id=(
                    event.actor_id
                ),
                occurred_at=(
                    event.occurred_at
                ),
                payload_hash=(
                    event.payload_hash
                ),
                previous_hash=(
                    event.previous_hash
                ),
            )

            if (
                calculated
                != event.event_hash
            ):
                raise AuditIntegrityError(
                    "audit event hash mismatch"
                )

            expected_previous = (
                event.event_hash
            )

        return True


# ============================================================
# DURABLE DATA-SPINE BRIDGE
# ============================================================


@dataclass(frozen=True)
class DurablePublishResult:
    event_id: str

    stream_version: int


class ExecutionPersistenceBridge:
    """
    Bridges verified execution audit events into GOAT DurableStore.

    The production application layer should persist authoritative business
    mutations through the durable transaction boundary. This bridge gives
    the execution domain a deterministic event contract without coupling
    business calculations to a particular database engine.
    """

    def __init__(
        self,
        *,
        store: DurableStore,
    ) -> None:
        self.store = store

    def publish(
        self,
        *,
        tenant_id: str,
        project_id: str,
        audit_event: ExecutionAuditEvent,
    ) -> DurablePublishResult:
        stream_id = (
            "execution:"
            + project_id
        )

        expected_version = (
            self.store
            .current_version(
                tenant_id=tenant_id,
                stream_id=stream_id,
            )
        )

        envelope = (
            self.store.append(
                tenant_id=tenant_id,
                stream_id=stream_id,
                expected_version=(
                    expected_version
                ),
                event_type=(
                    audit_event
                    .event_type
                ),
                payload={
                    "execution_event_id":
                        audit_event
                        .event_id,
                    "sequence":
                        audit_event
                        .sequence,
                    "event_hash":
                        audit_event
                        .event_hash,
                    "payload":
                        audit_event
                        .payload,
                },
                topic=(
                    "project.execution"
                ),
                actor_id=(
                    audit_event
                    .actor_id
                ),
            )
        )

        return DurablePublishResult(
            event_id=(
                envelope.event_id
            ),
            stream_version=(
                envelope.version
            ),
        )
