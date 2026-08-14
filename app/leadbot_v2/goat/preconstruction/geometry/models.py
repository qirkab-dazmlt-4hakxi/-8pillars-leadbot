from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot


@dataclass(frozen=True)
class Point2D:
    x: float
    y: float

    def distance_to(
        self,
        other: "Point2D",
    ) -> float:
        return hypot(
            other.x - self.x,
            other.y - self.y,
        )


@dataclass(frozen=True)
class BoundingBox:
    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        if self.x1 < self.x0:
            raise ValueError(
                "x1 cannot be less than x0"
            )

        if self.y1 < self.y0:
            raise ValueError(
                "y1 cannot be less than y0"
            )

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass(frozen=True)
class VectorLine:
    geometry_id: str
    start: Point2D
    end: Point2D
    layer: str | None = None
    stroke_width: float | None = None

    @property
    def length_points(self) -> float:
        return self.start.distance_to(
            self.end
        )


@dataclass(frozen=True)
class VectorPolyline:
    geometry_id: str
    points: tuple[Point2D, ...]
    layer: str | None = None

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValueError(
                "polyline requires at least two points"
            )

    @property
    def length_points(self) -> float:
        return sum(
            self.points[index].distance_to(
                self.points[index + 1]
            )
            for index
            in range(len(self.points) - 1)
        )


@dataclass(frozen=True)
class VectorPolygon:
    geometry_id: str
    points: tuple[Point2D, ...]
    layer: str | None = None

    def __post_init__(self) -> None:
        if len(self.points) < 3:
            raise ValueError(
                "polygon requires at least three points"
            )

    @property
    def area_points_squared(self) -> float:
        total = 0.0

        for index, point in enumerate(
            self.points
        ):
            next_point = self.points[
                (index + 1)
                % len(self.points)
            ]

            total += (
                point.x * next_point.y
                - next_point.x * point.y
            )

        return abs(total) / 2.0

    @property
    def perimeter_points(self) -> float:
        return sum(
            self.points[index].distance_to(
                self.points[
                    (index + 1)
                    % len(self.points)
                ]
            )
            for index
            in range(len(self.points))
        )

    @property
    def bounds(self) -> BoundingBox:
        xs = [
            point.x
            for point in self.points
        ]

        ys = [
            point.y
            for point in self.points
        ]

        return BoundingBox(
            min(xs),
            min(ys),
            max(xs),
            max(ys),
        )


@dataclass(frozen=True)
class TextSpan:
    text_id: str
    text: str
    bounds: BoundingBox
    font_size: float | None = None
    font_name: str | None = None

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError(
                "text span cannot be empty"
            )


@dataclass(frozen=True)
class GeometryProvenance:
    document_id: str
    sheet_number: str
    page_number: int
    source_ref: str
    geometry_ids: tuple[str, ...] = ()
    text_refs: tuple[str, ...] = ()
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError(
                "page_number must be >= 1"
            )

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "provenance confidence must be 0-1"
            )

        if not self.source_ref.strip():
            raise ValueError(
                "source_ref required"
            )


@dataclass(frozen=True)
class VectorSheet:
    document_id: str
    sheet_number: str
    page_number: int
    width_points: float
    height_points: float
    source_ref: str
    lines: tuple[VectorLine, ...] = ()
    polylines: tuple[VectorPolyline, ...] = ()
    polygons: tuple[VectorPolygon, ...] = ()
    text_spans: tuple[TextSpan, ...] = ()

    def __post_init__(self) -> None:
        if self.width_points <= 0:
            raise ValueError(
                "sheet width must be positive"
            )

        if self.height_points <= 0:
            raise ValueError(
                "sheet height must be positive"
            )
