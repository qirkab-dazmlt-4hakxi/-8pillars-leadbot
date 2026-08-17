from .canonical import (
    canonical_json,
    stable_hash,
    to_primitive,
)

from .clash import (
    ClashDetector,
    ClashPolicy,
)

from .constraints import (
    ModelConstraintEngine,
)

from .correction import (
    ClashCorrectionEngine,
)

from .dependency import (
    ModelDependencyGraph,
)

from .elements import (
    BIMElementFactory,
)

from .geometry import (
    EPS,
    aabb_distance,
    add,
    bounds_from_points,
    box_from_center,
    center,
    cross,
    distance,
    dot,
    expand,
    hard_intersects,
    magnitude,
    normalize,
    overlap_depths,
    overlap_volume,
    scale,
    segment_bounds,
    size,
    subtract,
    translate,
    union,
    validate_aabb,
    volume,
)

from .models import (
    AABB,
    BIMDiscipline,
    BIMKernelError,
    Clash,
    ClashSeverity,
    ClashType,
    ConstraintDisposition,
    ConstraintError,
    ConstraintFinding,
    CorrectionAlternative,
    DependencyEdge,
    DependencyError,
    ElementCategory,
    EngineeringOverlay,
    EngineeringOverlayDisposition,
    GeometryError,
    GridLine,
    Level,
    ModelElement,
    ModelHealth,
    ModelIntegrityError,
    ModelRevision,
    NumericConstraint,
    SpatialIndexError,
    Vec3,
    utcnow,
)

from .overlays import (
    EngineeringOverlayEngine,
)

from .persistence import (
    BIM_CLASH_ENTITY,
    BIM_CONSTRAINT_ENTITY,
    BIM_CORRECTION_ENTITY,
    BIM_ELEMENT_ENTITY,
    BIM_OVERLAY_ENTITY,
    BIM_REVISION_ENTITY,
    BIMRepository,
)

from .revisions import (
    ModelRevisionLedger,
)

from .service import (
    BIMKernelService,
)

from .spatial import (
    SpatialHash3D,
)
