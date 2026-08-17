from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any


class EngineeringCodeError(RuntimeError):
    pass


class JurisdictionResolutionError(EngineeringCodeError):
    pass


class CodeResolutionError(EngineeringCodeError):
    pass


class CalculationIntegrityError(EngineeringCodeError):
    pass


class ProfessionalReviewRequired(EngineeringCodeError):
    pass


class JurisdictionType(str, Enum):
    STATE = "state"
    COUNTY = "county"
    CITY = "city"
    SPECIAL_DISTRICT = "special_district"
    AHJ = "ahj"


class EngineeringDiscipline(str, Enum):
    ARCHITECTURAL = "architectural"
    STRUCTURAL = "structural"
    CONCRETE = "concrete"
    STEEL = "steel"
    GEOTECHNICAL = "geotechnical"
    CIVIL = "civil"
    EARTHWORK = "earthwork"
    MECHANICAL = "mechanical"
    ELECTRICAL = "electrical"
    PLUMBING = "plumbing"
    FIRE = "fire"
    ACCESSIBILITY = "accessibility"
    ENERGY = "energy"
    ENVIRONMENTAL = "environmental"
    WATERPROOFING = "waterproofing"


class StructureContext(str, Enum):
    ABOVE_GRADE = "above_grade"
    BELOW_GRADE = "below_grade"
    UNDERGROUND = "underground"
    MIXED = "mixed"


class CodeAuthority(str, Enum):
    OFFICIAL = "official"
    ADOPTED = "adopted"
    REFERENCE_STANDARD = "reference_standard"
    GUIDANCE = "guidance"
    UNVERIFIED = "unverified"


class AdoptionStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    PENDING = "pending"
    REPEALED = "repealed"


class RequirementSeverity(str, Enum):
    INFORMATIONAL = "informational"
    REVIEW = "review"
    MATERIAL = "material"
    CRITICAL = "critical"


class ComplianceStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    REVIEW = "review"
    NOT_APPLICABLE = "not_applicable"


class WaterRiskLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class Jurisdiction:
    jurisdiction_id: str

    name: str

    jurisdiction_type: JurisdictionType

    state_code: str = "TX"

    parent_id: str | None = None

    fips_code: str | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class CodeAdoption:
    adoption_id: str

    jurisdiction_id: str

    discipline: EngineeringDiscipline

    code_family: str

    edition: str

    effective_from: date

    effective_until: date | None

    authority: CodeAuthority

    status: AdoptionStatus

    source_fact_id: str

    amendment_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CodeAmendment:
    amendment_id: str

    jurisdiction_id: str

    discipline: EngineeringDiscipline

    code_family: str

    section: str

    operation: str

    payload: dict[str, Any]

    effective_from: date

    effective_until: date | None

    source_fact_id: str

    authority: CodeAuthority = CodeAuthority.OFFICIAL


@dataclass(frozen=True)
class EffectiveCodeStack:
    jurisdiction_path: tuple[str, ...]

    adoption: CodeAdoption

    amendments: tuple[CodeAmendment, ...]

    unresolved_conflicts: tuple[str, ...]

    source_fact_ids: tuple[str, ...]

    authoritative: bool


@dataclass(frozen=True)
class ProjectEngineeringContext:
    project_id: str

    jurisdiction_id: str

    project_date: date

    structure_context: StructureContext

    occupancy: str | None = None

    stories_above_grade: int = 0

    stories_below_grade: int = 0

    height_ft: float | None = None

    gross_area_sf: float | None = None

    construction_type: str | None = None

    sprinklered: bool | None = None

    flood_zone: str | None = None

    seismic_design_category: str | None = None

    wind_speed_mph: float | None = None

    risk_category: str | None = None

    project_tags: frozenset[str] = frozenset()

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class RuleRequirement:
    requirement_id: str

    discipline: EngineeringDiscipline

    name: str

    field_name: str

    operator: str

    expected: Any

    severity: RequirementSeverity

    source_fact_id: str

    jurisdictions: tuple[str, ...] = ()

    applicable_structure_contexts: tuple[
        StructureContext,
        ...
    ] = ()

    required_tags: frozenset[str] = frozenset()

    professional_review_required: bool = False


@dataclass(frozen=True)
class ComplianceFinding:
    requirement_id: str

    discipline: EngineeringDiscipline

    status: ComplianceStatus

    severity: RequirementSeverity

    message: str

    actual: Any

    expected: Any

    source_fact_id: str

    professional_review_required: bool


@dataclass(frozen=True)
class LoadCase:
    name: str
    value: Decimal
    unit: str


@dataclass(frozen=True)
class LoadFactor:
    load_case: str
    factor: Decimal


@dataclass(frozen=True)
class LoadCombination:
    combination_id: str

    name: str

    factors: tuple[LoadFactor, ...]

    source_fact_id: str

    code_family: str | None = None

    edition: str | None = None


@dataclass(frozen=True)
class LoadCombinationResult:
    combination_id: str

    result: Decimal

    unit: str

    contributions: tuple[
        tuple[str, Decimal],
        ...
    ]


@dataclass(frozen=True)
class CalculationTrace:
    calculation_id: str

    engine: str
    engine_version: str

    inputs: dict[str, Any]

    outputs: dict[str, Any]

    source_fact_ids: tuple[str, ...]

    executed_at: datetime

    previous_hash: str | None

    content_hash: str

    chain_hash: str


@dataclass(frozen=True)
class WaterIntrusionInputs:
    lowest_structural_elevation_ft: float

    groundwater_elevation_ft: float | None

    design_flood_elevation_ft: float | None

    below_grade_wall_height_ft: float

    slab_area_sf: float

    soil_permeability_index: float

    waterproofing_reliability: float

    drainage_reliability: float

    sump_reliability: float

    redundancy_count: int = 0


@dataclass(frozen=True)
class WaterIntrusionAssessment:
    governing_water_elevation_ft: float | None

    hydrostatic_head_ft: float

    base_pressure_psi: float

    estimated_uplift_kips: float

    intrusion_probability_index: float

    risk_level: WaterRiskLevel

    drainage_credit: float

    waterproofing_credit: float

    notes: tuple[str, ...]

    professional_review_required: bool = True


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
