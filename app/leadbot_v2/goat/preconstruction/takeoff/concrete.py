from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import uuid4

from leadbot_v2.goat.preconstruction.geometry.measurement import (
    GeometryMeasurementEngine,
    ScaleCalibration,
)
from leadbot_v2.goat.preconstruction.geometry.models import (
    GeometryProvenance,
    VectorPolygon,
    VectorPolyline,
)


CUBIC_FEET_PER_CUBIC_YARD = 27.0


class ConcreteAssemblyKind(str, Enum):
    SLAB = "slab"
    FOOTING = "footing"
    GRADE_BEAM = "grade_beam"
    WALL = "wall"
    COLUMN = "column"
    PIER = "pier"
    CURB = "curb"
    OTHER = "other"


@dataclass(frozen=True)
class ConcreteTakeoffItem:
    takeoff_id: str
    kind: ConcreteAssemblyKind
    description: str

    net_concrete_cy: float
    waste_percent: float
    bid_concrete_cy: float

    formwork_sf: float

    formula: str
    provenance: GeometryProvenance
    confidence: float

    def __post_init__(self) -> None:
        if self.net_concrete_cy < 0:
            raise ValueError(
                "concrete volume cannot be negative"
            )

        if self.bid_concrete_cy < 0:
            raise ValueError(
                "bid volume cannot be negative"
            )

        if self.formwork_sf < 0:
            raise ValueError(
                "formwork cannot be negative"
            )

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "confidence must be 0-1"
            )


class ConcreteTakeoffEngine:

    @staticmethod
    def _factor(
        waste_percent: float,
    ) -> float:
        if waste_percent < 0:
            raise ValueError(
                "waste percent cannot be negative"
            )

        return (
            1.0
            + waste_percent
            / 100.0
        )

    @classmethod
    def slab_from_polygon(
        cls,
        *,
        polygon: VectorPolygon,
        calibration: ScaleCalibration,
        thickness_inches: float,
        provenance: GeometryProvenance,
        waste_percent: float = 5.0,
        description: str = "Concrete slab",
    ) -> ConcreteTakeoffItem:
        if thickness_inches <= 0:
            raise ValueError(
                "slab thickness must be positive"
            )

        measurement = (
            GeometryMeasurementEngine
            .polygon_area(
                polygon,
                calibration,
            )
        )

        thickness_ft = (
            thickness_inches
            / 12.0
        )

        cubic_feet = (
            measurement.area_sqft
            * thickness_ft
        )

        net_cy = (
            cubic_feet
            / CUBIC_FEET_PER_CUBIC_YARD
        )

        factor = cls._factor(
            waste_percent
        )

        bid_cy = (
            net_cy
            * factor
        )

        edge_form_sf = (
            measurement.perimeter_ft
            * thickness_ft
        )

        confidence = min(
            measurement.confidence,
            provenance.confidence,
        )

        return ConcreteTakeoffItem(
            takeoff_id=(
                f"takeoff_{uuid4().hex}"
            ),
            kind=ConcreteAssemblyKind.SLAB,
            description=description,
            net_concrete_cy=net_cy,
            waste_percent=waste_percent,
            bid_concrete_cy=bid_cy,
            formwork_sf=edge_form_sf,
            formula=(
                f"{measurement.area_sqft:.3f} SF "
                f"× {thickness_ft:.4f} FT "
                f"/ 27 = {net_cy:.3f} CY; "
                f"× {factor:.3f} waste "
                f"= {bid_cy:.3f} CY"
            ),
            provenance=provenance,
            confidence=confidence,
        )

    @classmethod
    def footing_from_polygon(
        cls,
        *,
        polygon: VectorPolygon,
        calibration: ScaleCalibration,
        depth_inches: float,
        provenance: GeometryProvenance,
        waste_percent: float = 5.0,
        description: str = "Concrete footing",
    ) -> ConcreteTakeoffItem:
        if depth_inches <= 0:
            raise ValueError(
                "footing depth must be positive"
            )

        measurement = (
            GeometryMeasurementEngine
            .polygon_area(
                polygon,
                calibration,
            )
        )

        depth_ft = (
            depth_inches
            / 12.0
        )

        cubic_feet = (
            measurement.area_sqft
            * depth_ft
        )

        net_cy = (
            cubic_feet
            / CUBIC_FEET_PER_CUBIC_YARD
        )

        factor = cls._factor(
            waste_percent
        )

        return ConcreteTakeoffItem(
            takeoff_id=(
                f"takeoff_{uuid4().hex}"
            ),
            kind=(
                ConcreteAssemblyKind.FOOTING
            ),
            description=description,
            net_concrete_cy=net_cy,
            waste_percent=waste_percent,
            bid_concrete_cy=(
                net_cy * factor
            ),
            formwork_sf=0.0,
            formula=(
                f"{measurement.area_sqft:.3f} SF "
                f"× {depth_ft:.4f} FT "
                f"/ 27 = {net_cy:.3f} CY"
            ),
            provenance=provenance,
            confidence=min(
                measurement.confidence,
                provenance.confidence,
            ),
        )

    @classmethod
    def grade_beam_from_polyline(
        cls,
        *,
        polyline: VectorPolyline,
        calibration: ScaleCalibration,
        width_inches: float,
        depth_inches: float,
        provenance: GeometryProvenance,
        waste_percent: float = 5.0,
        formed_sides: int = 0,
        description: str = "Concrete grade beam",
    ) -> ConcreteTakeoffItem:
        if width_inches <= 0:
            raise ValueError(
                "grade beam width must be positive"
            )

        if depth_inches <= 0:
            raise ValueError(
                "grade beam depth must be positive"
            )

        if formed_sides not in {
            0,
            1,
            2,
        }:
            raise ValueError(
                "formed_sides must be 0, 1 or 2"
            )

        measurement = (
            GeometryMeasurementEngine
            .polyline_length(
                polyline,
                calibration,
            )
        )

        width_ft = (
            width_inches
            / 12.0
        )

        depth_ft = (
            depth_inches
            / 12.0
        )

        cubic_feet = (
            measurement.length_ft
            * width_ft
            * depth_ft
        )

        net_cy = (
            cubic_feet
            / CUBIC_FEET_PER_CUBIC_YARD
        )

        factor = cls._factor(
            waste_percent
        )

        formwork = (
            measurement.length_ft
            * depth_ft
            * formed_sides
        )

        return ConcreteTakeoffItem(
            takeoff_id=(
                f"takeoff_{uuid4().hex}"
            ),
            kind=(
                ConcreteAssemblyKind
                .GRADE_BEAM
            ),
            description=description,
            net_concrete_cy=net_cy,
            waste_percent=waste_percent,
            bid_concrete_cy=(
                net_cy * factor
            ),
            formwork_sf=formwork,
            formula=(
                f"{measurement.length_ft:.3f} LF "
                f"× {width_ft:.4f} FT "
                f"× {depth_ft:.4f} FT "
                f"/ 27 = {net_cy:.3f} CY"
            ),
            provenance=provenance,
            confidence=min(
                measurement.confidence,
                provenance.confidence,
            ),
        )

    @classmethod
    def wall_from_polyline(
        cls,
        *,
        polyline: VectorPolyline,
        calibration: ScaleCalibration,
        height_ft: float,
        thickness_inches: float,
        provenance: GeometryProvenance,
        waste_percent: float = 5.0,
        description: str = "Concrete wall",
    ) -> ConcreteTakeoffItem:
        if height_ft <= 0:
            raise ValueError(
                "wall height must be positive"
            )

        if thickness_inches <= 0:
            raise ValueError(
                "wall thickness must be positive"
            )

        measurement = (
            GeometryMeasurementEngine
            .polyline_length(
                polyline,
                calibration,
            )
        )

        thickness_ft = (
            thickness_inches
            / 12.0
        )

        cubic_feet = (
            measurement.length_ft
            * height_ft
            * thickness_ft
        )

        net_cy = (
            cubic_feet
            / CUBIC_FEET_PER_CUBIC_YARD
        )

        factor = cls._factor(
            waste_percent
        )

        two_sided_formwork = (
            measurement.length_ft
            * height_ft
            * 2.0
        )

        return ConcreteTakeoffItem(
            takeoff_id=(
                f"takeoff_{uuid4().hex}"
            ),
            kind=ConcreteAssemblyKind.WALL,
            description=description,
            net_concrete_cy=net_cy,
            waste_percent=waste_percent,
            bid_concrete_cy=(
                net_cy * factor
            ),
            formwork_sf=(
                two_sided_formwork
            ),
            formula=(
                f"{measurement.length_ft:.3f} LF "
                f"× {height_ft:.3f} FT "
                f"× {thickness_ft:.4f} FT "
                f"/ 27 = {net_cy:.3f} CY"
            ),
            provenance=provenance,
            confidence=min(
                measurement.confidence,
                provenance.confidence,
            ),
        )


class ConcreteTakeoffPackage:

    def __init__(self) -> None:
        self._items: dict[
            str,
            ConcreteTakeoffItem,
        ] = {}

    def add(
        self,
        item: ConcreteTakeoffItem,
    ) -> None:
        if item.takeoff_id in self._items:
            raise ValueError(
                "duplicate takeoff item"
            )

        self._items[
            item.takeoff_id
        ] = item

    @property
    def items(
        self,
    ) -> tuple[
        ConcreteTakeoffItem,
        ...
    ]:
        return tuple(
            self._items.values()
        )

    @property
    def total_bid_concrete_cy(
        self,
    ) -> float:
        return sum(
            item.bid_concrete_cy
            for item in self._items.values()
        )

    @property
    def total_formwork_sf(
        self,
    ) -> float:
        return sum(
            item.formwork_sf
            for item in self._items.values()
        )

    def by_kind(
        self,
        kind: ConcreteAssemblyKind,
    ) -> tuple[
        ConcreteTakeoffItem,
        ...
    ]:
        return tuple(
            item
            for item in self._items.values()
            if item.kind == kind
        )
