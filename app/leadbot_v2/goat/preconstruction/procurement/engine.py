from __future__ import annotations

import hashlib
import json
import math
import uuid

from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from typing import Any


class ProcurementError(RuntimeError):
    pass


class ProcurementNotFound(ProcurementError):
    pass


class ProcurementConflict(ProcurementError):
    pass


class ProcurementBlocked(ProcurementError):
    pass


class ProcurementAuditError(ProcurementError):
    pass


class SupplierKind(str, Enum):
    MATERIAL_SUPPLIER = "material_supplier"
    SUBCONTRACTOR = "subcontractor"
    EQUIPMENT_RENTAL = "equipment_rental"
    FABRICATOR = "fabricator"
    SERVICE_PROVIDER = "service_provider"
    MANUFACTURER = "manufacturer"
    DISTRIBUTOR = "distributor"
    OTHER = "other"


class ProcurementTrade(str, Enum):
    CONCRETE = "concrete"
    REBAR = "rebar"
    FORMWORK = "formwork"
    EARTHWORK = "earthwork"
    AGGREGATES = "aggregates"
    ELECTRICAL = "electrical"
    PLUMBING = "plumbing"
    MECHANICAL = "mechanical"
    FIRE_PROTECTION = "fire_protection"
    STRUCTURAL_STEEL = "structural_steel"
    WATERPROOFING = "waterproofing"
    MASONRY = "masonry"
    ROOFING = "roofing"
    DRYWALL = "drywall"
    FINISHES = "finishes"
    EQUIPMENT = "equipment"
    LOGISTICS = "logistics"
    OTHER = "other"


class RFQState(str, Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    RECEIVING = "receiving"
    LEVELING = "leveling"
    RECOMMENDATION_READY = "recommendation_ready"
    AWARDED = "awarded"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class QuoteState(str, Enum):
    RECEIVED = "received"
    REVIEW = "review"
    COMPARABLE = "comparable"
    NONCOMPARABLE = "noncomparable"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"
    AWARDED = "awarded"
    REJECTED = "rejected"


class QuoteDisposition(str, Enum):
    RECOMMENDED = "recommended"
    ALTERNATE = "alternate"
    REVIEW = "review"
    REJECT = "reject"


class FindingSeverity(str, Enum):
    INFO = "info"
    REVIEW = "review"
    BLOCKER = "blocker"


class ComplianceStatus(str, Enum):
    CURRENT = "current"
    EXPIRING = "expiring"
    EXPIRED = "expired"
    MISSING = "missing"
    NOT_REQUIRED = "not_required"


class CoverageStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING = "missing"
    EXTRA = "extra"


class CostTreatment(str, Enum):
    INCLUDED = "included"
    ADDITIONAL = "additional"
    EXCLUDED = "excluded"
    UNKNOWN = "unknown"


class AwardState(str, Enum):
    RECOMMENDED = "recommended"
    APPROVED = "approved"
    AWARDED = "awarded"
    REJECTED = "rejected"


@dataclass(frozen=True)
class SupplierContact:
    name: str
    email: str | None = None
    phone: str | None = None
    role: str | None = None


@dataclass(frozen=True)
class SupplierCompliance:
    w9_on_file: bool = False

    insurance_required: bool = False
    insurance_expiration: date | None = None

    safety_program_required: bool = False
    safety_program_on_file: bool = False

    license_required: bool = False
    license_current: bool = False

    bondable_required: bool = False
    bondable: bool | None = None

    approved_vendor: bool = False

    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SupplierPerformance:
    completed_projects: int = 0
    on_time_projects: int = 0
    quality_issue_count: int = 0
    change_order_issue_count: int = 0
    payment_dispute_count: int = 0
    safety_issue_count: int = 0
    response_count: int = 0
    invitation_count: int = 0
    award_count: int = 0

    @property
    def on_time_rate(self) -> float | None:
        if self.completed_projects <= 0:
            return None

        return (
            self.on_time_projects
            / self.completed_projects
        )

    @property
    def award_rate(self) -> float | None:
        if self.invitation_count <= 0:
            return None

        return (
            self.award_count
            / self.invitation_count
        )


@dataclass(frozen=True)
class Supplier:
    supplier_id: str

    tenant_id: str
    business_unit_id: str

    name: str
    kind: SupplierKind

    trades: tuple[
        ProcurementTrade,
        ...
    ]

    regions: tuple[str, ...]

    contacts: tuple[
        SupplierContact,
        ...
    ]

    compliance: SupplierCompliance
    performance: SupplierPerformance

    active: bool

    created_at: datetime
    updated_at: datetime

    version: int


@dataclass(frozen=True)
class RFQScopeLine:
    scope_line_id: str

    scope_key: str

    description: str

    trade: ProcurementTrade

    quantity: Decimal

    unit: str

    cost_code: str | None = None

    drawing_refs: tuple[str, ...] = ()
    specification_refs: tuple[str, ...] = ()

    required: bool = True

    allowance: bool = False

    alternate: bool = False


@dataclass(frozen=True)
class RFQPackage:
    rfq_id: str

    tenant_id: str
    business_unit_id: str

    project_id: str | None
    opportunity_id: str | None

    bid_package_id: str | None
    bid_package_revision_id: str | None

    estimate_id: str | None

    project_name: str

    trade: ProcurementTrade

    scope_lines: tuple[
        RFQScopeLine,
        ...
    ]

    invited_supplier_ids: tuple[
        str,
        ...
    ]

    due_at: datetime | None

    state: RFQState

    created_at: datetime
    updated_at: datetime

    created_by: str

    version: int


@dataclass(frozen=True)
class QuoteLine:
    quote_line_id: str

    scope_key: str

    description: str

    quoted_quantity: Decimal | None

    unit: str

    unit_price_cents: int | None

    lump_sum_cents: int | None

    included: bool

    notes: tuple[str, ...] = ()

    source_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class QuoteCommercialTerms:
    tax_treatment: CostTreatment
    tax_cents: int | None

    freight_treatment: CostTreatment
    freight_cents: int | None

    mobilization_treatment: CostTreatment
    mobilization_cents: int | None

    bond_treatment: CostTreatment
    bond_cents: int | None

    escalation_treatment: CostTreatment

    payment_terms: str | None

    retainage_percent: Decimal | None

    validity_through: date | None

    estimated_lead_days: int | None

    earliest_delivery_date: date | None

    schedule_notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SupplierQuote:
    quote_id: str

    rfq_id: str
    supplier_id: str

    quote_number: str | None

    received_at: datetime

    lines: tuple[
        QuoteLine,
        ...
    ]

    terms: QuoteCommercialTerms

    exclusions: tuple[str, ...]
    qualifications: tuple[str, ...]
    alternates: tuple[str, ...]

    source_refs: tuple[str, ...]

    state: QuoteState

    created_by: str

    version: int


@dataclass(frozen=True)
class QuoteFinding:
    code: str
    severity: FindingSeverity
    message: str

    scope_key: str | None = None
    quote_id: str | None = None
    supplier_id: str | None = None
    source_ref: str | None = None


@dataclass(frozen=True)
class LeveledScopeLine:
    scope_key: str

    description: str

    required_quantity: Decimal

    quoted_quantity: Decimal | None

    normalized_quantity: Decimal

    unit: str

    normalized_cost_cents: int | None

    coverage: CoverageStatus

    findings: tuple[
        QuoteFinding,
        ...
    ]


@dataclass(frozen=True)
class SupplierRiskProfile:
    supplier_id: str

    compliance_score: float
    performance_score: float
    schedule_score: float
    commercial_score: float

    overall_score: float

    findings: tuple[
        QuoteFinding,
        ...
    ]


@dataclass(frozen=True)
class LeveledQuote:
    quote_id: str
    supplier_id: str

    scope_lines: tuple[
        LeveledScopeLine,
        ...
    ]

    normalized_scope_cost_cents: int | None

    normalized_tax_cents: int | None
    normalized_freight_cents: int | None
    normalized_mobilization_cents: int | None
    normalized_bond_cents: int | None

    normalized_total_cents: int | None

    covered_required_scope_count: int
    required_scope_count: int

    coverage_percent: float

    risk: SupplierRiskProfile

    findings: tuple[
        QuoteFinding,
        ...
    ]

    comparable: bool

    expired: bool


@dataclass(frozen=True)
class QuoteRecommendation:
    rfq_id: str

    quote_id: str
    supplier_id: str

    disposition: QuoteDisposition

    normalized_total_cents: int | None

    evaluated_cost_cents: int | None

    coverage_percent: float

    supplier_risk_score: float

    value_score: float

    rank: int | None

    findings: tuple[
        QuoteFinding,
        ...
    ]


@dataclass(frozen=True)
class ProcurementRateCandidate:
    supplier_id: str
    quote_id: str

    scope_key: str
    description: str

    unit: str

    normalized_unit_price_cents: int

    quantity_basis: Decimal

    effective_date: date
    expiration_date: date | None

    source_refs: tuple[str, ...]

    confidence: float


@dataclass(frozen=True)
class AwardRecommendation:
    recommendation_id: str

    rfq_id: str

    selected_quote_id: str
    selected_supplier_id: str

    normalized_total_cents: int

    evaluated_cost_cents: int

    recommendation: QuoteDisposition

    reason: str

    comparison: tuple[
        QuoteRecommendation,
        ...
    ]

    generated_at: datetime


@dataclass(frozen=True)
class ProcurementAward:
    award_id: str

    rfq_id: str
    quote_id: str
    supplier_id: str

    awarded_amount_cents: int

    approved_by: str
    approved_at: datetime

    note: str

    state: AwardState


@dataclass(frozen=True)
class ProcurementAuditRecord:
    event_id: str

    aggregate_id: str

    sequence: int

    action: str

    actor_id: str

    occurred_at: datetime

    previous_hash: str

    payload_hash: str

    event_hash: str


def _now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def _id(
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


def _decimal(
    value: Any,
    field: str,
    *,
    allow_zero: bool = False,
) -> Decimal:
    try:
        result = Decimal(
            str(
                value
            )
        )
    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            f"{field} must be numeric"
        ) from exc

    if not result.is_finite():
        raise ValueError(
            f"{field} must be finite"
        )

    if allow_zero:
        if result < 0:
            raise ValueError(
                f"{field} cannot be negative"
            )

    elif result <= 0:
        raise ValueError(
            f"{field} must be positive"
        )

    return result


def _money(
    value: Any,
    field: str,
    *,
    allow_none: bool = False,
) -> int | None:
    if value is None:
        if allow_none:
            return None

        raise ValueError(
            f"{field} is required"
        )

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
        date,
    ):
        return value.isoformat()

    if isinstance(
        value,
        Decimal,
    ):
        return str(
            value
        )

    if isinstance(
        value,
        dict,
    ):
        return {
            str(
                key
            ):
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


def _round_cents(
    value: Decimal,
) -> int:
    return int(
        value.quantize(
            Decimal("1"),
            rounding=(
                ROUND_HALF_UP
            ),
        )
    )


def _ratio(
    numerator: int,
    denominator: int,
) -> float:
    if denominator <= 0:
        return 0.0

    return (
        numerator
        / denominator
    )


class QuoteLevelingEngine:
    """
    Deterministic commercial quote-leveling engine.

    It does not assume the low quote is the best quote.

    A quote must first be normalized against the authoritative RFQ scope.
    Missing scope, excluded scope, unresolved commercial terms, stale
    validity, unit mismatch, quantity mismatch, schedule issues, and vendor
    risk are explicitly represented.

    The engine never invents a missing quote value.
    """

    def __init__(
        self,
        *,
        compliance_expiring_days: int = 30,
        evaluated_risk_penalty_bps: int = 1500,
    ) -> None:
        if compliance_expiring_days < 0:
            raise ValueError(
                "compliance_expiring_days cannot be negative"
            )

        if (
            evaluated_risk_penalty_bps
            < 0
        ):
            raise ValueError(
                "evaluated_risk_penalty_bps cannot be negative"
            )

        self.compliance_expiring_days = (
            compliance_expiring_days
        )

        self.evaluated_risk_penalty_bps = (
            evaluated_risk_penalty_bps
        )

    def _compliance_score(
        self,
        supplier: Supplier,
        *,
        as_of: date,
    ) -> tuple[
        float,
        tuple[
            QuoteFinding,
            ...
        ],
    ]:
        c = supplier.compliance

        score = 100.0
        findings = []

        if not c.w9_on_file:
            score -= 10.0

            findings.append(
                QuoteFinding(
                    code=(
                        "W9_MISSING"
                    ),
                    severity=(
                        FindingSeverity
                        .REVIEW
                    ),
                    message=(
                        "Supplier W-9 is not on file."
                    ),
                    supplier_id=(
                        supplier
                        .supplier_id
                    ),
                )
            )

        if c.insurance_required:
            if (
                c.insurance_expiration
                is None
            ):
                score -= 45.0

                findings.append(
                    QuoteFinding(
                        code=(
                            "INSURANCE_MISSING"
                        ),
                        severity=(
                            FindingSeverity
                            .BLOCKER
                        ),
                        message=(
                            "Required insurance evidence "
                            "is unresolved."
                        ),
                        supplier_id=(
                            supplier
                            .supplier_id
                        ),
                    )
                )

            elif (
                c.insurance_expiration
                < as_of
            ):
                score -= 60.0

                findings.append(
                    QuoteFinding(
                        code=(
                            "INSURANCE_EXPIRED"
                        ),
                        severity=(
                            FindingSeverity
                            .BLOCKER
                        ),
                        message=(
                            "Required supplier insurance "
                            "has expired."
                        ),
                        supplier_id=(
                            supplier
                            .supplier_id
                        ),
                    )
                )

            elif (
                (
                    c.insurance_expiration
                    - as_of
                ).days
                <= self
                .compliance_expiring_days
            ):
                score -= 15.0

                findings.append(
                    QuoteFinding(
                        code=(
                            "INSURANCE_EXPIRING"
                        ),
                        severity=(
                            FindingSeverity
                            .REVIEW
                        ),
                        message=(
                            "Supplier insurance expires soon."
                        ),
                        supplier_id=(
                            supplier
                            .supplier_id
                        ),
                    )
                )

        if (
            c.safety_program_required
            and not c
            .safety_program_on_file
        ):
            score -= 25.0

            findings.append(
                QuoteFinding(
                    code=(
                        "SAFETY_PROGRAM_MISSING"
                    ),
                    severity=(
                        FindingSeverity
                        .REVIEW
                    ),
                    message=(
                        "Required supplier safety program "
                        "is not on file."
                    ),
                    supplier_id=(
                        supplier
                        .supplier_id
                    ),
                )
            )

        if (
            c.license_required
            and not c
            .license_current
        ):
            score -= 50.0

            findings.append(
                QuoteFinding(
                    code=(
                        "LICENSE_NOT_CURRENT"
                    ),
                    severity=(
                        FindingSeverity
                        .BLOCKER
                    ),
                    message=(
                        "Required supplier/trade license "
                        "is not current."
                    ),
                    supplier_id=(
                        supplier
                        .supplier_id
                    ),
                )
            )

        if c.bondable_required:
            if c.bondable is not True:
                score -= 35.0

                findings.append(
                    QuoteFinding(
                        code=(
                            "BONDABILITY_UNRESOLVED"
                        ),
                        severity=(
                            FindingSeverity
                            .BLOCKER
                        ),
                        message=(
                            "Required bondability "
                            "is unresolved."
                        ),
                        supplier_id=(
                            supplier
                            .supplier_id
                        ),
                    )
                )

        return (
            max(
                0.0,
                min(
                    100.0,
                    score,
                ),
            ),
            tuple(
                findings
            ),
        )

    @staticmethod
    def _performance_score(
        supplier: Supplier,
    ) -> tuple[
        float,
        tuple[
            QuoteFinding,
            ...
        ],
    ]:
        p = supplier.performance

        score = 75.0

        findings = []

        on_time = p.on_time_rate

        if on_time is not None:
            score += (
                on_time
                - 0.75
            ) * 40.0

        score -= min(
            20.0,
            p.quality_issue_count
            * 4.0,
        )

        score -= min(
            12.0,
            p.change_order_issue_count
            * 2.0,
        )

        score -= min(
            20.0,
            p.payment_dispute_count
            * 5.0,
        )

        score -= min(
            35.0,
            p.safety_issue_count
            * 10.0,
        )

        if (
            p.completed_projects
            == 0
        ):
            findings.append(
                QuoteFinding(
                    code=(
                        "SUPPLIER_HISTORY_LIMITED"
                    ),
                    severity=(
                        FindingSeverity
                        .REVIEW
                    ),
                    message=(
                        "Supplier has no completed-project "
                        "history in GOAT."
                    ),
                    supplier_id=(
                        supplier
                        .supplier_id
                    ),
                )
            )

        if p.safety_issue_count:
            findings.append(
                QuoteFinding(
                    code=(
                        "SUPPLIER_SAFETY_HISTORY"
                    ),
                    severity=(
                        FindingSeverity
                        .REVIEW
                    ),
                    message=(
                        "Supplier has recorded safety issues."
                    ),
                    supplier_id=(
                        supplier
                        .supplier_id
                    ),
                )
            )

        return (
            max(
                0.0,
                min(
                    100.0,
                    score,
                ),
            ),
            tuple(
                findings
            ),
        )

    @staticmethod
    def _schedule_score(
        quote: SupplierQuote,
        *,
        required_by: date | None,
    ) -> tuple[
        float,
        tuple[
            QuoteFinding,
            ...
        ],
    ]:
        terms = quote.terms

        findings = []

        if required_by is None:
            return (
                75.0,
                (),
            )

        if (
            terms
            .earliest_delivery_date
            is not None
        ):
            if (
                terms
                .earliest_delivery_date
                > required_by
            ):
                findings.append(
                    QuoteFinding(
                        code=(
                            "DELIVERY_AFTER_REQUIRED_DATE"
                        ),
                        severity=(
                            FindingSeverity
                            .BLOCKER
                        ),
                        message=(
                            "Quoted earliest delivery "
                            "is later than the required date."
                        ),
                        quote_id=(
                            quote.quote_id
                        ),
                        supplier_id=(
                            quote.supplier_id
                        ),
                    )
                )

                return (
                    10.0,
                    tuple(
                        findings
                    ),
                )

            days_early = (
                required_by
                - terms
                .earliest_delivery_date
            ).days

            score = min(
                100.0,
                80.0
                + max(
                    0,
                    days_early,
                ),
            )

            return (
                score,
                tuple(
                    findings
                ),
            )

        if (
            terms
            .estimated_lead_days
            is None
        ):
            findings.append(
                QuoteFinding(
                    code=(
                        "LEAD_TIME_UNRESOLVED"
                    ),
                    severity=(
                        FindingSeverity
                        .REVIEW
                    ),
                    message=(
                        "Supplier lead time is unresolved."
                    ),
                    quote_id=(
                        quote.quote_id
                    ),
                    supplier_id=(
                        quote.supplier_id
                    ),
                )
            )

            return (
                50.0,
                tuple(
                    findings
                ),
            )

        return (
            75.0,
            tuple(
                findings
            ),
        )

    @staticmethod
    def _commercial_score(
        quote: SupplierQuote,
    ) -> tuple[
        float,
        tuple[
            QuoteFinding,
            ...
        ],
    ]:
        terms = quote.terms

        score = 100.0

        findings = []

        fields = (
            (
                "TAX",
                terms.tax_treatment,
            ),
            (
                "FREIGHT",
                terms.freight_treatment,
            ),
            (
                "MOBILIZATION",
                terms
                .mobilization_treatment,
            ),
            (
                "BOND",
                terms.bond_treatment,
            ),
        )

        for label, treatment in fields:
            if (
                treatment
                == CostTreatment.UNKNOWN
            ):
                score -= 15.0

                findings.append(
                    QuoteFinding(
                        code=(
                            f"{label}_TREATMENT_UNKNOWN"
                        ),
                        severity=(
                            FindingSeverity
                            .REVIEW
                        ),
                        message=(
                            f"{label.title()} cost "
                            "treatment is unresolved."
                        ),
                        quote_id=(
                            quote.quote_id
                        ),
                        supplier_id=(
                            quote.supplier_id
                        ),
                    )
                )

        if (
            terms
            .escalation_treatment
            == CostTreatment.UNKNOWN
        ):
            score -= 20.0

            findings.append(
                QuoteFinding(
                    code=(
                        "ESCALATION_TREATMENT_UNKNOWN"
                    ),
                    severity=(
                        FindingSeverity
                        .REVIEW
                    ),
                    message=(
                        "Price escalation treatment "
                        "is unresolved."
                    ),
                    quote_id=(
                        quote.quote_id
                    ),
                    supplier_id=(
                        quote.supplier_id
                    ),
                )
            )

        if quote.exclusions:
            score -= min(
                30.0,
                len(
                    quote.exclusions
                )
                * 4.0,
            )

            findings.append(
                QuoteFinding(
                    code=(
                        "QUOTE_EXCLUSIONS_PRESENT"
                    ),
                    severity=(
                        FindingSeverity
                        .REVIEW
                    ),
                    message=(
                        "Quote contains exclusions "
                        "requiring estimator review."
                    ),
                    quote_id=(
                        quote.quote_id
                    ),
                    supplier_id=(
                        quote.supplier_id
                    ),
                )
            )

        return (
            max(
                0.0,
                score,
            ),
            tuple(
                findings
            ),
        )

    @staticmethod
    def _commercial_adders(
        quote: SupplierQuote,
    ) -> tuple[
        int | None,
        int | None,
        int | None,
        int | None,
        tuple[
            QuoteFinding,
            ...
        ],
    ]:
        terms = quote.terms

        findings = []

        def resolve(
            label: str,
            treatment: CostTreatment,
            value: int | None,
        ) -> int | None:
            if (
                treatment
                == CostTreatment.INCLUDED
            ):
                return 0

            if (
                treatment
                == CostTreatment.EXCLUDED
            ):
                return 0

            if (
                treatment
                == CostTreatment.ADDITIONAL
            ):
                if value is None:
                    findings.append(
                        QuoteFinding(
                            code=(
                                f"{label}_AMOUNT_UNRESOLVED"
                            ),
                            severity=(
                                FindingSeverity.BLOCKER
                            ),
                            message=(
                                f"{label.title()} is additional "
                                "but no amount was provided."
                            ),
                            quote_id=(
                                quote.quote_id
                            ),
                            supplier_id=(
                                quote.supplier_id
                            ),
                        )
                    )

                    return None

                return int(
                    value
                )

            findings.append(
                QuoteFinding(
                    code=(
                        f"{label}_TREATMENT_UNKNOWN"
                    ),
                    severity=(
                        FindingSeverity.REVIEW
                    ),
                    message=(
                        f"{label.title()} cost treatment "
                        "must be resolved."
                    ),
                    quote_id=(
                        quote.quote_id
                    ),
                    supplier_id=(
                        quote.supplier_id
                    ),
                )
            )

            return None

        tax = resolve(
            "tax",
            terms.tax_treatment,
            terms.tax_cents,
        )

        freight = resolve(
            "freight",
            terms.freight_treatment,
            terms.freight_cents,
        )

        mobilization = resolve(
            "mobilization",
            terms.mobilization_treatment,
            terms.mobilization_cents,
        )

        bond = resolve(
            "bond",
            terms.bond_treatment,
            terms.bond_cents,
        )

        return (
            tax,
            freight,
            mobilization,
            bond,
            tuple(
                findings
            ),
        )

    @staticmethod
    def _line_cost(
        rfq_line: RFQScopeLine,
        quote_line: QuoteLine,
    ) -> tuple[
        int | None,
        tuple[
            QuoteFinding,
            ...
        ],
    ]:
        findings = []

        if not quote_line.included:
            findings.append(
                QuoteFinding(
                    code=(
                        "REQUIRED_SCOPE_EXCLUDED"
                    ),
                    severity=(
                        FindingSeverity.BLOCKER
                        if rfq_line.required
                        else FindingSeverity.REVIEW
                    ),
                    message=(
                        "Quoted scope line is marked excluded."
                    ),
                    scope_key=(
                        rfq_line.scope_key
                    ),
                )
            )

            return (
                None,
                tuple(
                    findings
                ),
            )

        if (
            quote_line.unit.strip().upper()
            != rfq_line.unit
            .strip()
            .upper()
        ):
            findings.append(
                QuoteFinding(
                    code=(
                        "QUOTE_UNIT_MISMATCH"
                    ),
                    severity=(
                        FindingSeverity.BLOCKER
                    ),
                    message=(
                        "Supplier quote unit does not match "
                        "the authoritative RFQ unit."
                    ),
                    scope_key=(
                        rfq_line.scope_key
                    ),
                )
            )

            return (
                None,
                tuple(
                    findings
                ),
            )

        if (
            quote_line.lump_sum_cents
            is not None
        ):
            if (
                quote_line
                .quoted_quantity
                is not None
                and quote_line
                .quoted_quantity
                != rfq_line.quantity
            ):
                findings.append(
                    QuoteFinding(
                        code=(
                            "LUMP_SUM_QUANTITY_DIFFERENCE"
                        ),
                        severity=(
                            FindingSeverity.REVIEW
                        ),
                        message=(
                            "Lump-sum quote references a "
                            "different quantity than the RFQ."
                        ),
                        scope_key=(
                            rfq_line.scope_key
                        ),
                    )
                )

            return (
                int(
                    quote_line
                    .lump_sum_cents
                ),
                tuple(
                    findings
                ),
            )

        if (
            quote_line.unit_price_cents
            is None
        ):
            findings.append(
                QuoteFinding(
                    code=(
                        "QUOTE_PRICE_UNRESOLVED"
                    ),
                    severity=(
                        FindingSeverity.BLOCKER
                    ),
                    message=(
                        "Quote line contains neither "
                        "unit price nor lump sum."
                    ),
                    scope_key=(
                        rfq_line.scope_key
                    ),
                )
            )

            return (
                None,
                tuple(
                    findings
                ),
            )

        if (
            quote_line
            .quoted_quantity
            is not None
            and quote_line
            .quoted_quantity
            != rfq_line.quantity
        ):
            findings.append(
                QuoteFinding(
                    code=(
                        "QUOTE_QUANTITY_NORMALIZED"
                    ),
                    severity=(
                        FindingSeverity.REVIEW
                    ),
                    message=(
                        "Supplier quoted a different quantity; "
                        "GOAT normalized to the RFQ quantity."
                    ),
                    scope_key=(
                        rfq_line.scope_key
                    ),
                )
            )

        value = (
            rfq_line.quantity
            * Decimal(
                quote_line
                .unit_price_cents
            )
        )

        return (
            _round_cents(
                value
            ),
            tuple(
                findings
            ),
        )

    def level(
        self,
        *,
        rfq: RFQPackage,
        quote: SupplierQuote,
        supplier: Supplier,
        as_of: date,
        required_by: date | None = None,
    ) -> LeveledQuote:
        if quote.rfq_id != rfq.rfq_id:
            raise ProcurementConflict(
                "quote belongs to another RFQ"
            )

        if (
            quote.supplier_id
            != supplier.supplier_id
        ):
            raise ProcurementConflict(
                "quote supplier mismatch"
            )

        findings = []

        expired = False

        if (
            quote
            .terms
            .validity_through
            is not None
            and quote
            .terms
            .validity_through
            < as_of
        ):
            expired = True

            findings.append(
                QuoteFinding(
                    code=(
                        "QUOTE_EXPIRED"
                    ),
                    severity=(
                        FindingSeverity.BLOCKER
                    ),
                    message=(
                        "Supplier quote validity has expired."
                    ),
                    quote_id=(
                        quote.quote_id
                    ),
                    supplier_id=(
                        supplier
                        .supplier_id
                    ),
                )
            )

        quote_map = {}

        for line in quote.lines:
            key = (
                line.scope_key
                .strip()
                .upper()
            )

            if key in quote_map:
                findings.append(
                    QuoteFinding(
                        code=(
                            "DUPLICATE_QUOTE_SCOPE_KEY"
                        ),
                        severity=(
                            FindingSeverity.BLOCKER
                        ),
                        message=(
                            "Supplier quote contains duplicate "
                            "scope keys."
                        ),
                        scope_key=(
                            line.scope_key
                        ),
                        quote_id=(
                            quote.quote_id
                        ),
                        supplier_id=(
                            supplier
                            .supplier_id
                        ),
                    )
                )

                continue

            quote_map[
                key
            ] = line

        rfq_keys = {
            line.scope_key
            .strip()
            .upper()
            for line
            in rfq.scope_lines
        }

        leveled_lines = []

        total_scope = 0

        scope_resolved = True

        required_count = 0
        covered_required = 0

        for rfq_line in (
            rfq.scope_lines
        ):
            key = (
                rfq_line
                .scope_key
                .strip()
                .upper()
            )

            quote_line = (
                quote_map.get(
                    key
                )
            )

            line_findings = []

            if rfq_line.required:
                required_count += 1

            if quote_line is None:
                line_findings.append(
                    QuoteFinding(
                        code=(
                            "RFQ_SCOPE_MISSING_FROM_QUOTE"
                        ),
                        severity=(
                            FindingSeverity.BLOCKER
                            if rfq_line.required
                            else FindingSeverity.REVIEW
                        ),
                        message=(
                            "Supplier quote does not contain "
                            "this RFQ scope line."
                        ),
                        scope_key=(
                            rfq_line.scope_key
                        ),
                        quote_id=(
                            quote.quote_id
                        ),
                        supplier_id=(
                            supplier
                            .supplier_id
                        ),
                    )
                )

                coverage = (
                    CoverageStatus.MISSING
                )

                normalized_cost = None

                scope_resolved = False

                quoted_quantity = None

            else:
                normalized_cost, cost_findings = (
                    self._line_cost(
                        rfq_line,
                        quote_line,
                    )
                )

                line_findings.extend(
                    cost_findings
                )

                quoted_quantity = (
                    quote_line
                    .quoted_quantity
                )

                if (
                    normalized_cost
                    is None
                ):
                    coverage = (
                        CoverageStatus.PARTIAL
                    )

                    scope_resolved = False

                else:
                    coverage = (
                        CoverageStatus.COMPLETE
                    )

                    total_scope += (
                        normalized_cost
                    )

                    if rfq_line.required:
                        covered_required += 1

            leveled_lines.append(
                LeveledScopeLine(
                    scope_key=(
                        rfq_line.scope_key
                    ),
                    description=(
                        rfq_line.description
                    ),
                    required_quantity=(
                        rfq_line.quantity
                    ),
                    quoted_quantity=(
                        quoted_quantity
                    ),
                    normalized_quantity=(
                        rfq_line.quantity
                    ),
                    unit=(
                        rfq_line.unit
                    ),
                    normalized_cost_cents=(
                        normalized_cost
                    ),
                    coverage=(
                        coverage
                    ),
                    findings=tuple(
                        line_findings
                    ),
                )
            )

            findings.extend(
                line_findings
            )

        extra_keys = (
            set(
                quote_map
            )
            - rfq_keys
        )

        for extra in sorted(
            extra_keys
        ):
            findings.append(
                QuoteFinding(
                    code=(
                        "EXTRA_QUOTED_SCOPE"
                    ),
                    severity=(
                        FindingSeverity.REVIEW
                    ),
                    message=(
                        "Supplier quote contains scope "
                        "not present in the RFQ."
                    ),
                    scope_key=extra,
                    quote_id=(
                        quote.quote_id
                    ),
                    supplier_id=(
                        supplier
                        .supplier_id
                    ),
                )
            )

        (
            tax,
            freight,
            mobilization,
            bond,
            commercial_adders_findings,
        ) = self._commercial_adders(
            quote
        )

        findings.extend(
            commercial_adders_findings
        )

        commercial_resolved = all(
            value is not None
            for value
            in (
                tax,
                freight,
                mobilization,
                bond,
            )
        )

        if (
            scope_resolved
            and commercial_resolved
        ):
            total = (
                total_scope
                + int(
                    tax
                )
                + int(
                    freight
                )
                + int(
                    mobilization
                )
                + int(
                    bond
                )
            )

        else:
            total = None

        compliance_score, compliance_findings = (
            self._compliance_score(
                supplier,
                as_of=as_of,
            )
        )

        performance_score, performance_findings = (
            self._performance_score(
                supplier
            )
        )

        schedule_score, schedule_findings = (
            self._schedule_score(
                quote,
                required_by=(
                    required_by
                ),
            )
        )

        commercial_score, commercial_findings = (
            self._commercial_score(
                quote
            )
        )

        findings.extend(
            compliance_findings
        )

        findings.extend(
            performance_findings
        )

        findings.extend(
            schedule_findings
        )

        findings.extend(
            commercial_findings
        )

        overall_risk_score = (
            compliance_score
            * 0.35
            + performance_score
            * 0.30
            + schedule_score
            * 0.20
            + commercial_score
            * 0.15
        )

        risk = SupplierRiskProfile(
            supplier_id=(
                supplier.supplier_id
            ),
            compliance_score=round(
                compliance_score,
                4,
            ),
            performance_score=round(
                performance_score,
                4,
            ),
            schedule_score=round(
                schedule_score,
                4,
            ),
            commercial_score=round(
                commercial_score,
                4,
            ),
            overall_score=round(
                overall_risk_score,
                4,
            ),
            findings=tuple(
                compliance_findings
                + performance_findings
                + schedule_findings
                + commercial_findings
            ),
        )

        blocker_exists = any(
            finding.severity
            == FindingSeverity.BLOCKER
            for finding
            in findings
        )

        coverage_percent = (
            _ratio(
                covered_required,
                required_count,
            )
            * 100.0
            if required_count
            else 100.0
        )

        comparable = (
            not blocker_exists
            and total is not None
            and not expired
        )

        return LeveledQuote(
            quote_id=(
                quote.quote_id
            ),
            supplier_id=(
                supplier.supplier_id
            ),
            scope_lines=tuple(
                leveled_lines
            ),
            normalized_scope_cost_cents=(
                total_scope
                if scope_resolved
                else None
            ),
            normalized_tax_cents=tax,
            normalized_freight_cents=(
                freight
            ),
            normalized_mobilization_cents=(
                mobilization
            ),
            normalized_bond_cents=(
                bond
            ),
            normalized_total_cents=(
                total
            ),
            covered_required_scope_count=(
                covered_required
            ),
            required_scope_count=(
                required_count
            ),
            coverage_percent=round(
                coverage_percent,
                4,
            ),
            risk=risk,
            findings=tuple(
                findings
            ),
            comparable=(
                comparable
            ),
            expired=expired,
        )

    def recommend(
        self,
        *,
        rfq: RFQPackage,
        leveled_quotes: tuple[
            LeveledQuote,
            ...
        ],
    ) -> tuple[
        QuoteRecommendation,
        ...
    ]:
        comparable = [
            quote
            for quote
            in leveled_quotes
            if (
                quote.comparable
                and quote
                .normalized_total_cents
                is not None
            )
        ]

        lowest = (
            min(
                quote
                .normalized_total_cents
                for quote
                in comparable
            )
            if comparable
            else None
        )

        recommendations = []

        scored = []

        for quote in (
            leveled_quotes
        ):
            if (
                not quote.comparable
                or quote
                .normalized_total_cents
                is None
            ):
                recommendations.append(
                    QuoteRecommendation(
                        rfq_id=(
                            rfq.rfq_id
                        ),
                        quote_id=(
                            quote.quote_id
                        ),
                        supplier_id=(
                            quote.supplier_id
                        ),
                        disposition=(
                            QuoteDisposition.REJECT
                            if any(
                                finding.severity
                                == FindingSeverity.BLOCKER
                                for finding
                                in quote.findings
                            )
                            else QuoteDisposition.REVIEW
                        ),
                        normalized_total_cents=(
                            quote
                            .normalized_total_cents
                        ),
                        evaluated_cost_cents=None,
                        coverage_percent=(
                            quote
                            .coverage_percent
                        ),
                        supplier_risk_score=(
                            quote
                            .risk
                            .overall_score
                        ),
                        value_score=0.0,
                        rank=None,
                        findings=(
                            quote.findings
                        ),
                    )
                )

                continue

            risk_fraction = (
                (
                    100.0
                    - quote
                    .risk
                    .overall_score
                )
                / 100.0
            )

            penalty = int(
                round(
                    quote
                    .normalized_total_cents
                    * risk_fraction
                    * (
                        self
                        .evaluated_risk_penalty_bps
                        / 10_000.0
                    )
                )
            )

            evaluated_cost = (
                quote
                .normalized_total_cents
                + penalty
            )

            price_score = (
                (
                    lowest
                    / quote
                    .normalized_total_cents
                )
                * 100.0
                if (
                    lowest
                    and quote
                    .normalized_total_cents
                    > 0
                )
                else 100.0
            )

            value_score = (
                price_score
                * 0.60
                + quote
                .risk
                .overall_score
                * 0.30
                + quote
                .coverage_percent
                * 0.10
            )

            scored.append(
                (
                    quote,
                    evaluated_cost,
                    value_score,
                )
            )

        scored.sort(
            key=lambda item:
                (
                    -item[2],
                    item[1],
                    item[0]
                    .normalized_total_cents,
                    item[0]
                    .supplier_id,
                )
        )

        for index, (
            quote,
            evaluated_cost,
            value_score,
        ) in enumerate(
            scored,
            1,
        ):
            disposition = (
                QuoteDisposition.RECOMMENDED
                if index == 1
                else QuoteDisposition.ALTERNATE
            )

            recommendations.append(
                QuoteRecommendation(
                    rfq_id=(
                        rfq.rfq_id
                    ),
                    quote_id=(
                        quote.quote_id
                    ),
                    supplier_id=(
                        quote.supplier_id
                    ),
                    disposition=(
                        disposition
                    ),
                    normalized_total_cents=(
                        quote
                        .normalized_total_cents
                    ),
                    evaluated_cost_cents=(
                        evaluated_cost
                    ),
                    coverage_percent=(
                        quote
                        .coverage_percent
                    ),
                    supplier_risk_score=(
                        quote
                        .risk
                        .overall_score
                    ),
                    value_score=round(
                        value_score,
                        4,
                    ),
                    rank=index,
                    findings=(
                        quote.findings
                    ),
                )
            )

        return tuple(
            sorted(
                recommendations,
                key=lambda item:
                    (
                        item.rank
                        is None,
                        item.rank
                        or 999999,
                        item.supplier_id,
                    ),
            )
        )


class ProcurementService:
    """
    Procurement domain service.

    Manages supplier master records, RFQ packages, supplier quote intake,
    deterministic quote leveling, evaluated-value recommendation, award
    decisions, price-candidate export, and tamper-evident audit records.
    """

    def __init__(
        self,
        *,
        leveling_engine: (
            QuoteLevelingEngine
            | None
        ) = None,
        package_control: Any | None = None,
    ) -> None:
        self.leveling_engine = (
            leveling_engine
            or QuoteLevelingEngine()
        )

        self.package_control = (
            package_control
        )

        self._suppliers: dict[
            str,
            Supplier,
        ] = {}

        self._rfqs: dict[
            str,
            RFQPackage,
        ] = {}

        self._quotes: dict[
            str,
            SupplierQuote,
        ] = {}

        self._awards: dict[
            str,
            ProcurementAward,
        ] = {}

        self._audit: dict[
            str,
            list[
                ProcurementAuditRecord
            ],
        ] = {}

        self._quote_identity: dict[
            tuple[
                str,
                str,
                str,
            ],
            str,
        ] = {}

    def _record_audit(
        self,
        *,
        aggregate_id: str,
        action: str,
        actor_id: str,
        payload: dict[
            str,
            Any,
        ],
    ) -> ProcurementAuditRecord:
        records = (
            self._audit.setdefault(
                aggregate_id,
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
            "aggregate_id":
                aggregate_id,
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
            ProcurementAuditRecord(
                event_id=(
                    _id(
                        "paud"
                    )
                ),
                aggregate_id=(
                    aggregate_id
                ),
                sequence=(
                    sequence
                ),
                action=action,
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

        return record

    def verify_audit(
        self,
        aggregate_id: str,
    ) -> bool:
        records = tuple(
            self._audit.get(
                aggregate_id,
                (),
            )
        )

        previous = "GENESIS"

        for expected, record in enumerate(
            records,
            1,
        ):
            if (
                record.sequence
                != expected
            ):
                raise ProcurementAuditError(
                    "audit sequence mismatch"
                )

            if (
                record.previous_hash
                != previous
            ):
                raise ProcurementAuditError(
                    "audit previous hash mismatch"
                )

            material = {
                "aggregate_id":
                    record.aggregate_id,
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
                raise ProcurementAuditError(
                    "audit event hash mismatch"
                )

            previous = (
                record.event_hash
            )

        return True

    def supplier(
        self,
        supplier_id: str,
    ) -> Supplier:
        result = (
            self._suppliers.get(
                supplier_id
            )
        )

        if result is None:
            raise ProcurementNotFound(
                supplier_id
            )

        return result

    def rfq(
        self,
        rfq_id: str,
    ) -> RFQPackage:
        result = (
            self._rfqs.get(
                rfq_id
            )
        )

        if result is None:
            raise ProcurementNotFound(
                rfq_id
            )

        return result

    def quote(
        self,
        quote_id: str,
    ) -> SupplierQuote:
        result = (
            self._quotes.get(
                quote_id
            )
        )

        if result is None:
            raise ProcurementNotFound(
                quote_id
            )

        return result

    def create_supplier(
        self,
        *,
        tenant_id: str,
        business_unit_id: str,
        name: str,
        kind: SupplierKind,
        trades: tuple[
            ProcurementTrade,
            ...
        ],
        actor_id: str,
        regions: tuple[str, ...] = (),
        contacts: tuple[
            SupplierContact,
            ...
        ] = (),
        compliance: (
            SupplierCompliance
            | None
        ) = None,
        performance: (
            SupplierPerformance
            | None
        ) = None,
    ) -> Supplier:
        tenant_id = _required(
            tenant_id,
            "tenant_id",
        )

        business_unit_id = (
            _required(
                business_unit_id,
                "business_unit_id",
            )
        )

        name = _required(
            name,
            "name",
        )

        actor_id = _required(
            actor_id,
            "actor_id",
        )

        normalized_name = (
            name.strip()
            .lower()
        )

        for supplier in (
            self._suppliers
            .values()
        ):
            if (
                supplier.tenant_id
                == tenant_id
                and supplier.name
                .strip()
                .lower()
                == normalized_name
            ):
                return supplier

        now = _now()

        supplier = Supplier(
            supplier_id=(
                _id(
                    "sup"
                )
            ),
            tenant_id=(
                tenant_id
            ),
            business_unit_id=(
                business_unit_id
            ),
            name=name,
            kind=kind,
            trades=tuple(
                dict.fromkeys(
                    trades
                )
            ),
            regions=tuple(
                dict.fromkeys(
                    regions
                )
            ),
            contacts=tuple(
                contacts
            ),
            compliance=(
                compliance
                or SupplierCompliance()
            ),
            performance=(
                performance
                or SupplierPerformance()
            ),
            active=True,
            created_at=now,
            updated_at=now,
            version=1,
        )

        self._suppliers[
            supplier.supplier_id
        ] = supplier

        self._record_audit(
            aggregate_id=(
                supplier
                .supplier_id
            ),
            action=(
                "supplier.created"
            ),
            actor_id=(
                actor_id
            ),
            payload={
                "name":
                    name,
                "kind":
                    kind.value,
                "trades":
                    [
                        trade.value
                        for trade
                        in supplier.trades
                    ],
            },
        )

        return supplier

    def create_rfq(
        self,
        *,
        tenant_id: str,
        business_unit_id: str,
        project_name: str,
        trade: ProcurementTrade,
        scope_lines: tuple[
            RFQScopeLine,
            ...
        ],
        invited_supplier_ids: tuple[
            str,
            ...
        ],
        actor_id: str,
        project_id: str | None = None,
        opportunity_id: str | None = None,
        bid_package_id: str | None = None,
        bid_package_revision_id: str | None = None,
        estimate_id: str | None = None,
        due_at: datetime | None = None,
    ) -> RFQPackage:
        project_name = (
            _required(
                project_name,
                "project_name",
            )
        )

        actor_id = _required(
            actor_id,
            "actor_id",
        )

        due_at = _aware(
            due_at,
            "due_at",
        )

        if not scope_lines:
            raise ValueError(
                "RFQ requires at least one scope line"
            )

        keys = set()

        for line in scope_lines:
            _decimal(
                line.quantity,
                "RFQ quantity",
            )

            key = (
                line.scope_key
                .strip()
                .upper()
            )

            if not key:
                raise ValueError(
                    "scope_key required"
                )

            if key in keys:
                raise ProcurementConflict(
                    "duplicate RFQ scope_key"
                )

            keys.add(
                key
            )

        for supplier_id in (
            invited_supplier_ids
        ):
            supplier = self.supplier(
                supplier_id
            )

            if not supplier.active:
                raise ProcurementBlocked(
                    "inactive supplier cannot be invited"
                )

        if (
            bid_package_revision_id
            and self.package_control
            is not None
        ):
            revision = (
                self.package_control
                .get_revision(
                    bid_package_revision_id
                )
            )

            if (
                bid_package_id
                and revision.package_id
                != bid_package_id
            ):
                raise ProcurementConflict(
                    "bid package revision mismatch"
                )

        now = _now()

        rfq = RFQPackage(
            rfq_id=(
                _id(
                    "rfq"
                )
            ),
            tenant_id=(
                _required(
                    tenant_id,
                    "tenant_id",
                )
            ),
            business_unit_id=(
                _required(
                    business_unit_id,
                    "business_unit_id",
                )
            ),
            project_id=project_id,
            opportunity_id=(
                opportunity_id
            ),
            bid_package_id=(
                bid_package_id
            ),
            bid_package_revision_id=(
                bid_package_revision_id
            ),
            estimate_id=(
                estimate_id
            ),
            project_name=(
                project_name
            ),
            trade=trade,
            scope_lines=tuple(
                scope_lines
            ),
            invited_supplier_ids=tuple(
                dict.fromkeys(
                    invited_supplier_ids
                )
            ),
            due_at=due_at,
            state=(
                RFQState.DRAFT
            ),
            created_at=now,
            updated_at=now,
            created_by=(
                actor_id
            ),
            version=1,
        )

        self._rfqs[
            rfq.rfq_id
        ] = rfq

        self._record_audit(
            aggregate_id=(
                rfq.rfq_id
            ),
            action="rfq.created",
            actor_id=(
                actor_id
            ),
            payload={
                "trade":
                    trade.value,
                "scope_line_count":
                    len(
                        scope_lines
                    ),
                "supplier_count":
                    len(
                        invited_supplier_ids
                    ),
                "bid_package_revision_id":
                    (
                        bid_package_revision_id
                        or ""
                    ),
            },
        )

        return rfq

    def issue_rfq(
        self,
        *,
        rfq_id: str,
        actor_id: str,
    ) -> RFQPackage:
        rfq = self.rfq(
            rfq_id
        )

        if (
            rfq.state
            != RFQState.DRAFT
        ):
            raise ProcurementConflict(
                "only draft RFQ may be issued"
            )

        if (
            not rfq
            .invited_supplier_ids
        ):
            raise ProcurementBlocked(
                "RFQ has no invited suppliers"
            )

        updated = replace(
            rfq,
            state=(
                RFQState.ISSUED
            ),
            updated_at=_now(),
            version=(
                rfq.version
                + 1
            ),
        )

        self._rfqs[
            rfq_id
        ] = updated

        self._record_audit(
            aggregate_id=(
                rfq_id
            ),
            action="rfq.issued",
            actor_id=(
                actor_id
            ),
            payload={
                "supplier_count":
                    len(
                        updated
                        .invited_supplier_ids
                    ),
            },
        )

        return updated

    def receive_quote(
        self,
        *,
        rfq_id: str,
        supplier_id: str,
        actor_id: str,
        lines: tuple[
            QuoteLine,
            ...
        ],
        terms: QuoteCommercialTerms,
        received_at: datetime,
        quote_number: str | None = None,
        exclusions: tuple[str, ...] = (),
        qualifications: tuple[str, ...] = (),
        alternates: tuple[str, ...] = (),
        source_refs: tuple[str, ...] = (),
    ) -> SupplierQuote:
        rfq = self.rfq(
            rfq_id
        )

        supplier = self.supplier(
            supplier_id
        )

        actor_id = _required(
            actor_id,
            "actor_id",
        )

        received_at = _aware(
            received_at,
            "received_at",
        )

        if (
            rfq.state
            not in {
                RFQState.ISSUED,
                RFQState.RECEIVING,
                RFQState.LEVELING,
            }
        ):
            raise ProcurementBlocked(
                "RFQ is not accepting quotes"
            )

        if (
            supplier_id
            not in rfq
            .invited_supplier_ids
        ):
            raise ProcurementBlocked(
                "supplier was not invited to this RFQ"
            )

        identity = (
            rfq_id,
            supplier_id,
            str(
                quote_number
                or "NO_NUMBER"
            )
            .strip()
            .upper(),
        )

        existing = (
            self._quote_identity.get(
                identity
            )
        )

        if existing:
            return self.quote(
                existing
            )

        if not lines:
            raise ValueError(
                "quote requires at least one line"
            )

        for line in lines:
            if (
                line.unit_price_cents
                is None
                and line
                .lump_sum_cents
                is None
                and line.included
            ):
                raise ValueError(
                    "included quote line requires "
                    "unit price or lump sum"
                )

            if (
                line.unit_price_cents
                is not None
            ):
                _money(
                    line.unit_price_cents,
                    "unit_price_cents",
                )

            if (
                line.lump_sum_cents
                is not None
            ):
                _money(
                    line.lump_sum_cents,
                    "lump_sum_cents",
                )

            if (
                line.quoted_quantity
                is not None
            ):
                _decimal(
                    line.quoted_quantity,
                    "quoted_quantity",
                )

        quote = SupplierQuote(
            quote_id=(
                _id(
                    "quote"
                )
            ),
            rfq_id=(
                rfq_id
            ),
            supplier_id=(
                supplier_id
            ),
            quote_number=(
                quote_number
            ),
            received_at=(
                received_at
            ),
            lines=tuple(
                lines
            ),
            terms=terms,
            exclusions=tuple(
                exclusions
            ),
            qualifications=tuple(
                qualifications
            ),
            alternates=tuple(
                alternates
            ),
            source_refs=tuple(
                source_refs
            ),
            state=(
                QuoteState.RECEIVED
            ),
            created_by=(
                actor_id
            ),
            version=1,
        )

        self._quotes[
            quote.quote_id
        ] = quote

        self._quote_identity[
            identity
        ] = quote.quote_id

        if (
            rfq.state
            == RFQState.ISSUED
        ):
            self._rfqs[
                rfq_id
            ] = replace(
                rfq,
                state=(
                    RFQState.RECEIVING
                ),
                updated_at=_now(),
                version=(
                    rfq.version
                    + 1
                ),
            )

        self._record_audit(
            aggregate_id=(
                rfq_id
            ),
            action=(
                "quote.received"
            ),
            actor_id=(
                actor_id
            ),
            payload={
                "quote_id":
                    quote.quote_id,
                "supplier_id":
                    supplier_id,
                "quote_number":
                    quote_number or "",
                "line_count":
                    len(
                        lines
                    ),
            },
        )

        return quote

    def level_rfq(
        self,
        *,
        rfq_id: str,
        actor_id: str,
        as_of: date,
        required_by: date | None = None,
    ) -> tuple[
        LeveledQuote,
        ...
    ]:
        rfq = self.rfq(
            rfq_id
        )

        quotes = tuple(
            quote
            for quote
            in self._quotes
            .values()
            if (
                quote.rfq_id
                == rfq_id
                and quote.state
                not in {
                    QuoteState.WITHDRAWN,
                    QuoteState.REJECTED,
                }
            )
        )

        if not quotes:
            raise ProcurementBlocked(
                "RFQ has no received quotes"
            )

        leveled = []

        for quote in quotes:
            supplier = self.supplier(
                quote.supplier_id
            )

            result = (
                self.leveling_engine
                .level(
                    rfq=rfq,
                    quote=quote,
                    supplier=supplier,
                    as_of=as_of,
                    required_by=(
                        required_by
                    ),
                )
            )

            leveled.append(
                result
            )

            if result.expired:
                state = (
                    QuoteState.EXPIRED
                )

            elif result.comparable:
                state = (
                    QuoteState.COMPARABLE
                )

            else:
                state = (
                    QuoteState.NONCOMPARABLE
                )

            self._quotes[
                quote.quote_id
            ] = replace(
                quote,
                state=state,
                version=(
                    quote.version
                    + 1
                ),
            )

        recommendations = (
            self.leveling_engine
            .recommend(
                rfq=rfq,
                leveled_quotes=tuple(
                    leveled
                ),
            )
        )

        has_recommended = any(
            item.disposition
            == QuoteDisposition
            .RECOMMENDED
            for item
            in recommendations
        )

        self._rfqs[
            rfq_id
        ] = replace(
            rfq,
            state=(
                RFQState
                .RECOMMENDATION_READY
                if has_recommended
                else RFQState.LEVELING
            ),
            updated_at=_now(),
            version=(
                rfq.version
                + 1
            ),
        )

        self._record_audit(
            aggregate_id=(
                rfq_id
            ),
            action=(
                "rfq.leveled"
            ),
            actor_id=(
                actor_id
            ),
            payload={
                "quote_count":
                    len(
                        leveled
                    ),
                "comparable_count":
                    sum(
                        1
                        for item
                        in leveled
                        if item.comparable
                    ),
                "recommendation_ready":
                    has_recommended,
            },
        )

        return tuple(
            leveled
        )

    def recommendations(
        self,
        *,
        rfq_id: str,
        as_of: date,
        required_by: date | None = None,
    ) -> tuple[
        QuoteRecommendation,
        ...
    ]:
        rfq = self.rfq(
            rfq_id
        )

        leveled = tuple(
            self.leveling_engine
            .level(
                rfq=rfq,
                quote=quote,
                supplier=(
                    self.supplier(
                        quote
                        .supplier_id
                    )
                ),
                as_of=as_of,
                required_by=(
                    required_by
                ),
            )
            for quote
            in self._quotes
            .values()
            if (
                quote.rfq_id
                == rfq_id
                and quote.state
                not in {
                    QuoteState.WITHDRAWN,
                    QuoteState.REJECTED,
                }
            )
        )

        return (
            self.leveling_engine
            .recommend(
                rfq=rfq,
                leveled_quotes=(
                    leveled
                ),
            )
        )

    def award_recommendation(
        self,
        *,
        rfq_id: str,
        as_of: date,
        required_by: date | None = None,
    ) -> AwardRecommendation:
        recommendations = (
            self.recommendations(
                rfq_id=(
                    rfq_id
                ),
                as_of=as_of,
                required_by=(
                    required_by
                ),
            )
        )

        selected = next(
            (
                item
                for item
                in recommendations
                if (
                    item.disposition
                    == QuoteDisposition
                    .RECOMMENDED
                )
            ),
            None,
        )

        if (
            selected is None
            or selected
            .normalized_total_cents
            is None
            or selected
            .evaluated_cost_cents
            is None
        ):
            raise ProcurementBlocked(
                "no award-ready quote recommendation"
            )

        return AwardRecommendation(
            recommendation_id=(
                _id(
                    "prec"
                )
            ),
            rfq_id=(
                rfq_id
            ),
            selected_quote_id=(
                selected.quote_id
            ),
            selected_supplier_id=(
                selected.supplier_id
            ),
            normalized_total_cents=(
                selected
                .normalized_total_cents
            ),
            evaluated_cost_cents=(
                selected
                .evaluated_cost_cents
            ),
            recommendation=(
                selected.disposition
            ),
            reason=(
                "Selected by GOAT evaluated-value "
                "ranking after scope normalization, "
                "commercial normalization, schedule, "
                "compliance, and supplier-risk analysis."
            ),
            comparison=(
                recommendations
            ),
            generated_at=(
                _now()
            ),
        )

    def award(
        self,
        *,
        rfq_id: str,
        quote_id: str,
        actor_id: str,
        note: str,
        as_of: date,
        required_by: date | None = None,
    ) -> ProcurementAward:
        rfq = self.rfq(
            rfq_id
        )

        quote = self.quote(
            quote_id
        )

        if (
            quote.rfq_id
            != rfq_id
        ):
            raise ProcurementConflict(
                "quote belongs to another RFQ"
            )

        recommendations = (
            self.recommendations(
                rfq_id=(
                    rfq_id
                ),
                as_of=as_of,
                required_by=(
                    required_by
                ),
            )
        )

        chosen = next(
            (
                item
                for item
                in recommendations
                if (
                    item.quote_id
                    == quote_id
                )
            ),
            None,
        )

        if (
            chosen is None
            or chosen
            .normalized_total_cents
            is None
        ):
            raise ProcurementBlocked(
                "quote is not awardable"
            )

        if (
            chosen.disposition
            not in {
                QuoteDisposition.RECOMMENDED,
                QuoteDisposition.ALTERNATE,
            }
        ):
            raise ProcurementBlocked(
                "quote has unresolved blockers"
            )

        award = ProcurementAward(
            award_id=(
                _id(
                    "pawd"
                )
            ),
            rfq_id=(
                rfq_id
            ),
            quote_id=(
                quote_id
            ),
            supplier_id=(
                quote.supplier_id
            ),
            awarded_amount_cents=(
                chosen
                .normalized_total_cents
            ),
            approved_by=(
                actor_id
            ),
            approved_at=(
                _now()
            ),
            note=(
                _required(
                    note,
                    "note",
                )
            ),
            state=(
                AwardState.AWARDED
            ),
        )

        self._awards[
            award.award_id
        ] = award

        self._quotes[
            quote_id
        ] = replace(
            quote,
            state=(
                QuoteState.AWARDED
            ),
            version=(
                quote.version
                + 1
            ),
        )

        for other in tuple(
            self._quotes
            .values()
        ):
            if (
                other.rfq_id
                == rfq_id
                and other.quote_id
                != quote_id
                and other.state
                not in {
                    QuoteState.WITHDRAWN,
                    QuoteState.EXPIRED,
                }
            ):
                self._quotes[
                    other.quote_id
                ] = replace(
                    other,
                    state=(
                        QuoteState.REJECTED
                    ),
                    version=(
                        other.version
                        + 1
                    ),
                )

        self._rfqs[
            rfq_id
        ] = replace(
            rfq,
            state=(
                RFQState.AWARDED
            ),
            updated_at=_now(),
            version=(
                rfq.version
                + 1
            ),
        )

        self._record_audit(
            aggregate_id=(
                rfq_id
            ),
            action=(
                "rfq.awarded"
            ),
            actor_id=(
                actor_id
            ),
            payload={
                "quote_id":
                    quote_id,
                "supplier_id":
                    quote
                    .supplier_id,
                "amount_cents":
                    award
                    .awarded_amount_cents,
                "note":
                    note,
            },
        )

        return award

    def price_candidates(
        self,
        *,
        quote_id: str,
        as_of: date,
    ) -> tuple[
        ProcurementRateCandidate,
        ...
    ]:
        quote = self.quote(
            quote_id
        )

        rfq = self.rfq(
            quote.rfq_id
        )

        supplier = self.supplier(
            quote.supplier_id
        )

        leveled = (
            self.leveling_engine
            .level(
                rfq=rfq,
                quote=quote,
                supplier=supplier,
                as_of=as_of,
            )
        )

        if not leveled.comparable:
            raise ProcurementBlocked(
                "noncomparable quote cannot "
                "be exported to pricing"
            )

        quote_map = {
            line.scope_key
            .strip()
            .upper():
                line
            for line
            in quote.lines
        }

        candidates = []

        for rfq_line in (
            rfq.scope_lines
        ):
            line = (
                quote_map.get(
                    rfq_line
                    .scope_key
                    .strip()
                    .upper()
                )
            )

            if (
                line is None
                or not line.included
            ):
                continue

            if (
                line.unit_price_cents
                is not None
            ):
                unit_price = int(
                    line.unit_price_cents
                )

            elif (
                line.lump_sum_cents
                is not None
                and rfq_line
                .quantity
                > 0
            ):
                unit_price = _round_cents(
                    Decimal(
                        line
                        .lump_sum_cents
                    )
                    / rfq_line.quantity
                )

            else:
                continue

            confidence = (
                leveled
                .risk
                .overall_score
                / 100.0
            )

            confidence *= (
                leveled
                .coverage_percent
                / 100.0
            )

            candidates.append(
                ProcurementRateCandidate(
                    supplier_id=(
                        supplier
                        .supplier_id
                    ),
                    quote_id=(
                        quote.quote_id
                    ),
                    scope_key=(
                        rfq_line
                        .scope_key
                    ),
                    description=(
                        rfq_line
                        .description
                    ),
                    unit=(
                        rfq_line.unit
                    ),
                    normalized_unit_price_cents=(
                        unit_price
                    ),
                    quantity_basis=(
                        rfq_line
                        .quantity
                    ),
                    effective_date=(
                        quote
                        .received_at
                        .date()
                    ),
                    expiration_date=(
                        quote
                        .terms
                        .validity_through
                    ),
                    source_refs=tuple(
                        dict.fromkeys(
                            quote.source_refs
                            + line.source_refs
                            + rfq_line
                            .drawing_refs
                            + rfq_line
                            .specification_refs
                        )
                    ),
                    confidence=round(
                        max(
                            0.0,
                            min(
                                1.0,
                                confidence,
                            ),
                        ),
                        4,
                    ),
                )
            )

        return tuple(
            candidates
        )
