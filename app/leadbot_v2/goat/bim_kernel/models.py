from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class BIMKernelError(RuntimeError):
    pass


class GeometryError(BIMKernelError):
    pass


class SpatialIndexError(BIMKernelError):
    pass


class DependencyError(BIMKernelError):
    pass


class ModelIntegrityError(BIMKernelError):
    pass


class ConstraintError(BIMKernelError):
    pass


class ElementCategory(str, Enum):
    GENERIC = "generic"

    WALL = "wall"
    SLAB = "slab"
    BEAM = "beam"
    COLUMN = "column"
    FOOTING = "footing"
    FOUNDATION = "foundation"

    PIPE = "pipe"
    DUCT = "duct"
    CONDUIT = "conduit"
    CABLE_TRAY = "cable_tray"

    EQUIPMENT = "equipment"
    OPENING = "opening"
    ROOM = "room"

    SITE = "site"
    EARTHWORK = "earthwork"
    UTILITY = "utility"


class BIMDiscipline(str, Enum):
    ARCHITECTURAL = "architectural"
    STRUCTURAL = "structural"
    CIVIL = "civil"
    GEOTECHNICAL = "geotechnical"

    MECHANICAL = "mechanical"
    ELECTRICAL = "electrical"
    PLUMBING = "plumbing"
    FIRE = "fire"

    SITE = "site"
    MULTIDISCIPLINE = "multidiscipline"


class ClashType(str, Enum):
    HARD = "hard"
    CLEARANCE = "clearance"


class ClashSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConstraintDisposition(str, Enum):
    PASS = "pass"
    REVIEW = "review"
    FAIL = "fail"


class EngineeringOverlayDisposition(str, Enum):
    PASS = "pass"
    REVIEW = "review"
    FAIL = "fail"


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class AABB:
    minimum: Vec3
    maximum: Vec3


@dataclass(frozen=True)
class Level:
    level_id: str
    name: str
    elevation_ft: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GridLine:
    grid_id: str
    name: str
    origin: Vec3
    direction: Vec3


@dataclass(frozen=True)
class ModelElement:
    element_id: str
    category: ElementCategory
    discipline: BIMDiscipline
    bounds: AABB

    level_id: str | None = None
    system_id: str | None = None

    material: str | None = None
    type_name: str | None = None

    clearance_ft: float = 0.0

    geometry_kind: str = "box"

    source_element_ids: tuple[str, ...] = ()
    source_fact_ids: tuple[str, ...] = ()

    professional_review_required: bool = False

    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Clash:
    clash_id: str

    element_a: str
    element_b: str

    clash_type: ClashType
    severity: ClashSeverity

    distance_ft: float

    overlap_x_ft: float
    overlap_y_ft: float
    overlap_z_ft: float

    overlap_volume_cf: float

    required_clearance_ft: float

    message: str

    professional_review_required: bool = True


@dataclass(frozen=True)
class NumericConstraint:
    constraint_id: str
    name: str

    field_name: str
    operator: str
    expected: float

    severity: ClashSeverity

    applicable_categories: tuple[ElementCategory, ...] = ()

    source_fact_id: str | None = None

    professional_review_required: bool = False


@dataclass(frozen=True)
class ConstraintFinding:
    constraint_id: str
    element_id: str

    disposition: ConstraintDisposition

    actual: float | None
    expected: float

    message: str

    source_fact_id: str | None

    professional_review_required: bool


@dataclass(frozen=True)
class DependencyEdge:
    source_id: str
    dependent_id: str
    relationship: str


@dataclass(frozen=True)
class EngineeringOverlay:
    overlay_id: str

    element_id: str
    metric: str

    value: float
    limit: float | None

    utilization: float | None

    disposition: EngineeringOverlayDisposition

    source_analysis_id: str
    source_fact_ids: tuple[str, ...]

    professional_review_required: bool


@dataclass(frozen=True)
class CorrectionAlternative:
    alternative_id: str

    clash_id: str
    element_id: str

    translation: Vec3

    score: float

    rationale: str

    resulting_clearance_ft: float

    requires_reanalysis: bool = True
    professional_review_required: bool = True


@dataclass(frozen=True)
class ModelRevision:
    revision_id: str

    model_id: str
    sequence: int

    snapshot_hash: str

    changed_element_ids: tuple[str, ...]

    created_at: datetime
    author_id: str

    previous_hash: str | None

    content_hash: str
    chain_hash: str


@dataclass(frozen=True)
class ModelHealth:
    element_count: int
    level_count: int

    clash_count: int
    hard_clash_count: int
    clearance_clash_count: int

    dependency_count: int
    revision_count: int

    integrity_ok: bool


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
