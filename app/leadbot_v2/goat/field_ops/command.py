from __future__ import annotations

import hashlib
import json
import math
import uuid

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum, IntEnum
from typing import Any, Iterable, Sequence


# ============================================================
# ERRORS
# ============================================================


class FieldOpsError(RuntimeError):
    pass


class FieldValidationError(FieldOpsError):
    pass


class CrewNotFound(FieldOpsError):
    pass


class WorkerNotFound(FieldOpsError):
    pass


class EquipmentNotFound(FieldOpsError):
    pass


class TimecardError(FieldOpsError):
    pass


class InspectionError(FieldOpsError):
    pass


class RFIError(FieldOpsError):
    pass


class SubmittalError(FieldOpsError):
    pass


class ComplianceError(FieldOpsError):
    pass


class MobileSyncConflict(FieldOpsError):
    pass


class FieldAuditIntegrityError(FieldOpsError):
    pass


# ============================================================
# ENUMS
# ============================================================


class WorkerStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class CrewRole(str, Enum):
    SUPERINTENDENT = "superintendent"
    FOREMAN = "foreman"
    JOURNEYMAN = "journeyman"
    OPERATOR = "operator"
    LABORER = "laborer"
    HELPER = "helper"
    APPRENTICE = "apprentice"
    DRIVER = "driver"
    OTHER = "other"


class TimecardStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    POSTED = "posted"


class EquipmentStatus(str, Enum):
    AVAILABLE = "available"
    ASSIGNED = "assigned"
    DOWN = "down"
    MAINTENANCE = "maintenance"
    RETIRED = "retired"


class InspectionResult(str, Enum):
    PASS = "pass"
    PASS_WITH_NOTES = "pass_with_notes"
    FAIL = "fail"
    HOLD = "hold"


class SafetySeverity(IntEnum):
    INFO = 10
    REVIEW = 20
    HIGH = 30
    CRITICAL = 40


class RFIStatus(str, Enum):
    DRAFT = "draft"
    OPEN = "open"
    ANSWERED = "answered"
    CLOSED = "closed"
    VOID = "void"


class SubmittalStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    REVISE_RESUBMIT = "revise_resubmit"
    APPROVED = "approved"
    APPROVED_AS_NOTED = "approved_as_noted"
    REJECTED = "rejected"
    CLOSED = "closed"


class PunchStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    READY_FOR_REVIEW = "ready_for_review"
    CLOSED = "closed"


class ComplianceStatus(str, Enum):
    UNKNOWN = "unknown"
    PENDING = "pending"
    COMPLIANT = "compliant"
    EXPIRED = "expired"
    NONCOMPLIANT = "noncompliant"


class WaiverType(str, Enum):
    CONDITIONAL_PROGRESS = "conditional_progress"
    UNCONDITIONAL_PROGRESS = "unconditional_progress"
    CONDITIONAL_FINAL = "conditional_final"
    UNCONDITIONAL_FINAL = "unconditional_final"


class PayAppStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    REJECTED = "rejected"


class SyncMutationType(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class FieldRiskSeverity(IntEnum):
    INFO = 10
    REVIEW = 20
    HIGH = 30
    CRITICAL = 40


# ============================================================
# UTILITIES
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
        raise FieldValidationError(
            f"{field_name} is required"
        )

    return result


def _money(
    value: int,
    field_name: str,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise FieldValidationError(
            f"{field_name} must be nonnegative integer cents"
        )

    return value


def _finite_nonnegative(
    value: float,
    field_name: str,
) -> float:
    result = float(
        value
    )

    if (
        not math.isfinite(result)
        or result < 0
    ):
        raise FieldValidationError(
            f"{field_name} must be finite and nonnegative"
        )

    return result


def _canonical_json(
    value: Any,
) -> str:
    def normalize(item: Any) -> Any:
        if isinstance(item, Enum):
            return item.value

        if isinstance(
            item,
            (date, datetime),
        ):
            return item.isoformat()

        if isinstance(item, dict):
            return {
                str(k):
                    normalize(v)
                for k, v
                in sorted(item.items())
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
        normalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )


def _hash(
    value: Any,
) -> str:
    return hashlib.sha256(
        _canonical_json(
            value
        ).encode("utf-8")
    ).hexdigest()


# ============================================================
# WORKFORCE / CREWS
# ============================================================


@dataclass
class Worker:
    worker_id: str

    employee_number: str
    name: str

    role: CrewRole

    base_rate_cents_per_hour: int

    payroll_burden_bps: int = 0
    benefits_bps: int = 0
    workers_comp_bps: int = 0
    supervision_bps: int = 0

    status: WorkerStatus = (
        WorkerStatus.ACTIVE
    )

    certifications: frozenset[
        str
    ] = frozenset()

    @property
    def burdened_rate_cents_per_hour(
        self,
    ) -> int:
        total_bps = (
            self.payroll_burden_bps
            + self.benefits_bps
            + self.workers_comp_bps
            + self.supervision_bps
        )

        return int(
            round(
                self.base_rate_cents_per_hour
                * (
                    1.0
                    + total_bps
                    / 10000.0
                )
            )
        )


@dataclass
class Crew:
    crew_id: str

    name: str

    project_id: str | None = None

    worker_ids: set[
        str
    ] = field(
        default_factory=set
    )

    foreman_worker_id: str | None = None

    active: bool = True


@dataclass(frozen=True)
class CrewAssignment:
    assignment_id: str

    crew_id: str
    project_id: str
    cost_code: str

    start_date: date
    end_date: date | None

    created_at: datetime


# ============================================================
# TIMECARDS / LABOR
# ============================================================


@dataclass
class Timecard:
    timecard_id: str

    worker_id: str
    project_id: str
    cost_code: str

    work_date: date

    regular_hours: float
    overtime_hours: float
    doubletime_hours: float

    status: TimecardStatus

    submitted_by: str

    approved_by: str | None = None

    note: str | None = None

    created_at: datetime = field(
        default_factory=_now
    )

    @property
    def total_hours(
        self,
    ) -> float:
        return (
            self.regular_hours
            + self.overtime_hours
            + self.doubletime_hours
        )


@dataclass(frozen=True)
class LaborCostResult:
    timecard_id: str

    worker_id: str

    regular_cost_cents: int
    overtime_cost_cents: int
    doubletime_cost_cents: int

    total_cost_cents: int


# ============================================================
# EQUIPMENT
# ============================================================


@dataclass
class EquipmentAsset:
    equipment_id: str

    name: str
    asset_number: str

    hourly_cost_cents: int

    status: EquipmentStatus = (
        EquipmentStatus.AVAILABLE
    )

    project_id: str | None = None

    meter_hours: float = 0.0


@dataclass(frozen=True)
class EquipmentUsage:
    usage_id: str

    equipment_id: str

    project_id: str
    cost_code: str

    work_date: date

    hours: float

    cost_cents: int

    operator_worker_id: str | None

    created_at: datetime


# ============================================================
# QA / QC
# ============================================================


@dataclass(frozen=True)
class InspectionItem:
    item_id: str

    description: str

    result: InspectionResult

    note: str | None = None


@dataclass
class QualityInspection:
    inspection_id: str

    project_id: str
    cost_code: str

    inspection_type: str

    performed_on: date
    performed_by: str

    result: InspectionResult

    items: tuple[
        InspectionItem,
        ...
    ]

    drawing_refs: tuple[
        str,
        ...
    ] = ()

    spec_refs: tuple[
        str,
        ...
    ] = ()

    corrective_action: str | None = None

    closed: bool = False

    created_at: datetime = field(
        default_factory=_now
    )


# ============================================================
# SAFETY / JSA DOCUMENTATION
# ============================================================


@dataclass(frozen=True)
class HazardControl:
    hazard: str
    control: str

    severity: SafetySeverity


@dataclass
class JobSafetyAnalysis:
    jsa_id: str

    project_id: str

    work_date: date

    activity: str

    prepared_by: str

    crew_id: str | None

    hazards: tuple[
        HazardControl,
        ...
    ]

    attendee_worker_ids: tuple[
        str,
        ...
    ]

    acknowledged: bool = False

    created_at: datetime = field(
        default_factory=_now
    )


# ============================================================
# RFI
# ============================================================


@dataclass
class RFI:
    rfi_id: str

    project_id: str

    number: int

    subject: str
    question: str

    drawing_refs: tuple[
        str,
        ...
    ]

    spec_refs: tuple[
        str,
        ...
    ]

    cost_code: str | None

    status: RFIStatus

    created_by: str

    assigned_to: str | None

    due_date: date | None

    answer: str | None = None

    answered_by: str | None = None

    created_at: datetime = field(
        default_factory=_now
    )

    answered_at: datetime | None = None


# ============================================================
# SUBMITTALS
# ============================================================


@dataclass
class Submittal:
    submittal_id: str

    project_id: str

    number: int

    title: str

    spec_section: str | None

    supplier: str | None

    status: SubmittalStatus

    required_on_site: date | None

    submitted_on: date | None = None
    returned_on: date | None = None

    review_notes: str | None = None

    revision: int = 0

    created_at: datetime = field(
        default_factory=_now
    )


# ============================================================
# PUNCH
# ============================================================


@dataclass
class PunchItem:
    punch_id: str

    project_id: str

    location: str
    description: str

    assigned_to: str | None

    due_date: date | None

    status: PunchStatus

    created_by: str

    photo_refs: tuple[
        str,
        ...
    ] = ()

    created_at: datetime = field(
        default_factory=_now
    )

    closed_at: datetime | None = None


# ============================================================
# SUBCONTRACTOR COMPLIANCE
# ============================================================


@dataclass
class ComplianceDocument:
    document_id: str

    document_type: str

    status: ComplianceStatus

    expires_on: date | None

    reference: str | None


@dataclass
class SubcontractorCompliance:
    subcontractor_id: str

    company_name: str

    insurance_status: ComplianceStatus = (
        ComplianceStatus.UNKNOWN
    )

    w9_status: ComplianceStatus = (
        ComplianceStatus.UNKNOWN
    )

    agreement_status: ComplianceStatus = (
        ComplianceStatus.UNKNOWN
    )

    safety_status: ComplianceStatus = (
        ComplianceStatus.UNKNOWN
    )

    documents: dict[
        str,
        ComplianceDocument,
    ] = field(
        default_factory=dict
    )


# ============================================================
# LIEN WAIVERS
# ============================================================


@dataclass
class LienWaiver:
    waiver_id: str

    subcontractor_id: str
    project_id: str

    waiver_type: WaiverType

    through_date: date

    amount_cents: int

    signed: bool

    reference: str | None

    created_at: datetime = field(
        default_factory=_now
    )


# ============================================================
# PAY APPLICATIONS
# ============================================================


@dataclass
class PayApplication:
    pay_app_id: str

    subcontractor_id: str
    project_id: str
    cost_code: str

    period_end: date

    gross_amount_cents: int

    retainage_cents: int

    approved_amount_cents: int = 0

    paid_amount_cents: int = 0

    status: PayAppStatus = (
        PayAppStatus.DRAFT
    )

    waiver_id: str | None = None

    created_at: datetime = field(
        default_factory=_now
    )

    @property
    def net_requested_cents(
        self,
    ) -> int:
        return max(
            0,
            self.gross_amount_cents
            - self.retainage_cents,
        )


# ============================================================
# MOBILE SYNC
# ============================================================


@dataclass(frozen=True)
class MobileMutation:
    mutation_id: str

    device_id: str

    entity_type: str
    entity_id: str

    mutation_type: SyncMutationType

    base_version: int

    payload: dict[
        str,
        Any,
    ]

    client_created_at: datetime


@dataclass(frozen=True)
class SyncResult:
    mutation_id: str

    accepted: bool

    server_version: int

    conflict: bool

    reason: str | None = None


@dataclass
class VersionedMobileEntity:
    entity_type: str
    entity_id: str

    version: int

    payload: dict[
        str,
        Any,
    ]

    updated_at: datetime


# ============================================================
# AUDIT
# ============================================================


@dataclass(frozen=True)
class FieldAuditEvent:
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
# FIELD INTELLIGENCE
# ============================================================


@dataclass(frozen=True)
class FieldRisk:
    risk_id: str

    severity: FieldRiskSeverity

    code: str

    title: str

    evidence: str

    recommended_action: str


@dataclass(frozen=True)
class FieldCommandSnapshot:
    project_id: str

    as_of: date

    active_workers: int
    approved_hours: float

    labor_cost_cents: int
    equipment_cost_cents: int

    open_rfis: int
    overdue_rfis: int

    open_submittals: int
    late_submittals: int

    failed_inspections: int
    open_punch_items: int

    noncompliant_subcontractors: int

    risks: tuple[
        FieldRisk,
        ...
    ]

    health_score: int


# ============================================================
# SERVICE
# ============================================================


class FieldOperationsService:
    def __init__(
        self,
    ) -> None:
        self.workers: dict[
            str,
            Worker,
        ] = {}

        self.crews: dict[
            str,
            Crew,
        ] = {}

        self.assignments: dict[
            str,
            CrewAssignment,
        ] = {}

        self.timecards: dict[
            str,
            Timecard,
        ] = {}

        self.equipment: dict[
            str,
            EquipmentAsset,
        ] = {}

        self.equipment_usage: dict[
            str,
            EquipmentUsage,
        ] = {}

        self.inspections: dict[
            str,
            QualityInspection,
        ] = {}

        self.jsas: dict[
            str,
            JobSafetyAnalysis,
        ] = {}

        self.rfis: dict[
            str,
            RFI,
        ] = {}

        self.submittals: dict[
            str,
            Submittal,
        ] = {}

        self.punch_items: dict[
            str,
            PunchItem,
        ] = {}

        self.subcontractors: dict[
            str,
            SubcontractorCompliance,
        ] = {}

        self.waivers: dict[
            str,
            LienWaiver,
        ] = {}

        self.pay_apps: dict[
            str,
            PayApplication,
        ] = {}

        self.mobile_entities: dict[
            tuple[
                str,
                str,
            ],
            VersionedMobileEntity,
        ] = {}

        self.audit: list[
            FieldAuditEvent
        ] = []

        self._rfi_numbers = defaultdict(
            int
        )

        self._submittal_numbers = defaultdict(
            int
        )

    # ========================================================
    # AUDIT
    # ========================================================

    def _audit(
        self,
        *,
        event_type: str,
        actor_id: str,
        payload: dict[str, Any],
    ) -> FieldAuditEvent:
        sequence = (
            len(self.audit)
            + 1
        )

        event_id = _id(
            "field_evt"
        )

        occurred_at = _now()

        payload_hash = _hash(
            payload
        )

        previous_hash = (
            self.audit[-1].event_hash
            if self.audit
            else "0" * 64
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

        event = FieldAuditEvent(
            sequence=sequence,
            event_id=event_id,
            event_type=event_type,
            actor_id=actor_id,
            occurred_at=occurred_at,
            payload=dict(payload),
            payload_hash=payload_hash,
            previous_hash=previous_hash,
            event_hash=event_hash,
        )

        self.audit.append(
            event
        )

        return event

    def verify_audit_chain(
        self,
    ) -> bool:
        previous = (
            "0" * 64
        )

        for sequence, event in enumerate(
            self.audit,
            start=1,
        ):
            if event.sequence != sequence:
                raise FieldAuditIntegrityError(
                    "audit sequence mismatch"
                )

            if event.previous_hash != previous:
                raise FieldAuditIntegrityError(
                    "audit previous hash mismatch"
                )

            if (
                _hash(event.payload)
                != event.payload_hash
            ):
                raise FieldAuditIntegrityError(
                    "audit payload tampered"
                )

            calculated = _event_hash(
                sequence=event.sequence,
                event_id=event.event_id,
                event_type=event.event_type,
                actor_id=event.actor_id,
                occurred_at=event.occurred_at,
                payload_hash=event.payload_hash,
                previous_hash=event.previous_hash,
            )

            if calculated != event.event_hash:
                raise FieldAuditIntegrityError(
                    "audit event hash mismatch"
                )

            previous = event.event_hash

        return True

    # ========================================================
    # WORKERS
    # ========================================================

    def create_worker(
        self,
        *,
        employee_number: str,
        name: str,
        role: CrewRole,
        base_rate_cents_per_hour: int,
        actor_id: str,
        payroll_burden_bps: int = 0,
        benefits_bps: int = 0,
        workers_comp_bps: int = 0,
        supervision_bps: int = 0,
        certifications: Iterable[str] = (),
    ) -> Worker:
        base_rate_cents_per_hour = _money(
            base_rate_cents_per_hour,
            "base_rate_cents_per_hour",
        )

        for value in (
            payroll_burden_bps,
            benefits_bps,
            workers_comp_bps,
            supervision_bps,
        ):
            if value < 0:
                raise FieldValidationError(
                    "burden basis points cannot be negative"
                )

        worker = Worker(
            worker_id=_id(
                "worker"
            ),
            employee_number=_required(
                employee_number,
                "employee_number",
            ),
            name=_required(
                name,
                "name",
            ),
            role=role,
            base_rate_cents_per_hour=(
                base_rate_cents_per_hour
            ),
            payroll_burden_bps=int(
                payroll_burden_bps
            ),
            benefits_bps=int(
                benefits_bps
            ),
            workers_comp_bps=int(
                workers_comp_bps
            ),
            supervision_bps=int(
                supervision_bps
            ),
            certifications=frozenset(
                str(item).strip()
                for item
                in certifications
                if str(item).strip()
            ),
        )

        self.workers[
            worker.worker_id
        ] = worker

        self._audit(
            event_type=(
                "workforce.worker_created"
            ),
            actor_id=actor_id,
            payload={
                "worker_id":
                    worker.worker_id,
                "employee_number":
                    worker.employee_number,
                "role":
                    worker.role.value,
            },
        )

        return worker

    def create_crew(
        self,
        *,
        name: str,
        actor_id: str,
    ) -> Crew:
        crew = Crew(
            crew_id=_id(
                "crew"
            ),
            name=_required(
                name,
                "crew name",
            ),
        )

        self.crews[
            crew.crew_id
        ] = crew

        self._audit(
            event_type=(
                "workforce.crew_created"
            ),
            actor_id=actor_id,
            payload={
                "crew_id":
                    crew.crew_id,
                "name":
                    crew.name,
            },
        )

        return crew

    def add_worker_to_crew(
        self,
        *,
        crew_id: str,
        worker_id: str,
        actor_id: str,
        as_foreman: bool = False,
    ) -> Crew:
        try:
            crew = self.crews[
                crew_id
            ]

        except KeyError as exc:
            raise CrewNotFound(
                crew_id
            ) from exc

        try:
            worker = self.workers[
                worker_id
            ]

        except KeyError as exc:
            raise WorkerNotFound(
                worker_id
            ) from exc

        if (
            worker.status
            != WorkerStatus.ACTIVE
        ):
            raise FieldValidationError(
                "worker is not active"
            )

        crew.worker_ids.add(
            worker_id
        )

        if as_foreman:
            crew.foreman_worker_id = (
                worker_id
            )

        self._audit(
            event_type=(
                "workforce.crew_member_added"
            ),
            actor_id=actor_id,
            payload={
                "crew_id":
                    crew_id,
                "worker_id":
                    worker_id,
                "foreman":
                    as_foreman,
            },
        )

        return crew

    def assign_crew(
        self,
        *,
        crew_id: str,
        project_id: str,
        cost_code: str,
        start_date: date,
        actor_id: str,
        end_date: date | None = None,
    ) -> CrewAssignment:
        try:
            crew = self.crews[
                crew_id
            ]

        except KeyError as exc:
            raise CrewNotFound(
                crew_id
            ) from exc

        if (
            end_date is not None
            and end_date < start_date
        ):
            raise FieldValidationError(
                "assignment end precedes start"
            )

        assignment = (
            CrewAssignment(
                assignment_id=_id(
                    "assign"
                ),
                crew_id=crew_id,
                project_id=_required(
                    project_id,
                    "project_id",
                ),
                cost_code=_required(
                    cost_code,
                    "cost_code",
                ),
                start_date=start_date,
                end_date=end_date,
                created_at=_now(),
            )
        )

        self.assignments[
            assignment.assignment_id
        ] = assignment

        crew.project_id = (
            project_id
        )

        self._audit(
            event_type=(
                "workforce.crew_assigned"
            ),
            actor_id=actor_id,
            payload={
                "assignment_id":
                    assignment.assignment_id,
                "crew_id":
                    crew_id,
                "project_id":
                    project_id,
                "cost_code":
                    cost_code,
            },
        )

        return assignment

    # ========================================================
    # TIMECARDS
    # ========================================================

    def create_timecard(
        self,
        *,
        worker_id: str,
        project_id: str,
        cost_code: str,
        work_date: date,
        regular_hours: float,
        overtime_hours: float,
        doubletime_hours: float,
        submitted_by: str,
        actor_id: str,
        note: str | None = None,
    ) -> Timecard:
        if worker_id not in self.workers:
            raise WorkerNotFound(
                worker_id
            )

        regular_hours = (
            _finite_nonnegative(
                regular_hours,
                "regular_hours",
            )
        )

        overtime_hours = (
            _finite_nonnegative(
                overtime_hours,
                "overtime_hours",
            )
        )

        doubletime_hours = (
            _finite_nonnegative(
                doubletime_hours,
                "doubletime_hours",
            )
        )

        total = (
            regular_hours
            + overtime_hours
            + doubletime_hours
        )

        if total > 24:
            raise TimecardError(
                "timecard exceeds 24 hours"
            )

        duplicate = [
            item
            for item
            in self.timecards.values()
            if (
                item.worker_id
                == worker_id
                and item.project_id
                == project_id
                and item.cost_code
                == cost_code
                and item.work_date
                == work_date
                and item.status
                not in {
                    TimecardStatus.REJECTED
                }
            )
        ]

        if duplicate:
            raise TimecardError(
                "duplicate active timecard"
            )

        timecard = Timecard(
            timecard_id=_id(
                "time"
            ),
            worker_id=worker_id,
            project_id=_required(
                project_id,
                "project_id",
            ),
            cost_code=_required(
                cost_code,
                "cost_code",
            ),
            work_date=work_date,
            regular_hours=regular_hours,
            overtime_hours=overtime_hours,
            doubletime_hours=doubletime_hours,
            status=(
                TimecardStatus.DRAFT
            ),
            submitted_by=_required(
                submitted_by,
                "submitted_by",
            ),
            note=note,
        )

        self.timecards[
            timecard.timecard_id
        ] = timecard

        self._audit(
            event_type=(
                "labor.timecard_created"
            ),
            actor_id=actor_id,
            payload={
                "timecard_id":
                    timecard.timecard_id,
                "worker_id":
                    worker_id,
                "project_id":
                    project_id,
                "cost_code":
                    cost_code,
                "hours":
                    total,
            },
        )

        return timecard

    def submit_timecard(
        self,
        *,
        timecard_id: str,
        actor_id: str,
    ) -> Timecard:
        try:
            card = self.timecards[
                timecard_id
            ]

        except KeyError as exc:
            raise TimecardError(
                timecard_id
            ) from exc

        if (
            card.status
            != TimecardStatus.DRAFT
        ):
            raise TimecardError(
                "only draft timecard can be submitted"
            )

        card.status = (
            TimecardStatus.SUBMITTED
        )

        self._audit(
            event_type=(
                "labor.timecard_submitted"
            ),
            actor_id=actor_id,
            payload={
                "timecard_id":
                    timecard_id
            },
        )

        return card

    def approve_timecard(
        self,
        *,
        timecard_id: str,
        approved_by: str,
        actor_id: str,
    ) -> Timecard:
        try:
            card = self.timecards[
                timecard_id
            ]

        except KeyError as exc:
            raise TimecardError(
                timecard_id
            ) from exc

        if (
            card.status
            != TimecardStatus.SUBMITTED
        ):
            raise TimecardError(
                "timecard must be submitted"
            )

        card.status = (
            TimecardStatus.APPROVED
        )

        card.approved_by = (
            _required(
                approved_by,
                "approved_by",
            )
        )

        self._audit(
            event_type=(
                "labor.timecard_approved"
            ),
            actor_id=actor_id,
            payload={
                "timecard_id":
                    timecard_id,
                "approved_by":
                    approved_by,
            },
        )

        return card

    def labor_cost(
        self,
        *,
        timecard_id: str,
    ) -> LaborCostResult:
        try:
            card = self.timecards[
                timecard_id
            ]

        except KeyError as exc:
            raise TimecardError(
                timecard_id
            ) from exc

        worker = self.workers[
            card.worker_id
        ]

        rate = (
            worker
            .burdened_rate_cents_per_hour
        )

        regular = int(
            round(
                rate
                * card.regular_hours
            )
        )

        overtime = int(
            round(
                rate
                * 1.5
                * card.overtime_hours
            )
        )

        doubletime = int(
            round(
                rate
                * 2.0
                * card.doubletime_hours
            )
        )

        return LaborCostResult(
            timecard_id=(
                timecard_id
            ),
            worker_id=(
                worker.worker_id
            ),
            regular_cost_cents=(
                regular
            ),
            overtime_cost_cents=(
                overtime
            ),
            doubletime_cost_cents=(
                doubletime
            ),
            total_cost_cents=(
                regular
                + overtime
                + doubletime
            ),
        )

    # ========================================================
    # EQUIPMENT
    # ========================================================

    def create_equipment(
        self,
        *,
        name: str,
        asset_number: str,
        hourly_cost_cents: int,
        actor_id: str,
    ) -> EquipmentAsset:
        equipment = EquipmentAsset(
            equipment_id=_id(
                "equip"
            ),
            name=_required(
                name,
                "equipment name",
            ),
            asset_number=_required(
                asset_number,
                "asset_number",
            ),
            hourly_cost_cents=(
                _money(
                    hourly_cost_cents,
                    "hourly_cost_cents",
                )
            ),
        )

        self.equipment[
            equipment.equipment_id
        ] = equipment

        self._audit(
            event_type=(
                "equipment.asset_created"
            ),
            actor_id=actor_id,
            payload={
                "equipment_id":
                    equipment.equipment_id,
                "asset_number":
                    asset_number,
            },
        )

        return equipment

    def record_equipment_usage(
        self,
        *,
        equipment_id: str,
        project_id: str,
        cost_code: str,
        work_date: date,
        hours: float,
        actor_id: str,
        operator_worker_id: str | None = None,
    ) -> EquipmentUsage:
        try:
            asset = self.equipment[
                equipment_id
            ]

        except KeyError as exc:
            raise EquipmentNotFound(
                equipment_id
            ) from exc

        if (
            asset.status
            in {
                EquipmentStatus.DOWN,
                EquipmentStatus
                .MAINTENANCE,
                EquipmentStatus.RETIRED,
            }
        ):
            raise FieldValidationError(
                "equipment unavailable"
            )

        hours = _finite_nonnegative(
            hours,
            "hours",
        )

        if operator_worker_id:
            if (
                operator_worker_id
                not in self.workers
            ):
                raise WorkerNotFound(
                    operator_worker_id
                )

        cost = int(
            round(
                asset.hourly_cost_cents
                * hours
            )
        )

        usage = EquipmentUsage(
            usage_id=_id(
                "equipuse"
            ),
            equipment_id=equipment_id,
            project_id=_required(
                project_id,
                "project_id",
            ),
            cost_code=_required(
                cost_code,
                "cost_code",
            ),
            work_date=work_date,
            hours=hours,
            cost_cents=cost,
            operator_worker_id=(
                operator_worker_id
            ),
            created_at=_now(),
        )

        self.equipment_usage[
            usage.usage_id
        ] = usage

        asset.project_id = (
            project_id
        )

        asset.status = (
            EquipmentStatus.ASSIGNED
        )

        asset.meter_hours += (
            hours
        )

        self._audit(
            event_type=(
                "equipment.usage_recorded"
            ),
            actor_id=actor_id,
            payload={
                "usage_id":
                    usage.usage_id,
                "equipment_id":
                    equipment_id,
                "project_id":
                    project_id,
                "hours":
                    hours,
                "cost_cents":
                    cost,
            },
        )

        return usage

    # ========================================================
    # QA / QC
    # ========================================================

    def create_inspection(
        self,
        *,
        project_id: str,
        cost_code: str,
        inspection_type: str,
        performed_on: date,
        performed_by: str,
        result: InspectionResult,
        items: Sequence[
            InspectionItem
        ],
        actor_id: str,
        drawing_refs: Sequence[str] = (),
        spec_refs: Sequence[str] = (),
        corrective_action: str | None = None,
    ) -> QualityInspection:
        if (
            result
            in {
                InspectionResult.FAIL,
                InspectionResult.HOLD,
            }
            and not corrective_action
        ):
            raise InspectionError(
                "failed/hold inspection requires corrective action"
            )

        inspection = (
            QualityInspection(
                inspection_id=_id(
                    "inspect"
                ),
                project_id=_required(
                    project_id,
                    "project_id",
                ),
                cost_code=_required(
                    cost_code,
                    "cost_code",
                ),
                inspection_type=_required(
                    inspection_type,
                    "inspection_type",
                ),
                performed_on=(
                    performed_on
                ),
                performed_by=_required(
                    performed_by,
                    "performed_by",
                ),
                result=result,
                items=tuple(items),
                drawing_refs=tuple(
                    drawing_refs
                ),
                spec_refs=tuple(
                    spec_refs
                ),
                corrective_action=(
                    corrective_action
                ),
            )
        )

        self.inspections[
            inspection.inspection_id
        ] = inspection

        self._audit(
            event_type=(
                "quality.inspection_created"
            ),
            actor_id=actor_id,
            payload={
                "inspection_id":
                    inspection.inspection_id,
                "project_id":
                    project_id,
                "result":
                    result.value,
            },
        )

        return inspection

    def close_inspection(
        self,
        *,
        inspection_id: str,
        actor_id: str,
    ) -> QualityInspection:
        try:
            inspection = (
                self.inspections[
                    inspection_id
                ]
            )

        except KeyError as exc:
            raise InspectionError(
                inspection_id
            ) from exc

        inspection.closed = True

        self._audit(
            event_type=(
                "quality.inspection_closed"
            ),
            actor_id=actor_id,
            payload={
                "inspection_id":
                    inspection_id
            },
        )

        return inspection

    # ========================================================
    # SAFETY / JSA
    # ========================================================

    def create_jsa(
        self,
        *,
        project_id: str,
        work_date: date,
        activity: str,
        prepared_by: str,
        hazards: Sequence[
            HazardControl
        ],
        attendee_worker_ids: Sequence[
            str
        ],
        actor_id: str,
        crew_id: str | None = None,
    ) -> JobSafetyAnalysis:
        for worker_id in (
            attendee_worker_ids
        ):
            if worker_id not in self.workers:
                raise WorkerNotFound(
                    worker_id
                )

        if (
            crew_id
            and crew_id
            not in self.crews
        ):
            raise CrewNotFound(
                crew_id
            )

        jsa = JobSafetyAnalysis(
            jsa_id=_id(
                "jsa"
            ),
            project_id=_required(
                project_id,
                "project_id",
            ),
            work_date=work_date,
            activity=_required(
                activity,
                "activity",
            ),
            prepared_by=_required(
                prepared_by,
                "prepared_by",
            ),
            crew_id=crew_id,
            hazards=tuple(
                hazards
            ),
            attendee_worker_ids=tuple(
                attendee_worker_ids
            ),
        )

        self.jsas[
            jsa.jsa_id
        ] = jsa

        self._audit(
            event_type=(
                "safety.jsa_created"
            ),
            actor_id=actor_id,
            payload={
                "jsa_id":
                    jsa.jsa_id,
                "project_id":
                    project_id,
                "activity":
                    activity,
                "hazard_count":
                    len(hazards),
            },
        )

        return jsa

    def acknowledge_jsa(
        self,
        *,
        jsa_id: str,
        actor_id: str,
    ) -> JobSafetyAnalysis:
        try:
            jsa = self.jsas[
                jsa_id
            ]

        except KeyError as exc:
            raise FieldOpsError(
                jsa_id
            ) from exc

        jsa.acknowledged = True

        self._audit(
            event_type=(
                "safety.jsa_acknowledged"
            ),
            actor_id=actor_id,
            payload={
                "jsa_id":
                    jsa_id
            },
        )

        return jsa

    # ========================================================
    # RFI
    # ========================================================

    def create_rfi(
        self,
        *,
        project_id: str,
        subject: str,
        question: str,
        created_by: str,
        actor_id: str,
        drawing_refs: Sequence[str] = (),
        spec_refs: Sequence[str] = (),
        cost_code: str | None = None,
        assigned_to: str | None = None,
        due_date: date | None = None,
    ) -> RFI:
        self._rfi_numbers[
            project_id
        ] += 1

        rfi = RFI(
            rfi_id=_id(
                "rfi"
            ),
            project_id=_required(
                project_id,
                "project_id",
            ),
            number=(
                self._rfi_numbers[
                    project_id
                ]
            ),
            subject=_required(
                subject,
                "subject",
            ),
            question=_required(
                question,
                "question",
            ),
            drawing_refs=tuple(
                drawing_refs
            ),
            spec_refs=tuple(
                spec_refs
            ),
            cost_code=cost_code,
            status=RFIStatus.OPEN,
            created_by=_required(
                created_by,
                "created_by",
            ),
            assigned_to=(
                assigned_to
            ),
            due_date=due_date,
        )

        self.rfis[
            rfi.rfi_id
        ] = rfi

        self._audit(
            event_type=(
                "rfi.opened"
            ),
            actor_id=actor_id,
            payload={
                "rfi_id":
                    rfi.rfi_id,
                "project_id":
                    project_id,
                "number":
                    rfi.number,
            },
        )

        return rfi

    def answer_rfi(
        self,
        *,
        rfi_id: str,
        answer: str,
        answered_by: str,
        actor_id: str,
    ) -> RFI:
        try:
            rfi = self.rfis[
                rfi_id
            ]

        except KeyError as exc:
            raise RFIError(
                rfi_id
            ) from exc

        if (
            rfi.status
            != RFIStatus.OPEN
        ):
            raise RFIError(
                "RFI is not open"
            )

        rfi.answer = _required(
            answer,
            "answer",
        )

        rfi.answered_by = _required(
            answered_by,
            "answered_by",
        )

        rfi.answered_at = _now()

        rfi.status = (
            RFIStatus.ANSWERED
        )

        self._audit(
            event_type=(
                "rfi.answered"
            ),
            actor_id=actor_id,
            payload={
                "rfi_id":
                    rfi_id,
                "answered_by":
                    answered_by,
            },
        )

        return rfi

    # ========================================================
    # SUBMITTALS
    # ========================================================

    def create_submittal(
        self,
        *,
        project_id: str,
        title: str,
        actor_id: str,
        spec_section: str | None = None,
        supplier: str | None = None,
        required_on_site: date | None = None,
    ) -> Submittal:
        self._submittal_numbers[
            project_id
        ] += 1

        submittal = Submittal(
            submittal_id=_id(
                "submittal"
            ),
            project_id=_required(
                project_id,
                "project_id",
            ),
            number=(
                self._submittal_numbers[
                    project_id
                ]
            ),
            title=_required(
                title,
                "title",
            ),
            spec_section=(
                spec_section
            ),
            supplier=supplier,
            status=(
                SubmittalStatus.DRAFT
            ),
            required_on_site=(
                required_on_site
            ),
        )

        self.submittals[
            submittal.submittal_id
        ] = submittal

        self._audit(
            event_type=(
                "submittal.created"
            ),
            actor_id=actor_id,
            payload={
                "submittal_id":
                    submittal.submittal_id,
                "project_id":
                    project_id,
                "number":
                    submittal.number,
            },
        )

        return submittal

    def submit_submittal(
        self,
        *,
        submittal_id: str,
        submitted_on: date,
        actor_id: str,
    ) -> Submittal:
        try:
            submittal = (
                self.submittals[
                    submittal_id
                ]
            )

        except KeyError as exc:
            raise SubmittalError(
                submittal_id
            ) from exc

        if (
            submittal.status
            not in {
                SubmittalStatus.DRAFT,
                SubmittalStatus
                .REVISE_RESUBMIT,
            }
        ):
            raise SubmittalError(
                "submittal cannot be submitted"
            )

        if (
            submittal.status
            == SubmittalStatus
            .REVISE_RESUBMIT
        ):
            submittal.revision += 1

        submittal.status = (
            SubmittalStatus.SUBMITTED
        )

        submittal.submitted_on = (
            submitted_on
        )

        self._audit(
            event_type=(
                "submittal.submitted"
            ),
            actor_id=actor_id,
            payload={
                "submittal_id":
                    submittal_id,
                "revision":
                    submittal.revision,
            },
        )

        return submittal

    def review_submittal(
        self,
        *,
        submittal_id: str,
        status: SubmittalStatus,
        returned_on: date,
        review_notes: str | None,
        actor_id: str,
    ) -> Submittal:
        allowed = {
            SubmittalStatus.APPROVED,
            SubmittalStatus
            .APPROVED_AS_NOTED,
            SubmittalStatus
            .REVISE_RESUBMIT,
            SubmittalStatus.REJECTED,
        }

        if status not in allowed:
            raise SubmittalError(
                "invalid review status"
            )

        try:
            submittal = (
                self.submittals[
                    submittal_id
                ]
            )

        except KeyError as exc:
            raise SubmittalError(
                submittal_id
            ) from exc

        if (
            submittal.status
            != SubmittalStatus.SUBMITTED
        ):
            raise SubmittalError(
                "submittal is not under review"
            )

        submittal.status = status

        submittal.returned_on = (
            returned_on
        )

        submittal.review_notes = (
            review_notes
        )

        self._audit(
            event_type=(
                "submittal.reviewed"
            ),
            actor_id=actor_id,
            payload={
                "submittal_id":
                    submittal_id,
                "status":
                    status.value,
            },
        )

        return submittal

    # ========================================================
    # PUNCH
    # ========================================================

    def create_punch_item(
        self,
        *,
        project_id: str,
        location: str,
        description: str,
        created_by: str,
        actor_id: str,
        assigned_to: str | None = None,
        due_date: date | None = None,
        photo_refs: Sequence[str] = (),
    ) -> PunchItem:
        item = PunchItem(
            punch_id=_id(
                "punch"
            ),
            project_id=_required(
                project_id,
                "project_id",
            ),
            location=_required(
                location,
                "location",
            ),
            description=_required(
                description,
                "description",
            ),
            assigned_to=(
                assigned_to
            ),
            due_date=due_date,
            status=(
                PunchStatus.OPEN
            ),
            created_by=_required(
                created_by,
                "created_by",
            ),
            photo_refs=tuple(
                photo_refs
            ),
        )

        self.punch_items[
            item.punch_id
        ] = item

        self._audit(
            event_type=(
                "punch.created"
            ),
            actor_id=actor_id,
            payload={
                "punch_id":
                    item.punch_id,
                "project_id":
                    project_id,
            },
        )

        return item

    def close_punch_item(
        self,
        *,
        punch_id: str,
        actor_id: str,
    ) -> PunchItem:
        try:
            item = self.punch_items[
                punch_id
            ]

        except KeyError as exc:
            raise FieldOpsError(
                punch_id
            ) from exc

        item.status = (
            PunchStatus.CLOSED
        )

        item.closed_at = _now()

        self._audit(
            event_type=(
                "punch.closed"
            ),
            actor_id=actor_id,
            payload={
                "punch_id":
                    punch_id
            },
        )

        return item

    # ========================================================
    # COMPLIANCE
    # ========================================================

    def create_subcontractor(
        self,
        *,
        company_name: str,
        actor_id: str,
    ) -> SubcontractorCompliance:
        subcontractor = (
            SubcontractorCompliance(
                subcontractor_id=_id(
                    "sub"
                ),
                company_name=_required(
                    company_name,
                    "company_name",
                ),
            )
        )

        self.subcontractors[
            subcontractor
            .subcontractor_id
        ] = subcontractor

        self._audit(
            event_type=(
                "compliance.subcontractor_created"
            ),
            actor_id=actor_id,
            payload={
                "subcontractor_id":
                    subcontractor
                    .subcontractor_id,
                "company":
                    company_name,
            },
        )

        return subcontractor

    def upsert_compliance_document(
        self,
        *,
        subcontractor_id: str,
        document_type: str,
        status: ComplianceStatus,
        actor_id: str,
        expires_on: date | None = None,
        reference: str | None = None,
    ) -> ComplianceDocument:
        try:
            subcontractor = (
                self.subcontractors[
                    subcontractor_id
                ]
            )

        except KeyError as exc:
            raise ComplianceError(
                subcontractor_id
            ) from exc

        document = (
            ComplianceDocument(
                document_id=_id(
                    "compdoc"
                ),
                document_type=_required(
                    document_type,
                    "document_type",
                ),
                status=status,
                expires_on=expires_on,
                reference=reference,
            )
        )

        subcontractor.documents[
            document.document_id
        ] = document

        normalized = (
            document_type
            .strip()
            .lower()
        )

        if normalized in {
            "insurance",
            "coi",
        }:
            subcontractor.insurance_status = (
                status
            )

        elif normalized == "w9":
            subcontractor.w9_status = (
                status
            )

        elif normalized in {
            "subcontract",
            "agreement",
        }:
            subcontractor.agreement_status = (
                status
            )

        elif normalized in {
            "safety",
            "safety_program",
        }:
            subcontractor.safety_status = (
                status
            )

        self._audit(
            event_type=(
                "compliance.document_updated"
            ),
            actor_id=actor_id,
            payload={
                "subcontractor_id":
                    subcontractor_id,
                "document_id":
                    document.document_id,
                "type":
                    document_type,
                "status":
                    status.value,
            },
        )

        return document

    def compliance_state(
        self,
        *,
        subcontractor_id: str,
        as_of: date,
    ) -> ComplianceStatus:
        try:
            subcontractor = (
                self.subcontractors[
                    subcontractor_id
                ]
            )

        except KeyError as exc:
            raise ComplianceError(
                subcontractor_id
            ) from exc

        states = []

        for document in (
            subcontractor
            .documents
            .values()
        ):
            if (
                document.expires_on
                is not None
                and document.expires_on
                < as_of
            ):
                states.append(
                    ComplianceStatus.EXPIRED
                )

            else:
                states.append(
                    document.status
                )

        if not states:
            return (
                ComplianceStatus.UNKNOWN
            )

        if any(
            item
            in {
                ComplianceStatus
                .NONCOMPLIANT,
                ComplianceStatus
                .EXPIRED,
            }
            for item
            in states
        ):
            return (
                ComplianceStatus
                .NONCOMPLIANT
            )

        if all(
            item
            == ComplianceStatus
            .COMPLIANT
            for item
            in states
        ):
            return (
                ComplianceStatus.COMPLIANT
            )

        return ComplianceStatus.PENDING

    # ========================================================
    # LIEN WAIVERS / PAY APPS
    # ========================================================

    def create_waiver(
        self,
        *,
        subcontractor_id: str,
        project_id: str,
        waiver_type: WaiverType,
        through_date: date,
        amount_cents: int,
        signed: bool,
        actor_id: str,
        reference: str | None = None,
    ) -> LienWaiver:
        if (
            subcontractor_id
            not in self.subcontractors
        ):
            raise ComplianceError(
                subcontractor_id
            )

        waiver = LienWaiver(
            waiver_id=_id(
                "waiver"
            ),
            subcontractor_id=(
                subcontractor_id
            ),
            project_id=_required(
                project_id,
                "project_id",
            ),
            waiver_type=waiver_type,
            through_date=(
                through_date
            ),
            amount_cents=(
                _money(
                    amount_cents,
                    "amount_cents",
                )
            ),
            signed=bool(
                signed
            ),
            reference=reference,
        )

        self.waivers[
            waiver.waiver_id
        ] = waiver

        self._audit(
            event_type=(
                "compliance.lien_waiver_created"
            ),
            actor_id=actor_id,
            payload={
                "waiver_id":
                    waiver.waiver_id,
                "subcontractor_id":
                    subcontractor_id,
                "signed":
                    signed,
            },
        )

        return waiver

    def create_pay_app(
        self,
        *,
        subcontractor_id: str,
        project_id: str,
        cost_code: str,
        period_end: date,
        gross_amount_cents: int,
        retainage_cents: int,
        actor_id: str,
        waiver_id: str | None = None,
    ) -> PayApplication:
        if (
            subcontractor_id
            not in self.subcontractors
        ):
            raise ComplianceError(
                subcontractor_id
            )

        gross_amount_cents = _money(
            gross_amount_cents,
            "gross_amount_cents",
        )

        retainage_cents = _money(
            retainage_cents,
            "retainage_cents",
        )

        if (
            retainage_cents
            > gross_amount_cents
        ):
            raise FieldValidationError(
                "retainage exceeds gross amount"
            )

        if waiver_id:
            waiver = self.waivers.get(
                waiver_id
            )

            if (
                waiver is None
                or not waiver.signed
            ):
                raise ComplianceError(
                    "linked lien waiver invalid or unsigned"
                )

        pay_app = PayApplication(
            pay_app_id=_id(
                "payapp"
            ),
            subcontractor_id=(
                subcontractor_id
            ),
            project_id=_required(
                project_id,
                "project_id",
            ),
            cost_code=_required(
                cost_code,
                "cost_code",
            ),
            period_end=period_end,
            gross_amount_cents=(
                gross_amount_cents
            ),
            retainage_cents=(
                retainage_cents
            ),
            waiver_id=waiver_id,
        )

        self.pay_apps[
            pay_app.pay_app_id
        ] = pay_app

        self._audit(
            event_type=(
                "billing.pay_app_created"
            ),
            actor_id=actor_id,
            payload={
                "pay_app_id":
                    pay_app.pay_app_id,
                "subcontractor_id":
                    subcontractor_id,
                "gross_amount_cents":
                    gross_amount_cents,
            },
        )

        return pay_app

    def submit_pay_app(
        self,
        *,
        pay_app_id: str,
        actor_id: str,
        as_of: date,
    ) -> PayApplication:
        try:
            pay_app = self.pay_apps[
                pay_app_id
            ]

        except KeyError as exc:
            raise FieldOpsError(
                pay_app_id
            ) from exc

        compliance = (
            self.compliance_state(
                subcontractor_id=(
                    pay_app
                    .subcontractor_id
                ),
                as_of=as_of,
            )
        )

        if (
            compliance
            != ComplianceStatus
            .COMPLIANT
        ):
            raise ComplianceError(
                "subcontractor not compliant"
            )

        if pay_app.waiver_id:
            waiver = self.waivers[
                pay_app.waiver_id
            ]

            if not waiver.signed:
                raise ComplianceError(
                    "lien waiver unsigned"
                )

        pay_app.status = (
            PayAppStatus.SUBMITTED
        )

        self._audit(
            event_type=(
                "billing.pay_app_submitted"
            ),
            actor_id=actor_id,
            payload={
                "pay_app_id":
                    pay_app_id
            },
        )

        return pay_app

    def approve_pay_app(
        self,
        *,
        pay_app_id: str,
        approved_amount_cents: int,
        actor_id: str,
    ) -> PayApplication:
        try:
            pay_app = self.pay_apps[
                pay_app_id
            ]

        except KeyError as exc:
            raise FieldOpsError(
                pay_app_id
            ) from exc

        if (
            pay_app.status
            != PayAppStatus.SUBMITTED
        ):
            raise FieldOpsError(
                "pay app must be submitted"
            )

        approved_amount_cents = (
            _money(
                approved_amount_cents,
                "approved_amount_cents",
            )
        )

        if (
            approved_amount_cents
            > pay_app
            .net_requested_cents
        ):
            raise FieldValidationError(
                "approval exceeds net requested"
            )

        pay_app.approved_amount_cents = (
            approved_amount_cents
        )

        pay_app.status = (
            PayAppStatus.APPROVED
        )

        self._audit(
            event_type=(
                "billing.pay_app_approved"
            ),
            actor_id=actor_id,
            payload={
                "pay_app_id":
                    pay_app_id,
                "approved_amount_cents":
                    approved_amount_cents,
            },
        )

        return pay_app

    # ========================================================
    # MOBILE SYNC
    # ========================================================

    def apply_mobile_mutation(
        self,
        *,
        mutation: MobileMutation,
        actor_id: str,
    ) -> SyncResult:
        key = (
            mutation.entity_type,
            mutation.entity_id,
        )

        current = (
            self.mobile_entities
            .get(key)
        )

        current_version = (
            current.version
            if current
            else 0
        )

        if (
            mutation.base_version
            != current_version
        ):
            return SyncResult(
                mutation_id=(
                    mutation.mutation_id
                ),
                accepted=False,
                server_version=(
                    current_version
                ),
                conflict=True,
                reason=(
                    "base version does not "
                    "match server version"
                ),
            )

        next_version = (
            current_version
            + 1
        )

        if (
            mutation.mutation_type
            == SyncMutationType.DELETE
        ):
            payload = {
                "_deleted":
                    True
            }

        else:
            payload = dict(
                mutation.payload
            )

        self.mobile_entities[
            key
        ] = VersionedMobileEntity(
            entity_type=(
                mutation.entity_type
            ),
            entity_id=(
                mutation.entity_id
            ),
            version=(
                next_version
            ),
            payload=payload,
            updated_at=_now(),
        )

        self._audit(
            event_type=(
                "mobile.mutation_applied"
            ),
            actor_id=actor_id,
            payload={
                "mutation_id":
                    mutation.mutation_id,
                "device_id":
                    mutation.device_id,
                "entity_type":
                    mutation.entity_type,
                "entity_id":
                    mutation.entity_id,
                "server_version":
                    next_version,
            },
        )

        return SyncResult(
            mutation_id=(
                mutation.mutation_id
            ),
            accepted=True,
            server_version=(
                next_version
            ),
            conflict=False,
        )

    # ========================================================
    # EXECUTION COST BRIDGE
    # ========================================================

    def post_approved_timecard_to_execution(
        self,
        *,
        timecard_id: str,
        execution_service: Any,
        tenant_id: str,
        actor_id: str,
    ) -> Any:
        try:
            card = self.timecards[
                timecard_id
            ]

        except KeyError as exc:
            raise TimecardError(
                timecard_id
            ) from exc

        if (
            card.status
            != TimecardStatus.APPROVED
        ):
            raise TimecardError(
                "timecard must be approved before posting"
            )

        cost = self.labor_cost(
            timecard_id=timecard_id
        )

        from leadbot_v2.goat.execution import (
            CostCategory,
        )

        result = (
            execution_service
            .record_actual_cost(
                tenant_id=tenant_id,
                project_id=(
                    card.project_id
                ),
                cost_code=(
                    card.cost_code
                ),
                category=(
                    CostCategory.LABOR
                ),
                amount_cents=(
                    cost.total_cost_cents
                ),
                incurred_on=(
                    card.work_date
                ),
                description=(
                    "Approved GOAT field timecard "
                    + timecard_id
                ),
                source_reference=(
                    "field-timecard:"
                    + timecard_id
                ),
                actor_id=actor_id,
                idempotency_key=(
                    "field-timecard:"
                    + timecard_id
                ),
            )
        )

        card.status = (
            TimecardStatus.POSTED
        )

        self._audit(
            event_type=(
                "labor.timecard_posted_to_job_cost"
            ),
            actor_id=actor_id,
            payload={
                "timecard_id":
                    timecard_id,
                "cost_cents":
                    cost.total_cost_cents,
            },
        )

        return result

    def post_equipment_usage_to_execution(
        self,
        *,
        usage_id: str,
        execution_service: Any,
        tenant_id: str,
        actor_id: str,
    ) -> Any:
        try:
            usage = self.equipment_usage[
                usage_id
            ]

        except KeyError as exc:
            raise EquipmentNotFound(
                usage_id
            ) from exc

        from leadbot_v2.goat.execution import (
            CostCategory,
        )

        return (
            execution_service
            .record_actual_cost(
                tenant_id=tenant_id,
                project_id=(
                    usage.project_id
                ),
                cost_code=(
                    usage.cost_code
                ),
                category=(
                    CostCategory.EQUIPMENT
                ),
                amount_cents=(
                    usage.cost_cents
                ),
                incurred_on=(
                    usage.work_date
                ),
                description=(
                    "GOAT equipment usage "
                    + usage.equipment_id
                ),
                source_reference=(
                    "field-equipment:"
                    + usage.usage_id
                ),
                actor_id=actor_id,
                idempotency_key=(
                    "field-equipment:"
                    + usage.usage_id
                ),
            )
        )

    # ========================================================
    # COMMAND CENTER
    # ========================================================

    def command_snapshot(
        self,
        *,
        project_id: str,
        as_of: date,
    ) -> FieldCommandSnapshot:
        approved_cards = [
            card
            for card
            in self.timecards.values()
            if (
                card.project_id
                == project_id
                and card.work_date
                <= as_of
                and card.status
                in {
                    TimecardStatus.APPROVED,
                    TimecardStatus.POSTED,
                }
            )
        ]

        active_workers = {
            card.worker_id
            for card
            in approved_cards
        }

        approved_hours = sum(
            card.total_hours
            for card
            in approved_cards
        )

        labor_cost = sum(
            self.labor_cost(
                timecard_id=(
                    card.timecard_id
                )
            ).total_cost_cents
            for card
            in approved_cards
        )

        equipment_usage = [
            item
            for item
            in self
            .equipment_usage
            .values()
            if (
                item.project_id
                == project_id
                and item.work_date
                <= as_of
            )
        ]

        equipment_cost = sum(
            item.cost_cents
            for item
            in equipment_usage
        )

        open_rfis = [
            item
            for item
            in self.rfis.values()
            if (
                item.project_id
                == project_id
                and item.status
                == RFIStatus.OPEN
            )
        ]

        overdue_rfis = [
            item
            for item
            in open_rfis
            if (
                item.due_date
                is not None
                and item.due_date
                < as_of
            )
        ]

        open_submittals = [
            item
            for item
            in self.submittals.values()
            if (
                item.project_id
                == project_id
                and item.status
                not in {
                    SubmittalStatus
                    .APPROVED,
                    SubmittalStatus
                    .APPROVED_AS_NOTED,
                    SubmittalStatus
                    .CLOSED,
                }
            )
        ]

        late_submittals = [
            item
            for item
            in open_submittals
            if (
                item.required_on_site
                is not None
                and item.required_on_site
                < as_of
            )
        ]

        failed_inspections = [
            item
            for item
            in self.inspections.values()
            if (
                item.project_id
                == project_id
                and not item.closed
                and item.result
                in {
                    InspectionResult.FAIL,
                    InspectionResult.HOLD,
                }
            )
        ]

        open_punch = [
            item
            for item
            in self
            .punch_items
            .values()
            if (
                item.project_id
                == project_id
                and item.status
                != PunchStatus.CLOSED
            )
        ]

        noncompliant = []

        for subcontractor in (
            self
            .subcontractors
            .values()
        ):
            state = (
                self.compliance_state(
                    subcontractor_id=(
                        subcontractor
                        .subcontractor_id
                    ),
                    as_of=as_of,
                )
            )

            if (
                state
                in {
                    ComplianceStatus
                    .NONCOMPLIANT,
                    ComplianceStatus
                    .EXPIRED,
                }
            ):
                noncompliant.append(
                    subcontractor
                )

        risks = []

        def add(
            severity: FieldRiskSeverity,
            code: str,
            title: str,
            evidence: str,
            action: str,
        ) -> None:
            risks.append(
                FieldRisk(
                    risk_id=(
                        "risk_"
                        + _hash(
                            {
                                "project":
                                    project_id,
                                "as_of":
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
                    recommended_action=action,
                )
            )

        if overdue_rfis:
            add(
                FieldRiskSeverity.HIGH,
                "OVERDUE_RFI",
                "RFI decisions are overdue",
                (
                    f"{len(overdue_rfis)} "
                    "RFI(s) past due"
                ),
                (
                    "Escalate design response and "
                    "document schedule/cost exposure."
                ),
            )

        if late_submittals:
            add(
                FieldRiskSeverity.HIGH,
                "LATE_SUBMITTAL",
                "Submittal cycle threatens required-on-site date",
                (
                    f"{len(late_submittals)} "
                    "late submittal(s)"
                ),
                (
                    "Escalate supplier/reviewer cycle "
                    "and approved substitution path."
                ),
            )

        if failed_inspections:
            add(
                FieldRiskSeverity.HIGH,
                "OPEN_QAQC_FAILURE",
                "Failed or hold inspections remain open",
                (
                    f"{len(failed_inspections)} "
                    "inspection(s)"
                ),
                (
                    "Complete corrective action and "
                    "document reinspection before covering work."
                ),
            )

        if noncompliant:
            add(
                FieldRiskSeverity.HIGH,
                "SUBCONTRACTOR_COMPLIANCE",
                "Subcontractor compliance issue detected",
                (
                    f"{len(noncompliant)} "
                    "noncompliant subcontractor(s)"
                ),
                (
                    "Resolve required company compliance "
                    "before affected payment/work authorization."
                ),
            )

        critical_jsas = [
            item
            for item
            in self.jsas.values()
            if (
                item.project_id
                == project_id
                and item.work_date
                == as_of
                and any(
                    hazard.severity
                    >= SafetySeverity.CRITICAL
                    for hazard
                    in item.hazards
                )
                and not item.acknowledged
            )
        ]

        if critical_jsas:
            add(
                FieldRiskSeverity.CRITICAL,
                "UNACKNOWLEDGED_CRITICAL_JSA",
                "Critical-risk JSA remains unacknowledged",
                (
                    f"{len(critical_jsas)} "
                    "critical JSA(s)"
                ),
                (
                    "Require project-specific competent-person "
                    "review and documented acknowledgment."
                ),
            )

        overtime_hours = sum(
            card.overtime_hours
            + card.doubletime_hours
            for card
            in approved_cards
        )

        if (
            approved_hours >= 40
            and overtime_hours
            / approved_hours
            > 0.20
        ):
            add(
                FieldRiskSeverity.REVIEW,
                "HIGH_OVERTIME",
                "Overtime utilization is elevated",
                (
                    f"{overtime_hours:.1f} overtime/doubletime "
                    f"hours of {approved_hours:.1f} total"
                ),
                (
                    "Review manpower plan, productivity, "
                    "schedule pressure and labor-cost forecast."
                ),
            )

        deductions = {
            FieldRiskSeverity.INFO:
                1,
            FieldRiskSeverity.REVIEW:
                5,
            FieldRiskSeverity.HIGH:
                12,
            FieldRiskSeverity.CRITICAL:
                25,
        }

        score = max(
            0,
            100
            - sum(
                deductions[
                    risk.severity
                ]
                for risk
                in risks
            ),
        )

        risks.sort(
            key=lambda item: (
                -int(item.severity),
                item.code,
            )
        )

        return FieldCommandSnapshot(
            project_id=project_id,
            as_of=as_of,
            active_workers=len(
                active_workers
            ),
            approved_hours=(
                approved_hours
            ),
            labor_cost_cents=(
                labor_cost
            ),
            equipment_cost_cents=(
                equipment_cost
            ),
            open_rfis=len(
                open_rfis
            ),
            overdue_rfis=len(
                overdue_rfis
            ),
            open_submittals=len(
                open_submittals
            ),
            late_submittals=len(
                late_submittals
            ),
            failed_inspections=len(
                failed_inspections
            ),
            open_punch_items=len(
                open_punch
            ),
            noncompliant_subcontractors=(
                len(noncompliant)
            ),
            risks=tuple(
                risks
            ),
            health_score=score,
        )
