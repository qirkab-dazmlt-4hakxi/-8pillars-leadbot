from __future__ import annotations

import math
import re

from dataclasses import dataclass
from enum import Enum

from leadbot_v2.goat.preconstruction.geometry.measurement import (
    ScaleCalibration,
)
from leadbot_v2.goat.preconstruction.geometry.models import (
    BoundingBox,
    GeometryProvenance,
    Point2D,
    TextSpan,
    VectorPolygon,
    VectorPolyline,
)
from leadbot_v2.goat.preconstruction.takeoff.concrete import (
    ConcreteTakeoffEngine,
    ConcreteTakeoffItem,
)
from leadbot_v2.goat.preconstruction.takeoff.rebar import (
    RebarIntelligence,
    RebarSpec,
    RebarTakeoff,
)


class AssemblyKind(str, Enum):
    SLAB = "slab"
    FOOTING = "footing"
    GRADE_BEAM = "grade_beam"
    WALL = "wall"
    UNKNOWN = "unknown"


class AssemblyInferenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class StructuralCallout:
    kind: AssemblyKind
    label: str
    thickness_inches: float | None
    width_inches: float | None
    depth_inches: float | None
    height_ft: float | None
    rebar: RebarSpec | None
    raw_text: str
    confidence: float
    text_id: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "callout confidence must be 0-1"
            )


@dataclass(frozen=True)
class GeometryAssociation:
    text_id: str
    geometry_id: str
    distance_points: float
    confidence: float

    def __post_init__(self) -> None:
        if self.distance_points < 0:
            raise ValueError(
                "distance cannot be negative"
            )

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "association confidence must be 0-1"
            )


@dataclass(frozen=True)
class StructuralAssemblyCandidate:
    kind: AssemblyKind
    label: str
    callout: StructuralCallout
    geometry_id: str
    association: GeometryAssociation
    provenance: GeometryProvenance
    confidence: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "assembly confidence must be 0-1"
            )


@dataclass(frozen=True)
class AutomatedConcreteAssembly:
    candidate: StructuralAssemblyCandidate
    concrete: ConcreteTakeoffItem
    rebar: RebarTakeoff | None
    requires_review: bool


SLAB_PATTERNS = (
    re.compile(
        r'\b(?P<thickness>\d+(?:\.\d+)?)\s*["”]\s*'
        r'(?:SOG|SLAB(?:\s+ON\s+GRADE)?)\b',
        re.I,
    ),
    re.compile(
        r'\b(?:SOG|SLAB(?:\s+ON\s+GRADE)?)\s*'
        r'(?P<thickness>\d+(?:\.\d+)?)\s*["”]\b',
        re.I,
    ),
)


GRADE_BEAM = re.compile(
    r"\b(?P<label>GB[-\s]?\d+[A-Z]?)"
    r"(?:\s*[-:]?\s*)"
    r"(?P<width>\d+(?:\.\d+)?)\s*"
    r"[\"”]?\s*[Xx×]\s*"
    r"(?P<depth>\d+(?:\.\d+)?)\s*"
    r"[\"”]?",
    re.I,
)


GRADE_BEAM_GENERIC = re.compile(
    r"\bGRADE\s+BEAM\b.*?"
    r"(?P<width>\d+(?:\.\d+)?)\s*"
    r"[\"”]?\s*[Xx×]\s*"
    r"(?P<depth>\d+(?:\.\d+)?)\s*"
    r"[\"”]?",
    re.I,
)


FOOTING = re.compile(
    r"\b(?P<label>F[-\s]?\d+[A-Z]?)"
    r"(?:\s*[-:]?\s*)"
    r"(?P<width>\d+(?:\.\d+)?)\s*"
    r"[\"”]?\s*[Xx×]\s*"
    r"(?P<depth>\d+(?:\.\d+)?)\s*"
    r"[\"”]?",
    re.I,
)


WALL = re.compile(
    r'\b(?P<thickness>\d+(?:\.\d+)?)\s*["”]\s*'
    r"(?:CONC(?:RETE)?\s+)?WALL\b",
    re.I,
)


HEIGHT = re.compile(
    r"\b(?:H|HT|HEIGHT)\s*=?\s*"
    r"(?P<feet>\d+(?:\.\d+)?)\s*'",
    re.I,
)


def _center(
    bounds: BoundingBox,
) -> Point2D:
    return Point2D(
        (
            bounds.x0
            + bounds.x1
        )
        / 2.0,
        (
            bounds.y0
            + bounds.y1
        )
        / 2.0,
    )


def _polygon_center(
    polygon: VectorPolygon,
) -> Point2D:
    xs = tuple(
        point.x
        for point in polygon.points
    )

    ys = tuple(
        point.y
        for point in polygon.points
    )

    return Point2D(
        sum(xs) / len(xs),
        sum(ys) / len(ys),
    )


def _polyline_center(
    polyline: VectorPolyline,
) -> Point2D:
    xs = tuple(
        point.x
        for point in polyline.points
    )

    ys = tuple(
        point.y
        for point in polyline.points
    )

    return Point2D(
        sum(xs) / len(xs),
        sum(ys) / len(ys),
    )


class StructuralCalloutParser:

    @staticmethod
    def parse(
        text: str,
        *,
        text_id: str | None = None,
    ) -> StructuralCallout | None:
        normalized = (
            " ".join(
                text.strip().split()
            )
        )

        if not normalized:
            return None

        rebar = RebarIntelligence.parse(
            normalized
        )

        for pattern in SLAB_PATTERNS:
            match = pattern.search(
                normalized
            )

            if match:
                return StructuralCallout(
                    kind=AssemblyKind.SLAB,
                    label="SOG",
                    thickness_inches=float(
                        match.group(
                            "thickness"
                        )
                    ),
                    width_inches=None,
                    depth_inches=None,
                    height_ft=None,
                    rebar=rebar,
                    raw_text=normalized,
                    confidence=0.98,
                    text_id=text_id,
                )

        match = GRADE_BEAM.search(
            normalized
        )

        if match:
            return StructuralCallout(
                kind=AssemblyKind.GRADE_BEAM,
                label=(
                    match.group(
                        "label"
                    )
                    .upper()
                    .replace(" ", "-")
                ),
                thickness_inches=None,
                width_inches=float(
                    match.group("width")
                ),
                depth_inches=float(
                    match.group("depth")
                ),
                height_ft=None,
                rebar=rebar,
                raw_text=normalized,
                confidence=0.98,
                text_id=text_id,
            )

        match = GRADE_BEAM_GENERIC.search(
            normalized
        )

        if match:
            return StructuralCallout(
                kind=AssemblyKind.GRADE_BEAM,
                label="GRADE-BEAM",
                thickness_inches=None,
                width_inches=float(
                    match.group("width")
                ),
                depth_inches=float(
                    match.group("depth")
                ),
                height_ft=None,
                rebar=rebar,
                raw_text=normalized,
                confidence=0.94,
                text_id=text_id,
            )

        match = FOOTING.search(
            normalized
        )

        if match:
            return StructuralCallout(
                kind=AssemblyKind.FOOTING,
                label=(
                    match.group(
                        "label"
                    )
                    .upper()
                    .replace(" ", "-")
                ),
                thickness_inches=None,
                width_inches=float(
                    match.group("width")
                ),
                depth_inches=float(
                    match.group("depth")
                ),
                height_ft=None,
                rebar=rebar,
                raw_text=normalized,
                confidence=0.96,
                text_id=text_id,
            )

        match = WALL.search(
            normalized
        )

        if match:
            height_match = HEIGHT.search(
                normalized
            )

            return StructuralCallout(
                kind=AssemblyKind.WALL,
                label="CONCRETE-WALL",
                thickness_inches=float(
                    match.group(
                        "thickness"
                    )
                ),
                width_inches=None,
                depth_inches=None,
                height_ft=(
                    float(
                        height_match.group(
                            "feet"
                        )
                    )
                    if height_match
                    else None
                ),
                rebar=rebar,
                raw_text=normalized,
                confidence=(
                    0.96
                    if height_match
                    else 0.88
                ),
                text_id=text_id,
            )

        return None


class GeometryAssociationEngine:

    @staticmethod
    def associate_polygon(
        *,
        span: TextSpan,
        polygons: tuple[
            VectorPolygon,
            ...
        ],
        max_distance_points: float = 250.0,
    ) -> GeometryAssociation | None:
        if not polygons:
            return None

        text_center = _center(
            span.bounds
        )

        ranked = []

        for polygon in polygons:
            center = _polygon_center(
                polygon
            )

            distance = (
                text_center.distance_to(
                    center
                )
            )

            ranked.append(
                (
                    distance,
                    polygon.geometry_id,
                )
            )

        ranked.sort()

        distance, geometry_id = ranked[0]

        if distance > max_distance_points:
            return None

        confidence = max(
            0.25,
            1.0
            - (
                distance
                / max_distance_points
            ),
        )

        return GeometryAssociation(
            text_id=span.text_id,
            geometry_id=geometry_id,
            distance_points=distance,
            confidence=confidence,
        )

    @staticmethod
    def associate_polyline(
        *,
        span: TextSpan,
        polylines: tuple[
            VectorPolyline,
            ...
        ],
        max_distance_points: float = 250.0,
    ) -> GeometryAssociation | None:
        if not polylines:
            return None

        text_center = _center(
            span.bounds
        )

        ranked = []

        for polyline in polylines:
            center = _polyline_center(
                polyline
            )

            distance = (
                text_center.distance_to(
                    center
                )
            )

            ranked.append(
                (
                    distance,
                    polyline.geometry_id,
                )
            )

        ranked.sort()

        distance, geometry_id = ranked[0]

        if distance > max_distance_points:
            return None

        confidence = max(
            0.25,
            1.0
            - (
                distance
                / max_distance_points
            ),
        )

        return GeometryAssociation(
            text_id=span.text_id,
            geometry_id=geometry_id,
            distance_points=distance,
            confidence=confidence,
        )


class StructuralAssemblyInferenceEngine:

    def infer(
        self,
        *,
        document_id: str,
        sheet_number: str,
        page_number: int,
        source_ref: str,
        text_spans: tuple[
            TextSpan,
            ...
        ],
        polygons: tuple[
            VectorPolygon,
            ...
        ],
        polylines: tuple[
            VectorPolyline,
            ...
        ],
    ) -> tuple[
        StructuralAssemblyCandidate,
        ...
    ]:
        results = []

        polygon_map = {
            polygon.geometry_id:
                polygon
            for polygon in polygons
        }

        polyline_map = {
            polyline.geometry_id:
                polyline
            for polyline in polylines
        }

        for span in text_spans:
            callout = (
                StructuralCalloutParser
                .parse(
                    span.text,
                    text_id=span.text_id,
                )
            )

            if callout is None:
                continue

            if callout.kind in {
                AssemblyKind.SLAB,
                AssemblyKind.FOOTING,
            }:
                association = (
                    GeometryAssociationEngine
                    .associate_polygon(
                        span=span,
                        polygons=polygons,
                    )
                )

            elif callout.kind in {
                AssemblyKind.GRADE_BEAM,
                AssemblyKind.WALL,
            }:
                association = (
                    GeometryAssociationEngine
                    .associate_polyline(
                        span=span,
                        polylines=polylines,
                    )
                )

            else:
                association = None

            if association is None:
                continue

            if (
                association.geometry_id
                not in polygon_map
                and association.geometry_id
                not in polyline_map
            ):
                raise AssemblyInferenceError(
                    "associated geometry disappeared"
                )

            confidence = min(
                callout.confidence,
                association.confidence,
            )

            provenance = GeometryProvenance(
                document_id=document_id,
                sheet_number=sheet_number,
                page_number=page_number,
                source_ref=source_ref,
                geometry_ids=(
                    association.geometry_id,
                ),
                text_refs=(
                    span.text_id,
                ),
                confidence=confidence,
            )

            results.append(
                StructuralAssemblyCandidate(
                    kind=callout.kind,
                    label=callout.label,
                    callout=callout,
                    geometry_id=(
                        association.geometry_id
                    ),
                    association=association,
                    provenance=provenance,
                    confidence=confidence,
                )
            )

        return tuple(results)


class AutomaticStructuralTakeoffEngine:

    REVIEW_THRESHOLD = 0.80

    def build(
        self,
        *,
        candidate: StructuralAssemblyCandidate,
        calibration: ScaleCalibration,
        polygon: VectorPolygon | None = None,
        polyline: VectorPolyline | None = None,
        waste_percent: float = 5.0,
        rebar_waste_percent: float = 10.0,
    ) -> AutomatedConcreteAssembly:
        callout = candidate.callout

        concrete: ConcreteTakeoffItem

        if callout.kind == AssemblyKind.SLAB:
            if polygon is None:
                raise AssemblyInferenceError(
                    "slab requires polygon geometry"
                )

            if callout.thickness_inches is None:
                raise AssemblyInferenceError(
                    "slab thickness missing"
                )

            concrete = (
                ConcreteTakeoffEngine
                .slab_from_polygon(
                    polygon=polygon,
                    calibration=calibration,
                    thickness_inches=(
                        callout
                        .thickness_inches
                    ),
                    provenance=(
                        candidate.provenance
                    ),
                    waste_percent=(
                        waste_percent
                    ),
                    description=(
                        candidate.label
                    ),
                )
            )

        elif (
            callout.kind
            == AssemblyKind.FOOTING
        ):
            if polygon is None:
                raise AssemblyInferenceError(
                    "footing requires polygon geometry"
                )

            if callout.depth_inches is None:
                raise AssemblyInferenceError(
                    "footing depth missing"
                )

            concrete = (
                ConcreteTakeoffEngine
                .footing_from_polygon(
                    polygon=polygon,
                    calibration=calibration,
                    depth_inches=(
                        callout.depth_inches
                    ),
                    provenance=(
                        candidate.provenance
                    ),
                    waste_percent=(
                        waste_percent
                    ),
                    description=(
                        candidate.label
                    ),
                )
            )

        elif (
            callout.kind
            == AssemblyKind.GRADE_BEAM
        ):
            if polyline is None:
                raise AssemblyInferenceError(
                    "grade beam requires polyline geometry"
                )

            if (
                callout.width_inches is None
                or callout.depth_inches
                is None
            ):
                raise AssemblyInferenceError(
                    "grade beam size missing"
                )

            concrete = (
                ConcreteTakeoffEngine
                .grade_beam_from_polyline(
                    polyline=polyline,
                    calibration=calibration,
                    width_inches=(
                        callout.width_inches
                    ),
                    depth_inches=(
                        callout.depth_inches
                    ),
                    provenance=(
                        candidate.provenance
                    ),
                    waste_percent=(
                        waste_percent
                    ),
                    description=(
                        candidate.label
                    ),
                )
            )

        elif (
            callout.kind
            == AssemblyKind.WALL
        ):
            if polyline is None:
                raise AssemblyInferenceError(
                    "wall requires polyline geometry"
                )

            if (
                callout.thickness_inches
                is None
            ):
                raise AssemblyInferenceError(
                    "wall thickness missing"
                )

            if callout.height_ft is None:
                raise AssemblyInferenceError(
                    "wall height unresolved; "
                    "human/detail review required"
                )

            concrete = (
                ConcreteTakeoffEngine
                .wall_from_polyline(
                    polyline=polyline,
                    calibration=calibration,
                    height_ft=(
                        callout.height_ft
                    ),
                    thickness_inches=(
                        callout
                        .thickness_inches
                    ),
                    provenance=(
                        candidate.provenance
                    ),
                    waste_percent=(
                        waste_percent
                    ),
                    description=(
                        candidate.label
                    ),
                )
            )

        else:
            raise AssemblyInferenceError(
                "unsupported assembly kind"
            )

        rebar_takeoff = None

        if (
            callout.rebar is not None
            and callout.kind
            == AssemblyKind.SLAB
            and polygon is not None
        ):
            area = (
                concrete.net_concrete_cy
                * 27.0
                / (
                    callout
                    .thickness_inches
                    / 12.0
                )
            )

            rebar_takeoff = (
                RebarIntelligence
                .slab_grid_takeoff(
                    spec=callout.rebar,
                    area_sqft=area,
                    provenance=(
                        candidate.provenance
                    ),
                    lap_waste_percent=(
                        rebar_waste_percent
                    ),
                )
            )

        return AutomatedConcreteAssembly(
            candidate=candidate,
            concrete=concrete,
            rebar=rebar_takeoff,
            requires_review=(
                candidate.confidence
                < self.REVIEW_THRESHOLD
            ),
        )
