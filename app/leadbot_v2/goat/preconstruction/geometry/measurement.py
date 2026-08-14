from __future__ import annotations

from dataclasses import dataclass

from leadbot_v2.goat.preconstruction.documents.models import (
    ScaleState,
    SheetScale,
)
from leadbot_v2.goat.preconstruction.geometry.models import (
    BoundingBox,
    VectorLine,
    VectorPolygon,
    VectorPolyline,
)


PDF_POINTS_PER_INCH = 72.0


class ScaleCalibrationError(ValueError):
    pass


class AmbiguousScaleError(
    ScaleCalibrationError
):
    pass


class UnmeasurableGeometryError(
    ScaleCalibrationError
):
    pass


@dataclass(frozen=True)
class ScaleCalibration:
    """
    Real-world calibration for PDF coordinate geometry.

    PDF coordinates are measured in points.
    72 points == 1 paper inch.
    """

    paper_inches: float
    model_feet: float
    confidence: float
    source: str

    def __post_init__(self) -> None:
        if self.paper_inches <= 0:
            raise ScaleCalibrationError(
                "paper_inches must be positive"
            )

        if self.model_feet <= 0:
            raise ScaleCalibrationError(
                "model_feet must be positive"
            )

        if not 0.0 <= self.confidence <= 1.0:
            raise ScaleCalibrationError(
                "calibration confidence must be 0-1"
            )

    @property
    def feet_per_paper_inch(self) -> float:
        return (
            self.model_feet
            / self.paper_inches
        )

    @property
    def feet_per_pdf_point(self) -> float:
        return (
            self.feet_per_paper_inch
            / PDF_POINTS_PER_INCH
        )

    def points_to_feet(
        self,
        points: float,
    ) -> float:
        return (
            points
            * self.feet_per_pdf_point
        )

    def points_squared_to_sqft(
        self,
        points_squared: float,
    ) -> float:
        factor = self.feet_per_pdf_point

        return (
            points_squared
            * factor
            * factor
        )


class SheetCalibrationResolver:

    @staticmethod
    def from_declared_scale(
        scale: SheetScale,
    ) -> ScaleCalibration:
        if scale.state != ScaleState.DECLARED:
            raise UnmeasurableGeometryError(
                "scale is not a declared measurable scale"
            )

        if (
            scale.paper_units is None
            or scale.model_units is None
            or scale.model_unit_name is None
        ):
            raise UnmeasurableGeometryError(
                "declared scale lacks conversion data"
            )

        if scale.paper_units <= 0:
            raise UnmeasurableGeometryError(
                "paper scale must be positive"
            )

        if scale.model_units <= 0:
            raise UnmeasurableGeometryError(
                "model scale must be positive"
            )

        if scale.model_unit_name == "inch":
            model_feet = (
                scale.model_units
                / 12.0
            )

        elif scale.model_unit_name == "foot":
            model_feet = (
                scale.model_units
            )

        else:
            raise UnmeasurableGeometryError(
                f"unsupported model unit: "
                f"{scale.model_unit_name}"
            )

        return ScaleCalibration(
            paper_inches=scale.paper_units,
            model_feet=model_feet,
            confidence=scale.confidence,
            source=scale.raw,
        )

    @classmethod
    def resolve(
        cls,
        scales: tuple[SheetScale, ...],
    ) -> ScaleCalibration:
        if not scales:
            raise UnmeasurableGeometryError(
                "sheet has no scale information"
            )

        if any(
            scale.state
            == ScaleState.CONFLICT
            for scale in scales
        ):
            raise AmbiguousScaleError(
                "sheet has conflicting declared scales"
            )

        declared = tuple(
            scale
            for scale in scales
            if scale.state
            == ScaleState.DECLARED
        )

        if not declared:
            if any(
                scale.state
                == ScaleState.NTS
                for scale in scales
            ):
                raise UnmeasurableGeometryError(
                    "sheet is not to scale"
                )

            raise UnmeasurableGeometryError(
                "sheet has no measurable declared scale"
            )

        unique = {
            (
                scale.paper_units,
                scale.model_units,
                scale.model_unit_name,
            )
            for scale in declared
        }

        if len(unique) != 1:
            raise AmbiguousScaleError(
                "multiple incompatible scales require "
                "region-specific calibration"
            )

        return cls.from_declared_scale(
            declared[0]
        )


@dataclass(frozen=True)
class LinearMeasurement:
    length_ft: float
    confidence: float
    formula: str


@dataclass(frozen=True)
class AreaMeasurement:
    area_sqft: float
    perimeter_ft: float
    confidence: float
    formula: str


@dataclass(frozen=True)
class RectangleMeasurement:
    width_ft: float
    height_ft: float
    area_sqft: float
    confidence: float


class GeometryMeasurementEngine:

    @staticmethod
    def line_length(
        line: VectorLine,
        calibration: ScaleCalibration,
    ) -> LinearMeasurement:
        length_ft = (
            calibration.points_to_feet(
                line.length_points
            )
        )

        return LinearMeasurement(
            length_ft=length_ft,
            confidence=calibration.confidence,
            formula=(
                f"{line.length_points:.4f} PDF points "
                f"× {calibration.feet_per_pdf_point:.8f} "
                "ft/point"
            ),
        )

    @staticmethod
    def polyline_length(
        polyline: VectorPolyline,
        calibration: ScaleCalibration,
    ) -> LinearMeasurement:
        length_ft = (
            calibration.points_to_feet(
                polyline.length_points
            )
        )

        return LinearMeasurement(
            length_ft=length_ft,
            confidence=calibration.confidence,
            formula=(
                f"{polyline.length_points:.4f} PDF points "
                f"× {calibration.feet_per_pdf_point:.8f} "
                "ft/point"
            ),
        )

    @staticmethod
    def polygon_area(
        polygon: VectorPolygon,
        calibration: ScaleCalibration,
    ) -> AreaMeasurement:
        area_sqft = (
            calibration.points_squared_to_sqft(
                polygon.area_points_squared
            )
        )

        perimeter_ft = (
            calibration.points_to_feet(
                polygon.perimeter_points
            )
        )

        return AreaMeasurement(
            area_sqft=area_sqft,
            perimeter_ft=perimeter_ft,
            confidence=calibration.confidence,
            formula=(
                f"{polygon.area_points_squared:.4f} "
                "PDF points² × "
                f"{calibration.feet_per_pdf_point:.8f}² "
                "ft²/point²"
            ),
        )

    @staticmethod
    def bounding_rectangle(
        bounds: BoundingBox,
        calibration: ScaleCalibration,
    ) -> RectangleMeasurement:
        width_ft = (
            calibration.points_to_feet(
                bounds.width
            )
        )

        height_ft = (
            calibration.points_to_feet(
                bounds.height
            )
        )

        return RectangleMeasurement(
            width_ft=width_ft,
            height_ft=height_ft,
            area_sqft=(
                width_ft
                * height_ft
            ),
            confidence=calibration.confidence,
        )
